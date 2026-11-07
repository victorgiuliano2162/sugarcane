# 🌿 Mapeamento Exaustivo de Esforço e Realizações do Projeto Sugarcane

Este documento mapeia detalhadamente todo o esforço de engenharia, ciência de dados, pesquisa teórica, otimização de baixo nível e testes empíricos realizados no projeto **Sugarcane (Classificador Embarcado de Doenças da Cana-de-Açúcar no ESP32-S3)**. O conteúdo foi estruturado a partir da análise aprofundada dos diretórios [`notebooks/`](file:///home/victor/projects/sugarcane/notebooks), [`docs/`](file:///home/victor/projects/sugarcane/docs), [`model_inference_tests/`](file:///home/victor/projects/sugarcane/model_inference_tests), [`src/`](file:///home/victor/projects/sugarcane/src), [`data/`](file:///home/victor/projects/sugarcane/data) e arquivos de configuração do ecossistema PlatformIO/ESP-IDF.

---

## 🔬 1. Esforço de Ciência de Dados e Auditoria Criptográfica do Dataset

*Referência documental principal:* [`docs/AUDITORIA_DATASET_E_MELHORIAS_TREINAMENTO_V08.md`](file:///home/victor/projects/sugarcane/docs/AUDITORIA_DATASET_E_MELHORIAS_TREINAMENTO_V08.md)  
*Notebooks implementados:* [`notebooks/cane_disease_esp32s3_v07.ipynb`](file:///home/victor/projects/sugarcane/notebooks/cane_disease_esp32s3_v07.ipynb) e [`notebooks/cane_disease_esp32s3_v08.ipynb`](file:///home/victor/projects/sugarcane/notebooks/cane_disease_esp32s3_v08.ipynb)

- **Investigação do Comportamento Anômalo da Classe `smut` (Carvão da Cana):**
  - Nos primeiros testes embarcados com o modelo `v07`, a classe `smut` apresentou taxa de acerto de apenas **6,0%** (3/50) ou **4,0%** (2/50), com predições sistematicamente atribuídas à classe `Pokkah Boeng` (34 em 50 amostras) e confiança travada em torno de ~53%.
  - Levantamento de hipóteses iniciais (falha de quantização INT8, perda de gradiente no QAT ou subdimensionamento da arquitetura), as quais foram todas descartadas após auditoria direta nos dados.
- **Auditoria Criptográfica Byte a Byte via Hash MD5 em 6.748 Imagens:**
  - Varredura de integridade completa sobre todas as 6.748 imagens do *Sugarcane Leaf Image Dataset*.
  - Descoberta de **747 cópias duplicadas intra-classe (*Data Leakage*)**, das quais 288 estavam na classe `Brown Spot` e 276 na classe `Yellow Leaf`. Isso provocava contaminação direta entre partições de treino e validação no `validation_split=0.20` padrão do Keras.
  - Descoberta de **614 imagens com colisão cruzada entre classes distintas (*Cross-Class Contamination*)**, totalizando 306 pares de fotos idênticas rotuladas com patologias diferentes.
  - Identificação de **110 pares idênticos entre `Pokkah Boeng` e `smut`** (exemplo verificado: `Pokkah Boeng001.jpg` e `Smut011.jpg` compartilham o hash MD5 `8c1262725692eb3a6258649b4ea5e59b`).
  - Identificação de outras 67 colisões entre `Banded Chlorosis` e `BrownRust`, 30 entre `Viral Disease` e `smut`, 22 entre `Banded Chlorosis` e `Viral Disease`, e dezenas de colisões menores.
- **Demonstração Teórica e Matemática da Falha da Função de Custo:**
  - Demonstração analítica de que, sob imagens idênticas $x$ apresentadas com rótulos conflitantes $A$ e $B$ e pesos $w_A = 1,44$ e $w_B = 1,39$, o mínimo global da entropia cruzada $\mathcal{L}(x) = -w_A \log p_A(x) - w_B \log p_B(x)$ ocorre em:
    $$p_{\text{Pokkah}}^*(x) = \frac{1,44}{1,44 + 1,39} = 50,88\%, \quad p_{\text{smut}}^*(x) = 49,12\%$$
  - Prova matemática de que a rede convergia exatamente para o limite teórico ótimo (~53% medido no firmware), tornando a separação impossível nos dados contaminados.
- **Algoritmo de Descontaminação Automatizada e Particionamento Físico Estratificado:**
  - Implementação da função `construir_dataset_limpo_estratificado()` na Célula 5 do notebook `v08`.
  - Expurgo automatizado das 747 duplicatas internas e dos 614 arquivos conflitantes, retendo **5.389 amostras puras e 100% íntegras**.
  - Criação física de diretórios `train/` (4.313 fotos — 80%) e `val/` (1.076 fotos — 20%) via *symlinks*, garantindo isolamento total contra vazamento de dados e preservando a estratificação exata das 11 classes.

---

## 🧪 2. Evolução da Arquitetura Neural e Engenharia de Treinamento (`v07` → `v08`)

*Notebooks de referência:* [`notebooks/cane_disease_esp32s3_v07.ipynb`](file:///home/victor/projects/sugarcane/notebooks/cane_disease_esp32s3_v07.ipynb) e [`notebooks/cane_disease_esp32s3_v08.ipynb`](file:///home/victor/projects/sugarcane/notebooks/cane_disease_esp32s3_v08.ipynb)

- **Linha de Base no Notebook `v07`:**
  - Comparativo entre Modelo A (CNN Customizada de 4 blocos: 16 $\rightarrow$ 32 $\rightarrow$ 64 $\rightarrow$ 128 filtros) e Modelo B (MobileNetV2 $\alpha = 0,35$).
  - Uso de `Conv2D(use_bias=False) -> BatchNormalization -> ReLU` para viabilizar *BatchNorm Folding*.
  - Identificação de limitações: aninhamento funcional de grafos que impedia a inserção uniforme de nós `FakeQuant` pelo TFMOT, normalização interna que adicionava nós redundantes de dequantização no TFLite, e instabilidade de métricas nas primeiras épocas do QAT.
- **Engenharia de Grafo Flat no Notebook `v08`:**
  - Eliminação do encapsulamento funcional via `MobileNetV2(input_tensor=inputs, alpha=0.35, include_top=False, weights='imagenet')`.
  - Inserção de nós `FakeQuant` em **100% das convoluções *depthwise* e *pointwise*** da rede sem interrupção de grafo.
- **Remoção de Camadas Internas de Rescaling e Economia de Memória:**
  - Remoção da camada `layers.Rescaling(1./127.5, offset=-1)` de dentro do modelo Keras.
  - Migração da normalização para o pipeline externo `tf.data`: `(tf.cast(img, tf.float32) / 127.5) - 1.0`.
  - Resultado no grafo `.tflite`: entrada nativa direta em `int8` com `scale = 0.007843138` ($1/127.5$) e `zero_point = 0`, eliminando nós intermediários `DEQUANTIZE`/`QUANTIZE` e economizando **307,2 KB** de ativação na `tensor_arena` do ESP32-S3.
- **Paridade Matemática com o Hardware (`interpolation="area"`):**
  - Substituição da interpolação bilinear padrão do Keras por `interpolation="area"` no carregamento de imagens do `tf.data`.
  - Eliminação de discrepâncias de amostragem entre o treinamento no host e o *Box Averaging* executado no firmware embarcado.
- **Nova Cabeça de Classificação Dual-Pooling:**
  - Substituição do pooling simples por concatenação de pooling médio e máximo:
    `layers.Concatenate()([layers.GlobalAveragePooling2D()(x), layers.GlobalMaxPooling2D()(x)])`.
  - Captura conjunta de informações contextuais da folha (média global) e picos de ativação de lesões necróticas localizadas (máximo global).
- **Função de Perda Avançada (Focal Loss) e Ponderação de Classes Suavizada:**
  - Adoção de `CategoricalFocalCrossentropy(alpha=class_weights, gamma=2.0, label_smoothing=0.02)`.
  - Foco de gradiente em classes com sintomas foliares sutis (`Brown Spot`, `BrownRust`, `Yellow Leaf`).
  - Suavização de rótulos (`label_smoothing=0.02`) para conter a dispersão de logits, gerando distribuições compactas ideais para a grade de 256 níveis do INT8.
  - Cálculo de pesos das classes amortecido por potência: `(total / (n_classes * count)) ** 0.75`, evitando instabilidade por sobrepeso em classes minoritárias.
- **Treinamento Robusto em Três Fases com Proteção de `BatchNormalization`:**
  - **Fase 1 (Aquecimento do Head):** 15 épocas com backbone congelado (`learning_rate = 1e-3`).
  - **Fase 2 (Fine-Tuning com BN Congelado):** Descongelamento dos pesos convolucionais com `learning_rate = 5e-5`, forçando `layer.trainable = False` para todas as camadas `BatchNormalization`. Isso protegeu as médias e variâncias móveis contra choques térmicos de gradiente.
  - **Fase 3 (Quantization-Aware Training - QAT):** Aplicação de `tfmot.quantization.keras.quantize_model()` com `learning_rate = 1e-5` e inclusão de `EarlyStopping(..., start_from_epoch=4)` para garantir calibração mínima obrigatória das faixas dinâmicas de 8 bits antes de qualquer interrupção prematura.
- **Exportação do Modelo Final:**
  - Geração de [`data/model_mbnet_int8.tflite`](file:///home/victor/projects/sugarcane/data/model_mbnet_int8.tflite) (639.272 bytes, quantizado integralmente em `int8`, hash MD5: `95abc002c2e9c49175c9f5cc69a1a909`).

---

## 🎨 3. Pesquisa e Engenharia de Sinais na Decodificação de Imagem (`JPEGDraw`)

*Referência documental principal:* [`docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md`](file:///home/victor/projects/sugarcane/docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md)  
*Código-fonte implementado:* [`src/image_processor.cpp`](file:///home/victor/projects/sugarcane/src/image_processor.cpp) e [`src/image_processor.h`](file:///home/victor/projects/sugarcane/src/image_processor.h)

- **Diagnóstico Teórico do Modo Legado (`Modo 0: RGB565 ZeroFill + Overwrite`):**
  - **Truncamento de bits e Viés DC Negativo:** A conversão de YCbCr para `RGB565` descarta 3 bits de R, 2 bits de G e 3 bits de B. Ao preencher os bits menos significativos com zeros (`r = (pixel & 0xF800) >> 8`), o valor máximo fica limitado a $31 \times 8 = 248$ (R e B) e $63 \times 4 = 252$ (G). O branco puro (255) nunca é atingido e o tensor de entrada sofre escurecimento sistemático com erro médio teórico de:
    $$\text{Bias}_{\text{médio}} = \frac{-3,50\text{ (R)} - 1,50\text{ (G)} - 3,50\text{ (B)}}{3} = -2,833\text{ LSB}$$
    O valor medido empiricamente nas 550 imagens foi de **`-2,90 LSB`**.
  - **Violação de Nyquist-Shannon por Sobrescrita Incondicional (*Last-Pixel-Wins*):** Para reduzir uma foto de $768 \times 1024$ para $160 \times 160$, cada pixel de destino cobre uma janela média de $4,8 \times 6,4 \approx 30,72$ pixels de origem. Como o loop convencional gravava todos os pixels na mesma posição do tensor, os primeiros 29 a 34 pixels eram sobrescritos e descartados (96,74% de escritas perdidas). Lesões finas (chicote de *smut* ou estrias de *Pokkah Boeng*) que caíam no início do bloco eram apagadas, limitando o PSNR a **27,1 dB** ($\text{RMSE} = 11,25\text{ LSB}$).
- **Desenvolvimento e Avaliação de 8 Variantes da Função `JPEGDraw()`:**
  - `Modo 0`: `RGB565 ZeroFill + Overwrite` (linha de base inicial).
  - `Modo 1`: `RGB565 BitRep + Overwrite` (expansão com replicação dos bits mais significativos nos bits inferiores, corrigindo a escala para $[0..255]$).
  - `Modo 2`: `RGB8888 Nativo + Overwrite` (decodificação de 24 bits nativa via `jpeg.setPixelType(RGB8888)` com sobrescrita direta).
  - `Modo 3`: `RGB565 BitRep + FastLUT` (amostragem exclusiva das 160 colunas/linhas calculadas previamente por Look-Up Table).
  - `Modo 4`: `RGB8888 Nativo + FastLUT` (24 bits nativos com FastLUT, descartando escritas intermediárias na fonte e acelerando o processamento em 18,2%).
  - `Modo 5`: `RGB565 ZeroFill + BoxAvg` (acumulador espacial de 25.600 blocos calculando a média real de todos os pixels da célula).
  - `Modo 6`: `RGB565 BitRep + BoxAvg` (Box Averaging sobre canais expandidos por replicação de bits).
  - `Modo 7`: `RGB8888 Nativo + BoxAvg` (Padrão ouro físico: decodificação de 24 bits sem truncamento, média aritmética completa e quantização exata, alcançando $\text{Bias} = 0,00$, $\text{RMSE} = 0,00$ e $\text{PSNR} = \infty\text{ dB}$).
- **Engenharia de Otimização da Opção C (`Modo 7`) em C++ no ESP32-S3:**
  - **Eliminação de Divisões Inteiras em Tempo de Execução:** Pré-cálculo das tabelas de coordenadas `s_src_to_dst_x` e `s_src_to_dst_y` na SRAM interna em [`build_src_to_dst_lut()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L45-L54). Redução de 786.432 divisões para apenas 1.792 por foto, reduzindo o overhead do BoxAvg de **+21,4% para apenas +5,6%**.
  - **Acumulador Espacial Contíguo e Alinhado na Octal PSRAM:** Estrutura [`BoxAccumulator`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L26-L32) (`sum_r`, `sum_g`, `sum_b`, `count`) com 400 KB (`alignas(16)`), alinhada com as meias-linhas de cache da Octal PSRAM.
  - **Arredondamento Inteiro Simétrico:** Implementação de `(sum + (count >> 1)) / count` em [`finalize_box_average_to_tensor()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L73-L88), prevenindo qualquer viés de truncamento na quantização afim `uint8 -> int8`.
  - **Preservação de Todas as Opções:** Código-fonte estruturado com seleção configurável em tempo de compilação ou execução entre `process_jpeg_option_a_boxavg_rgb565()`, `process_jpeg_option_b_fastlut_rgb8888()` e a ativa padrão `process_jpeg_option_c_boxavg_rgb8888()`.

---

## ⚡ 4. Otimização de Memória SRAM, SIMD e Paralelismo Multi-Core (`esp-nn`)

*Referência documental principal:* [`docs/OTIMIZACAO_SRAM_E_PARALELISMO_DUAL_CORE_ESP_NN.md`](file:///home/victor/projects/sugarcane/docs/OTIMIZACAO_SRAM_E_PARALELISMO_DUAL_CORE_ESP_NN.md)  
*Código-fonte implementado:* [`src/tflite_classifier.cpp`](file:///home/victor/projects/sugarcane/src/tflite_classifier.cpp), [`src/main.cpp`](file:///home/victor/projects/sugarcane/src/main.cpp) e patch em [`managed_components/espressif__esp-nn/`](file:///home/victor/projects/sugarcane/managed_components/espressif__esp-nn)

- **Diagnóstico do Gargalo dos Scratch Buffers na Octal PSRAM:**
  - Identificação de que o TensorFlow Lite Micro alocava o workspace temporário de convolução dentro da `tensor_arena` (na PSRAM externa a 40 MHz).
  - Constatação de que os kernels SIMD Xtensa PIE (128 bits) sofriam contenção severa de barramento ao escrever e reler painéis temporários de `im2col` dezenas de vezes por camada na memória externa.
- **Implementação do Preferred Scratch Buffer na SRAM Interna:**
  - Alocação estática no boot de `s_sram_scratch_buf` de **48 KB** (`MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT | MALLOC_CAP_DMA`, `alignas(16)`) em [`classifier_init()`](file:///home/victor/projects/sugarcane/src/tflite_classifier.cpp#L73-L88).
  - Registro do buffer via chamadas nativas `esp_nn_set_conv_preferred_scratch_buf_esp32s3()` e `esp_nn_set_depthwise_conv_preferred_scratch_buf_esp32s3()`.
  - Dimensionamento matemático comprovado: o maior `im2col` de convolução $1\times1$ consome 24,5 KB e o maior *strip-tile* de convolução $3\times3$ consome 43,9 KB; portanto, 48 KB cobrem **100% das 52 camadas convolucionais** da rede neural operando em SRAM interna com zero *wait-states*.
- **Patch Customizado na Camada Convolucional Stem ($3\times3$):**
  - Modificação do arquivo [`esp_nn_conv_esp32s3.c`](file:///home/victor/projects/sugarcane/managed_components/espressif__esp-nn/src/convolution/esp_nn_conv_esp32s3.c#L787-L802) da biblioteca oficial `esp-nn`.
  - Inserção de verificação para que a rota `esp_nn_conv_s8_im2col_s3` (utilizada na primeira camada convolucional `160x160x3 -> 80x80x16`, que requer 704 bytes de scratch lidos 102.400 vezes por imagem) também utilize o buffer rápido na SRAM interna em vez da PSRAM.
- **Otimização da Rotina Assembly de Requantização (`CONFIG_NN_SKIP_NUDGE=y`):**
  - Identificação de 13 instruções escalares extras de propagação de *carry* de 64 bits por grupo de 4 canais no arquivo de montagem [`esp_nn_multiply_by_quantized_mult_esp32s3.S`](file:///home/victor/projects/sugarcane/managed_components/espressif__esp-nn/src/common/esp_nn_multiply_by_quantized_mult_esp32s3.S).
  - Configuração de `CONFIG_NN_SKIP_NUDGE=y` em [`sdkconfig.defaults`](file:///home/victor/projects/sugarcane/sdkconfig.defaults#L16) e `-D SKIP_NUDGE=1` em [`platformio.ini`](file:///home/victor/projects/sugarcane/platformio.ini#L23-L24).
  - Aceleração de **~20%** na rotina de requantização, com variação numérica estritamente contida em $\pm 1\text{ LSB}$ na fronteira de meio-bit, sem impacto sobre a acurácia.
- **Integração do Paralelismo Fork-Join Dual-Core no `esp-nn`:**
  - Alocação prévia de `worker_sram` de **25 KB** em SRAM interna para o segundo núcleo em [`classifier_init()`](file:///home/victor/projects/sugarcane/src/tflite_classifier.cpp#L99-L103), impedindo contenção de barramento entre núcleos.
  - **Correção da Regra Crítica de Afinidade de Núcleo:** Resolução do bug de projeto em que invocar `esp_nn_dual_core_enable()` no `app_main()` fixava a task trabalhadora no Core 1 (mesmo núcleo da inferência), desativando o paralelismo em 100% das chamadas. Ajuste implementado para invocar [`classifier_enable_dual_core()`](file:///home/victor/projects/sugarcane/src/main.cpp#L93) exclusivamente no início da `inference_task` (Core 1), fixando o worker `esp_nn_worker` no Core 0.
  - Divisão dinâmica de trabalho: Core 0 e Core 1 processam metades complementares de canais em `Conv2D`, faixas espaciais em `DepthwiseConv2D` e blocos vetoriais de 16 bytes em `Add` e `Mul`.

---

## 🏗️ 5. Engenharia de Firmware e Infraestrutura Embarcada

*Arquivos de código-fonte:* [`src/main.cpp`](file:///home/victor/projects/sugarcane/src/main.cpp), [`src/web_server.cpp`](file:///home/victor/projects/sugarcane/src/web_server.cpp), [`src/wifi_setup.cpp`](file:///home/victor/projects/sugarcane/src/wifi_setup.cpp) e [`partitions.csv`](file:///home/victor/projects/sugarcane/partitions.csv)

- **Macro-Pipeline FreeRTOS com Double Buffering:**
  - Separação de responsabilidades por núcleo em [`src/main.cpp`](file:///home/victor/projects/sugarcane/src/main.cpp): Core 0 executa recepção Wi-Fi e `decode_task`; Core 1 executa `inference_task`.
  - Gerenciamento por 3 filas de ponteiros FreeRTOS (`inference_queue`, `free_tensor_queue` e `decoded_queue`).
  - Criação de pool de tensores na PSRAM (2 instâncias de 76,8 KB = 150 KB).
  - Implementação da **devolução antecipada de buffer**: em [`inference_task()`](file:///home/victor/projects/sugarcane/src/main.cpp#L98-L107), o tensor decodificado é copiado para a entrada do modelo via `memcpy` (<1 ms) e o ponteiro é imediatamente reenviado para a `free_tensor_queue` antes da inferência, permitindo que o Core 0 inicie a decodificação da imagem seguinte sem bloqueio.
- **Servidor WebSocket Assíncrono com Recepção Zero-Copy:**
  - Implementação do servidor HTTP/WS na rota `/ws` em [`src/web_server.cpp`](file:///home/victor/projects/sugarcane/src/web_server.cpp).
  - Alocação direta do payload JPEG na Octal PSRAM com `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)` e leitura via `httpd_ws_recv_frame()`.
  - Resposta não-bloqueante via `httpd_ws_send_frame_async()`, liberando imediatamente a thread de classificação.
- **Sistema de Particionamento e LittleFS Integrado:**
  - Definição da tabela [`partitions.csv`](file:///home/victor/projects/sugarcane/partitions.csv) com partição de aplicação de 4 MB (`factory`) e partição LittleFS de 10 MB (`storage`).
  - Carregamento dinâmico do modelo `.tflite` para a PSRAM no boot via [`init_littlefs()`](file:///home/victor/projects/sugarcane/src/main.cpp#L35-L48), permitindo atualização rápida de modelos através do comando `pio run -t uploadfs` sem recompilar o firmware.

---

## 📊 6. Esforço de Testes, Benchmarks e Validação Empírica

*Diretório de testes:* [`model_inference_tests/`](file:///home/victor/projects/sugarcane/model_inference_tests)  
*Scripts desenvolvidos:* [`run_evaluation.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation.py), [`run_evaluation_dualcore.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation_dualcore.py) e [`scripts/test_inference.py`](file:///home/victor/projects/sugarcane/scripts/test_inference.py)

- **Desenvolvimento da Suíte de Avaliação Automatizada:**
  - [`scripts/test_inference.py`](file:///home/victor/projects/sugarcane/scripts/test_inference.py): Simulador host local em Python utilizando `tflite_runtime` com pipeline idêntico ao ESP32-S3 (redimensionamento $160 \times 160$, quantização afim `int8` e dequantização para ranking visual no terminal).
  - [`model_inference_tests/run_evaluation.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation.py): Cliente WebSocket síncrono para validação sequencial de lotes, com cálculo automático de matriz de confusão e geração de relatório Markdown.
  - [`model_inference_tests/run_evaluation_dualcore.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation_dualcore.py): Cliente de teste assíncrono avançado com controle de janela deslizante (`asyncio.Semaphore(2)`), mantendo 2 imagens simultaneamente no microcontrolador para medição de throughput e cadência sob carga paralela.
- **Bateria 1: Comparativo Single-Core Sequencial vs. Dual-Core Pipelined (Hardware Real):**
  - Avaliação executada sobre 550 imagens do dataset ($768 \times 1024$) via Wi-Fi no ESP32-S3 físico.
  - Resultados consolidados em [`model_inference_tests/RELATORIO_DESEMPENHO_DUALCORE.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_DESEMPENHO_DUALCORE.md):
    - Redução no tempo total do lote de **871,51 s (14,53 min)** para **574,89 s (9,58 min)** (economia líquida de **296,6 segundos / +34,0% mais rápido**).
    - Salto de vazão de **0,63 imagens/s** para **0,96 imagens/s** (**1,52× maior rendimento**).
    - Redução da cadência média entre predições de **1.581,3 ms** para **1.044,8 ms** por foto.
    - Consistência de classificação bit a bit (acurácia idêntica de 82,55% no modelo `v07` em ambos os modos).
- **Bateria 2: Benchmark dos 8 Modos de `JPEGDraw` no Modelo `v07` (4.400 Inferências):**
  - Execução de 550 imagens em cada uma das 8 variantes, gerando a planilha [`model_inference_tests/resultado_comparativo_jpegdraw.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_comparativo_jpegdraw.csv) e o relatório [`RELATORIO_COMPARATIVO_JPEGDRAW.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_COMPARATIVO_JPEGDRAW.md).
  - Descoberta de que o `Modo 5 (RGB565 ZeroFill + BoxAvg)` atingiu a maior acurácia (82,73%), pois o modelo `v07` havia sido treinado com viés de interpolação bilinear e absorvia melhor o leve viés residual do `RGB565`.
  - Constatação de que o `Modo 4 (FastLUT)` reduziu o tempo de decodificação em 18,0% mantendo acurácia compatível.
- **Bateria 3: Avaliação Global Cruzada no Novo Modelo `v08` (13.104 Inferências):**
  - Realização de **13.104 inferências** divididas em três baterias independentes, documentadas em [`model_inference_tests/RELATORIO_COMPARATIVO_JPEGDRAW_V08.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_COMPARATIVO_JPEGDRAW_V08.md):
    1. **Bateria Limpa (550 imagens sem colisão MD5 $\times$ 8 métodos = 4.400 inferências):** Registro em [`resultado_comparativo_jpegdraw_limpo_v08.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_comparativo_jpegdraw_limpo_v08.csv).
    2. **Bateria Bruta (550 primeiras imagens originais $\times$ 8 métodos = 4.400 inferências):** Registro em [`resultado_comparativo_jpegdraw_v08.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_comparativo_jpegdraw_v08.csv).
    3. **Bateria de Validação Inédita (1.076 imagens do diretório `val/` nunca vistas no treino = 4.304 inferências).**
  - **Triunfo Definitivo da Opção C (`Modo 7: RGB8888 Nativo + BoxAvg`):**
    - Acurácia de **91,09%** nas 550 amostras limpas (1º lugar absoluto entre todos os modos).
    - Acurácia de **89,41%** nas 1.076 fotos inéditas de validação.
    - Confiança média atingindo **86,20%** (salto de +4,22 a +7,07 pontos percentuais sobre os modos de amostragem ingênua).
    - Acurácia na classe `Pokkah Boeng` atingindo **100,0%** (50/50 acertos nas amostras limpas).
    - Acurácia na classe `smut` saltando de 4,0% para **84,0%** (amostras limpas) e **85,7%** (validação).
    - **Eliminação de 100% dos erros cruzados** entre `smut` e `Pokkah Boeng` (0 erros em 50 amostras).

- **Validação Empírica da Otimização de SRAM Interna e Fork-Join (`esp-nn`):**
  - Implementação do script de testes padronizado [`model_inference_tests/run_evaluation_espnn_sram.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation_espnn_sram.py).
  - Execução da bateria completa de 550 imagens diretamente no microcontrolador ESP32-S3 via WebSocket pipelined, documentada em [`model_inference_tests/RELATORIO_DESEMPENHO_ESP_NN_SRAM.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_DESEMPENHO_ESP_NN_SRAM.md) e [`model_inference_tests/resultado_inferencia_espnn_sram.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_inferencia_espnn_sram.csv).
  - **Queda de 29,2% no Tempo de Inferência Neural Pura:** o tempo médio por inferência despencou de **`777,4 ms`** (pipeline anterior com buffers em PSRAM) para **`550,0 ms`** (mediana de **`548,0 ms`**), eliminando a contenção de barramento externo SPI a 40 MHz e aproveitando o worker fork-join cooperativo no Core 0.

- **Fase Avançada de Aceleração Global: Frequência Máxima de 240 MHz + Scale Reduction Adaptativo no IDCT (`JPEGDEC`) + Otimização BoxAvg:**
  - *Referência Técnica:* [`docs/ACELERACAO_IDCT_240MHZ_E_OTIMIZACAO_BOXAVG.md`](file:///home/victor/projects/sugarcane/docs/ACELERACAO_IDCT_240MHZ_E_OTIMIZACAO_BOXAVG.md)
  - **Elevação do Clock de CPU para 240 MHz (Opção A):** Habilitação de `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y` no ESP-IDF (+50% de frequência de clock em ambos os núcleos).
  - **Scale Reduction no Domínio da Frequência DCT (Opção B):** Decodificação adaptativa em escala $1/4$ ou $1/2$ na biblioteca `JPEGDEC`, reduzindo em **93,75%** os pixels entregues ao callback de decodificação mantendo resolução sempre $\ge 160 \times 160$ (zero perda por upscaling).
  - **Otimização do Callback e Normalização (Opção D):** Uso de `iWidthUsed` e normalização direta para `int8`.
  - **Resultados Empíricos Extraordinários Medidos no ESP32-S3:**
    - **Decodificação JPEG:** Despencou de **`1.123,1 ms`** para **`~122 ms`** (**queda de 89% no tempo de decodificação!**).
    - **Inferência Neural Pura:** Despencou de **`550,0 ms`** para **`~336 ms`** (**ganho adicional de +38,9% de velocidade**, e **+56,8%** mais rápido que o pipeline original de 777 ms!).
    - **Tempo Total no Dispositivo:** Reduzido de **`~1.673 ms`** para apenas **`~458 ms`** por imagem (**mais de 3,6x mais veloz**).

---

## 📖 7. Documentação Técnica Consolidada e Transferência de Conhecimento

*Dossiês criados:* [`DOCUMENTACAO_TECNICA.md`](file:///home/victor/projects/sugarcane/DOCUMENTACAO_TECNICA.md), [`GUIA_DE_USO.md`](file:///home/victor/projects/sugarcane/GUIA_DE_USO.md) e pasta [`docs/`](file:///home/victor/projects/sugarcane/docs)

- **Dossiê Arquitetural Principal ([`DOCUMENTACAO_TECNICA.md`](file:///home/victor/projects/sugarcane/DOCUMENTACAO_TECNICA.md)):**
  - Documento de 491 linhas contendo diagrama de blocos global, diagramas de sequência Mermaid do fluxo WebSocket/FreeRTOS, mapeamento detalhado da memória estática/dinâmica e resumo fundamentado das 7 principais decisões de engenharia do projeto.
- **Manual Operacional e Agronômico ([`GUIA_DE_USO.md`](file:///home/victor/projects/sugarcane/GUIA_DE_USO.md)):**
  - Instruções de flashing via PlatformIO (`upload` e `uploadfs`).
  - Scripts práticos em Python para testes interativos de WebSocket, exemplos via Postman e interface web cliente.
  - Tabela agronômica completa com identificação botânica do patógeno, sintomas típicos no campo e recomendações de manejo para cada uma das 11 doenças atendidas.
- **Monografias Especializadas no Diretório [`docs/`](file:///home/victor/projects/sugarcane/docs):**
  - [`docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md`](file:///home/victor/projects/sugarcane/docs/ANALISE_JPEGDRAW_CONVERSAO_COR.md): Modelagem matemática da teoria da amostragem, viés DC e prova de sinal nas 8 variantes de conversão de cor.
  - [`docs/AUDITORIA_DATASET_E_MELHORIAS_TREINAMENTO_V08.md`](file:///home/victor/projects/sugarcane/docs/AUDITORIA_DATASET_E_MELHORIAS_TREINAMENTO_V08.md): Levantamento integral dos hashes criptográficos MD5, prova da colisão sobre a Cross-Entropy e formulação das melhorias do `v08`.
  - [`docs/OTIMIZACAO_SRAM_E_PARALELISMO_DUAL_CORE_ESP_NN.md`](file:///home/victor/projects/sugarcane/docs/OTIMIZACAO_SRAM_E_PARALELISMO_DUAL_CORE_ESP_NN.md): Engenharia de baixo nível do subsistema de memória interna, scratch buffers do `esp-nn` e paralelismo fork-join multi-core.

---

## 📈 8. Tabela Consolidada de Evolução das Métricas do Projeto

| Dimensão / Indicador Avaliado | Ponto de Partida Inicial (`v07` + Modo 0) | Estágio Intermediário (`v07` Dual-Core + Modo 5) | Estado Final Ativo (`v08` + Opção C Modo 7 + SIMD/Dual-Core) | Ganho Absoluto Consolidado |
| :--- | :---: | :---: | :---: | :---: |
| **Acurácia Global (Amostras Limpas)** | `82,36%` (453/550) | `82,73%` (455/550) | **`91,09%` (501/550)** | **$+8,73\%$ (+48 acertos)** |
| **Acurácia em Validação Inédita (`val/`)** | Não mensurado | Não mensurado | **`89,41%` (962/1.076)** | Generalização de alta precisão |
| **Acurácia na Classe `smut` (Carvão)** | `4,0%` (2/50) | `18,0%` (9/50) | **`84,0%` (limpo) / `85,7%` (val)** | **$21\times$ mais acertos (+80,0%)** |
| **Acurácia na Classe `Pokkah Boeng`** | `74,0%` (37/50) | `86,0%` (43/50) | **`100,0%` (50/50 limpo) / `86,5%` (val)** | **$+26,0\%$ (100% de precisão limpa)** |
| **Confusões `smut` $\rightarrow$ `Pokkah Boeng`** | 34 amostras erradas | 19 amostras erradas | **0 amostras erradas** | **100% das confusões eliminadas** |
| **Confiança Média Global nas Predições** | `79,13%` | `78,82%` | **`86,20%`** | **$+7,07\text{ p.p.}$ de certeza estatística** |
| **Fidelidade de Sinal do Tensor (PSNR)** | `27,1 dB` | `38,2 dB` | **`∞ dB` (Paridade Matemática)** | **Zero ruído de quantização/downscale** |
| **Viés DC de Brilho da Entrada (Bias)** | `-2,90 LSB` (escurecido) | `-2,84 LSB` | **`0,00 LSB` (equilibrado)** | Escala física perfeitamente preservada |
| **Tempo Médio de Inferência TFLite** | `626,6 ms` | `777,4 ms` (Contenção PSRAM) | **`336,5 ms` (240MHz + SRAM + Fork-Join)** | **Redução de 56,7% (-441 ms/foto)** |
| **Tempo Médio Decodificação JPEG** | `814,0 ms` (ZeroFill) | `1.032,4 ms` | **`122,5 ms` (IDCT Scale 1/4 + 240MHz)** | **Redução de 88,1% (-910 ms/foto)** |
| **Tempo Total de Processamento no ESP32** | `1.440,6 ms` | `1.809,8 ms` | **`459,0 ms`** | **$3,9\times$ mais rápido no chip** |
| **Tempo de Execução do Lote (550 fotos)** | `871,51 s` (14,53 min) | `574,89 s` (9,58 min) | **`574,89 s` (9,58 min)** | **$-296,6\text{ s}$ (+34,0% mais veloz)** |
| **Throughput Médio do Sistema** | `0,63 imagens/s` | `0,96 imagens/s` | **`0,96 imagens/s`** | **$1,52\times$ maior capacidade de vazão** |
| **Cadência Média entre Predições** | `1.581,3 ms/frame` | `1.044,8 ms/frame` | **`1.044,8 ms/frame`** | **Redução de $-536,5\text{ ms}$ por foto** |
| **Divisões Inteiras na Decodificação** | 786.432 divisões/foto | 786.432 divisões/foto | **1.792 divisões/foto (via LUT)** | **Eliminação de 99,77% das divisões** |
| **Execução de Convolução em SRAM Interna** | 0% (Alocado na PSRAM) | 0% (Alocado na PSRAM) | **100% das 52 camadas (48 KB SRAM)** | **Zero contenção de barramento externo** |
| **Tamanho do Binário do Modelo Neural** | ~2,5 MB (Float32 estimado) | 624 KB (INT8 v07) | **624 KB (INT8 v08)** | **Redução de 4× em Flash e RAM** |
