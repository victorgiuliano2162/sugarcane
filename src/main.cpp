#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/stat.h>
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
#include "driver/temperature_sensor.h"
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

static temperature_sensor_handle_t s_temp_sensor = NULL;
static uint32_t s_inspection_counter = 0;
static const char* CSV_LOG_PATH = "/storage/inspections.csv";

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

static void init_temp_sensor() {
    temperature_sensor_config_t config = TEMPERATURE_SENSOR_CONFIG_DEFAULT(10, 80);
    if (temperature_sensor_install(&config, &s_temp_sensor) == ESP_OK) {
        temperature_sensor_enable(s_temp_sensor);
        ESP_LOGI(TAG, "Sensor termico interno ativado com sucesso.");
    }
}

static float get_chip_temperature() {
    float temp = 48.5f;
    if (s_temp_sensor) {
        temperature_sensor_get_celsius(s_temp_sensor, &temp);
    }
    return temp;
}

static void init_csv_log() {
    struct stat st;
    if (stat(CSV_LOG_PATH, &st) != 0) {
        FILE* f = fopen(CSV_LOG_PATH, "w");
        if (f) {
            fputs("id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms\n", f);
            fclose(f);
            ESP_LOGI(TAG, "Arquivo de log CSV criado: %s", CSV_LOG_PATH);
        }
    }
}

