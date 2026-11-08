# Relatório Comparativo de Desempenho: Otimização SRAM Interna e Paralelismo Fork-Join (esp-nn)

**Data da Avaliação:** 08/11/2026 06:03:57  
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
| **Tempo Médio de Inferência** | `626.6 ms` | `777.4 ms` | **`283.4 ms`** | **`+63.5%`** | **`+54.8%`** |
| **Mediana da Inferência** | ~`625 ms` | ~`775 ms` | **`283.0 ms`** | - | - |
| **Tempo Médio Decodificação JPEG** | `814.0 ms` | `1032.4 ms` | **`102.7 ms`** | `+90.1%` | `+87.4%` |
| **Cadência Média entre Imagens** | `1581.0 ms` | `1044.8 ms` | **`564.7 ms`** | `+46.0%` | `+64.3%` |
| **Tempo Total do Lote (550 imagens)** | `871.51 s` (`14.5 min`) | `574.89 s` (`9.6 min`) | **`310.83 s` (`5.18 min`)** | **`+45.9%`** | **`+64.3%`** |
| **Vazão Média (Throughput)** | `0.63 img/s` | `0.96 img/s` | **`1.77 img/s`** | **`1.84x`** | **`2.81x`** |
| **Acurácia Global no ESP32** | `82.55%` (454/550) | `82.55%` (454/550) | **`89.82%` (`494/550`)** | **`+7.27%`** | **`+7.27%`** |
| **Confiança Média das Predições** | `81.4%` | `81.5%` | **`84.83%`** | - | - |

---

## 2. Desempenho Detalhado por Classe

| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Cadência Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 50 | 47 | **94.0%** | 94.3% | 508.7 ms | 283.3 ms | 75.2 ms |
| **Brown Spot** | 50 | 50 | **100.0%** | 95.9% | 494.5 ms | 283.4 ms | 75.3 ms |
| **BrownRust** | 50 | 49 | **98.0%** | 88.0% | 509.4 ms | 283.5 ms | 73.4 ms |
| **Dried Leaves** | 50 | 26 | **52.0%** | 74.2% | 507.4 ms | 283.4 ms | 74.4 ms |
| **Grassy shoot** | 50 | 50 | **100.0%** | 93.5% | 722.4 ms | 283.2 ms | 197.9 ms |
| **Healthy Leaves** | 50 | 40 | **80.0%** | 88.2% | 579.1 ms | 283.4 ms | 112.2 ms |
| **Pokkah Boeng** | 50 | 50 | **100.0%** | 70.8% | 605.8 ms | 283.2 ms | 112.9 ms |
| **Sett Rot** | 50 | 50 | **100.0%** | 87.4% | 646.6 ms | 283.4 ms | 125.2 ms |
| **Viral Disease** | 50 | 46 | **92.0%** | 86.2% | 518.1 ms | 283.4 ms | 78.4 ms |
| **Yellow Leaf** | 50 | 44 | **88.0%** | 80.8% | 513.2 ms | 283.4 ms | 80.9 ms |
| **smut** | 50 | 42 | **84.0%** | 73.8% | 605.8 ms | 283.4 ms | 124.1 ms |
| **TOTAL / MÉDIA** | **550** | **494** | **89.82%** | **84.8%** | **564.7 ms** | **283.4 ms** | **102.7 ms** |

---

## 3. Matriz de Confusão no Microcontrolador

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **47** | - | `3` | - | - | - | - | - | - | - | - |
| **Brown Spot** | - | **50** | - | - | - | - | - | - | - | - | - |
| **BrownRust** | - | `1` | **49** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | `17` | - | - | **26** | - | - | - | - | - | `7` | - |
| **Grassy shoot** | - | - | - | - | **50** | - | - | - | - | - | - |
| **Healthy Leaves** | `1` | - | - | - | - | **40** | - | - | `9` | - | - |
| **Pokkah Boeng** | - | - | - | - | - | - | **50** | - | - | - | - |
| **Sett Rot** | - | - | - | - | - | - | - | **50** | - | - | - |
| **Viral Disease** | - | `1` | `1` | - | - | `2` | - | - | **46** | - | - |
| **Yellow Leaf** | `5` | `1` | - | - | - | - | - | - | - | **44** | - |
| **smut** | - | - | - | - | `2` | - | - | - | `4` | `2` | **42** |

---

## 4. Análise Técnica dos Resultados e Conclusão

1. **Impacto da Eliminação de Gargalo de PSRAM pelos Scratch Buffers em SRAM:**
   - Ao alocar `48 KB` de workspace SIMD direto na SRAM Interna para os operadores `Conv2D` e `DepthwiseConv2D`, o núcleo vetorial do ESP32-S3 deixou de disputar o barramento SPI da PSRAM a 40 MHz durante os estágios intensivos de `im2col` e reorganização de tensores.
   - O tempo de inferência neural atingiu **`283.4 ms`** (comparado a `777.4 ms` no pipeline anterior sem SRAM dedicada, ganho de **`+63.5%`**).

2. **Eficiência do Paralelismo Fork-Join Multi-Core no esp-nn:**
   - O Core 0 agora assume cooperativamente metade das fatias de tensores das camadas convolucionais pesadas e conexões residuais (`ADD`/`MUL`), mantendo a estabilidade de cache e garantindo consistência matemática bit-a-bit.

3. **Convergência com o Modelo v08 e Box Averaging Nativo:**
   - A acurácia global no dispositivo atingiu **`89.82%`** com confiança média de **`84.8%`**, refletindo a eliminação de *aliasing* pela decodificação `Modo 7 (RGB8888 + BoxAvg)` pré-computada em LUTs.

4. **Registro de Rastreabilidade:** Dados brutos exportados em [`resultado_inferencia_espnn_sram_limpo.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_espnn_sram_limpo.csv).
