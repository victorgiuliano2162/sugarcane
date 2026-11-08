# 🌿 Relatório de Avaliação Exaustiva do Dataset Completo (6748 Imagens)
**Data da Avaliação:** 07/11/2026 20:19:10  
**Dispositivo:** ESP32-S3 (Xtensa Dual-Core LX7 @ 240 MHz, 512 KB SRAM, 8 MB Octal PSRAM)  
**Modelo Neural:** `data/model_mbnet_int8.tflite` (MobileNetV3Small Int8 v08)  
**Processamento de Imagem:** Modo 7 Otimizado (RGB8888 Nativo 24-bit + IDCT Scale Reduction + BoxAvg em SRAM)  
**Total de Imagens Avaliadas:** **6748 imagens** (100% de todas as 11 classes)  
**Base de Dados:** [`resultado_inferencia_dataset_completo.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_dataset_completo.csv)  

---

## 1. Resumo Executivo Geral

| Métrica de Avaliação | Resultado Obtido |
| :--- | :---: |
| **Total de Imagens Testadas** | **6,748 imagens** |
| **Acurácia Global no Dataset Inteiro** | **92.43%** (6,237/6,748 acertos) |
| **Confiança Média Estatística** | **87.48%** |
| **Tempo Total do Lote** | **4821.73 s** (80.36 min) |
| **Taxa de Transferência (Throughput)** | **1.40 imagens/s** |
| **Tempo Médio de Inferência Neural** | **336.1 ms** (Mediana: 336.0 ms) |
| **Tempo Médio de Decodificação JPEG** | **148.1 ms** (Mediana: 129.0 ms) |
| **Tempo Total Médio no Dispositivo** | **484.3 ms** |

---

## 2. Desempenho Detalhado por Classe Patológica

| Classe Patológica | Total Fotos | Acertos | Acurácia (%) | Confiança Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 471 | 391 | **83.0%** | 81.5% | 336.1 ms | 133.7 ms |
| **Brown Spot** | 1722 | 1651 | **95.9%** | 91.1% | 336.1 ms | 139.7 ms |
| **BrownRust** | 314 | 291 | **92.7%** | 83.9% | 336.0 ms | 136.9 ms |
| **Dried Leaves** | 343 | 333 | **97.1%** | 89.3% | 336.1 ms | 130.8 ms |
| **Grassy shoot** | 346 | 344 | **99.4%** | 90.2% | 336.1 ms | 209.4 ms |
| **Healthy Leaves** | 430 | 416 | **96.7%** | 92.2% | 336.2 ms | 158.3 ms |
| **Pokkah Boeng** | 297 | 243 | **81.8%** | 68.1% | 336.2 ms | 144.5 ms |
| **Sett Rot** | 652 | 652 | **100.0%** | 96.5% | 336.2 ms | 181.3 ms |
| **Viral Disease** | 663 | 579 | **87.3%** | 83.2% | 336.0 ms | 135.3 ms |
| **Yellow Leaf** | 1194 | 1150 | **96.3%** | 88.2% | 336.1 ms | 139.5 ms |
| **smut** | 316 | 187 | **59.2%** | 74.6% | 336.1 ms | 159.3 ms |

---

## 3. Matriz de Confusão Completa (11x11)

| Classe Real \ Predita | BC | BS | BR | DL | GS | HL | PB | SR | VD | YL | SM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis (BC)** | **391** | `18` | `50` | - | - | - | - | - | - | `12` | - |
| **Brown Spot (BS)** | `12` | **1651** | `38` | `6` | - | - | - | - | `3` | `12` | - |
| **BrownRust (BR)** | `17` | - | **291** | - | - | - | - | - | `6` | - | - |
| **Dried Leaves (DL)** | - | `1` | `1` | **333** | - | - | - | - | - | `8` | - |
| **Grassy shoot (GS)** | - | - | `1` | - | **344** | - | - | - | - | `1` | - |
| **Healthy Leaves (HL)** | - | `1` | - | - | - | **416** | - | - | `13` | - | - |
| **Pokkah Boeng (PB)** | `1` | `25` | `1` | `3` | - | - | **243** | - | `1` | `6` | `17` |
| **Sett Rot (SR)** | - | - | - | - | - | - | - | **652** | - | - | - |
| **Viral Disease (VD)** | `24` | `3` | `30` | - | - | `4` | - | - | **579** | `16` | `7` |
| **Yellow Leaf (YL)** | `15` | `4` | `4` | `16` | - | - | `1` | - | `4` | **1150** | - |
| **smut (SM)** | `1` | `2` | `5` | `3` | `1` | - | `89` | - | `28` | - | **187** |

---

## 4. Legenda das Abreviaturas da Matriz

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
