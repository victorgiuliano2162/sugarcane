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

#ifndef CONFIG_SUGARCANE_WS_AUTH_TOKEN
#define CONFIG_SUGARCANE_WS_AUTH_TOKEN "sugarcane"
#endif

static const char* TAG = "WEB_SERVER";
extern QueueHandle_t inference_queue;
extern bool csv_lock(TickType_t timeout);
extern void csv_unlock();
extern void csv_clear_history();
static httpd_handle_t server = NULL;
static SemaphoreHandle_t s_ws_mutex = NULL;

struct WsWorkItem {
    httpd_handle_t hd;
    int fd;
    char* payload;
    size_t len;
};

static esp_err_t stream_file_chunks(httpd_req_t *req, FILE *f) {
    const size_t kChunkSize = 2048;
    char* chunk = (char*)heap_caps_malloc(kChunkSize, MALLOC_CAP_SPIRAM);
    if (!chunk) {
        chunk = (char*)malloc(kChunkSize);
    }
    if (!chunk) {
        ESP_LOGE(TAG, "Falha ao alocar buffer de streaming (%u bytes)", (unsigned)kChunkSize);
        httpd_resp_send_500(req);
        return ESP_ERR_NO_MEM;
    }

    size_t read_bytes = 0;
    esp_err_t err = ESP_OK;
    while ((read_bytes = fread(chunk, 1, kChunkSize, f)) > 0) {
        err = httpd_resp_send_chunk(req, chunk, read_bytes);
        if (err != ESP_OK) {
            break;
        }
    }
    if (err == ESP_OK) {
        httpd_resp_send_chunk(req, NULL, 0);
    }

    free(chunk);
    return err;
}

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

    // Streaming em blocos alocados na Octal PSRAM (com fallback seguro)
    esp_err_t err = stream_file_chunks(req, f);
    fclose(f);
    return err;
}

// ==============================================================
// Handler: GET /assets/* (Serve arquivos estáticos comprimidos)
// ==============================================================
static esp_err_t assets_handler(httpd_req_t *req) {
    // Rejeita path traversal e remove query string
    if (strstr(req->uri, "..") || strchr(req->uri, '\\')) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid path");
        return ESP_FAIL;
    }

    char clean_uri[128];
    strncpy(clean_uri, req->uri, sizeof(clean_uri) - 1);
    clean_uri[sizeof(clean_uri) - 1] = '\0';
    char* qmark = strchr(clean_uri, '?');
    if (qmark) *qmark = '\0';

    char filepath[192];
    char gz_filepath[196];

    int n1 = snprintf(filepath, sizeof(filepath), "/storage/www%s", clean_uri);
    int n2 = snprintf(gz_filepath, sizeof(gz_filepath), "%s.gz", filepath);
    if (n1 < 0 || n1 >= (int)sizeof(filepath) || n2 < 0 || n2 >= (int)sizeof(gz_filepath)) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "URI too long");
        return ESP_FAIL;
    }

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

    if (strstr(clean_uri, ".js")) {
        httpd_resp_set_type(req, "application/javascript");
    } else if (strstr(clean_uri, ".css")) {
        httpd_resp_set_type(req, "text/css");
    } else if (strstr(clean_uri, ".svg")) {
        httpd_resp_set_type(req, "image/svg+xml");
    } else if (strstr(clean_uri, ".png")) {
        httpd_resp_set_type(req, "image/png");
    }

    if (is_gzip) {
        httpd_resp_set_hdr(req, "Content-Encoding", "gzip");
    }
    httpd_resp_set_hdr(req, "Cache-Control", "public, max-age=86400, immutable");

    esp_err_t err = stream_file_chunks(req, f);
    fclose(f);
    return err;
}

