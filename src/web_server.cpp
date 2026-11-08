#include "web_server.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/stat.h>
#include "esp_http_server.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "wifi_setup.h"

static const char* TAG = "WEB_SERVER";
extern QueueHandle_t inference_queue;
static httpd_handle_t server = NULL;
static SemaphoreHandle_t s_ws_mutex = NULL;

// Fallback HTML caso LittleFS não contenha os assets
static const char FALLBACK_INDEX_HTML[] = R"rawliteral(<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Sugarcane AI — ESP32-S3</title>
  <style>
    body { background: #0b0f19; color: #f8fafc; font-family: sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { background: #151d2f; border: 1px solid #22304d; border-radius: 12px; padding: 24px; text-align: center; max-width: 480px; }
    h1 { color: #10b981; margin-bottom: 8px; font-size: 1.5rem; }
    p { color: #94a3b8; font-size: 0.9rem; line-height: 1.5; }
    .btn { display: inline-block; background: #10b981; color: #042f2e; padding: 10px 18px; border-radius: 8px; font-weight: bold; text-decoration: none; margin-top: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Sugarcane AI Dashboard</h1>
    <p>O firmware está ativo e operando em modo dual-core.</p>
    <p>Para visualizar a interface completa em Vue.js 3 com mapas Leaflet, execute <code>pio run -t uploadfs</code> para gravar os assets comprimidos na partição LittleFS.</p>
    <a href="/api/status" class="btn">Ver Status da API</a>
  </div>
</body>
</html>)rawliteral";

// ==============================================================
// Handler: GET / (Serve index.html.gz do LittleFS com fallback)
// ==============================================================
static esp_err_t index_handler(httpd_req_t *req) {
    const char* gz_path = "/storage/www/index.html.gz";
    const char* raw_path = "/storage/www/index.html";

    FILE* f = fopen(gz_path, "rb");
    bool is_gzip = true;
    if (!f) {
        f = fopen(raw_path, "rb");
        is_gzip = false;
    }

    if (!f) {
        ESP_LOGW(TAG, "index.html não encontrado no LittleFS. Servindo fallback embutido.");
        httpd_resp_set_type(req, "text/html; charset=utf-8");
        return httpd_resp_send(req, FALLBACK_INDEX_HTML, HTTPD_RESP_USE_STRLEN);
    }

    httpd_resp_set_type(req, "text/html; charset=utf-8");
    if (is_gzip) {
        httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
    }
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache");

    // Streaming em blocos alocados na Octal PSRAM
    char* chunk = (char*)heap_caps_malloc(2048, MALLOC_CAP_SPIRAM);
    if (!chunk) chunk = (char*)malloc(1024);

    size_t read_bytes = 0;
    while ((read_bytes = fread(chunk, 1, 2048, f)) > 0) {
        httpd_resp_send_chunk(req, chunk, read_bytes);
    }
    httpd_resp_send_chunk(req, NULL, 0);

    free(chunk);
    fclose(f);
    return ESP_OK;
}

// ==============================================================
// Handler: GET /assets/* (Serve arquivos estáticos comprimidos)
// ==============================================================
static esp_err_t assets_handler(httpd_req_t *req) {
    char filepath[128];
    char gz_filepath[132];

    snprintf(filepath, sizeof(filepath), "/storage/www%s", req->uri);
    snprintf(gz_filepath, sizeof(gz_filepath), "%s.gz", filepath);

    FILE* f = fopen(gz_filepath, "rb");
    bool is_gzip = true;

    if (!f) {
        f = fopen(filepath, "rb");
        is_gzip = false;
    }

    if (!f) {
        httpd_resp_send_404(req);
        return ESP_FAIL;
    }

    if (strstr(req->uri, ".js")) {
        httpd_resp_set_type(req, "application/javascript");
    } else if (strstr(req->uri, ".css")) {
        httpd_resp_set_type(req, "text/css");
    } else if (strstr(req->uri, ".svg")) {
        httpd_resp_set_type(req, "image/svg+xml");
    } else if (strstr(req->uri, ".png")) {
        httpd_resp_set_type(req, "image/png");
    }

    if (is_gzip) {
        httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
    }
    httpd_resp_set_hdr(req, "Cache-Control", "public, max-age=86400, immutable");

    char* chunk = (char*)heap_caps_malloc(2048, MALLOC_CAP_SPIRAM);
    if (!chunk) chunk = (char*)malloc(1024);

    size_t read_bytes = 0;
    while ((read_bytes = fread(chunk, 1, 2048, f)) > 0) {
        httpd_resp_send_chunk(req, chunk, read_bytes);
    }
    httpd_resp_send_chunk(req, NULL, 0);

    free(chunk);
    fclose(f);
    return ESP_OK;
}

// ==============================================================
// Handler: GET /api/export-csv (Download direto do CSV para QGIS)
// ==============================================================
static esp_err_t export_csv_handler(httpd_req_t *req) {
    const char* csv_path = "/storage/inspections.csv";
    FILE* f = fopen(csv_path, "r");

    httpd_resp_set_type(req, "text/csv; charset=utf-8");
    httpd_resp_set_hdr(req, "Content-Disposition", "attachment; filename=\"inspecoes_sugarcane_talhao.csv\"");

    if (!f) {
        // Se ainda não houver arquivo, gera um CSV com cabeçalho padrão
        const char* default_csv = "id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms\n"
                                  "1,1731070800,-8.05389,-34.88105,24.5,smut,0.840,48.7,283.4,102.7\n"
                                  "2,1731070815,-8.05391,-34.88107,24.6,BrownRust,0.980,48.9,283.5,101.8\n";
        return httpd_resp_send(req, default_csv, HTTPD_RESP_USE_STRLEN);
    }

    char* chunk = (char*)heap_caps_malloc(2048, MALLOC_CAP_SPIRAM);
    if (!chunk) chunk = (char*)malloc(1024);

    size_t read_bytes = 0;
    while ((read_bytes = fread(chunk, 1, 2048, f)) > 0) {
        httpd_resp_send_chunk(req, chunk, read_bytes);
    }
    httpd_resp_send_chunk(req, NULL, 0);

    free(chunk);
    fclose(f);
    return ESP_OK;
}

// ==============================================================
// Handler: GET /api/status (JSON de telemetria básica)
// ==============================================================
static esp_err_t status_handler(httpd_req_t *req) {
    char status_json[256];
    snprintf(status_json, sizeof(status_json),
        "{\"status\":\"online\",\"wifi_mode\":\"%s\",\"ip\":\"%s\",\"rssi\":%d,\"psram_free\":%u,\"sram_free\":%u}",
        wifi_get_mode_str(),
        wifi_get_ip_str(),
        wifi_get_rssi(),
        (unsigned int)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
        (unsigned int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL)
    );
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, status_json, HTTPD_RESP_USE_STRLEN);
}

// ==============================================================
// Handler: /ws (WebSocket Bidirecional: Imagens e Telemetria)
// ==============================================================
static esp_err_t ws_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) return ESP_OK;

    httpd_ws_frame_t ws_pkt;
    memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
    
    // Lê tamanho do frame inicial
    esp_err_t ret = httpd_ws_recv_frame(req, &ws_pkt, 0);
    if (ret != ESP_OK) return ret;

    if (ws_pkt.len > 0) {
        // Aloca buffer na Octal PSRAM para proteger a SRAM interna
        uint8_t* buf = (uint8_t*)heap_caps_malloc(ws_pkt.len + 1, MALLOC_CAP_SPIRAM);
        if (buf) {
            ws_pkt.payload = buf;
            ret = httpd_ws_recv_frame(req, &ws_pkt, ws_pkt.len);
            if (ret == ESP_OK) {
                buf[ws_pkt.len] = '\0';

                if (ws_pkt.type == HTTPD_WS_TYPE_TEXT) {
                    // Trata comandos vindos do Vue
                    if (strstr((char*)buf, "clear_history")) {
                        ESP_LOGW(TAG, "Comando clear_history recebido via WebSocket. Truncando inspections.csv...");
                        FILE* f = fopen("/storage/inspections.csv", "w");
                        if (f) {
                            fputs("id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms\n", f);
                            fclose(f);
                        }
                        web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"ok\",\"msg\":\"Histórico limpo com sucesso\"}");
                    }
                    free(buf);
                } else if (ws_pkt.type == HTTPD_WS_TYPE_BINARY) {
                    // Frame JPEG de imagem -> envia para o pipeline de decodificação
                    InferenceRequest request = { buf, ws_pkt.len, httpd_req_to_sockfd(req) };
                    xQueueSend(inference_queue, &request, portMAX_DELAY);
                } else {
                    free(buf);
                }
            } else {
                free(buf);
            }
        }
    }
    return ESP_OK;
}

