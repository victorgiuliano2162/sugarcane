# Análise de Lacunas Funcionais e Melhorias (Gap Analysis) — Sugarcane

- **Data da análise:** 2026-11-23
- **Escopo:** Repositório completo (firmware `src/`, frontend `frontend/src/`, scripts `scripts/` e `model_inference_tests/`, configurações PlatformIO/ESP-IDF e documentação operacional/arquitetural)
- **Commit analisado:** `93903d3`

---

## Diagnóstico Atual

O repositório **Sugarcane** implementa um sistema embarcado de visão computacional e TinyML no **ESP32-S3** (ESP-IDF via PlatformIO, TFLite Micro + `esp-nn` Dual-Core Fork-Join, `JPEGDEC` em RGB8888 com Box Averaging e Octal PSRAM a 80 MHz) integrado a um **Dashboard Web SPA em Vue.js 3** (servido em gzip a partir do LittleFS via HTTP/WebSocket), além de scripts Python de benchmark em silício, co-simulação HIL MAVLink e geração de mapas SIG/Leaflet. O projeto está em estágio de **MVP funcional validado em bancada** (com benchmarks extensivos em hardware e monografia LaTeX), destacando-se pela engenharia de baixo nível bem resolvida no pipeline de inferência (`src/tflite_classifier.cpp` com buffers em SRAM interna e `src/image_processor.cpp` com `BoxAccumulator` de 8 bytes e LUTs em SRAM). As fontes consultadas foram `README.md`, `docs/01_visao_geral/*`, `docs/04_otimizacao_hardware_e_firmware/03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md`, `platformio.ini`, `partitions.csv`, `sdkconfig.defaults`, `src/*`, `frontend/src/*`, `scripts/*`, `model_inference_tests/run_evaluation_espnn_sram.py`, `test/README` e `git log --oneline -30`.

## Escopo e Limites da Análise

- **O que foi lido:** Código de produção do firmware (`src/`), frontend Vue 3 (`frontend/src/`), scripts de inferência, build e HIL (`scripts/`, `model_inference_tests/`), configurações (`platformio.ini`, `partitions.csv`, `sdkconfig.defaults`, `frontend/package.json`) e documentação operacional/arquitetural (`README.md`, `docs/01_visao_geral/`, `docs/04_otimizacao_hardware_e_firmware/`).
- **O que ficou de fora:** Revisão textual dos capítulos LaTeX (`tcc/`), execução dos notebooks de treino (`notebooks/`) e execução de testes em hardware físico (análise exclusivamente estática).
- **Suposições assumidas:** O sistema opera como MVP embarcado single-device (ESP32-S3) em rede local/campo (STA ou SoftAP) com operação assistida via navegador ou scripts Python via WebSocket, não exigindo multi-tenancy em nuvem.

## Lacunas Identificadas

