# Índice Central da Documentação — Projeto Sugarcane (ESP32-S3)

Este diretório concentra toda a documentação técnica, relatórios de benchmark, estudos teóricos, análises de processamento de imagem, planilhas CSV de resultados e artefatos cartográficos (SIG/HIL) do projeto **Sugarcane**, segmentados por domínio e ordenados cronológica/logicamente.

---

## Estrutura de Pastas

| Pasta | Escopo |
| :--- | :--- |
| **[`01_visao_geral/`](01_visao_geral/)** | Timeline unificada, mapa de realizações, documentação arquitetural, guia de uso e roadmap. |
| **[`02_engenharia_de_dados_e_modelos/`](02_engenharia_de_dados_e_modelos/)** | Auditoria criptográfica MD5, ablação multi-escala `v09`, fundamentação da quantização INT8, robustez estatística e estudo OOD. |
| **[`03_processamento_de_imagem/`](03_processamento_de_imagem/)** | Análise matemática e benchmarks comparativos dos 8 modos `JPEGDraw()`, aceleração IDCT a 240 MHz, BoxAvg e respectivos CSVs em `dados/`. |
| **[`04_otimizacao_hardware_e_firmware/`](04_otimizacao_hardware_e_firmware/)** | Engenharia de baixo nível no ESP32-S3: SRAM interna, Fork-Join `esp-nn`, PSRAM 80 MHz DDR, rede híbrida e dashboard Vue.js 3. |
| **[`05_testes_de_desempenho/`](05_testes_de_desempenho/)** | Cronologia e relatórios de todos os benchmarks executados no hardware físico ESP32-S3, com dados brutos em `dados/`. |
| **[`06_simulacao_hil_e_sig/`](06_simulacao_hil_e_sig/)** | Co-simulação Hardware-in-the-Loop (HIL) MAVLink e produtos cartográficos (GeoJSON, HTML interativo, PNGs KDE e CSV) em `mapas_e_dados/`. |

---

## 1. Visão Geral, Arquitetura e Planejamento (`01_visao_geral/`)

| # | Documento | Descrição |
| :-: | :--- | :--- |
| 01 | [01_TIMELINE_E_HISTORICO_DA_APLICACAO.md](01_visao_geral/01_TIMELINE_E_HISTORICO_DA_APLICACAO.md) | **Linha do tempo mestre** unificando histórico Git, trocas de CNN, algoritmos de imagem, firmware, testes e auditoria documental. |
| 02 | [02_REALIZACOES_E_MARCOS_DO_PROJETO.md](01_visao_geral/02_REALIZACOES_E_MARCOS_DO_PROJETO.md) | Mapeamento exaustivo de esforço, conquistas de engenharia e tabela evolutiva de métricas. |
| 03 | [03_DOCUMENTACAO_TECNICA_E_ARQUITETURA.md](01_visao_geral/03_DOCUMENTACAO_TECNICA_E_ARQUITETURA.md) | Especificação completa do firmware C++, FreeRTOS, hierarquia SRAM/PSRAM, WebSocket e LittleFS. |
| 04 | [04_GUIA_DE_USO_E_OPERACAO.md](01_visao_geral/04_GUIA_DE_USO_E_OPERACAO.md) | Manual prático de build, `uploadfs`, modos Wi-Fi (STA/SoftAP/mDNS), dashboard Vue 3 e WebSocket. |
| 05 | [05_DIAGNOSTICO_PENDENCIAS_E_ROADMAP.md](01_visao_geral/05_DIAGNOSTICO_PENDENCIAS_E_ROADMAP.md) | Diagnóstico de pendências (P1–P6), oportunidades (O1–O5) e tarefas futuras pós-TCC (TF1). |

---

## 2. Engenharia de Dados, CNNs e Fundamentação Teórica (`02_engenharia_de_dados_e_modelos/`)

| # | Documento | Descrição |
| :-: | :--- | :--- |
| 01 | [01_AUDITORIA_MD5_DATASET_E_TREINAMENTO_V08.md](02_engenharia_de_dados_e_modelos/01_AUDITORIA_MD5_DATASET_E_TREINAMENTO_V08.md) | Auditoria criptográfica de 6.748 imagens (747 duplicatas + 614 colisões cruzadas) e arquitetura do treino `v08`. |
| 02 | [02_ABLACAO_MULTIESCALA_E_GRAFICOS_V09.md](02_engenharia_de_dados_e_modelos/02_ABLACAO_MULTIESCALA_E_GRAFICOS_V09.md) | Guia dos 6 painéis analíticos do estudo de ablação MobileNetV2 ($\alpha \in \{0.35, 0.50, 0.75\}$) no `v09`. |
| 03 | [03_FUNDAMENTACAO_QUANTIZACAO_INT8_E_QAT.md](02_engenharia_de_dados_e_modelos/03_FUNDAMENTACAO_QUANTIZACAO_INT8_E_QAT.md) | Base científica (12 referências): *Flat Minima*, MDL, *Information Bottleneck*, QAT/STE e regularização implícita. |
| 04 | [04_ROBUSTEZ_ESTATISTICA_E_SEMENTES_ALEATORIAS.md](02_engenharia_de_dados_e_modelos/04_ROBUSTEZ_ESTATISTICA_E_SEMENTES_ALEATORIAS.md) | Análise de variância estocástica, impacto de sementes aleatórias, $\text{IC}_{95\%}$ e protocolo *Multi-Seed*. |
| 05 | [05_ESTUDO_MUNDO_FECHADO_E_DETECCAO_OOD.md](02_engenharia_de_dados_e_modelos/05_ESTUDO_MUNDO_FECHADO_E_DETECCAO_OOD.md) | Estudo de vulnerabilidade OOD (não-cana) e estratégias de mitigação (pré-filtro ExG, 12ª classe e thresholding). |

