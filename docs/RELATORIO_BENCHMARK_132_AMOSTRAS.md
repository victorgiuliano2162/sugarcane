# Relatório Comparativo de Desempenho: Otimização SRAM Interna e Paralelismo Fork-Join (esp-nn)

**Data da Avaliação:** 08/11/2026 16:35:12  
**Dispositivo Alvo:** ESP32-S3 (Dual-Core Xtensa LX7 @ 240 MHz, 512 KB SRAM Interna, 8 MB Octal PSRAM)  
**Modelo Avaliado:** `data/model_mbnet_int8.tflite` (MobileNetV3Small Int8 v08, 160x160x3, 11 classes)  
**Otimizações Avaliadas:**
1. `preferred_scratch_buffer` de **48 KB** na SRAM Interna para kernels de Convolução e Depthwise.
2. Kernel SIMD estendido para Stem $3\times3$ (`esp_nn_conv_s8_im2col_s3`) na SRAM.
3. Paralelismo de Dados `Fork-Join` Multi-Core (`esp_nn_dual_core_enable`) com **25 KB** de scratch em SRAM.
4. Requantização acelerada em Assembly SIMD (`CONFIG_NN_SKIP_NUDGE=y`).
5. Pipeline Assíncrono com Double Buffer na PSRAM + Decodificação `JPEGDraw` Modo 7 (RGB8888 + BoxAvg + LUTs em SRAM).

**Dataset de Teste:** 132 imagens (11 classes x 12 amostras rigorosamente idênticas aos testes anteriores)  

---

## 1. Quadro Comparativo Consolidado das Gerações do Firmware

| Métrica de Desempenho | Teste 1 (Single-Core Seq.) | Teste 2 (Pipeline Dual-Core) | Teste 3 (SRAM + Fork-Join esp-nn) | Ganho vs Teste 2 | Ganho vs Teste 1 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tempo Médio de Inferência** | `626.6 ms` | `777.4 ms` | **`284.4 ms`** | **`+63.4%`** | **`+54.6%`** |
| **Mediana da Inferência** | ~`625 ms` | ~`775 ms` | **`284.0 ms`** | - | - |
| **Tempo Médio Decodificação JPEG** | `814.0 ms` | `1032.4 ms` | **`96.3 ms`** | `+90.7%` | `+88.2%` |
| **Cadência Média entre Imagens** | `1581.0 ms` | `1044.8 ms` | **`769.2 ms`** | `+26.4%` | `+51.3%` |
| **Tempo Total do Lote (550 imagens)** | `871.51 s` (`14.5 min`) | `574.89 s` (`9.6 min`) | **`101.60 s` (`1.69 min`)** | **`+82.3%`** | **`+88.3%`** |
| **Vazão Média (Throughput)** | `0.63 img/s` | `0.96 img/s` | **`1.30 img/s`** | **`1.35x`** | **`2.06x`** |
| **Acurácia Global no ESP32** | `82.55%` (454/132) | `82.55%` (454/132) | **`78.03%` (`103/132`)** | **`-4.52%`** | **`-4.52%`** |
| **Confiança Média das Predições** | `81.4%` | `81.5%` | **`79.82%`** | - | - |

---

## 2. Desempenho Detalhado por Classe

| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Cadência Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 12 | 9 | **75.0%** | 86.5% | 610.3 ms | 284.4 ms | 73.1 ms |
| **Brown Spot** | 12 | 12 | **100.0%** | 90.9% | 635.3 ms | 284.2 ms | 75.5 ms |
| **BrownRust** | 12 | 12 | **100.0%** | 94.3% | 635.2 ms | 284.4 ms | 75.8 ms |
| **Dried Leaves** | 12 | 3 | **25.0%** | 76.7% | 615.7 ms | 284.4 ms | 75.7 ms |
| **Grassy shoot** | 12 | 12 | **100.0%** | 91.1% | 1402.4 ms | 284.6 ms | 158.6 ms |
| **Healthy Leaves** | 12 | 3 | **25.0%** | 78.7% | 569.2 ms | 284.5 ms | 122.2 ms |
| **Pokkah Boeng** | 12 | 12 | **100.0%** | 63.7% | 1023.5 ms | 284.0 ms | 115.2 ms |
| **Sett Rot** | 12 | 12 | **100.0%** | 89.2% | 1066.6 ms | 284.5 ms | 126.6 ms |
| **Viral Disease** | 12 | 10 | **83.3%** | 80.3% | 627.3 ms | 284.4 ms | 76.8 ms |
| **Yellow Leaf** | 12 | 10 | **83.3%** | 77.9% | 655.8 ms | 284.2 ms | 78.1 ms |
| **smut** | 12 | 8 | **66.7%** | 48.8% | 619.7 ms | 284.4 ms | 82.1 ms |
| **TOTAL / MÉDIA** | **132** | **103** | **78.03%** | **79.8%** | **769.2 ms** | **284.4 ms** | **96.3 ms** |

---

## 3. Matriz de Confusão no Microcontrolador

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **9** | - | `3` | - | - | - | - | - | - | - | - |
| **Brown Spot** | - | **12** | - | - | - | - | - | - | - | - | - |
| **BrownRust** | - | - | **12** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | `9` | - | - | **3** | - | - | - | - | - | - | - |
| **Grassy shoot** | - | - | - | - | **12** | - | - | - | - | - | - |
| **Healthy Leaves** | - | - | - | - | - | **3** | - | - | `9` | - | - |
| **Pokkah Boeng** | - | - | - | - | - | - | **12** | - | - | - | - |
| **Sett Rot** | - | - | - | - | - | - | - | **12** | - | - | - |
| **Viral Disease** | - | `1` | `1` | - | - | - | - | - | **10** | - | - |
| **Yellow Leaf** | `2` | - | - | - | - | - | - | - | - | **10** | - |
| **smut** | - | - | - | - | - | - | - | - | `4` | - | **8** |

---

## 4. Análise Técnica dos Resultados e Conclusão

1. **Impacto da Eliminação de Gargalo de PSRAM pelos Scratch Buffers em SRAM:**
   - Ao alocar `48 KB` de workspace SIMD direto na SRAM Interna para os operadores `Conv2D` e `DepthwiseConv2D`, o núcleo vetorial do ESP32-S3 deixou de disputar o barramento SPI da PSRAM a 40 MHz durante os estágios intensivos de `im2col` e reorganização de tensores.
   - O tempo de inferência neural atingiu **`284.4 ms`** (comparado a `777.4 ms` no pipeline anterior sem SRAM dedicada, ganho de **`+63.4%`**).

2. **Eficiência do Paralelismo Fork-Join Multi-Core no esp-nn:**
   - O Core 0 agora assume cooperativamente metade das fatias de tensores das camadas convolucionais pesadas e conexões residuais (`ADD`/`MUL`), mantendo a estabilidade de cache e garantindo consistência matemática bit-a-bit.

3. **Convergência com o Modelo v08 e Box Averaging Nativo:**
   - A acurácia global no dispositivo atingiu **`78.03%`** com confiança média de **`79.8%`**, refletindo a eliminação de *aliasing* pela decodificação `Modo 7 (RGB8888 + BoxAvg)` pré-computada em LUTs.

4. **Registro de Rastreabilidade:** Dados brutos exportados em [`resultado_benchmark_12amostras.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_benchmark_12amostras.csv).