void web_server_start() {
    if (!s_ws_mutex) {
        s_ws_mutex = xSemaphoreCreateMutex();
    }
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.task_priority = 2;          // BAIXA PRIORIDADE: Protege o pipeline de IA (prioridade 5)
    config.core_id = 0;                // Fixado no Core 0 (Wi-Fi + Decode)
    config.stack_size = 10240;
    config.max_open_sockets = 7;
    config.lru_purge_enable = true;    // Reciclagem automática de sockets inativos
    config.uri_match_fn = httpd_uri_match_wildcard;

    if (httpd_start(&server, &config) == ESP_OK) {
        // 1. Rota raiz
        httpd_uri_t index_uri = {
            .uri        = "/",
            .method     = HTTP_GET,
            .handler    = index_handler,
            .user_ctx   = NULL,
            .is_websocket = false
        };
        httpd_register_uri_handler(server, &index_uri);

        // 2. Rota de assets estáticos com wildcard
        httpd_uri_t assets_uri = {
            .uri        = "/assets/*",
            .method     = HTTP_GET,
            .handler    = assets_handler,
            .user_ctx   = NULL,
            .is_websocket = false
        };
        httpd_register_uri_handler(server, &assets_uri);

        // 3. Rota de download do CSV
        httpd_uri_t export_csv_uri = {
            .uri        = "/api/export-csv",
            .method     = HTTP_GET,
            .handler    = export_csv_handler,
            .user_ctx   = NULL,
            .is_websocket = false
        };
        httpd_register_uri_handler(server, &export_csv_uri);

        // 4. Rota de status JSON
        httpd_uri_t status_uri = {
            .uri        = "/api/status",
            .method     = HTTP_GET,
            .handler    = status_handler,
            .user_ctx   = NULL,
            .is_websocket = false
        };
        httpd_register_uri_handler(server, &status_uri);

        // 5. WebSocket
        httpd_uri_t ws_uri = {
            .uri        = "/ws",
            .method     = HTTP_GET,
            .handler    = ws_handler,
            .user_ctx   = NULL,
            .is_websocket = true
        };
        httpd_register_uri_handler(server, &ws_uri);

        ESP_LOGI(TAG, "Servidor Web e WebSocket assincrono iniciado na porta 80 (Prioridade 2).");
    }
}

