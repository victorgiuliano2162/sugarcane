#include <cstdio>
#include <cstring>
#include "tflite_classifier.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"

// ============================================================================
// [IMPLEMENTAÇÃO: HEADERS ESP-NN PARA SCRATCH EM SRAM E DUAL-CORE (v08)]
// ============================================================================
#include <esp_nn.h>
#include <esp_nn_multicore.h>

static const char* TAG = "TFLITE_CLASSIFIER";

const int NUM_CLASSES = 11;
const char* LABELS[11] = {
    "Banded Chlorosis", "Brown Spot", "BrownRust", "Dried Leaves",
    "Grassy shoot", "Healthy Leaves", "Pokkah Boeng", "Sett Rot",
    "Viral Disease", "Yellow Leaf", "smut"
};

static uint8_t* model_buffer = nullptr;
static const tflite::Model* model = nullptr;
static tflite::MicroInterpreter* interpreter = nullptr;
static TfLiteTensor* input_tensor = nullptr;
static TfLiteTensor* output_tensor = nullptr;

const int kTensorArenaSize = 800 * 1024;
static uint8_t* tensor_arena = nullptr;
static char result_json[1024];

// ============================================================================
// [IMPLEMENTAÇÃO: BUFFERS DEDICADOS EM SRAM INTERNA PARA O ESP-NN (v08)]
// Em vez de deixar o esp-nn usar a tensor_arena na PSRAM externa (40 MHz) para
// operações críticas de im2col, padding e transposição SIMD 1x1/3x3, alocamos:
//   1) s_sram_scratch_buf (48 KB, alinhado em 16 bytes na SRAM Interna DMA):
//      Cobre 100% dos workspaces de Conv2D (máx ~24,5 KB) e DepthwiseConv2D
//      (máx ~43 KB) do MobileNetV3 v08 via preferred_scratch_buffer.
//   2) Scratch do worker Dual-Core (25 KB na SRAM Interna):
//      Pré-alocado no boot via esp_nn_dual_core_scratch() para evitar
//      realocações dinâmicas ou fragmentação durante a inferência.
// ============================================================================
static const size_t kPreferredSramScratchSize = 48 * 1024; // 49.152 bytes
static const size_t kFallbackSramScratchSize  = 40 * 1024; // 40.960 bytes
static const int    kDualCoreWorkerScratchSize = 25 * 1024; // 25.600 bytes (máx real v08: 24.576 B)

static uint8_t* s_sram_scratch_buf = nullptr;
static size_t   s_sram_scratch_size = 0;

void classifier_enable_dual_core() {
#if defined(ARCH_ESP32_S3) && ESP_NN_DUAL_CORE_SUPPORTED
    if (!esp_nn_dual_core_active()) {
        esp_nn_dual_core_enable();
        ESP_LOGI(TAG, "[DUAL-CORE ESP-NN] Fork-Join ativado a partir do Core %d (worker no Core %d, ativo=%d)",
                 (int)xPortGetCoreID(), (xPortGetCoreID() == 0) ? 1 : 0, (int)esp_nn_dual_core_active());
    }
#endif
}

