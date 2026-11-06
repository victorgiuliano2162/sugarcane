#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_timer.h"
#include "esp_littlefs.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "image_processor.h"
#include "wifi_setup.h"
#include "tflite_classifier.h"
#include "web_server.h"

static const char* TAG = "MAIN";

// Tamanho do tensor de entrada (160 x 160 x 3 bytes = 76.800 bytes)
static const size_t TENSOR_SIZE = 160 * 160 * 3;

struct DecodedJob {
    int8_t* tensor_buf;
    uint32_t decode_time_ms;
    bool decode_ok;
    int ws_fd;
};

QueueHandle_t inference_queue;          // Fila de requisições brutas recebidas via WebSocket
static QueueHandle_t decoded_queue;     // Fila de frames decodificados para inferência
static QueueHandle_t free_tensor_queue; // Pool de Double Buffer na PSRAM

static void init_littlefs() {
    esp_vfs_littlefs_conf_t conf = {
        .base_path = "/storage",
        .partition_label = "storage",
        .format_if_mount_failed = false,
        .dont_mount = false
    };
    esp_err_t err = esp_vfs_littlefs_register(&conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Falha ao montar LittleFS: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "LittleFS montado com sucesso em /storage");
    }
}

// ==============================================================
// Task 1: Decodificação JPEG (Core 0 - junto com Wi-Fi/LwIP)
// ==============================================================
void decode_task(void* pvParameters) {
    InferenceRequest req;
    while (true) {
        if (xQueueReceive(inference_queue, &req, portMAX_DELAY)) {
            int8_t* tensor_buf = nullptr;
            // Obtém um buffer livre do pool na Octal PSRAM
            xQueueReceive(free_tensor_queue, &tensor_buf, portMAX_DELAY);

            unsigned long start_decode = esp_timer_get_time() / 1000;
            bool decode_ok = process_jpeg(req.image_buffer, req.image_size, tensor_buf);
            unsigned long decode_time = (esp_timer_get_time() / 1000) - start_decode;

            // Libera o JPEG bruto da memória imediatamente
            free(req.image_buffer);

            DecodedJob job = {
                .tensor_buf = tensor_buf,
                .decode_time_ms = (uint32_t)decode_time,
                .decode_ok = decode_ok,
                .ws_fd = req.ws_fd
            };

            // Envia para o Core 1 processar a inferência
            xQueueSend(decoded_queue, &job, portMAX_DELAY);
        }
    }
}

// ==============================================================
// Task 2: Inferência TensorFlow Lite Micro (Core 1 Exclusivo)
// ==============================================================
void inference_task(void* pvParameters) {
    DecodedJob job;
    while (true) {
        if (xQueueReceive(decoded_queue, &job, portMAX_DELAY)) {
            if (job.decode_ok) {
                // Copia dados para a entrada do modelo
                memcpy(classifier_get_input_ptr(), job.tensor_buf, TENSOR_SIZE);

                // Libera o buffer de volta ao pool IMEDIATAMENTE!
                // O Core 0 já pode decodificar a próxima foto enquanto o Core 1 executa Invoke()
                xQueueSend(free_tensor_queue, &job.tensor_buf, portMAX_DELAY);

                // Inferência dedicada com instruções SIMD no Core 1
                classifier_run(job.decode_time_ms);
                web_server_send_ws_text(job.ws_fd, classifier_get_json_results());
            } else {
                xQueueSend(free_tensor_queue, &job.tensor_buf, portMAX_DELAY);
                web_server_send_ws_text(job.ws_fd, "{\"status\":\"erro\",\"mensagem\":\"Falha ao ler JPEG\"}");
            }
        }
    }
}

extern "C" void app_main() {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    init_littlefs();
    
    wifi_init_sta();

    if (classifier_init()) {
        inference_queue = xQueueCreate(5, sizeof(InferenceRequest));
        decoded_queue = xQueueCreate(2, sizeof(DecodedJob));
        free_tensor_queue = xQueueCreate(2, sizeof(int8_t*));

        // Prealoca Double Buffer de tensores (2x 150 KB) na PSRAM
        for (int i = 0; i < 2; i++) {
            int8_t* buf = (int8_t*)heap_caps_malloc(TENSOR_SIZE, MALLOC_CAP_SPIRAM);
            if (!buf) {
                ESP_LOGE(TAG, "Falha ao alocar buffer de tensor na PSRAM!");
            }
            xQueueSend(free_tensor_queue, &buf, portMAX_DELAY);
        }

        // Core 0: Descompressão JPEG
        xTaskCreatePinnedToCore(decode_task, "decode_task", 8192, NULL, 5, NULL, 0);

        // Core 1: Rede Neural TFLite Micro
        xTaskCreatePinnedToCore(inference_task, "inference_task", 8192, NULL, 5, NULL, 1);

        web_server_start();
        ESP_LOGI(TAG, "Pipeline assincrono Dual-Core iniciado com sucesso!");
    }
}