| # | Prioridade | Tipo | Categoria | Lacuna | Evidência | Impacto (e probabilidade) | Esforço | Confiança |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | **Alta** | Bug | Resiliência | `httpd_ws_send_frame_async` recebe ponteiros para buffers na stack (`event_json`, `json_buf`) ou estático sobrescritos (`result_json`) sem cópia | `src/web_server.cpp:303-343`, `src/main.cpp:185-234`, `src/tflite_classifier.cpp:36` | Envio assíncrono pode ler memória liberada ou sobrescrita (use-after-return / race condition), corrompendo frames WS sob rajadas | P | Confirmado |
| 2 | **Alta** | Bug | Segurança | Credenciais Wi-Fi STA e senha padrão do SoftAP hardcoded em texto claro no código-fonte | `src/wifi_setup.cpp:12-16` | Exposição de credenciais no Git e impossibilidade de trocar de rede sem recompilar o firmware | P | Confirmado |
| 3 | **Alta** | Bug | Dados | Acesso concorrente sem mutex a `/storage/inspections.csv` e `s_inspection_counter` entre Core 1 (`inference_task`) e Core 0 (`httpd`) | `src/main.cpp:72-113`, `src/web_server.cpp:140-219` | Append, leitura para exportação CSV e truncamento (`clear_history`) simultâneos podem corromper o CSV ou gerar IDs inconsistentes | P | Confirmado |
| 4 | **Alta** | Bug | Fluxo | `test_inference.py` e `hil_mavlink_simulator.py` chamam `ws.recv()` uma vez sem filtrar pacotes `telemetry` / `diagnosis` | `scripts/test_inference.py:91-96`, `scripts/hil_mavlink_simulator.py:314-320` | Como o ESP32 faz broadcast `telemetry` a 1 Hz no mesmo `/ws`, o script pode consumir telemetria e falhar na leitura do diagnóstico | P | Confirmado |
| 5 | **Alta** | Bug | Segurança | `assets_handler` concatena `req->uri` sem sanitizar `..`/query string; fallback `malloc(1024)` lê `2048` bytes e não checa `NULL` | `src/web_server.cpp:71-160` | Risco de path traversal em `/storage/www` e heap buffer overflow / null dereference caso a alocação na PSRAM falhe | P | Confirmado |
| 6 | **Alta** | Lacuna funcional | Fluxo | Coordenadas GPS (NEO-6M), status de satélites e `fps_throughput` são simulados/hardcoded no firmware e frontend | `src/main.cpp:176-230`, `frontend/src/components/TelemetryCards.vue:49-83` | Em voo real no campo, todas as inspeções são registradas com coordenadas fictícias e vazão fixa (`1.77`) | G | Confirmado |
| 7 | **Média** | Bug | Fluxo | Ordenação por `total_ms` quebrada na tabela e `anomaly_alert` incorreto quando payload usa `data.classe` | `frontend/src/components/InspectionsTable.vue:53`, `frontend/src/App.vue:165-167` | Clicar em "Latência Chip" não ordena (`a.total_ms` é `undefined`); payload legado marca folha saudável como anomalia | P | Confirmado |
| 8 | **Média** | Bug | Dados | `timestamp_epoch` no CSV e no evento WS grava uptime do boot (`esp_timer_get_time`) em vez de horário real | `src/main.cpp:105`, `frontend/src/components/InspectionsTable.vue:159-163` | Dashboard mostra datas baseadas em `1970-01-01` e o CSV exportado para QGIS perde a referência temporal real | P | Confirmado |
| 9 | **Média** | Bug | Fluxo | `ws_handler` usa `portMAX_DELAY` ao enfileirar imagem na `inference_queue` e silencia erro se `heap_caps_malloc` falhar | `src/web_server.cpp:199-232` | Trava todo o servidor HTTP/WebSocket se a fila de 5 itens lotar e deixa o cliente aguardando timeout se faltar PSRAM | P | Confirmado |
| 10 | **Média** | Lacuna funcional | Segurança | Comando `clear_history` aceito via `strstr` sem validar o `auth_token` enviado pelo frontend | `src/web_server.cpp:210-219`, `frontend/src/App.vue:212` | Qualquer cliente na mesma rede pode apagar `/storage/inspections.csv` enviando a string `clear_history` no `/ws` | P | Confirmado |
| 11 | **Média** | Lacuna funcional | Resiliência | Leitura térmica ativa, porém sem alerta nem *thermal throttling* acima de 75 °C | `src/main.cpp:64-70`, `docs/01_visao_geral/05_DIAGNOSTICO_PENDENCIAS_E_ROADMAP.md:123` | Risco de superaquecimento sem aviso ao operador em operação contínua sob sol pleno | P | Confirmado |
| 12 | **Média** | Lacuna funcional | Resiliência | Queda do Wi-Fi STA após o boot não aciona fallback para SoftAP nem atualiza `s_current_mode` | `src/wifi_setup.cpp:65-74` | Se o roteador cair em campo após a inicialização, o dispositivo tenta reconectar em loop sem expor o SoftAP | P | Confirmado |
| 13 | **Média** | Lacuna funcional | Testes | Ausência de testes unitários automatizados (C++ / Vue 3) e pipeline de CI | `test/README`, `frontend/package.json:6-10` | Regressões no pré-processamento JPEG, servidor HTTP ou parsing no dashboard dependem apenas de teste manual em bancada | M | Confirmado |
| 14 | **Baixa** | Melhoria | Operação | `telemetry_task` monta JSON e varre clientes WS a 1 Hz mesmo sem nenhum cliente conectado | `src/main.cpp:215-236`, `src/web_server.cpp:319-343` | Desperdício recorrente de ciclos no Core 0 quando o dispositivo opera de forma autônoma sem dashboard aberto | P | Confirmado |
| 15 | **Baixa** | Melhoria | Docs | Divergências pontuais de tamanhos de partição, nomes de scripts e snippets Python desatualizados na documentação | `README.md:164`, `docs/01_visao_geral/04_GUIA_DE_USO_E_OPERACAO.md:78-L117` | Pode induzir erro de entendimento sobre a tabela de partições ou falha no snippet de exemplo ao receber telemetria | P | Confirmado |

## Divergências Documentação × Código

