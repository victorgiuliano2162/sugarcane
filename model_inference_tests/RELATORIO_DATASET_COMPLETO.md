# 🌿 Relatório de Avaliação Exaustiva — Dataset Completo + Archive (9,269 Imagens)

**Data da Avaliação:** 08/11/2026 08:42:57  
**Dispositivo Físico:** ESP32-S3 DevKitM-1 (Dual-Core Xtensa LX7 @ 240 MHz, 512 KB SRAM, 8 MB Octal PSRAM @ 80 MHz DDR)  
**Firmware:** Sugarcane Classifier v5.0 (Fork-Join esp-nn + BoxAvg RGB8888 24-bit + PSRAM 80 MHz DDR + -O2)  
**Modelo Neural:** `data/model_mbnet_int8.tflite` (MobileNetV3Small Int8 v08, 160x160x3, 11 classes)  
**Planilha de Dados Brutos:** [`resultado_inferencia_dataset_completo.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_dataset_completo.csv)  

---

## 1. Resumo Executivo Geral

| Indicador Global | Resultado Medido |
| :--- | :---: |
| **Total de Imagens Processadas** | **9,269 imagens** (6.748 primário + 2.521 archive) |
| **Tempo Total do Lote** | **5678.06 s** (94.63 min) |
| **Vazão Média do Sistema (Throughput)** | **1.63 imagens/s** |
| **Tempo Médio de Inferência Neural** | **283.4 ms** (Mediana: **283.0 ms**) |
| **Tempo Médio de Decodificação JPEG** | **92.6 ms** (Mediana: **85.0 ms**) |
| **Tempo Total Médio no Microcontrolador** | **376.0 ms** |
| **Acurácia Global no Dataset Primário** | **82.26%** (5,551/6,748 acertos) |
| **Confiança Média no Dataset Primário** | **82.33%** |
| **Acurácia Mapeada no Dataset Archive** | **3.13%** (79/2,521 acertos) |
| **Confiança Média no Dataset Archive** | **71.30%** |

---

## 2. Desempenho Detalhado por Classe no Dataset Primário (11 Classes)

| Subpasta / Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 471 | 403 | **85.56%** | 86.9% | 283.3 ms | 83.9 ms |
| **Brown Spot** | 1,722 | 1,504 | **87.34%** | 79.7% | 283.4 ms | 89.9 ms |
| **BrownRust** | 314 | 254 | **80.89%** | 84.6% | 283.3 ms | 87.6 ms |
| **Dried Leaves** | 343 | 253 | **73.76%** | 78.5% | 283.4 ms | 81.7 ms |
| **Grassy shoot** | 346 | 346 | **100.00%** | 95.6% | 283.3 ms | 157.0 ms |
| **Healthy Leaves** | 430 | 406 | **94.42%** | 92.4% | 283.4 ms | 108.7 ms |
| **Pokkah Boeng** | 297 | 161 | **54.21%** | 69.4% | 283.4 ms | 95.3 ms |
| **Sett Rot** | 652 | 644 | **98.77%** | 89.1% | 283.4 ms | 131.9 ms |
| **Viral Disease** | 663 | 542 | **81.75%** | 86.6% | 283.4 ms | 83.9 ms |
| **Yellow Leaf** | 1,194 | 875 | **73.28%** | 75.7% | 283.4 ms | 89.6 ms |
| **smut** | 316 | 163 | **51.58%** | 78.1% | 283.4 ms | 109.1 ms |

### 2.1. Matriz de Confusão do Dataset Primário (11x11)

| Classe Real \ Predita | BC | BS | BR | DL | GS | HL | PB | SR | VD | YL | SM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis (BC)** | **403** | `9` | `36` | - | - | - | - | - | `9` | `14` | - |
| **Brown Spot (BS)** | `41` | **1504** | `49` | `6` | - | `33` | `16` | - | `44` | `29` | - |
| **BrownRust (BR)** | `36` | `6` | **254** | - | - | - | - | - | `15` | `3` | - |
| **Dried Leaves (DL)** | `73` | - | - | **253** | `1` | - | - | - | - | `16` | - |
| **Grassy shoot (GS)** | - | - | - | - | **346** | - | - | - | - | - | - |
| **Healthy Leaves (HL)** | `1` | `1` | - | - | - | **406** | - | - | `22` | - | - |
| **Pokkah Boeng (PB)** | `17` | `41` | - | `61` | `2` | `7` | **161** | - | `7` | `1` | - |
| **Sett Rot (SR)** | - | - | - | - | `5` | - | - | **644** | - | - | `3` |
| **Viral Disease (VD)** | `29` | `6` | `79` | - | - | `2` | - | - | **542** | `3` | `2` |
| **Yellow Leaf (YL)** | `207` | `43` | `38` | `8` | `5` | `1` | `1` | - | `14` | **875** | `2` |
| **smut (SM)** | `14` | `39` | `24` | `61` | `5` | - | - | `1` | `7` | `2` | **163** |

---

## 3. Desempenho no Dataset Archive (5 Classes de Validação Externa)

Cada subpasta deste repositório representa uma classe botânica/patológica independente:

| Subpasta | Amostras | Classe Equivalente no Modelo | Predições Corretas | Taxa de Concordância | Confiança Média |
| :--- | :---: | :--- | :---: | :---: | :---: |
| **Healthy** | 522 | `Healthy Leaves` | 10 | **1.92%** | 60.8% |
| **Mosaic** | 462 | `Viral Disease` | 30 | **6.49%** | 77.0% |
| **RedRot** | 518 | `RedRot` | 0 | **0.00%** | 69.1% |
| **Rust** | 514 | `BrownRust` | 2 | **0.39%** | 80.6% |
| **Yellow** | 505 | `Yellow Leaf` | 37 | **7.33%** | 69.7% |

### 3.1. Matriz de Distribuição das Predições do Archive (5 Subpastas x 11 Classes Modelo)

| Subpasta Archive \ Predição | BC | BS | BR | DL | GS | HL | PB | SR | VD | YL | SM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Healthy** | - | `311` | - | `1` | - | **10** | `26` | `5` | `161` | `8` | - |
| **Mosaic** | - | `413` | - | `2` | - | `7` | `5` | `2` | **30** | `2` | `1` |
| **RedRot** | `2` | `406` | `8` | `3` | `1` | `41` | `8` | `6` | `21` | `22` | - |
| **Rust** | - | `490` | **2** | - | `1` | `5` | - | `3` | `7` | `5` | `1` |
| **Yellow** | - | `432` | - | `2` | `1` | `7` | `2` | `3` | `21` | **37** | - |

---

## 4. Legenda das Classes e Siglas

- **BC**: Banded Chlorosis
- **BS**: Brown Spot
- **BR**: BrownRust
- **DL**: Dried Leaves
- **GS**: Grassy shoot
- **HL**: Healthy Leaves
- **PB**: Pokkah Boeng
- **SR**: Sett Rot
- **VD**: Viral Disease
- **YL**: Yellow Leaf
- **SM**: smut
