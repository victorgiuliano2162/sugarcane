# Pontos de Execução e Fluxos Operacionais — Projeto Sugarcane

Este documento descreve todos os **pontos de entrada (entrypoints)** do sistema, a sequência de boot do firmware, os contratos HTTP/WebSocket em tempo de execução e os comandos operacionais de build, teste e simulação.

---

## 1. Sequência de Boot do ESP32-S3 (`app_main`)

Em [src/main.cpp](../../src/main.cpp), `app_main()` executa exatamente na seguinte ordem:

1. Inicializa `nvs_flash_init()` (apagando e reinicializando em caso de `ESP_ERR_NVS_NO_FREE_PAGES` ou `ESP_ERR_NVS_NEW_VERSION_FOUND`).
2. Cria o mutex `s_csv_mutex = xSemaphoreCreateMutex()`.
3. Monta a partição LittleFS em `/storage` (`init_littlefs()`).
4. Instala e habilita o sensor térmico interno (`init_temp_sensor()`, faixa `10..80 °C`).
5. Inicializa ou recupera `/storage/inspections.csv` e `s_inspection_counter` sob `s_csv_mutex` (`init_csv_log()`).
6. Inicializa o receptor GPS NEO-6M na `UART_NUM_2` (`gps_neo6m_init()`, criando `gps_task` no Core 0).
7. Inicializa o Wi-Fi híbrido (`wifi_init_auto()`): lê NVS `wifi_cfg` (fallback `Kconfig`), tenta STA por `5 s` (aciona SNTP ao obter IP), ou ativa SoftAP `Sugarcane-AI-AP` (`192.168.4.1`) e inicia mDNS (`sugarcane.local`).
8. Inicializa o classificador (`classifier_init()`): aloca `48 KB` + `25 KB` na SRAM interna, carrega `/storage/model_mbnet_int8.tflite` na PSRAM, aloca `tensor_arena` (`800 KB` PSRAM) e registra `MicroMutableOpResolver<6>`.
9. Cria as filas `inference_queue` (5), `decoded_queue` (2) e `free_tensor_queue` (2) e pré-aloca o *Double Buffer* (`2 × 76,8 KB` na PSRAM).
10. Cria `decode_task` (Core 0, prioridade 5), `inference_task` (Core 1, prioridade 5 — que chama `classifier_enable_dual_core()` fixando `esp_nn_worker` no Core 0) e `telemetry_task` (Core 0, prioridade 2).
11. Inicia o servidor HTTP/WebSocket (`web_server_start()`, Core 0, prioridade 2, porta 80).

---

## 2. Fluxo de Execução de uma Inferência em Produção

```mermaid
sequenceDiagram
    participant CLI as Cliente / Dashboard Vue 3
    participant WS as httpd / ws_handler (Core 0, P2)
    participant DEC as decode_task (Core 0, P5)
    participant INF as inference_task (Core 1, P5)
    participant WKR as esp_nn_worker (Core 0)
    participant TEL as telemetry_task (Core 0, P2)

    CLI->>WS: Frame Binário JPEG (/ws)
    WS->>DEC: xQueueSend(inference_queue, timeout 100ms)
    DEC->>DEC: process_jpeg() Modo 7 + free(jpeg_buf)
    DEC->>INF: xQueueSend(decoded_queue)
    INF->>INF: memcpy -> input_tensor + devolve free_tensor_queue
    INF<-->WKR: classifier_run() [Fork-Join SIMD INT8]
    INF->>INF: gps_get_state() + log_inspection() (s_csv_mutex)
    INF->>WS: httpd_queue_work (WsWorkItem) -> Resposta Direta JSON
    INF->>WS: httpd_queue_work (WsWorkItem) -> Broadcast "diagnosis"
    WS-->>CLI: JSON Diagnóstico
    loop A cada 1000 ms (se web_server_has_ws_clients())
        TEL->>WS: Broadcast "telemetry" (temp, thermal_alert, RAM, GPS, FPS)
        WS-->>CLI: JSON Telemetria
    end
```

---

## 3. Catálogo de Endpoints HTTP e Contratos WebSocket

### 3.1. Rotas HTTP (`porta 80`)