---

## 3. Processamento de Imagem e Avaliação de Algoritmos (`03_processamento_de_imagem/`)

| # | Documento / Dados | Descrição |
| :-: | :--- | :--- |
| 01 | [01_ANALISE_MATEMATICA_JPEGDRAW_COR_E_AMOSTRAGEM.md](03_processamento_de_imagem/01_ANALISE_MATEMATICA_JPEGDRAW_COR_E_AMOSTRAGEM.md) | Prova matemática do viés DC (`-2,90 LSB`), violação de Nyquist e comparação das 8 variantes de `JPEGDraw()`. |
| 02 | [02_BENCHMARK_8_MODOS_JPEGDRAW_MODELO_V07.md](03_processamento_de_imagem/02_BENCHMARK_8_MODOS_JPEGDRAW_MODELO_V07.md) | Avaliação comparativa dos 8 modos `JPEGDraw()` sobre o modelo `v07` (4.400 inferências). |
| 03 | [03_BENCHMARK_8_MODOS_JPEGDRAW_MODELO_V08.md](03_processamento_de_imagem/03_BENCHMARK_8_MODOS_JPEGDRAW_MODELO_V08.md) | Avaliação cruzada dos 8 modos sobre o modelo `v08` (13.104 inferências; vitória do Modo 7 com `91,09%` limpo / `89,41%` `val/`). |
| 04 | [04_ACELERACAO_IDCT_240MHZ_E_OTIMIZACAO_BOXAVG.md](03_processamento_de_imagem/04_ACELERACAO_IDCT_240MHZ_E_OTIMIZACAO_BOXAVG.md) | Aceleração via IDCT `1/4` e `1/2`, clock a 240 MHz e otimização `iWidthUsed` / BoxAvg. |
| CSV | [`dados/01_jpegdraw_8modos_v07_550brutas.csv`](03_processamento_de_imagem/dados/01_jpegdraw_8modos_v07_550brutas.csv) | Dados brutos das 4.400 inferências no modelo `v07`. |
| CSV | [`dados/02_jpegdraw_8modos_v08_550brutas.csv`](03_processamento_de_imagem/dados/02_jpegdraw_8modos_v08_550brutas.csv) | Dados brutos das 4.400 inferências no modelo `v08` (lote bruto). |
| CSV | [`dados/03_jpegdraw_8modos_v08_550limpas.csv`](03_processamento_de_imagem/dados/03_jpegdraw_8modos_v08_550limpas.csv) | Dados brutos das 4.400 inferências no modelo `v08` (lote limpo MD5). |

---

## 4. Otimização de Hardware, Firmware e Dashboard Web (`04_otimizacao_hardware_e_firmware/`)

| # | Documento | Descrição |
| :-: | :--- | :--- |
| 01 | [01_OTIMIZACAO_SRAM_E_FORK_JOIN_DUAL_CORE_ESP_NN.md](04_otimizacao_hardware_e_firmware/01_OTIMIZACAO_SRAM_E_FORK_JOIN_DUAL_CORE_ESP_NN.md) | Scratch buffers em SRAM interna (`48 KB` + `25 KB`), patch Stem $3\times3$, `SKIP_NUDGE` e paralelismo Fork-Join `esp-nn`. |
| 02 | [02_FASE1_PSRAM_80MHZ_BOXACC8B_REDE_E_V08.md](04_otimizacao_hardware_e_firmware/02_FASE1_PSRAM_80MHZ_BOXACC8B_REDE_E_V08.md) | Relatório da Fase 1: `uploadfs` do `v08`, Octal PSRAM @ 80 MHz DDR, `-O2`, `BoxAccumulator` 8 B e `WIFI_PS_NONE`. |
| 03 | [03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md](04_otimizacao_hardware_e_firmware/03_ESPECIFICACAO_DASHBOARD_VUE3_TELEMETRIA_E_GPS.md) | Especificação da SPA Vue.js 3 offline, rede híbrida STA/SoftAP, mDNS, telemetria 1 Hz, CSV e driver GPS NEO-6M. |
| 04 | [04_FASE2_HOMOLOGACAO_DASHBOARD_VUE3_E_TELEMETRIA.md](04_otimizacao_hardware_e_firmware/04_FASE2_HOMOLOGACAO_DASHBOARD_VUE3_E_TELEMETRIA.md) | Homologação em silício da Fase 2: assets Gzip (`89,1 KB`), sensor térmico, `/storage/inspections.csv` e mutex `s_ws_mutex`. |

