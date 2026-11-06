#include <cstdio>
#include <cstring>
#include "tflite_classifier.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"

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

bool classifier_init() {
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