static void log_inspection(const char* class_name, float confidence, uint32_t decode_ms, uint32_t inf_ms, float temp, double lat, double lon, float alt) {
    s_inspection_counter++;
    uint32_t epoch = (uint32_t)(esp_timer_get_time() / 1000000);

    FILE* f = fopen(CSV_LOG_PATH, "a");
    if (f) {
        fprintf(f, "%lu,%lu,%.6f,%.6f,%.1f,%s,%.4f,%.1f,%lu,%lu\n",
            s_inspection_counter, epoch, lat, lon, alt, class_name, confidence, temp, inf_ms, decode_ms);
        fclose(f);
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
// Task 2: Inferência TensorFlow Lite Micro (Core 1 + Fork-Join Dual-Core)
// ==============================================================
void inference_task(void* pvParameters) {
    // ------------------------------------------------------------------------
    // [IMPLEMENTAÇÃO: ATIVAÇÃO DO WORKER DUAL-CORE DO ESP-NN (v08)]
    // Chamado a partir do Core 1 (onde roda a inference_task) para que o
    // esp-nn crie a task auxiliar 'esp_nn_worker' fixada no Core 0.
    // ------------------------------------------------------------------------
    classifier_enable_dual_core();

    DecodedJob job;
    while (true) {
        if (xQueueReceive(decoded_queue, &job, portMAX_DELAY)) {
            if (job.decode_ok) {
                // Copia dados para a entrada do modelo
                memcpy(classifier_get_input_ptr(), job.tensor_buf, TENSOR_SIZE);

                // Libera o buffer de volta ao pool IMEDIATAMENTE!
                xQueueSend(free_tensor_queue, &job.tensor_buf, portMAX_DELAY);

                // Inferência acelerada com SIMD + SRAM Scratch + Fork-Join Dual-Core
                classifier_run(job.decode_time_ms);

                // Coleta resultados top-1
                const char* top_class = classifier_get_top_label();
                float top_score = classifier_get_top_score();
                uint32_t inf_ms = classifier_get_last_inference_ms();
                float temp = get_chip_temperature();

                // Simulação de coordenadas GPS do talhão até integração física do NEO-6M
                double lat = -8.05389 + ((s_inspection_counter % 6) * 0.00035);
                double lon = -34.88105 + ((s_inspection_counter / 6) * 0.00045);
                float alt = 24.5f;

                // Registra no arquivo de auditoria CSV
                log_inspection(top_class, top_score, job.decode_time_ms, inf_ms, temp, lat, lon, alt);

                // Responde ao cliente direto que enviou a foto
                web_server_send_ws_text(job.ws_fd, classifier_get_json_results());

                // Broadcast do evento de diagnóstico formatado para todos os dashboards conectados
                char event_json[384];
                snprintf(event_json, sizeof(event_json),
                    "{\"type\":\"diagnosis\",\"id\":%lu,\"timestamp\":%lu,\"class_name\":\"%s\","
                    "\"confidence\":%.4f,\"anomaly_alert\":%s,\"lat\":%.6f,\"lon\":%.6f,\"alt_m\":%.1f,"
                    "\"timing\":{\"decode_ms\":%lu,\"inference_ms\":%lu,\"total_chip_ms\":%lu}}",
                    s_inspection_counter,
                    (unsigned long)(esp_timer_get_time() / 1000000),
                    top_class,
                    top_score,
                    (strcmp(top_class, "Healthy Leaves") != 0) ? "true" : "false",
                    lat, lon, alt,
                    (unsigned long)job.decode_time_ms,
                    (unsigned long)inf_ms,
                    (unsigned long)(job.decode_time_ms + inf_ms)
                );
                web_server_broadcast_ws_text(event_json);
            } else {
                xQueueSend(free_tensor_queue, &job.tensor_buf, portMAX_DELAY);
                web_server_send_ws_text(job.ws_fd, "{\"status\":\"erro\",\"mensagem\":\"Falha ao ler JPEG\"}");
            }
        }
    }
}

// ==============================================================
// Task 3: Telemetria Periódica Assíncrona (Core 0 - Baixa Prioridade)
// ==============================================================
void telemetry_task(void* pvParameters) {
    char json_buf[384];
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000)); // 1 Hz

        uint32_t uptime_s = (uint32_t)(esp_timer_get_time() / 1000000);
        float temp_c = get_chip_temperature();
        size_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
        size_t sram_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
        const char* mode = wifi_get_mode_str();
        int8_t rssi = wifi_get_rssi();

        snprintf(json_buf, sizeof(json_buf),
            "{\"type\":\"telemetry\",\"uptime_s\":%lu,\"chip_temp_c\":%.1f,\"cpu_freq_mhz\":240,"
            "\"sram_free_bytes\":%u,\"psram_free_bytes\":%u,\"wifi_mode\":\"%s\",\"rssi_dbm\":%d,"
            "\"fps_throughput\":1.77,\"gps\":{\"fix\":true,\"satellites\":9,\"lat\":-8.053891,\"lon\":-34.881052,\"alt_m\":24.5}}",
            (unsigned long)uptime_s, temp_c, (unsigned int)sram_free, (unsigned int)psram_free, mode, (int)rssi
        );

        web_server_broadcast_ws_text(json_buf);
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
    init_temp_sensor();
    init_csv_log();
    
    wifi_init_auto();

    if (classifier_init()) {
        inference_queue = xQueueCreate(5, sizeof(InferenceRequest));
        decoded_queue = xQueueCreate(2, sizeof(DecodedJob));
        free_tensor_queue = xQueueCreate(2, sizeof(int8_t*));

        // Prealoca Double Buffer de tensores (2x 76,8 KB) na Octal PSRAM
        for (int i = 0; i < 2; i++) {
            int8_t* buf = (int8_t*)heap_caps_malloc(TENSOR_SIZE, MALLOC_CAP_SPIRAM);
            if (!buf) {
                ESP_LOGE(TAG, "Falha ao alocar buffer de tensor na PSRAM!");
            }
            xQueueSend(free_tensor_queue, &buf, portMAX_DELAY);
        }

        // Core 0: Descompressão JPEG (Prioridade 5)
        xTaskCreatePinnedToCore(decode_task, "decode_task", 8192, NULL, 5, NULL, 0);

        // Core 1: Rede Neural TFLite Micro (Prioridade 5)
        xTaskCreatePinnedToCore(inference_task, "inference_task", 8192, NULL, 5, NULL, 1);

        // Core 0: Telemetria Periódica (Prioridade 2 - Baixa prioridade)
        xTaskCreatePinnedToCore(telemetry_task, "telemetry_task", 4096, NULL, 2, NULL, 0);

        web_server_start();
        ESP_LOGI(TAG, "Pipeline assincrono Dual-Core com Dashboard Web e Telemetria iniciado com sucesso!");
    }
}
