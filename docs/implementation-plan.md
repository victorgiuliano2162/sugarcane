# Plano de Implementação — Sugarcane

- **Data:** 2026-11-23
- **Referência:** [gap-analysis.md](file:///home/victor/projects/sugarcane/docs/gap-analysis.md) (commit `93903d3`)
- **Escopo:** Detalhamento completo da **Fase 1** (`#1` a `#6`) e checklist resumida das **Fases 2 e 3** (`#7` a `#15`).

---

## 1. Visão Geral

### Objetivo
Sanar as falhas críticas de concorrência, segurança, estabilidade de rede/arquivos e fluxo ponta a ponta no firmware ESP32-S3 (`src/`), nos scripts de inferência/HIL (`scripts/`) e na telemetria de posicionamento, mantendo estrita aderência à stack atual (ESP-IDF / PlatformIO, FreeRTOS, LittleFS, Vue 3 e Python `websockets`).

### Pré-requisitos Globais
- Criar uma branch dedicada a partir de `master` (`git checkout -b fix/fase-1-estabilidade-seguranca`).
- Ambiente PlatformIO (`pio`) funcional para compilação ESP-IDF (`esp32-s3-devkitm-1`) e gravação (`upload` e `uploadfs`).
- Ambiente Python 3 com `websockets`, `pymavlink`, `numpy` e `Pillow` instalados para validação dos scripts.
- Se houver dados em campo em `/storage/inspections.csv` no dispositivo físico, baixar uma cópia via `GET /api/export-csv` antes de regravar firmware/LittleFS.

### Ordem de Execução

| Ordem | # | Título | Esforço | Dependências |
| :---: | :-: | :--- | :---: | :--- |
| 1 | **#1** | Cópia/sincronização segura no envio WebSocket (`web_server.cpp`) | P | Nenhuma |
| 2 | **#5** | Sanitização de path em `assets_handler` e correção de buffer de streaming | P | Nenhuma (mesmo arquivo que `#1`) |
| 3 | **#3** | Mutex em `/storage/inspections.csv` e `s_inspection_counter` | P | Nenhuma |
| 4 | **#2** | Credenciais Wi-Fi STA/AP em NVS/`Kconfig` e rotação de senha exposta | P | Nenhuma |
| 5 | **#4** | Filtragem de pacotes `telemetry`/`diagnosis` em `test_inference.py` e `hil_mavlink_simulator.py` | P | Nenhuma |
| 6 | **#6** | Integração UART do GPS NEO-6M e cálculo dinâmico de `fps_throughput` | G | `#1`, `#3` |

---

## 2. Tarefas Detalhadas (Fase 1)

### Tarefa 1 — `#1`: `httpd_ws_send_frame_async` recebe ponteiros para buffers na stack ou estático sobrescritos

- **Achado:** `#1` — `httpd_ws_send_frame_async` recebe ponteiros para buffers na stack (`event_json`, `json_buf`) ou estático sobrescritos (`result_json`) sem cópia.
- **Objetivo:** Garantir que todo envio WebSocket leia memória válida e imutável até a conclusão da transmissão TCP pelo `httpd`.
- **Pré-condições:** Nenhuma.
- **Passos:**
  1. Em `src/web_server.cpp:303-343` (`web_server_send_ws_text` e `web_server_broadcast_ws_text`), substituir o envio assíncrono com ponteiro externo por um helper interno que aloca uma cópia do texto (ex.: `strdup` ou `heap_caps_malloc(len + 1, MALLOC_CAP_SPIRAM)` com fallback `malloc`) ou usa envio síncrono via `httpd_ws_send_frame_async` apenas dentro de `httpd_queue_work`, onde o callback de trabalho é dono do buffer alocado e executa `free()` imediatamente após `httpd_ws_send_frame_async` / `httpd_ws_send_frame`:
     ```cpp
     struct WsWorkItem { httpd_handle_t hd; int fd; char* payload; size_t len; };
     // No work callback na thread do httpd:
     httpd_ws_send_frame_async(item->hd, item->fd, &ws_pkt);
     free(item->payload);
     free(item);
     ```
     Alternativamente (mais enxuto se `web_server_send_ws_text` e `broadcast` já rodarem fora da task `httpd`), usar `httpd_queue_work` com payload copiado no heap e `httpd_ws_send_frame` síncrono dentro do callback do `httpd`, liberando `payload` logo após o retorno.
  2. Em `src/main.cpp:185,203,234`, manter os buffers locais `event_json` e `json_buf` sem alteração de escopo, pois passarão a ser copiados na entrada de `web_server_send_ws_text` / `web_server_broadcast_ws_text`.
  3. Em `src/tflite_classifier.cpp:36,160-192`, proteger `result_json` ou retornar cópia/manter apenas leitura imediata antes da próxima inferência (com a cópia feita dentro de `web_server_send_ws_text`, `result_json` já fica protegido contra sobrescrita pelo próximo frame).
- **Testes:**
  - Disparar rajada contínua de inferências (ex.: 50 imagens em pipelining com `run_evaluation_espnn_sram.py`) enquanto o dashboard Vue 3 está conectado recebendo `telemetry` a 1 Hz e `diagnosis` em paralelo.
  - Caso de borda: simular falha de alocação (`payload == NULL`) e confirmar que a função retorna sem crash nem vazamento do mutex `s_ws_mutex`.
- **Como validar:** Executar `pio run` (compilação limpa) e rodar 50+ inferências concorrentes com o dashboard aberto verificando no console do navegador e no script Python que 100% dos payloads chegam como JSON válido sem truncamento.
- **Risco e rollback:** Risco de fragmentação ou vazamento se `free()` não for chamado em caso de erro de `httpd_queue_work`; garantir `free` no caminho de erro quando `httpd_queue_work != ESP_OK`. Rollback simples via `git checkout -- src/web_server.cpp`.
- **Critério de pronto:** Nenhum ponteiro para buffer de stack (`event_json`, `json_buf`) ou estático mutável (`result_json`) é retido após o retorno de `web_server_send_ws_text` e `web_server_broadcast_ws_text`.
- **Esforço:** P

---

### Tarefa 2 — `#5`: `assets_handler` concatena `req->uri` sem sanitizar e fallback `malloc(1024)` lê `2048` bytes

- **Achado:** `#5` — `assets_handler` concatena `req->uri` sem sanitizar `..`/query string; fallback `malloc(1024)` lê `2048` bytes e não checa `NULL`.
- **Objetivo:** Eliminar o risco de *path traversal*, *heap buffer overflow* e *null dereference* nos handlers de arquivo do servidor HTTP.
- **Pré-condições:** Nenhuma (executar em sequência com a Tarefa 1 no mesmo arquivo `src/web_server.cpp`).
- **Passos:**
  1. Em `src/web_server.cpp:71-83` (`index_handler`), `123-134` (`assets_handler`) e `155-166` (`export_csv_handler`), extrair um helper único `stream_file_chunks(httpd_req_t *req, FILE *f)` que aloca `chunk` de `2048` bytes (na PSRAM ou heap padrão), verifica `if (!chunk)` retornando `ESP_ERR_NO_MEM` (`httpd_resp_send_500(req)`), e usa exatamente o tamanho alocado no `fread`.
  2. Em `src/web_server.cpp:88-106` (`assets_handler`), antes de montar `filepath`:
     - Remover query string truncando no primeiro `'?'` (se houver);
     - Rejeitar com `httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid path")` se `req->uri` contiver `".."` ou `'\\'`;
     - Verificar que `snprintf` não truncou o caminho (`ret < 0 || ret >= sizeof(filepath)`).
- **Testes:**
  - Caso normal: `GET /`, `GET /assets/index.js`, `GET /assets/index.js?v=123` e `GET /api/export-csv` retornam `200 OK` com conteúdo íntegro.
  - Caso de borda/erro: `GET /assets/../../inspections.csv` ou `GET /assets/../model_mbnet_int8.tflite` deve retornar `400` ou `404` sem expor arquivos fora de `/storage/www`.
- **Como validar:** Compilar com `pio run` e testar via `curl -i "http://<IP>/assets/../model_mbnet_int8.tflite"` e `curl -i "http://<IP>/assets/index.js?cache=1"`.
- **Risco e rollback:** Baixo risco; caso algum asset tenha caminho maior que `128` bytes, aumentar o buffer para `192` bytes. Rollback via `git checkout -- src/web_server.cpp`.
- **Critério de pronto:** Todos os três handlers usam o helper compartilhado com verificação de `NULL` e `assets_handler` bloqueia sequências `..` e ignora query strings.
- **Esforço:** P

---

### Tarefa 3 — `#3`: Acesso concorrente sem mutex a `/storage/inspections.csv` e `s_inspection_counter`

- **Achado:** `#3` — Acesso concorrente sem mutex a `/storage/inspections.csv` e `s_inspection_counter` entre Core 1 (`inference_task`) e Core 0 (`httpd`).
- **Objetivo:** Serializar toda leitura, escrita e truncamento de `/storage/inspections.csv` e atualizações de `s_inspection_counter`.
- **Pré-condições:** Nenhuma.
- **Passos:**
  1. Em `src/main.cpp:37-40`, criar um `SemaphoreHandle_t s_csv_mutex = NULL` inicializado em `app_main()` antes de iniciar as tasks e o `web_server_start()`.
  2. Em `src/main.cpp:72-113`, proteger `reset_inspection_counter()`, `init_csv_log()` e `log_inspection()` com `xSemaphoreTake(s_csv_mutex, portMAX_DELAY)` / `xSemaphoreGive(s_csv_mutex)`.
  3. Expor helpers públicos (ex.: em `src/main.cpp` ou novo cabeçalho/declaração em `web_server.cpp`): `bool csv_lock(TickType_t timeout)` / `void csv_unlock()`, ou encapsular `csv_clear_history()` em `main.cpp` para que `web_server.cpp:210-219` não manipule o arquivo diretamente sem lock.
  4. Em `src/web_server.cpp:140-167` (`export_csv_handler`), adquirir o lock antes de abrir/ler `/storage/inspections.csv` (ou copiar/streamar sob proteção do mutex com timeout finito, ex. `pdMS_TO_TICKS(2000)`, retornando `503` se ocupado).
- **Testes:**
  - Disparar envio de imagens em rajada (`inference_task` gravando no CSV) enquanto o navegador aciona `GET /api/export-csv` e, em seguida, `clear_history`.
  - Caso de borda: acionar `clear_history` durante uma inferência e verificar que o CSV mantém o cabeçalho íntegro e o próximo ID reinicia em `1` sem linhas corrompidas.
- **Como validar:** Inspecionar o arquivo baixado por `curl http://<IP>/api/export-csv` após testes concorrentes, confirmando número correto de colunas em todas as linhas e IDs estritamente crescentes.
- **Risco e rollback:** Risco de deadlock se `export_csv_handler` segurar o mutex enquanto o cliente HTTP demorar para consumir o socket; mitigar usando timeout finito no `xSemaphoreTake` ou fechando o `FILE*` imediatamente em caso de erro de `httpd_resp_send_chunk`. Rollback via `git checkout -- src/main.cpp src/web_server.cpp`.
- **Critério de pronto:** Todas as operações em `/storage/inspections.csv` e `s_inspection_counter` ocorrem exclusivamente sob `s_csv_mutex`.
- **Esforço:** P

---

### Tarefa 4 — `#2`: Credenciais Wi-Fi STA e SoftAP hardcoded em texto claro

- **Achado:** `#2` — Credenciais Wi-Fi STA e senha padrão do SoftAP hardcoded em texto claro no código-fonte.
- **Objetivo:** Remover segredos do código-fonte versionado, carregando credenciais via NVS com fallback configurável em tempo de compilação (`Kconfig.projbuild` / `sdkconfig`).
- **Pré-condições:** Nenhuma.
- **Passos:**
  1. Criar `src/Kconfig.projbuild` (suportado nativamente pelo ESP-IDF/PlatformIO) definindo `CONFIG_SUGARCANE_WIFI_STA_SSID`, `CONFIG_SUGARCANE_WIFI_STA_PASS`, `CONFIG_SUGARCANE_WIFI_AP_SSID` e `CONFIG_SUGARCANE_WIFI_AP_PASS` com valores padrão vazios/placeholder (ex.: `"CONFIGURE_SSID"`, `""`).
  2. Adicionar `sdkconfig.local` (ou equivalente) ao `.gitignore` caso o desenvolvedor grave credenciais locais fora do Git, mantendo `sdkconfig.defaults` limpo.
  3. Em `src/wifi_setup.cpp:12-16` e `126-130`, remover os `#define` com credenciais reais e implementar leitura prévia do namespace NVS `"wifi_cfg"` (`nvs_open`, `nvs_get_str` para `"sta_ssid"` e `"sta_pass"`), usando `CONFIG_SUGARCANE_WIFI_*` apenas como fallback se a chave não existir no NVS. Se `sta_ssid` estiver vazio, pular direto para `start_softap()`.
  4. **Rotação de credencial (obrigatório):** Alterar a senha da rede Wi-Fi local exposta anteriormente no histórico e a senha padrão do SoftAP em campo, pois o valor antigo já consta nos commits anteriores.
- **Testes:**
  - Caso 1 (NVS vazio e `CONFIG_SUGARCANE_WIFI_STA_SSID` vazio): dispositivo deve iniciar diretamente em modo `SoftAP` sem tentar conectar em SSID inexistente.
  - Caso 2 (NVS populado com credenciais válidas): dispositivo conecta em modo `STA` usando os valores do NVS.
- **Como validar:** Rodar `rg -n "WIFI_STA_PASS|WIFI_AP_PASS" src/` e verificar que não há nenhuma senha real em `src/wifi_setup.cpp`; compilar com `pio run` e conferir log serial de boot.
- **Risco e rollback:** Se `sdkconfig` não tiver credenciais nem o NVS estiver gravado, a placa cairá em SoftAP (comportamento seguro esperado). Rollback via `git checkout -- src/wifi_setup.cpp`.
- **Critério de pronto:** Nenhuma senha real no código-fonte, leitura via NVS implementada e credenciais expostas rotacionadas.
- **Esforço:** P

---

### Tarefa 5 — `#4`: `test_inference.py` e `hil_mavlink_simulator.py` não filtram pacotes `telemetry` / `diagnosis`

- **Achado:** `#4` — `test_inference.py` e `hil_mavlink_simulator.py` chamam `ws.recv()` uma vez sem filtrar pacotes `telemetry` / `diagnosis`.
- **Objetivo:** Garantir que ambos os scripts Python aguardem especificamente o JSON de resposta da inferência (`"status"` / `"resultados"`), ignorando broadcasts assíncronos de `telemetry` e `diagnosis`.
- **Pré-condições:** Nenhuma.
- **Passos:**
  1. Em `scripts/test_inference.py:91-96` (`classify_esp32_async`), substituir o único `raw = await ws.recv()` por um loop com timeout total (ex.: `asyncio.wait_for(..., timeout=15.0)`) que lê mensagens JSON do WebSocket e descarta qualquer mensagem cujo campo `type` seja `"telemetry"` ou `"diagnosis"`, retornando apenas quando receber `"resultados"` ou `"status" == "erro"`.
  2. Aplicar o mesmo loop de filtragem em `scripts/hil_mavlink_simulator.py:314-320` (`classify_on_esp32`).
  3. (Opcional enxuto dentro do mesmo padrão): Reaproveitar a mesma lógica já validada em `model_inference_tests/run_evaluation_espnn_sram.py` (commit `af0164c`) para evitar divergência futura.
- **Testes:**
  - Caso normal: enviar uma imagem com `test_inference.py --esp32 <IP>` enquanto `telemetry_task` emite pacotes a 1 Hz e confirmar exibição do Top-3 e latências (`decode_ms`, `inferencia_ms`).
  - Caso de borda/erro: enviar arquivo inválido (não JPEG) e verificar que o loop encerra imediatamente ao receber `{"status":"erro", ...}` sem travar até o timeout.
- **Como validar:** Executar `python scripts/test_inference.py <amostra.jpg> --esp32 <IP>` e `python scripts/hil_mavlink_simulator.py --esp32 <IP> --waypoints 5` com telemetria 1 Hz ativa no firmware.
- **Risco e rollback:** Baixo risco; se o servidor não responder dentro de 15 s, `asyncio.TimeoutError` deve ser capturado e reportado com mensagem clara. Rollback via `git checkout -- scripts/test_inference.py scripts/hil_mavlink_simulator.py`.
- **Critério de pronto:** `test_inference.py` e `hil_mavlink_simulator.py` nunca falham por consumir um pacote `telemetry` ou `diagnosis` no lugar da resposta da inferência.
- **Esforço:** P

---

### Tarefa 6 — `#6`: Integração UART do GPS NEO-6M e cálculo dinâmico de `fps_throughput`

- **Achado:** `#6` — Coordenadas GPS (NEO-6M), status de satélites e `fps_throughput` são simulados/hardcoded no firmware e frontend.
- **Objetivo:** Substituir coordenadas e FPS fictícios por leitura real do receptor GPS NEO-6M via UART (com fallback explícito `fix: false` quando sem sinal) e medição real da vazão do pipeline.
- **Pré-condições:** Tarefas `#1` (WS seguro) e `#3` (CSV/contador protegido) concluídas.
- **Passos (quebrados em 3 subpassos entregáveis separadamente):**
  1. **Subpasso 6.1 — Módulo GPS UART + Parser NMEA (`src/gps_neo6m.cpp/.h`):**
     - Criar driver leve usando `driver/uart.h` (UART1 ou UART2 configurável, 9600 bps padrão NEO-6M) em uma task de baixa prioridade no Core 0.
     - Implementar parser NMEA mínimo para sentenças `$GPGGA` / `$GNGGA` (latitude, longitude, altitude em metros, fix válido, número de satélites) e `$GPRMC` / `$GNRMC` (opcional para data/hora UTC).
     - Expor `gps_get_state(GpsState* out)` protegido por mutex ou cópia atômica; inicializar com `fix = false, satellites = 0, lat = 0.0, lon = 0.0, alt_m = 0.0`.
  2. **Subpasso 6.2 — Integração no `main.cpp` e FPS real:**
     - Em `src/main.cpp:176-179` (`inference_task`) e `src/main.cpp:227-232` (`telemetry_task`), substituir as coordenadas hardcoded pela leitura de `gps_get_state()`. Se `fix == false`, registrar `0.0, 0.0, 0.0` (ou último fix válido sinalizado) sem inventar `fix: true`.
     - Calcular `fps_throughput` dinamicamente a partir do intervalo real entre inferências ou `1000.0f / (float)(job.decode_time_ms + inf_ms)` (atualizado em variável compartilhada após cada inferência, iniciando em `0.0f` no boot).
  3. **Subpasso 6.3 — Alinhamento do Frontend (`TelemetryCards.vue`):**
     - Em `frontend/src/components/TelemetryCards.vue:76-83` e `App.vue:49-65`, remover os valores iniciais hardcoded que simulam hardware ativo (`fix: true`, `satellites: 9`, `fps_throughput: 1.77`, `~386 ms`) antes da primeira mensagem WS, exibindo estado neutro (`--` / `Buscando`) até chegar o primeiro pacote `telemetry` ou `diagnosis`.
     - Recompilar os assets com `python3 scripts/build_and_compress_frontend.py`.
- **Testes:**
  - Sem módulo NEO-6M conectado (ou sem fix em ambiente fechado): dashboard deve mostrar `Buscando`, `0 satélites` e não gravar coordenadas falsas como se fossem `fix: true`.
  - Com sentenças `$GPGGA` válidas injetadas na UART: confirmar atualização de `lat`, `lon`, `alt_m` e `satellites` tanto no `/ws` quanto no `/storage/inspections.csv`.
- **Como validar:** Compilar com `pio run`, executar `python3 scripts/build_and_compress_frontend.py`, gravar com `pio run -t upload && pio run -t uploadfs` e verificar os payloads `telemetry` e `diagnosis` no DevTools do navegador.
- **Risco e rollback:** Pinos UART escolhidos não devem conflitar com a Octal PSRAM/Flash do ESP32-S3 (evitar GPIOs 26–37 reservados para Flash/PSRAM Octal). Cada subpasso pode ser revertido isoladamente sem afetar o motor TFLite.
- **Critério de pronto:** Nenhum valor fictício de GPS (`-8.05389`, `satellites: 9`, `fix: true`) ou `fps_throughput: 1.77` fixo permanece hardcoded no firmware ou no estado inicial da UI.
- **Esforço:** G

---

## 3. Checklist Resumida — Fases 2 e 3

*(Detalhamento completo disponível sob demanda quando for iniciar a execução destas fases.)*

### Fase 2: Experiência e Produtividade
- [x] **#7** — Corrigir ordenação por `timing.total_chip_ms` em `frontend/src/components/InspectionsTable.vue:184-191` e normalizar `className` no cálculo de `anomaly_alert` em `frontend/src/App.vue:165-167`.
- [x] **#8** — Sincronizar relógio do sistema via SNTP (quando em STA) para gravar Unix epoch real em `timestamp_epoch` (`src/main.cpp`, `src/wifi_setup.cpp`).
- [x] **#9** — Substituir `portMAX_DELAY` por timeout finito em `xQueueSend(inference_queue, ...)` e enviar JSON de erro ao cliente WS quando a fila lotar ou `heap_caps_malloc` falhar (`src/web_server.cpp`).
- [x] **#10** — Validar `auth_token` contra valor armazenado em `Kconfig` (`CONFIG_SUGARCANE_WS_AUTH_TOKEN`) antes de executar `clear_history` no handler WebSocket (`src/web_server.cpp`).
- [x] **#11** — Emitir alerta `thermal_alert` na telemetria e aplicar redução preventiva de cadência quando `chip_temp_c > 75.0f` (`src/main.cpp`).
- [x] **#12** — Contabilizar falhas consecutivas de reconexão em `WIFI_EVENT_STA_DISCONNECTED` para acionar `start_softap()` como fallback após queda de rede (`src/wifi_setup.cpp`).
- [x] **#13** — Adicionar testes unitários em `test/test_image_math/test_main.cpp` (PlatformIO Unity) e workflow de CI em `.github/workflows/ci.yml` validando `pio run` e `npm run build` em `frontend/`.

### Fase 3: Maturidade e Escala
- [x] **#14** — Evitar montagem de JSON em `telemetry_task` quando não houver nenhum cliente WebSocket conectado (`src/main.cpp`, `src/web_server.cpp`).
- [x] **#15** — Atualizar `README.md`, `docs/01_visao_geral/04_GUIA_DE_USO_E_OPERACAO.md` e `docs/04_otimizacao_hardware_e_firmware/03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md` para refletir `partitions.csv` (`4M`/`10M`), `build_and_compress_frontend.py` e o filtro de telemetria WS.

---

## 4. Checklist Final da Fase 1

- [x] Todos os itens `#1`, `#2`, `#3`, `#4`, `#5` e `#6` implementados e compilados.
- [x] Firmware compila sem erros (`pio run`) e frontend compila/comprime sem erros (`python3 scripts/build_and_compress_frontend.py`).
- [ ] Credenciais expostas anteriormente rotacionadas na rede Wi-Fi local (ação operacional externa).
- [ ] Bateria de validação em hardware executada após gravação (`pio run -t upload && pio run -t uploadfs`): rajada WebSocket com dashboard conectado, `test_inference.py`, `hil_mavlink_simulator.py`, teste de path traversal em `/assets/` e verificação do CSV exportado.
- [x] Documentação afetada (`README.md`, `04_GUIA_DE_USO_E_OPERACAO.md`, `03_ESPECIFICACAO_...md`, `02_REALIZACOES_E_MARCOS_DO_PROJETO.md`) atualizada.
