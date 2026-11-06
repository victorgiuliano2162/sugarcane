# Relatório Comparativo de Desempenho: Métodos de Conversão de Cor e Redimensionamento em `JPEGDraw()`

**Data da Avaliação:** 06/11/2026  
**Motor de Decodificação:** Biblioteca `JPEGDEC` (Caminho de Referência C do ESP32-S3)  
**Modelo Avaliado:** `data/model_mbnet_int8.tflite` (MobileNetV2 Int8 — `[1, 160, 160, 3]`)  
**Dataset Avaliado:** 550 imagens (50 amostras $\times$ 11 classes — Total de 4.400 inferências nos 8 métodos)  
**Planilha de Dados Brutos:** [`model_inference_tests/resultado_comparativo_jpegdraw.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_comparativo_jpegdraw.csv)  
**Documentação Matemática Detalhada:** [`docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md`](file:///home/victor/projects/sugarcane/docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md)

---

## 1. Resumo Geral Comparativo (8 Variantes da `JPEGDraw()`)

| Método Avaliado | Acertos (550) | Acurácia Global | Confiança Média | Viés de Brilho (Bias DC) | Erro de Cor (MAE) | Erro Global (RMSE) | Qualidade Sinal (PSNR) | Tempo Médio Decode (Ref) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0. Atual (`RGB565 ZeroFill + Overwrite`)** | 453 / 550 | **82.36%** | 79.13% | `-2.90 LSB` | 2.83 LSB | 11.25 LSB | 27.1 dB | 5.689 µs (Base) |
| **1. `RGB565 BitRep + Overwrite`** | 449 / 550 | **81.64%** | **79.56%** | `+0.60 LSB` | 1.93 LSB | 11.00 LSB | 27.3 dB | 6.397 µs (+12.4%) |
| **2. `RGB8888 Nativo + Overwrite`** | 450 / 550 | **81.82%** | 78.92% | **`-0.06 LSB`** | **0.00 LSB** | 10.35 LSB | 27.8 dB | 6.116 µs (+7.5%) |
| **3. `RGB565 BitRep + FastLUT`** | 449 / 550 | **81.64%** | **79.56%** | `+0.60 LSB` | 1.93 LSB | 11.00 LSB | 27.3 dB | **3.904 µs (-31.4%)** |
| **4. `RGB8888 Nativo + FastLUT`** | 450 / 550 | **81.82%** | 78.92% | **`-0.06 LSB`** | **0.00 LSB** | 10.35 LSB | 27.8 dB | **4.663 µs (-18.0%)** |
| **5. `RGB565 ZeroFill + BoxAvg`** | **455 / 550** | **82.73% (1º)** | 78.82% | `-2.84 LSB` | 2.84 LSB | **3.15 LSB** | **38.2 dB** | 6.445 µs (+13.3%) |
| **6. `RGB565 BitRep + BoxAvg`** | 444 / 550 | **80.73%** | 78.75% | `+0.66 LSB` | 1.28 LSB | **1.69 LSB** | **43.6 dB** | 7.191 µs (+26.4%) |
| **7. `RGB8888 Nativo + BoxAvg (Ideal)`** | 445 / 550 | **80.91%** | 78.75% | **`0.00 LSB`** | **0.00 LSB** | **0.00 LSB** | **∞ dB** | 7.267 µs (+27.7%) |

---

## 2. Desempenho Detalhado por Classe (50 amostras cada)

### 2.1. Comparativo de Acertos e Confiança Média nos Principais Métodos

| Classe | 0. Atual (`ZeroFill + Overwrite`) | 2/4. `RGB8888 Nativo` (`Overwrite` / `FastLUT`) | 5. `RGB565 ZeroFill + BoxAvg` (Maior Acc) | 7. `RGB8888 Nativo + BoxAvg` (Sinal Ideal) |
| :--- | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 43/50 (**86.0%**) \| Conf: 78.7% | **46/50 (92.0%)** \| Conf: 80.0% | 43/50 (**86.0%**) \| Conf: 75.8% | 39/50 (78.0%) \| Conf: 75.3% |
| **Brown Spot** | **50/50 (100.0%)** \| Conf: 87.1% | 48/50 (96.0%) \| Conf: 87.5% | **50/50 (100.0%)** \| Conf: **94.1%** | **50/50 (100.0%)** \| Conf: **94.2%** |
| **BrownRust** | 40/50 (80.0%) \| Conf: 87.7% | 40/50 (80.0%) \| Conf: 86.5% | **41/50 (82.0%)** \| Conf: 81.0% | **41/50 (82.0%)** \| Conf: 80.7% |
| **Dried Leaves** | **49/50 (98.0%)** \| Conf: 90.9% | 47/50 (94.0%) \| Conf: 90.0% | 48/50 (96.0%) \| Conf: 83.1% | 46/50 (92.0%) \| Conf: 81.9% |
| **Grassy shoot** | **50/50 (100.0%)** \| Conf: 91.9% | **50/50 (100.0%)** \| Conf: 91.8% | 48/50 (96.0%) \| Conf: 83.1% | 48/50 (96.0%) \| Conf: 82.1% |
| **Healthy Leaves** | 41/50 (82.0%) \| Conf: 79.7% | **45/50 (90.0%)** \| Conf: 81.5% | 33/50 (66.0%) \| Conf: 84.1% | 35/50 (70.0%) \| Conf: 85.3% |
| **Pokkah Boeng** | 37/50 (74.0%) \| Conf: 53.8% | 38/50 (76.0%) \| Conf: 51.7% | **43/50 (86.0%)** \| Conf: **59.6%** | 38/50 (76.0%) \| Conf: **60.0%** |
| **Sett Rot** | **50/50 (100.0%)** \| Conf: 96.6% | **50/50 (100.0%)** \| Conf: 96.7% | **50/50 (100.0%)** \| Conf: 96.9% | **50/50 (100.0%)** \| Conf: **97.2%** |
| **Viral Disease** | **45/50 (90.0%)** \| Conf: 62.4% | 36/50 (72.0%) \| Conf: 61.2% | 43/50 (86.0%) \| Conf: **66.7%** | 41/50 (82.0%) \| Conf: 65.4% |
| **Yellow Leaf** | 46/50 (92.0%) \| Conf: 88.7% | **47/50 (94.0%)** \| Conf: 89.3% | **47/50 (94.0%)** \| Conf: 84.3% | **47/50 (94.0%)** \| Conf: 85.5% |
| **smut** | 2/50 (4.0%) \| Conf: 53.1% | 3/50 (6.0%) \| Conf: 51.9% | **9/50 (18.0%)** \| Conf: 58.3% | **10/50 (20.0%)** \| Conf: **58.7%** |

---

## 3. Matrizes de Confusão Comparativas

### 3.1. Matriz de Confusão — Modo 4 (`RGB8888 Nativo + FastLUT`)
*(Cor 24-bit exata sem perda RGB565 e 18% mais rápido que o código atual)*

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **46** | `3` | - | - | - | - | - | - | - | `1` | - |
| **Brown Spot** | - | **48** | - | - | - | - | - | - | - | `2` | - |
| **BrownRust** | `10` | - | **40** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | `1` | - | - | **47** | - | - | - | - | - | `2` | - |
| **Grassy shoot** | - | - | - | - | **50** | - | - | - | - | - | - |
| **Healthy Leaves** | - | - | - | - | - | **45** | - | - | `5` | - | - |
| **Pokkah Boeng** | - | - | `2` | `7` | - | - | **38** | - | - | - | `3` |
| **Sett Rot** | - | - | - | - | - | - | - | **50** | - | - | - |
| **Viral Disease** | - | - | `1` | - | - | - | - | - | **36** | - | `13` |
| **Yellow Leaf** | `1` | - | - | `2` | - | - | - | - | - | **47** | - |
| **smut** | - | `1` | `5` | `1` | - | - | `34` | - | `6` | - | **3** |

---

### 3.2. Matriz de Confusão — Modo 5 (`RGB565 ZeroFill + BoxAvg`)
*(Maior acurácia global — `82.73%`, eliminando os falsos positivos de `Pokkah Boeng` em `Dried Leaves`/`BrownRust` e quadruplicando os acertos em `smut`)*

| Classe Real \ Predição | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | **43** | `1` | - | - | - | - | - | - | - | `6` | - |
| **Brown Spot** | - | **50** | - | - | - | - | - | - | - | - | - |
| **BrownRust** | `9` | - | **41** | - | - | - | - | - | - | - | - |
| **Dried Leaves** | `1` | `1` | - | **48** | - | - | - | - | - | - | - |
| **Grassy shoot** | - | - | - | - | **48** | - | - | - | - | `2` | - |
| **Healthy Leaves** | - | - | - | - | - | **33** | - | - | `17` | - | - |
| **Pokkah Boeng** | - | - | - | - | - | - | **43** | - | - | - | `7` |
| **Sett Rot** | - | - | - | - | - | - | - | **50** | - | - | - |
| **Viral Disease** | - | - | `1` | - | - | - | - | - | **43** | `2` | `4` |
| **Yellow Leaf** | - | `2` | - | `1` | - | - | - | - | - | **47** | - |
| **smut** | - | `1` | - | - | - | - | `36` | - | `4` | - | **9** |

---

## 4. Conclusões Práticas

1. **O ganho de cor 24-bit (`RGB8888 Nativo`) melhora classes cromáticas:** `Banded Chlorosis` sobe de `86%` para **`92%`** e `Healthy Leaves` sobe de `82%` para **`90%`**, eliminando 100% do erro de quantização `RGB565` (`Color MAE = 0.00`).
2. **O ganho de anti-aliasing espacial (`BoxAvg`) recupera lesões finas:** `smut` sobe de `4%` para **`18%–20%`** (até **5x mais acertos**) e `Pokkah Boeng` sobe de `74%` para **`86%`** (`+12%`), elevando o PSNR global de `27.1 dB` para **`38.2–43.6 dB`**.
3. **A otimização `FastLUT` elimina 96,7% do trabalho desperdiçado:** Para qualquer modo de amostragem pontual (`RGB565` ou `RGB8888`), pular as linhas/colunas que seriam sobrescritas reduz o tempo de CPU da decodificação em **18% a 31%**, mantendo o resultado matemático 100% idêntico.