bool classifier_init() {
    // ------------------------------------------------------------------------
    // [IMPLEMENTAÇÃO 1: ALOCAÇÃO DO PREFERRED SCRATCH BUFFER NA SRAM INTERNA]
    // Alocamos antes de inicializar sub-sistemas pesados para garantir bloco
    // contíguo na SRAM interna rápida (zero wait-states, 16-byte aligned).
    // ------------------------------------------------------------------------
#if defined(ARCH_ESP32_S3)
    const uint32_t sram_caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT | MALLOC_CAP_DMA;
    s_sram_scratch_buf = (uint8_t*)heap_caps_aligned_alloc(16, kPreferredSramScratchSize, sram_caps);
    if (s_sram_scratch_buf) {
        s_sram_scratch_size = kPreferredSramScratchSize;
    } else {
        s_sram_scratch_buf = (uint8_t*)heap_caps_aligned_alloc(16, kFallbackSramScratchSize, sram_caps);
        if (s_sram_scratch_buf) {
            s_sram_scratch_size = kFallbackSramScratchSize;
        }
    }

    if (s_sram_scratch_buf) {
        esp_nn_set_conv_preferred_scratch_buf_esp32s3(s_sram_scratch_buf, s_sram_scratch_size);
        esp_nn_set_depthwise_conv_preferred_scratch_buf_esp32s3(s_sram_scratch_buf, s_sram_scratch_size);
        ESP_LOGI(TAG, "[SRAM SCRATCH] Buffer preferencial esp-nn alocado na SRAM Interna: %u bytes @ %p",
                 (unsigned)s_sram_scratch_size, (void*)s_sram_scratch_buf);
    } else {
        ESP_LOGW(TAG, "[SRAM SCRATCH] Sem bloco contiguo na SRAM; usando fallback na tensor_arena (PSRAM)");
    }

    // ------------------------------------------------------------------------
    // [IMPLEMENTAÇÃO 2: PRÉ-ALOCAÇÃO DO SCRATCH DO WORKER DUAL-CORE NA SRAM]
    // Garante que a fatia do segundo núcleo (esp_nn_worker) também resida em
    // SRAM interna desde a primeira inferência, sem realocações em runtime.
    // ------------------------------------------------------------------------
#if ESP_NN_DUAL_CORE_SUPPORTED
    void* worker_sram = esp_nn_dual_core_scratch(kDualCoreWorkerScratchSize);
    if (worker_sram) {
        ESP_LOGI(TAG, "[SRAM DUAL-CORE] Scratch do worker pre-alocado na SRAM Interna: %d bytes @ %p",
                 kDualCoreWorkerScratchSize, worker_sram);
    }
#endif
    ESP_LOGI(TAG, "[MEMORIA] SRAM Interna livre apos buffers esp-nn: %u bytes",
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
#endif

    FILE* f = fopen("/storage/model_mbnet_int8.tflite", "rb");
    if (!f) return false;
    
    fseek(f, 0, SEEK_END);
    size_t model_size = ftell(f);
    fseek(f, 0, SEEK_SET);

    model_buffer = (uint8_t*)heap_caps_malloc(model_size, MALLOC_CAP_SPIRAM);
    if (!model_buffer) { fclose(f); return false; }
    
    fread(model_buffer, 1, model_size, f);
    fclose(f);

    model = tflite::GetModel(model_buffer);
    tensor_arena = (uint8_t*)heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_SPIRAM);
    if (!tensor_arena) return false;

    static tflite::MicroMutableOpResolver<6> resolver;
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddAdd();
    resolver.AddMean();
    resolver.AddFullyConnected();
    resolver.AddSoftmax();

    static tflite::MicroInterpreter static_interpreter(model, resolver, tensor_arena, kTensorArenaSize);
    interpreter = &static_interpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) return false;

    input_tensor = interpreter->input(0);
    output_tensor = interpreter->output(0);
    return true;
}

int8_t* classifier_get_input_ptr() {
    return input_tensor->data.int8;
}

bool classifier_run(uint32_t decode_time_ms) {
    // [IMPLEMENTAÇÃO: GARANTIA DE ATIVAÇÃO DUAL-CORE NO NÚCLEO DE INFERÊNCIA]
    if (!esp_nn_dual_core_active()) {
        classifier_enable_dual_core();
    }

    unsigned long start_time = esp_timer_get_time() / 1000;
    
    if (interpreter->Invoke() != kTfLiteOk) {
        snprintf(result_json, sizeof(result_json), "{\"status\":\"erro\",\"mensagem\":\"Falha no classificador\"}");
        return false;
    }
    
    unsigned long end_time = esp_timer_get_time() / 1000;
    
    int written = snprintf(result_json, sizeof(result_json),
        "{\"status\":\"sucesso\",\"decode_ms\":%lu,\"inferencia_ms\":%lu,\"resultados\":[",
        decode_time_ms, end_time - start_time);

    float out_scale = output_tensor->params.scale;
    int out_zero_point = output_tensor->params.zero_point;
    
    for (int ix = 0; ix < NUM_CLASSES; ix++) {
        int8_t raw_val = output_tensor->data.int8[ix];
        float score = (float)(raw_val - out_zero_point) * out_scale;
        if (score < 0.0f) score = 0.0f;
        if (score > 1.0f) score = 1.0f;

        written += snprintf(result_json + written, sizeof(result_json) - written,
            "{\"label\":\"%s\",\"score\":%.4f}%s",
            LABELS[ix], score, (ix < NUM_CLASSES - 1) ? "," : "");
    }
    snprintf(result_json + written, sizeof(result_json) - written, "]}");
    return true;
}

const char* classifier_get_json_results() {
    return result_json;
}