---

## 5. Testes de Desempenho em Hardware Físico (`05_testes_de_desempenho/`)

| # | Relatório | Planilha CSV Correspondente | Escopo |
| :-: | :--- | :--- | :--- |
| 00 | [00_INDICE_E_CRONOLOGIA_DE_BENCHMARKS.md](05_testes_de_desempenho/00_INDICE_E_CRONOLOGIA_DE_BENCHMARKS.md) | — | Mapa cronológico consolidado de todos os ensaios de inferência. |
| 01 | [01_BENCHMARK_BASELINE_SINGLE_CORE_V07_550.md](05_testes_de_desempenho/01_BENCHMARK_BASELINE_SINGLE_CORE_V07_550.md) | [`dados/01_baseline_single_core_v07_550.csv`](05_testes_de_desempenho/dados/01_baseline_single_core_v07_550.csv) | Baseline Single-Core Sequencial (`v07`, 550 brutas). |
| 02 | [02_BENCHMARK_PIPELINE_DUAL_CORE_V07_550.md](05_testes_de_desempenho/02_BENCHMARK_PIPELINE_DUAL_CORE_V07_550.md) | [`dados/02_pipeline_dual_core_v07_550.csv`](05_testes_de_desempenho/dados/02_pipeline_dual_core_v07_550.csv) | Pipeline Assíncrono Dual-Core (`v07`, 550 brutas). |
| 03 | [03_BENCHMARK_SRAM_FORK_JOIN_240MHZ_BRUTO_550.md](05_testes_de_desempenho/03_BENCHMARK_SRAM_FORK_JOIN_240MHZ_BRUTO_550.md) | [`dados/03_sram_fork_join_240mhz_bruto_550.csv`](05_testes_de_desempenho/dados/03_sram_fork_join_240mhz_bruto_550.csv) | SRAM + Fork-Join + 240 MHz + IDCT (550 brutas). |
| 04 | [04_BENCHMARK_PSRAM80MHZ_V08_LIMPO_550.md](05_testes_de_desempenho/04_BENCHMARK_PSRAM80MHZ_V08_LIMPO_550.md) | [`dados/04_psram80mhz_v08_limpo_550.csv`](05_testes_de_desempenho/dados/04_psram80mhz_v08_limpo_550.csv) | `v08` + PSRAM 80 MHz + `-O2` + BoxAcc 8B (550 limpas). |
| 05 | [05_BENCHMARK_EXAUSTIVO_DATASET_COMPLETO_9269.md](05_testes_de_desempenho/05_BENCHMARK_EXAUSTIVO_DATASET_COMPLETO_9269.md) | [`dados/05_dataset_completo_9269.csv`](05_testes_de_desempenho/dados/05_dataset_completo_9269.csv) | Stress test de 9.269 imagens (6.748 primárias + 2.521 Archive / *Domain Shift*). |
| 06 | [06_BENCHMARK_HOMOLOGACAO_FASE2_TELEMETRIA_132.md](05_testes_de_desempenho/06_BENCHMARK_HOMOLOGACAO_FASE2_TELEMETRIA_132.md) | [`dados/06_homologacao_fase2_telemetria_132.csv`](05_testes_de_desempenho/dados/06_homologacao_fase2_telemetria_132.csv) | Homologação Fase 2 com SPA Vue 3 e telemetria 1 Hz concorrente (132 amostras). |

---

## 6. Co-Simulação HIL MAVLink e Mapas SIG (`06_simulacao_hil_e_sig/`)

| # | Documento / Artefato | Descrição |
| :-: | :--- | :--- |
| 01 | [01_CO_SIMULACAO_HIL_MAVLINK_E_MAPAS_DE_CALOR.md](06_simulacao_hil_e_sig/01_CO_SIMULACAO_HIL_MAVLINK_E_MAPAS_DE_CALOR.md) | Arquitetura *Pause-and-Classify* MAVLink v2, resultados da missão de 55 waypoints e guia QGIS. |
| SIG | [`mapas_e_dados/missao_hil_georreferenciada.csv`](06_simulacao_hil_e_sig/mapas_e_dados/missao_hil_georreferenciada.csv) | Série temporal georreferenciada dos 55 waypoints. |
| SIG | [`mapas_e_dados/infestacao_talhao.geojson`](06_simulacao_hil_e_sig/mapas_e_dados/infestacao_talhao.geojson) | Camada vetorial GeoJSON (RFC 7946 / EPSG:4326) para QGIS/ArcGIS. |
| SIG | [`mapas_e_dados/mapa_calor_interativo.html`](06_simulacao_hil_e_sig/mapas_e_dados/mapa_calor_interativo.html) | Dashboard Web GIS interativo (Leaflet / Folium). |
| IMG | [`mapas_e_dados/`](06_simulacao_hil_e_sig/mapas_e_dados/) | Painéis KDE 2D estáticos (`mapa_infestacao_talhao_2d.png`, `mapa_foco_carvao_smut.png`, `mapa_foco_ferrugem_brownrust.png`). |
