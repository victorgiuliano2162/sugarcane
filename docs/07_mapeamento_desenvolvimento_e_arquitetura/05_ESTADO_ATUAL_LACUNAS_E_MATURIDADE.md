# Estado Atual, Lacunas e Maturidade — Projeto Sugarcane

Este documento avalia de forma objetiva a maturidade atual do projeto `sugarcane` no commit `49d53a8` (`23/11/2026`), listando o que já foi validado em silício, as pendências operacionais imediatas e as inconsistências técnicas identificadas na auditoria do código.

---

## 1. Matriz de Maturidade por Subsistema

| Subsistema | Status | Evidência / Validação |
| :--- | :---: | :--- |
| **Motor Neural (`tflite_classifier.cpp`)** | **Validado em Silício** | `283,4 ms` no ESP32-S3, `9.269` imagens sem falhas (`05_BENCHMARK_EXAUSTIVO...`) |
| **Processamento JPEG (`image_processor.cpp`)** | **Validado em Silício** | Modo 7 (`92,6–102,7 ms`), `PSNR = ∞ dB`, `BoxAccumulator` 8 B (`200 KB`) |
| **Rede, Segurança & Persistência** | **Implementado / Compila em CI** | `WsWorkItem`, `s_csv_mutex`, NVS/Kconfig, `auth_token`, SNTP, fallback SoftAP (`23/11`) |
| **GPS NEO-6M (`gps_neo6m.cpp`)** | **Implementado / Compila em CI** | Driver UART2 (`9600 bps`) + parser NMEA `$GxGGA` (`4ee611d`) |
| **Frontend SPA (`frontend/` → `data/www/`)** | **Validado (Fase 2) + Atualizado** | `89,1 KB` Gzip, `npm run build` no CI, correções de `23/11` aplicadas |
| **Ciência de Dados (`notebooks/v07..v10`)** | **v08 em Produção; v09/v10 Pesquisa** | `v08` embarcado em `data/model_mbnet_int8.tflite`; `v10` ainda em notebook |
| **Co-Simulação HIL & SIG (`scripts/`)** | **Validado em Silício (55 WPs)** | `100%` entrega, GeoJSON/HTML/PNGs gerados; filtro WS atualizado em `bb066b8` |
| **Testes & CI (`.github/workflows/ci.yml`)** | **Ativo (Básico)** | `npm run build` + `pio run`; suíte Unity em `test/test_image_math/` |
| **Monografia & Docs (`tcc/`, `docs/`)** | **Consolidado** | PDFs compilados (`tcc/`) + 7 eixos documentais em `docs/` |

---

## 2. Pendências Operacionais Imediatas (Pós-Endurecimento `23/11`)

Conforme registrado em [implementation-plan.md](../implementation-plan.md):
1. **Rotação de Credenciais Wi-Fi:** Alterar na rede local a senha Wi-Fi exposta em commits anteriores a `4ee611d` (ação operacional externa).
2. **Bateria de Validação em Silício Físico Pós-`23/11`:** Regravar `pio run -t upload && pio run -t uploadfs` e validar em bancada: rajada WebSocket com dashboard aberto, `test_inference.py`, `hil_mavlink_simulator.py`, bloqueio de *path traversal* em `/assets/`, recepção NMEA real no NEO-6M e integridade de `/api/export-csv`.

---

## 3. Inconsistências e Pontos de Atenção Detectados no Código

1. **Descompasso entre Modelo em Produção (`v08`) e Notebooks (`v09`/`v10`):**
   * [data/model_mbnet_int8.tflite](../../data/model_mbnet_int8.tflite) ainda é o binário `v08` (`160×160`). Caso se adote o `v10` (`192×192` ou `224×224`), será necessário parametrizar `TARGET_W`/`TARGET_H` em [src/image_processor.cpp](../../src/image_processor.cpp), `TENSOR_SIZE` em [src/main.cpp](../../src/main.cpp) e `kTensorArenaSize` em [src/tflite_classifier.cpp](../../src/tflite_classifier.cpp).
2. **Fallback de Coordenadas no Frontend ([frontend/src/App.vue](../../frontend/src/App.vue)):**
   * Nas funções `loadHistoryFromESP32` (linhas 94–96) e `ws.onmessage` (linhas 169–171), o uso do operador `||` converte `0.0` (enviado pelo firmware quando o GPS NEO-6M está sem fix) para as coordenadas hardcoded `-8.05389, -34.88105, 24.5`, mascarando visualmente a ausência de fix no mapa/tabela.
3. **Duplicação de Assets em `data/www/`:**
   * [scripts/build_and_compress_frontend.py](../../scripts/build_and_compress_frontend.py) grava tanto os arquivos `.gz` quanto os originais descompactados em `data/www/` (impacto baixo nos 10 MB de LittleFS, mas redundante).
4. **Cobertura de Testes Unitários e CI:**
   * [test/test_image_math/test_main.cpp](../../test/test_image_math/test_main.cpp) reimplementa `quantize_box_channel` localmente em vez de testar funções exportadas de [src/image_processor.cpp](../../src/image_processor.cpp).
   * [.github/workflows/ci.yml](../../.github/workflows/ci.yml) valida `npm run build` e `pio run`, mas ainda não executa `pio test` nem checagem sintática (`py_compile`) nos scripts Python.
5. **Patch Manual em `managed_components/`:**
   * A customização do Stem $3\times 3$ em [esp_nn_conv_esp32s3.c](../../managed_components/espressif__esp-nn/src/convolution/esp_nn_conv_esp32s3.c) reside dentro de `managed_components/` e pode ser sobrescrita se o componente for baixado novamente do zero sem reaplicação do patch.
6. **Risco Agronômico em Campo (*Domain Shift* e OOD):**
   * O stress test de 9.269 imagens registrou `3,13%` de acurácia no dataset externo *Archive* (*Domain Shift*), e o pré-filtro cromático `ExG` (`2G - R - B`) / 12ª classe (`Background_NonCane` / `RedRot`) ainda não foi integrado ao firmware de produção.

---

## 4. Roadmap Consolidado Recomendado

* **Curto Prazo:** Executar a bateria de validação em silício físico pós-`23/11`, rotacionar credenciais Wi-Fi antigas e ajustar o operador `??` (em vez de `||`) em [frontend/src/App.vue](../../frontend/src/App.vue) para não mascarar `lat=0.0` sem fix GPS.
* **Médio Prazo:** Integrar o pré-filtro `ExG` (`~1,8 ms`) em `image_processor.cpp`, adicionar `pio test` ao `ci.yml` e automatizar a aplicação do patch `esp-nn` no build.
* **Longo Prazo:** Treinar e embarcar modelo com 12ª classe (`Background_NonCane` / `RedRot`) e adaptação de domínio (*DANN*) conforme tarefa futura `TF1`.