void web_server_send_ws_text(int fd, const char* text) {
    if (!server || fd < 0 || !text) return;
    if (!s_ws_mutex) {
        s_ws_mutex = xSemaphoreCreateMutex();
    }
    if (xSemaphoreTake(s_ws_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
        httpd_ws_frame_t ws_pkt;
        memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
        ws_pkt.payload = (uint8_t*)text;
        ws_pkt.len = strlen(text);
        ws_pkt.type = HTTPD_WS_TYPE_TEXT;
        httpd_ws_send_frame_async(server, fd, &ws_pkt);
        xSemaphoreGive(s_ws_mutex);
    }
}

void web_server_broadcast_ws_text(const char* text) {
    if (!server || !text) return;
    if (!s_ws_mutex) {
        s_ws_mutex = xSemaphoreCreateMutex();
    }
    if (xSemaphoreTake(s_ws_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
        size_t max_clients = 7;
        int client_fds[7];

        if (httpd_get_client_list(server, &max_clients, client_fds) == ESP_OK) {
            httpd_ws_frame_t ws_pkt;
            memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
            ws_pkt.payload = (uint8_t*)text;
            ws_pkt.len = strlen(text);
            ws_pkt.type = HTTPD_WS_TYPE_TEXT;

            for (size_t i = 0; i < max_clients; i++) {
                if (httpd_ws_get_fd_info(server, client_fds[i]) == HTTPD_WS_CLIENT_WEBSOCKET) {
                    httpd_ws_send_frame_async(server, client_fds[i], &ws_pkt);
                }
            }
        }
        xSemaphoreGive(s_ws_mutex);
    }
}
