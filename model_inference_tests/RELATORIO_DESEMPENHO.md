# Relatório de Desempenho e Inferência da Rede Neural no ESP32-S3
**Data da Avaliação:** 06/11/2026 15:38:24
**Dispositivo:** ESP32-S3 (8MB Octal PSRAM @ 40MHz, Xtensa Dual Core @ 240MHz)
**Framework de Inferência:** TensorFlow Lite Micro com SIMD Xtensa / NN Optimized
**Comunicação:** WebSocket (`ws://192.168.1.44/ws`)
**Dataset de Teste:** 50 primeiras amostras de cada uma das 11 classes (550 imagens no total)

## 1. Resumo Executivo Geral
| Métrica | Valor |
| :--- | :--- |
| **Total de Imagens Avaliadas** | **550 imagens** |
| **Acurácia Global** | **82.55%** (454/550 acertos) |
| **Tempo Total do Lote (550 imagens)** | **871.51 segundos** (14.53 minutos) |
| **Vazão Média (Throughput)** | **0.63 imagens/segundo** |
| **Tempo Médio de Inferência (Rede Neural)** | **626.6 ms** (Mín: 625 ms / Máx: 633 ms / Desvio: ±1.0 ms) |
| **Tempo Médio de Decodificação JPEG** | **814.0 ms** (Mín: 435 ms / Máx: 1070 ms) |
| **Tempo Total Médio no Dispositivo (Decode + Inferência)** | **1440.6 ms** |
| **Latência Média Completa (Rede + ESP32 Roundtrip)** | **1581.3 ms** |

## 2. Desempenho Detalhado por Classe
| Classe | Amostras | Acertos | Acurácia (%) | Confiança Média | Tempo Médio Inf. |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 50 | 42 | **84.0%** | 79.2% | 626.8 ms |
| **Brown Spot** | 50 | 50 | **100.0%** | 87.3% | 626.6 ms |
| **BrownRust** | 50 | 40 | **80.0%** | 87.7% | 626.8 ms |
| **Dried Leaves** | 50 | 47 | **94.0%** | 91.0% | 626.6 ms |
| **Grassy shoot** | 50 | 50 | **100.0%** | 91.7% | 626.4 ms |
| **Healthy Leaves** | 50 | 43 | **86.0%** | 79.7% | 626.4 ms |
| **Pokkah Boeng** | 50 | 38 | **76.0%** | 53.9% | 626.9 ms |
| **Sett Rot** | 50 | 50 | **100.0%** | 96.5% | 626.6 ms |
| **Viral Disease** | 50 | 45 | **90.0%** | 62.9% | 626.5 ms |
| **Yellow Leaf** | 50 | 46 | **92.0%** | 88.4% | 626.5 ms |
| **smut** | 50 | 3 | **6.0%** | 52.7% | 626.4 ms |

## 3. Matriz de Confusão (50 amostras por linha)
As linhas representam a **Classe Real** e as colunas a **Classe Predita**:

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

## 4. Análise de Eficiência e Recursos do Hardware
* **Decodificação JPEG:** Processada diretamente em memória PSRAM a uma média de **814.0 ms** por imagem em alta resolução (resolução original da câmera do dataset), comprovando a capacidade do ESP32-S3 de descomprimir imagens pesadas sem esgotar memória RAM interna.
* **Inferência TFLite Micro:** A execução da MobileNetV2 INT8 consumiu em média **626.6 ms** por frame com estabilidade impressionante (Mínimo: 625 ms / Máximo: 633 ms / Desvio: apenas ±1.0 ms), demonstrando excelente estabilidade térmica dos núcleos Xtensa LX7 a 240 MHz com instruções SIMD.
* **Latência Total:** Média de **1,44 s** no dispositivo e **1,58 s** considerando o envio via rede Wi-Fi.
* **Tempo Total do Lote:** **871.51 segundos** (14 minutos e 31 segundos) para processar as 550 imagens completas.

## 5. Destaques e Padrões de Diagnóstico
1. **Classes com 100% de Acerto:** `Brown Spot`, `Grassy shoot` e `Sett Rot` alcançaram precisão perfeita (50/50).
2. **Altíssima Performance (>90%):** `Dried Leaves` (94%), `Yellow Leaf` (92%) e `Viral Disease` (90%).
3. **Padrão de Confusão Relevante (`smut` vs `Pokkah Boeng`):** 
   * A classe `smut` obteve apenas 6.0% de acurácia nesta amostra, tendo sido classificada 34 vezes como `Pokkah Boeng` e 8 vezes como `Viral Disease`.
   * Essa confusão visual decorre das características morfológicas semelhantes em folhas afetadas por fungos do topo da cana (chicote do carvão vs deformação foliar do Pokkah Boeng).
4. **Planilha Completa:** Os registros detalhados (amostra por amostra com todas as probabilidades) estão persistidos em `model_inference_tests/resultado_inferencia.csv`.