// ==============================================================
// Handler: GET /api/export-csv (Download direto do CSV para QGIS)
// ==============================================================
static esp_err_t export_csv_handler(httpd_req_t *req) {
    const char* csv_path = "/storage/inspections.csv";

    if (!csv_lock(pdMS_TO_TICKS(2000))) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "CSV busy");
        return ESP_FAIL;
    }

    FILE* f = fopen(csv_path, "r");

    httpd_resp_set_type(req, "text/csv; charset=utf-8");
    httpd_resp_set_hdr(req, "Content-Disposition", "attachment; filename=\"inspecoes_sugarcane_talhao.csv\"");

    if (!f) {
        csv_unlock();
        const char* default_csv = "id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms\n";
        return httpd_resp_send(req, default_csv, HTTPD_RESP_USE_STRLEN);
    }

    esp_err_t err = stream_file_chunks(req, f);
    fclose(f);
    csv_unlock();
    return err;
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
        if (!buf) {
            ESP_LOGE(TAG, "Falha ao alocar %u bytes na PSRAM para frame WS.", (unsigned)(ws_pkt.len + 1));
            web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"erro\",\"mensagem\":\"Memoria PSRAM insuficiente\"}");
            return ESP_FAIL;
        }

        ws_pkt.payload = buf;
        ret = httpd_ws_recv_frame(req, &ws_pkt, ws_pkt.len);
        if (ret == ESP_OK) {
            buf[ws_pkt.len] = '\0';

            if (ws_pkt.type == HTTPD_WS_TYPE_TEXT) {
                // Trata comandos vindos do Vue com validacao de auth_token
                if (strstr((char*)buf, "clear_history")) {
                    char expected_token[96];
                    snprintf(expected_token, sizeof(expected_token), "\"auth_token\":\"%s\"", CONFIG_SUGARCANE_WS_AUTH_TOKEN);
                    if (strlen(CONFIG_SUGARCANE_WS_AUTH_TOKEN) > 0 && !strstr((char*)buf, expected_token)) {
                        ESP_LOGW(TAG, "Tentativa de clear_history com auth_token invalido.");
                        web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"erro\",\"mensagem\":\"Token invalido\"}");
                    } else {
                        ESP_LOGW(TAG, "Comando clear_history autorizado. Truncando inspections.csv...");
                        csv_clear_history();
                        web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"ok\",\"msg\":\"Histórico limpo com sucesso\"}");
                    }
                }
                free(buf);
            } else if (ws_pkt.type == HTTPD_WS_TYPE_BINARY) {
                // Frame JPEG de imagem -> envia para o pipeline de decodificacao sem travar httpd
                InferenceRequest request = { buf, ws_pkt.len, httpd_req_to_sockfd(req) };
                if (xQueueSend(inference_queue, &request, pdMS_TO_TICKS(100)) != pdTRUE) {
                    free(buf);
                    ESP_LOGW(TAG, "Fila de inferencia cheia; frame descartado.");
                    web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"erro\",\"mensagem\":\"Fila de inferencia ocupada\"}");
                }
            } else {
                free(buf);
            }
        } else {
            free(buf);
            web_server_send_ws_text(httpd_req_to_sockfd(req), "{\"status\":\"erro\",\"mensagem\":\"Falha ao receber frame WebSocket\"}");
            return ret;
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

static void ws_send_work_cb(void* arg) {
    WsWorkItem* item = (WsWorkItem*)arg;
    if (!item) return;

    if (item->hd && item->fd >= 0 && item->payload &&
        httpd_ws_get_fd_info(item->hd, item->fd) == HTTPD_WS_CLIENT_WEBSOCKET) {
        httpd_ws_frame_t ws_pkt;
        memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
        ws_pkt.payload = (uint8_t*)item->payload;
        ws_pkt.len = item->len;
        ws_pkt.type = HTTPD_WS_TYPE_TEXT;
        httpd_ws_send_frame_async(item->hd, item->fd, &ws_pkt);
    }

    free(item->payload);
    free(item);
}

static void enqueue_ws_text(int fd, const char* text, size_t len) {
    if (!server || fd < 0 || !text || len == 0) return;

    WsWorkItem* item = (WsWorkItem*)malloc(sizeof(WsWorkItem));
    char* copy = (char*)heap_caps_malloc(len + 1, MALLOC_CAP_SPIRAM);
    if (!copy) copy = (char*)malloc(len + 1);

    if (!item || !copy) {
        free(item);
        free(copy);
        return;
    }

    memcpy(copy, text, len);
    copy[len] = '\0';
    item->hd = server;
    item->fd = fd;
    item->payload = copy;
    item->len = len;

    if (httpd_queue_work(server, ws_send_work_cb, item) != ESP_OK) {
        free(item->payload);
        free(item);
    }
}

void web_server_send_ws_text(int fd, const char* text) {
    if (!server || fd < 0 || !text) return;
    if (!s_ws_mutex) {
        s_ws_mutex = xSemaphoreCreateMutex();
    }
    if (xSemaphoreTake(s_ws_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
        enqueue_ws_text(fd, text, strlen(text));
        xSemaphoreGive(s_ws_mutex);
    }
}

bool web_server_has_ws_clients() {
    if (!server) return false;
    size_t max_clients = 7;
    int client_fds[7];
    if (httpd_get_client_list(server, &max_clients, client_fds) != ESP_OK) {
        return false;
    }
    for (size_t i = 0; i < max_clients; i++) {
        if (httpd_ws_get_fd_info(server, client_fds[i]) == HTTPD_WS_CLIENT_WEBSOCKET) {
            return true;
        }
    }
    return false;
}

void web_server_broadcast_ws_text(const char* text) {
    if (!server || !text) return;
    if (!s_ws_mutex) {
        s_ws_mutex = xSemaphoreCreateMutex();
    }
    if (xSemaphoreTake(s_ws_mutex, pdMS_TO_TICKS(500)) == pdTRUE) {
        size_t max_clients = 7;
        int client_fds[7];
        size_t len = strlen(text);

        if (httpd_get_client_list(server, &max_clients, client_fds) == ESP_OK) {
            for (size_t i = 0; i < max_clients; i++) {
                if (httpd_ws_get_fd_info(server, client_fds[i]) == HTTPD_WS_CLIENT_WEBSOCKET) {
                    enqueue_ws_text(client_fds[i], text, len);
                }
            }
        }
        xSemaphoreGive(s_ws_mutex);
    }
}

bool web_server_has_ws_clients() {
    if (!server) return false;
    size_t max_clients = 7;
    int client_fds[7];
    if (httpd_get_client_list(server, &max_clients, client_fds) != ESP_OK) {
        return false;
    }
    for (size_t i = 0; i < max_clients; i++) {
        if (httpd_ws_get_fd_info(server, client_fds[i]) == HTTPD_WS_CLIENT_WEBSOCKET) {
            return true;
        }
    }
    return false;
}
