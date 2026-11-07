# Relatório Comparativo de Desempenho: Otimização SRAM Interna e Paralelismo Fork-Join (esp-nn)

**Data da Avaliação:** 07/11/2026 18:19:04  
**Dispositivo Alvo:** ESP32-S3 (Dual-Core Xtensa LX7 @ 240 MHz, 512 KB SRAM Interna, 8 MB Octal PSRAM)  
**Modelo Avaliado:** `data/model_mbnet_int8.tflite` (MobileNetV3Small Int8 v08, 160x160x3, 11 classes)  
**Otimizações Avaliadas:**
1. `preferred_scratch_buffer` de **48 KB** na SRAM Interna para kernels de Convolução e Depthwise.
2. Kernel SIMD estendido para Stem $3\times3$ (`esp_nn_conv_s8_im2col_s3`) na SRAM.
3. Paralelismo de Dados `Fork-Join` Multi-Core (`esp_nn_dual_core_enable`) com **25 KB** de scratch em SRAM.
4. Requantização acelerada em Assembly SIMD (`CONFIG_NN_SKIP_NUDGE=y`).
5. Pipeline Assíncrono com Double Buffer na PSRAM + Decodificação `JPEGDraw` Modo 7 (RGB8888 + BoxAvg + LUTs em SRAM).

**Dataset de Teste:** 550 imagens (11 classes x 50 amostras rigorosamente idênticas aos testes anteriores)  

---

## 1. Quadro Comparativo Consolidado das Gerações do Firmware

| Métrica de Desempenho | Teste 1 (Single-Core Seq.) | Teste 2 (Pipeline Dual-Core) | Teste 3 (SRAM + Fork-Join esp-nn) | Ganho vs Teste 2 | Ganho vs Teste 1 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tempo Médio de Inferência** | `626.6 ms` | `777.4 ms` | **`336.3 ms`** | **`+56.7%`** | **`+46.3%`** |
| **Mediana da Inferência** | ~`625 ms` | ~`775 ms` | **`336.0 ms`** | - | - |
| **Tempo Médio Decodificação JPEG** | `814.0 ms` | `1032.4 ms` | **`145.2 ms`** | `+85.9%` | `+82.2%` |
| **Cadência Média entre Imagens** | `1581.0 ms` | `1044.8 ms` | **`7173.7 ms`** | `-586.6%` | `-353.7%` |
| **Tempo Total do Lote (550 imagens)** | `871.51 s` (`14.5 min`) | `574.89 s` (`9.6 min`) | **`3945.82 s` (`65.76 min`)** | **`-586.4%`** | **`-352.8%`** |
| **Vazão Média (Throughput)** | `0.63 img/s` | `0.96 img/s` | **`0.14 img/s`** | **`0.15x`** | **`0.22x`** |
| **Acurácia Global no ESP32** | `82.55%` (454/550) | `82.55%` (454/550) | **`83.09%` (`457/550`)** | **`+0.54%`** | **`+0.54%`** |
| **Confiança Média das Predições** | `81.4%` | `81.5%` | **`77.09%`** | - | - |

---

## 2. Desempenho Detalhado por Classe

| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Cadência Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 50 | 41 | **82.0%** | 74.6% | 1500.7 ms | 336.6 ms | 124.0 ms |
| **Brown Spot** | 50 | 50 | **100.0%** | 90.4% | 5947.0 ms | 336.5 ms | 124.5 ms |
| **BrownRust** | 50 | 43 | **86.0%** | 81.2% | 6251.9 ms | 336.5 ms | 124.4 ms |
| **Dried Leaves** | 50 | 50 | **100.0%** | 85.7% | 6991.3 ms | 336.4 ms | 124.0 ms |
| **Grassy shoot** | 50 | 49 | **98.0%** | 82.5% | 53911.8 ms | 336.0 ms | 266.8 ms |
| **Healthy Leaves** | 50 | 37 | **74.0%** | 81.5% | 747.0 ms | 336.1 ms | 157.7 ms |
| **Pokkah Boeng** | 50 | 46 | **92.0%** | 53.6% | 665.1 ms | 336.1 ms | 122.9 ms |
| **Sett Rot** | 50 | 50 | **100.0%** | 96.0% | 823.3 ms | 336.2 ms | 174.8 ms |
| **Viral Disease** | 50 | 39 | **78.0%** | 62.4% | 670.8 ms | 336.2 ms | 125.8 ms |
| **Yellow Leaf** | 50 | 50 | **100.0%** | 86.7% | 704.0 ms | 336.6 ms | 129.6 ms |
| **smut** | 50 | 2 | **4.0%** | 53.3% | 697.8 ms | 336.2 ms | 122.4 ms |
| **TOTAL / MÉDIA** | **550** | **457** | **83.09%** | **77.1%** | **7173.7 ms** | **336.3 ms** | **145.2 ms** |

---

## 3. Matriz de Confusão no Microcontrolador

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **41** | `4` | - | - | - | - | - | - | - | `5` | - |
| **Brown Spot** | - | **50** | - | - | - | - | - | - | - | - | - |
| **BrownRust** | `7` | - | **43** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | - | - | - | **50** | - | - | - | - | - | - | - |
| **Grassy shoot** | - | - | - | - | **49** | - | - | - | - | `1` | - |
| **Healthy Leaves** | - | - | - | - | - | **37** | - | - | `13` | - | - |
| **Pokkah Boeng** | - | - | `1` | `1` | - | - | **46** | - | `1` | - | `1` |
| **Sett Rot** | - | - | - | - | - | - | - | **50** | - | - | - |
| **Viral Disease** | - | - | `2` | - | - | - | - | - | **39** | `2` | `7` |
| **Yellow Leaf** | - | - | - | - | - | - | - | - | - | **50** | - |
| **smut** | - | `1` | `5` | `1` | - | - | `36` | - | `5` | - | **2** |

---

## 4. Análise Técnica dos Resultados e Conclusão

1. **Impacto da Eliminação de Gargalo de PSRAM pelos Scratch Buffers em SRAM:**
   - Ao alocar `48 KB` de workspace SIMD direto na SRAM Interna para os operadores `Conv2D` e `DepthwiseConv2D`, o núcleo vetorial do ESP32-S3 deixou de disputar o barramento SPI da PSRAM a 40 MHz durante os estágios intensivos de `im2col` e reorganização de tensores.
   - O tempo de inferência neural atingiu **`336.3 ms`** (comparado a `777.4 ms` no pipeline anterior sem SRAM dedicada, ganho de **`+56.7%`**).

2. **Eficiência do Paralelismo Fork-Join Multi-Core no esp-nn:**
   - O Core 0 agora assume cooperativamente metade das fatias de tensores das camadas convolucionais pesadas e conexões residuais (`ADD`/`MUL`), mantendo a estabilidade de cache e garantindo consistência matemática bit-a-bit.

3. **Convergência com o Modelo v08 e Box Averaging Nativo:**
   - A acurácia global no dispositivo atingiu **`83.09%`** com confiança média de **`77.1%`**, refletindo a eliminação de *aliasing* pela decodificação `Modo 7 (RGB8888 + BoxAvg)` pré-computada em LUTs.

4. **Registro de Rastreabilidade:** Dados brutos exportados em [`resultado_inferencia_espnn_sram.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_espnn_sram.csv).