- **Tabela de partições:** `README.md:164` descreve `(App: 3MB, LittleFS: 1.5MB)`, mas `partitions.csv:5-6` define `factory` com `4M` e `storage` com `10M`.
- **Credenciais NVS e Captive Portal:** `docs/04_otimizacao_hardware_e_firmware/03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md:36-68` especifica credenciais Wi-Fi salvas em NVS e Captive Portal DNS opcional no SoftAP; `src/wifi_setup.cpp:12-16` ainda usa `#define` estático e não implementa servidor DNS UDP na porta 53.
- **Script de compressão e snippet de uso:** A mesma especificação (`03_ESPECIFICACAO_...md:88`) cita `scripts/compress_assets.py`, enquanto o script real é `scripts/build_and_compress_frontend.py`; e o snippet Python de `docs/01_visao_geral/04_GUIA_DE_USO_E_OPERACAO.md:98` não filtra mensagens `telemetry` antes de ler `resultados`.
- **GPS NEO-6M e proteção térmica:** Documentados como parte da arquitetura e roadmap (`03_ESPECIFICACAO_...md:19`, `05_DIAGNOSTICO_...md:123`), mas ainda operam com coordenadas simuladas e leitura térmica passiva em `src/main.cpp:176-231`.

## Plano de Evolução

- **Fase 1: Correções críticas e fechamento de fluxos.**
  - **#1:** Substituir `httpd_ws_send_frame_async` por `httpd_ws_send_frame` (ou copiar o payload para buffer alocado por envio e liberá-lo no callback de conclusão do `httpd`) em `src/web_server.cpp:303-343`.
  - **#2:** Mover credenciais STA/AP para NVS (`nvs_get_str`) com fallback de configuração via `sdkconfig` (`Kconfig.projbuild`) e remover a senha real de `src/wifi_setup.cpp:12-16` (rotacionando a credencial exposta).
  - **#3:** Proteger leitura/escrita/truncamento de `/storage/inspections.csv` e `s_inspection_counter` com um `SemaphoreHandle_t` dedicado em `src/main.cpp` e `src/web_server.cpp`.
  - **#4:** Atualizar `scripts/test_inference.py:91-96` e `scripts/hil_mavlink_simulator.py:314-320` para descartar frames cujo `type` seja `"telemetry"` ou `"diagnosis"` até receber o payload de resposta (`"resultados"`), como já feito em `model_inference_tests/run_evaluation_espnn_sram.py`.
  - **#5:** Sanitizar `req->uri` (bloquear `..` e remover query string) em `assets_handler` e corrigir o tamanho do buffer de chunk (`2048` bytes com checagem de `NULL`) em `src/web_server.cpp:71-160`.
  - **#6:** Integrar driver UART (`driver/uart.h`) com parser NMEA mínimo (GGA/RMC) para o módulo GPS NEO-6M em `src/` e calcular `fps_throughput` real a partir do tempo do último ciclo.

- **Fase 2: Experiência e produtividade.**
  - **#7:** Corrigir `filteredList` em `frontend/src/components/InspectionsTable.vue:184-191` para suportar `item.timing?.total_chip_ms` na ordenação e normalizar `className` antes de calcular `anomaly_alert` em `frontend/src/App.vue:165-167`.
  - **#8:** Sincronizar relógio via SNTP quando em STA (ou receber timestamp do navegador/GPS via NMEA) antes de gravar `timestamp_epoch` em `src/main.cpp:105`.
  - **#9:** Usar timeout finito (`pdMS_TO_TICKS(100)`) em `xQueueSend(inference_queue, ...)` e responder JSON de erro HTTP/WS quando a fila estiver cheia ou `heap_caps_malloc` falhar em `src/web_server.cpp:199-232`.
  - **#10:** Validar `auth_token` (comparado contra segredo em NVS/`sdkconfig`) antes de executar `clear_history` em `src/web_server.cpp:210-219`.
  - **#11:** Adicionar flag `thermal_alert` no payload de telemetria e redução preventiva de cadência quando `chip_temp_c > 75.0f` em `src/main.cpp:215-236`.
  - **#12:** Contabilizar falhas consecutivas de reconexão em `WIFI_EVENT_STA_DISCONNECTED` para acionar `start_softap()` como fallback em `src/wifi_setup.cpp:65-74`.
  - **#13:** Criar suíte mínima de testes unitários em `test/` (PlatformIO Unity para `image_processor`) e script de build/lint do frontend + `pio run` no CI.

- **Fase 3: Maturidade e escala.**
  - **#14:** Pular a montagem de JSON em `telemetry_task` quando não houver clientes WebSocket ativos.
  - **#15:** Alinhar `README.md`, `docs/01_visao_geral/04_GUIA_DE_USO_E_OPERACAO.md` e `docs/04_otimizacao_hardware_e_firmware/03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md` à tabela de partições (`4M`/`10M`) e ao protocolo WS atual.

## Pendências de Validação

Nenhum achado desta análise foi classificado como **Hipótese** ou **Provável** — todos os 15 itens possuem evidência direta confirmada nos arquivos do repositório no commit `93903d3`.
