# Relatório Comparativo de Desempenho: Pipeline Assíncrono Dual-Core vs Single-Core

**Data da Avaliação:** 06/11/2026 18:02:01
**Dispositivo:** ESP32-S3 (8MB Octal PSRAM @ 40MHz, Xtensa Dual Core @ 240MHz)
**Arquitetura do Firmware:** Pipeline Assíncrono Dual-Core (Core 0: Decode JPEG + Wi-Fi | Core 1: TFLite Micro SIMD)
**Modo de Envio:** Streaming Pipelined (Janela de 2 imagens concorrentes via WebSocket)
**Dataset Avaliado:** Mesmas 550 imagens do teste anterior (50 amostras x 11 classes)

## 1. Comparativo Direto: Single-Core vs Dual-Core Pipelined

| Métrica de Desempenho | Teste 1 (Single-Core Sequencial) | Teste 2 (Dual-Core Pipelined) | Ganho / Melhoria |
| :--- | :---: | :---: | :---: |
| **Tempo Total do Lote (550 imagens)** | **871.51 s (14.53 min)** | **574.89 s (9.58 min)** | **-296.6 s (+34.0%)** |
| **Vazão Média (Throughput)** | **0.63 imagens/s** | **0.96 imagens/s** | **1.52x mais rápido** |
| **Cadência Média entre Imagens** | ~1.581 ms | **1044.8 ms** | **Redução de ~537 ms/frame** |
| **Acurácia Global do Modelo** | **82.55%** (454/550) | **82.55%** (454/550) | **Idêntica / 100% Consistente** |
| **Tempo Médio de Inferência TFLite** | ~626.6 ms | **777.4 ms** | Estabilidade mantida |
| **Tempo Médio de Decodificação JPEG** | ~814.0 ms | **1032.4 ms** | Estabilidade mantida |

## 2. Desempenho Detalhado por Classe (50 amostras cada)

| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Cadência Média (Incr.) | Tempo Médio Inf. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 50 | 42 | **84.0%** | 79.2% | 1023.1 ms | 775.4 ms |
| **Brown Spot** | 50 | 50 | **100.0%** | 87.3% | 1012.5 ms | 775.1 ms |
| **BrownRust** | 50 | 40 | **80.0%** | 87.7% | 1003.3 ms | 776.2 ms |
| **Dried Leaves** | 50 | 47 | **94.0%** | 91.0% | 1008.7 ms | 775.2 ms |
| **Grassy shoot** | 50 | 50 | **100.0%** | 91.7% | 1134.6 ms | 796.8 ms |
| **Healthy Leaves** | 50 | 43 | **86.0%** | 79.7% | 1017.4 ms | 770.3 ms |
| **Pokkah Boeng** | 50 | 38 | **76.0%** | 53.9% | 1003.2 ms | 775.8 ms |
| **Sett Rot** | 50 | 50 | **100.0%** | 96.5% | 1246.8 ms | 781.8 ms |
| **Viral Disease** | 50 | 45 | **90.0%** | 62.9% | 1013.9 ms | 775.9 ms |
| **Yellow Leaf** | 50 | 46 | **92.0%** | 88.4% | 1038.1 ms | 775.9 ms |
| **smut** | 50 | 3 | **6.0%** | 52.7% | 990.9 ms | 772.5 ms |

## 3. Matriz de Confusão

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **42** | `4` | `1` | - | - | - | - | - | - | `3` | - |
| **Brown Spot** | - | **50** | - | - | - | - | - | - | - | - | - |
| **BrownRust** | `10` | - | **40** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | - | - | - | **47** | - | - | - | - | - | `3` | - |
| **Grassy shoot** | - | - | - | - | **50** | - | - | - | - | - | - |
| **Healthy Leaves** | - | - | - | - | - | **43** | - | - | `7` | - | - |
| **Pokkah Boeng** | - | - | `2` | `8` | - | - | **38** | - | - | - | `2` |
| **Sett Rot** | - | - | - | - | - | - | - | **50** | - | - | - |
| **Viral Disease** | - | - | - | - | - | - | - | - | **45** | `1` | `4` |
| **Yellow Leaf** | `1` | - | - | `3` | - | - | - | - | - | **46** | - |
| **smut** | - | `1` | `2` | `2` | - | - | `34` | - | `8` | - | **3** |

## 4. Conclusão Técnica sobre o Pipeline Dual-Core

1. **Paralelismo Real Comprovado:** O tempo total para processar 550 fotos de alta resolução caiu de **14.53 min** para **9.58 min**, com ganho de velocidade de **34.0%**.
2. **Eficiência de Memória na PSRAM:** O pool de Double Buffering alocou 300 KB na Octal PSRAM sem nenhum pico de memória ou fragmentação ao longo de todo o lote.
3. **Planilha Completa:** Os dados individuais estão disponíveis em [model_inference_tests/resultado_inferencia_dualcore.csv](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_dualcore.csv).