| Rota | Método | Handler | Descrição |
| :--- | :---: | :--- | :--- |
| `/` | `GET` | `index_handler` | Serve `/storage/www/index.html.gz` (fallback `index.html` ou `FALLBACK_INDEX_HTML`). |
| `/assets/*` | `GET` | `assets_handler` | Serve `.js`, `.css`, `.svg`, `.png` (preferência `.gz`, `Cache-Control: immutable`). Bloqueia `..` e `\`, remove query string. |
| `/api/status` | `GET` | `status_handler` | Retorna JSON com `status`, `wifi_mode`, `ip`, `rssi`, `psram_free`, `sram_free`. |
| `/api/export-csv` | `GET` | `export_csv_handler` | Faz streaming de `/storage/inspections.csv` sob `s_csv_mutex` (`inspecoes_sugarcane_talhao.csv`). |
| `/ws` | `GET` (WS) | `ws_handler` | Endpoint WebSocket bidirecional (binário JPEG e texto JSON). |

### 3.2. Mensagens WebSocket (`/ws`)

* **Entrada Binária (`HTTPD_WS_TYPE_BINARY`):** Bytes brutos do arquivo JPEG. Enfileirado em `inference_queue` (timeout `100 ms`).
* **Entrada Texto (`HTTPD_WS_TYPE_TEXT`):**
  ```json
  {"cmd":"clear_history","auth_token":"sugarcane"}
  ```
* **Saída Direta (Resposta ao remetente):**
  ```json
  {"status":"sucesso","decode_ms":94,"inferencia_ms":283,"resultados":[{"label":"Healthy Leaves","score":0.9531}, "..."]}
  ```
* **Broadcast `diagnosis` (Todos os clientes):**
  ```json
  {"type":"diagnosis","id":1,"timestamp":1732374000,"class_name":"Healthy Leaves","confidence":0.9531,"anomaly_alert":false,"lat":0.000000,"lon":0.000000,"alt_m":0.0,"timing":{"decode_ms":94,"inference_ms":283,"total_chip_ms":377}}
  ```
* **Broadcast `telemetry` (1 Hz, somente com clientes conectados):**
  ```json
  {"type":"telemetry","uptime_s":120,"chip_temp_c":56.4,"thermal_alert":false,"cpu_freq_mhz":240,"sram_free_bytes":123456,"psram_free_bytes":5810000,"wifi_mode":"STA","rssi_dbm":-52,"fps_throughput":2.65,"gps":{"fix":false,"satellites":0,"lat":0.000000,"lon":0.000000,"alt_m":0.0}}
  ```
* **Erros Padronizados (`{"status":"erro","mensagem":"..."}`):** `Memoria PSRAM insuficiente`, `Fila de inferencia ocupada`, `Token invalido`, `Falha ao ler JPEG`, `Falha no classificador`.

---

## 4. Comandos de Execução por Subsistema

### 4.1. Firmware, LittleFS e Testes Unitários (PlatformIO)
```bash
pio run                          # Compila firmware ESP-IDF
pio run -t upload                # Grava firmware na partição factory
pio run -t uploadfs              # Grava data/ (modelo .tflite + data/www/) no LittleFS
pio device monitor -b 115200     # Monitor serial
pio test                         # Executa suíte Unity (test/test_image_math/test_main.cpp)
```

### 4.2. Frontend SPA Vue 3
```bash
cd frontend && npm ci && npm run dev     # Desenvolvimento local (Vite)
python3 scripts/build_and_compress_frontend.py  # Build + Gzip nível 9 -> data/www/
```

### 4.3. Inferência, Benchmarks e Co-Simulação HIL/SIG
```bash
# Inferência local (emulação Python) ou no hardware via WebSocket
python3 scripts/test_inference.py caminho/folha.jpg
python3 scripts/test_inference.py caminho/folha.jpg --esp32 192.168.1.19

# Benchmarks em lote (model_inference_tests/)
python3 model_inference_tests/run_evaluation_espnn_sram.py

# Co-simulação HIL MAVLink (UDP 14550 + WS) e geração de mapas SIG
python3 scripts/hil_mavlink_simulator.py --esp32 192.168.1.19 --speed 10.0
python3 scripts/generate_infestation_heatmaps.py
```
