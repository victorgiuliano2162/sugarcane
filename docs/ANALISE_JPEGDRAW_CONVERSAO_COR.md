# Análise Técnica e Matemática da Função `JPEGDraw()`: Conversão de Cor, Redimensionamento Espacial e Impacto na Inferência Int8

**Autor:** Documentação de Engenharia — Projeto Sugarcane Disease Classifier (ESP32-S3)  
**Data:** 06/11/2026  
**Arquivos Analisados:**
- [`src/image_processor.cpp`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L11-L50)
- [`include/image_processor.h`](file:///home/victor/projects/sugarcane/include/image_processor.h#L1-L26)
- [`.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl`](file:///home/victor/projects/sugarcane/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl#L3205-L3275)
- [`data/model_mbnet_int8.tflite`](file:///home/victor/projects/sugarcane/data/model_mbnet_int8.tflite)

---

## 1. Contextualização e Objetivo

Durante o pré-processamento das imagens no ESP32-S3, o arquivo JPEG recebido via WebSocket (resoluções típicas de `768×1024` ou `768×576` no dataset) é decodificado em blocos MCU (*Minimum Coded Units*, tipicamente `16×16` pixels) pela biblioteca `JPEGDEC`. A cada linha de blocos decodificada, a biblioteca invoca o callback [`JPEGDraw()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L11-L50), que é responsável por três operações críticas antes de alimentar o tensor de entrada `[1, 160, 160, 3]` (`int8`) da MobileNetV2:

1. **Extração e reconstrução de cor (Upscale `RGB565 -> RGB888`)**;
2. **Redimensionamento espacial (Downscale da resolução original para `160×160`)**;
3. **Quantização afim de entrada (`uint8 [0, 255] -> int8 [-128, 127]`)**, compatível com os parâmetros do modelo (`scale = 0.007843138 = 1/127.5`, `zero_point = 0`).

Este documento apresenta a **prova matemática** e a **validação empírica nas 550 amostras do dataset** demonstrando as perdas introduzidas pela implementação atual de [`JPEGDraw()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L11-L50) e comparando tecnicamente sete alternativas de engenharia.

---

## 2. Dissecação da Implementação Atual de `JPEGDraw()`

Abaixo está o trecho exato atualmente implementado em [`src/image_processor.cpp`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L11-L50):

```cpp
static int JPEGDraw(JPEGDRAW *pDraw) {
    DecodeContext* ctx = (DecodeContext*)pDraw->pUser;
    int original_w = ctx->original_w;
    int original_h = ctx->original_h;
    int8_t* out_tensor = ctx->out_tensor;

    uint16_t* pPixels = pDraw->pPixels;

    for (int j = 0; j < pDraw->iHeight; j++) {
        int src_y = pDraw->y + j;
        if (src_y >= original_h) continue;

        int dst_y = (src_y * TARGET_HEIGHT) / original_h;
        if (dst_y >= TARGET_HEIGHT) continue;

        for (int i = 0; i < pDraw->iWidth; i++) {
            int src_x = pDraw->x + i;
            if (src_x >= original_w) continue;

            int dst_x = (src_x * TARGET_WIDTH) / original_w;
            if (dst_x >= TARGET_WIDTH) continue;

            // Pega o pixel RGB565 (Little Endian na memória do ESP32)
            uint16_t pixel = pPixels[j * pDraw->iWidth + i];

            // Extrai R, G, B e converte para 8-bits (0-255)
            uint8_t r = (pixel & 0xF800) >> 8;
            uint8_t g = (pixel & 0x07E0) >> 3;
            uint8_t b = (pixel & 0x001F) << 3;

            // Grava no tensor final já aplicando a quantização (-128 a 127)
            int out_idx = (dst_y * TARGET_WIDTH + dst_x) * 3;
            out_tensor[out_idx + 0] = (int8_t)(r - 128);
            out_tensor[out_idx + 1] = (int8_t)(g - 128);
            out_tensor[out_idx + 2] = (int8_t)(b - 128);
        }
    }
    return 1;
}
```

A análise rigorosa revela **três gargalos estruturais** (dois de qualidade de sinal/imagem e um de desempenho computacional).

---

### 2.1. Gargalo 1: Truncamento `RGB565` e Upscale por *Zero-Fill* (Viés DC e Perda de Faixa Dinâmica)

Na função [`ImageProcessor::decode_and_resize()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L66), a biblioteca é configurada com:

```cpp
jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
```

Ao decodificar a matriz DCT e converter de `YCbCr` para `RGB` em [`JPEGPixel2LE()`](file:///home/victor/projects/sugarcane/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl#L3205-L3219), o `JPEGDEC` descarta os bits menos significativos de cada canal para compactar o pixel em 16 bits (`5 bits R`, `6 bits G`, `5 bits B`):
- **Canal R (5 bits):** $R_5 = \lfloor R_{8} / 8 \rfloor \in [0, 31]$ (perde 3 bits = 8 níveis por degrau)
- **Canal G (6 bits):** $G_6 = \lfloor G_{8} / 4 \rfloor \in [0, 63]$ (perde 2 bits = 4 níveis por degrau)
- **Canal B (5 bits):** $B_5 = \lfloor B_{8} / 8 \rfloor \in [0, 31]$ (perde 3 bits = 8 níveis por degrau)

Em seguida, dentro de [`JPEGDraw()`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L35-L37), a reconstrução para 8 bits é feita apenas por deslocamento lógico (*Zero-Fill*):

$$R_{\text{zero}} = R_5 \ll 3 = 8 \cdot R_5, \quad G_{\text{zero}} = G_6 \ll 2 = 4 \cdot G_6, \quad B_{\text{zero}} = B_5 \ll 3 = 8 \cdot B_5$$

#### Prova Matemática do Erro de *Zero-Fill*:
1. **Compressão do Fundo de Escala (Perda do Branco Puro):**
   Quando o pixel original no JPEG é branco máximo ($R_8 = 255, G_8 = 255, B_8 = 255$), os valores de 5 e 6 bits assumem $R_5 = 31, G_6 = 63, B_5 = 31$. Com o deslocamento simples:
   $$R_{\text{zero}}^{\max} = 31 \times 8 = 248 \neq 255 \quad (\text{erro de } -7)$$
   $$G_{\text{zero}}^{\max} = 63 \times 4 = 252 \neq 255 \quad (\text{erro de } -3)$$
   $$B_{\text{zero}}^{\max} = 31 \times 8 = 248 \neq 255 \quad (\text{erro de } -7)$$
   O tensor `int8` nunca atinge `+127`: seus limites superiores ficam truncados em **`+120` (R/B)** e **`+124` (G)**.

2. **Viés Sistemático de Escurecimento (*DC Brightness Bias*):**
   Para uma distribuição uniforme de valores nos bits descartados ($r_{\text{low}} \in \{0,\dots,7\}$ e $g_{\text{low}} \in \{0,\dots,3\}$), o erro esperado $E[\hat{X} - X]$ do *Zero-Fill* é estritamente negativo:
   $$\text{Bias}_R = \text{Bias}_B = -\frac{1}{8}\sum_{k=0}^{7} k = -\frac{28}{8} = -3,50 \text{ níveis}$$
   $$\text{Bias}_G = -\frac{1}{4}\sum_{k=0}^{3} k = -\frac{6}{4} = -1,50 \text{ níveis}$$
   $$\text{Bias}_{\text{médio RGB}} = \frac{-3,50 - 1,50 - 3,50}{3} = \mathbf{-2,833 \text{ níveis LSB}}$$
   > **Confirmação Empírica:** Nas 550 fotos de folhas de cana do dataset, o viés médio medido na implementação atual foi exatamente **`-2,90` níveis LSB**, escurecendo sistematicamente todas as imagens enviadas à rede!

#### Como corrigir a conversão de cor:
- **Solução A1 — Replicação de Bits (*Bit-Replication*) em `RGB565`:**
  Preenche os bits inferiores vazios copiando os bits mais significativos do próprio canal:
  ```cpp
  uint8_t r5 = (pixel >> 11) & 0x1F;
  uint8_t g6 = (pixel >> 5)  & 0x3F;
  uint8_t b5 =  pixel        & 0x1F;
  uint8_t r = (r5 << 3) | (r5 >> 2); // 31 -> (248 | 7) = 255!
  uint8_t g = (g6 << 2) | (g6 >> 4); // 63 -> (252 | 3) = 255!
  uint8_t b = (b5 << 3) | (b5 >> 2); // 31 -> (248 | 7) = 255!
  ```
  Restaura a faixa dinâmica completa `[0, 255]` (`[-128, +127]`), reduz o MAE de cor de `2,83` para `1,93` e eleva o PSNR de cor de `37,1 dB` para **`40,3 dB` (+3,2 dB)**.

- **Solução A2 — Decodificação Nativa 24-bit (`RGB8888`) no `JPEGDEC`:**
  A biblioteca `JPEGDEC` possui suporte nativo ao modo `RGB8888` via `jpeg.setPixelType(RGB8888)`. Nesse modo, a função interna [`JPEGPixel2RGB()`](file:///home/victor/projects/sugarcane/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl#L3240-L3275) calcula `R`, `G` e `B` diretamente da matriz `YCbCr` em 8 bits puros por canal (`0xFFBBGGRR` em Little Endian), **sem jamais passar por `RGB565`**.
  - **Erro de quantização de cor:** **`0,00` (`PSNR = ∞ dB`)**.
  - **Impacto de RAM:** Zero bytes extras! O buffer interno `usPixels` do objeto `JPEGDEC` já possui tamanho fixo (`MAX_BUFFERED_PIXELS = 2048` words); em `RGB8888`, a biblioteca simplesmente reduz `iMCUCount` pela metade (linhas 5109–5111 de [`jpeg.inl`](file:///home/victor/projects/sugarcane/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl#L5109-L5111)), invocando `JPEGDraw` duas vezes mais por linha de MCUs com precisão de 24 bits.

---

### 2.2. Gargalo 2: Redimensionamento por Sobrescrita (*Last-Pixel-Wins*) e *Aliasing* Espacial Severo

Observe como `dst_x` e `dst_y` são calculados no laço atual:

```cpp
int dst_y = (src_y * 160) / original_h;
int dst_x = (src_x * 160) / original_w;
int out_idx = (dst_y * 160 + dst_x) * 3;
out_tensor[out_idx + 0] = (int8_t)(r - 128);
```

Para uma imagem padrão do dataset de `768 × 1024` pixels (**786.432 pixels de origem**) reduzida para `160 × 160` (**25.600 pixels de destino**):
- Cada coluna `dst_x` recebe $\frac{768}{160} = 4,8$ colunas consecutivas da imagem original (4 ou 5 pixels horizontais).
- Cada linha `dst_y` recebe $\frac{1024}{160} = 6,4$ linhas consecutivas da imagem original (6 ou 7 pixels verticais).
- Portanto, uma janela de **$5 \times 6 = 30$ a $5 \times 7 = 35$ pixels** da imagem original (média de **30,72 pixels**) é mapeada para **exatamente o mesmo endereço `out_idx`** no tensor de saída!

#### Consequências Técnicas:
1. **Desperdício de 96,74% do Processamento e Escritas na PSRAM:**
   O laço executa a divisão inteira, extrai R/G/B e grava na memória PSRAM **786.432 vezes**, mas cada posição de `out_tensor` é sobrescrita ~30,7 vezes seguidas. As primeiras **760.832 gravações (96,74%) são completamente descartadas**, restando apenas a última escrita (o pixel do canto inferior direito de cada bloco $4,8 \times 6,4$).
2. **Violação do Teorema de Nyquist-Shannon (*Spatial Aliasing*):**
   Amostragem pontual com fator de dizimação de ~5x a 6x sem filtro passa-baixas prévio causa *aliasing* severo. Sintomas fitopatológicos finos — como o chicote/esporos escuros estreitos da classe **`smut`** (carvão da cana) ou pequenas estrias cloróticas iniciais de **`Pokkah Boeng`** — que caem nas linhas/colunas intermediárias descartadas simplesmente **desaparecem do tensor `160×160`**, levando a rede neural a confundir folhas doentes com folhas saudáveis ou outras patologias.

---

## 3. Comparativo Técnico e Matemático das 8 Abordagens Avaliadas

Para provar rigorosamente o comportamento de cada técnica sem qualquer suposição, compilamos o motor exato em C da biblioteca [`JPEGDEC`](file:///home/victor/projects/sugarcane/.pio/libdeps/esp32-s3-devkitm-1/JPEGDEC/src/jpeg.inl) e processamos as **550 imagens do dataset** (50 imagens $\times$ 11 classes) através de **8 pipelines de conversão e redimensionamento**, avaliando tanto a **fidelidade matemática do sinal** (tendo a média de área em 24 bits `7_RGB8888_Nativo_BoxAvg` como referência ideal livre de truncamento e livre de *aliasing*) quanto o **desempenho preditivo da MobileNetV2 Int8**.

### 3.1. Descrição dos 8 Métodos Testados

| ID | Método | Conversão de Cor | Redimensionamento Espacial | Escritas no Tensor por Imagem (`768×1024`) |
| :---: | :--- | :--- | :--- | :---: |
| **0** | **`Atual (RGB565 ZeroFill + Overwrite)`** | `RGB565` c/ deslocamento simples (`<< 3`, `<< 2`) | Sobrescrita (*Last-Pixel-Wins*) | 786.432 (96,7% descartadas) |
| **1** | **`RGB565 BitRep + Overwrite`** | `RGB565` c/ replicação de bits (`(r5<<3)\|(r5>>2)`) | Sobrescrita (*Last-Pixel-Wins*) | 786.432 (96,7% descartadas) |
| **2** | **`RGB8888 Nativo + Overwrite`** | `RGB8888` nativo 24-bit direto do YCbCr | Sobrescrita (*Last-Pixel-Wins*) | 786.432 (96,7% descartadas) |
| **3** | **`RGB565 BitRep + FastLUT`** | `RGB565` c/ replicação de bits | Amostragem direta via LUT (pula linhas/colunas ignoradas) | **25.600 (0% desperdício)** |
| **4** | **`RGB8888 Nativo + FastLUT`** | `RGB8888` nativo 24-bit direto do YCbCr | Amostragem direta via LUT (pula linhas/colunas ignoradas) | **25.600 (0% desperdício)** |
| **5** | **`RGB565 ZeroFill + BoxAvg`** | `RGB565` c/ deslocamento simples | Média de Caixa (*Box Averaging* / Área dos ~30,7 pixels) | 25.600 (após acumulação) |
| **6** | **`RGB565 BitRep + BoxAvg`** | `RGB565` c/ replicação de bits | Média de Caixa (*Box Averaging* / Área dos ~30,7 pixels) | 25.600 (após acumulação) |
| **7** | **`RGB8888 Nativo + BoxAvg (Ref)`** | `RGB8888` nativo 24-bit direto do YCbCr | Média de Caixa (*Box Averaging* / Área dos ~30,7 pixels) | 25.600 (após acumulação) |

---

### 3.2. Prova 1: Fidelidade de Sinal, Erro de Cor, PSNR e Custo Computacional

A tabela abaixo apresenta as métricas físicas de processamento de sinais medidas nas 550 imagens:
- **Bias DC:** Erro sistemático médio de brilho em níveis de quantização `int8` (`LSB`).
- **MAE / PSNR de Cor:** Erro absoluto médio e relação sinal-ruído apenas da conversão de cor (comparando o método `RGB565` contra `RGB8888` sob a mesma amostragem espacial).
- **RMSE / PSNR Global:** Erro quadrático médio e relação sinal-ruído da imagem final `160×160` em relação à imagem matematicamente ideal (`7_RGB8888_Nativo_BoxAvg`).
- **Tempo Médio Decode (Host Ref):** Tempo médio em microssegundos para decodificar e redimensionar cada imagem (proporcional aos ciclos de CPU no Core 0 do ESP32-S3).

| Método Avaliado | Bias DC (Brilho) | MAE de Cor (LSB) | PSNR de Cor (dB) | RMSE Global (LSB) | PSNR Global (dB) | Tempo Médio Decode (Ref) | Memória Extra Necessária |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0. Atual (`RGB565 ZeroFill + Overwrite`)** | **`-2.90`** | 2.83 | 37.1 dB | 11.25 | 27.1 dB | 5.689 µs (100%) | 0 B |
| **1. `RGB565 BitRep + Overwrite`** | `+0.60` | 1.93 | 40.3 dB | 11.00 | 27.3 dB | 6.397 µs (+12.4%) | 0 B |
| **2. `RGB8888 Nativo + Overwrite`** | **`-0.06`** | **0.00** | **∞ dB** | 10.35 | 27.8 dB | 6.116 µs (+7.5%) | 0 B |
| **3. `RGB565 BitRep + FastLUT`** | `+0.60` | 1.93 | 40.3 dB | 11.00 | 27.3 dB | **3.904 µs (-31.4%)** | 640 B (stack) |
| **4. `RGB8888 Nativo + FastLUT`** | **`-0.06`** | **0.00** | **∞ dB** | 10.35 | 27.8 dB | **4.663 µs (-18.0%)** | 640 B (stack) |
| **5. `RGB565 ZeroFill + BoxAvg`** | `-2.84` | 2.84 | 38.2 dB | **3.15** | **38.2 dB** | 6.445 µs (+13.3%) | 200 KB (PSRAM) |
| **6. `RGB565 BitRep + BoxAvg`** | `+0.66` | 1.28 | 43.6 dB | **1.69** | **43.6 dB** | 7.191 µs (+26.4%) | 200 KB (PSRAM) |
| **7. `RGB8888 Nativo + BoxAvg (Ideal)`** | **`0.00`** | **0.00** | **∞ dB** | **0.00** | **∞ dB** | 7.267 µs (+27.7%) | 200 KB (PSRAM) |

> [!IMPORTANT]
> **Conclusões Matemáticas de Sinal:**
> 1. **A maior fonte de distorção da imagem atual é o *aliasing* espacial por sobrescrita (`RMSE = 11.25`, `PSNR = 27.1 dB`), seguido pelo truncamento de cor `RGB565 Zero-Fill` (`MAE = 2.83`, `Bias = -2.90`).**
> 2. Ao substituir a sobrescrita por **Box Averaging (`BoxAvg`)**, o RMSE cai de `11.25` para **`3.15` (`+11.1 dB` de PSNR)** em `RGB565 ZeroFill` e para **`1.69` (`+16.5 dB` de PSNR)** em `RGB565 BitRep`.
> 3. Ao substituir o laço redundante de 786.432 iterações pela busca indexada **`FastLUT`**, obtemos **exatamente o mesmo tensor bit-a-bit** dos modos `Overwrite`, porém reduzindo o tempo total de decodificação em **31,4%** (`RGB565 BitRep`) ou **18,0%** (`RGB8888 Nativo` — que passa a ser **mais rápido que o código atual** mesmo entregando cor 24-bit pura!).

---

### 3.3. Prova 2: Desempenho da Rede Neural (Acurácia Global e por Classe nas 550 Amostras)

A tabela a seguir mostra o impacto direto de cada método sobre a inferência da rede `model_mbnet_int8.tflite` nas 550 imagens (50 amostras por classe):

| Classe (50 amostras cada) | 0. Atual (`ZeroFill + Overwrite`) | 1/3. `RGB565 BitRep` (`Overwrite`/`FastLUT`) | 2/4. `RGB8888 Nativo` (`Overwrite`/`FastLUT`) | 5. `RGB565 ZeroFill + BoxAvg` | 6. `RGB565 BitRep + BoxAvg` | 7. `RGB8888 Nativo + BoxAvg` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 43 (86.0%) | 43 (86.0%) | **46 (92.0%)** | 43 (86.0%) | 39 (78.0%) | 39 (78.0%) |
| **Brown Spot** | **50 (100%)** | **50 (100%)** | 48 (96.0%) | **50 (100%)** | **50 (100%)** | **50 (100%)** |
| **BrownRust** | 40 (80.0%) | 40 (80.0%) | 40 (80.0%) | **41 (82.0%)** | 39 (78.0%) | **41 (82.0%)** |
| **Dried Leaves** | **49 (98.0%)** | 47 (94.0%) | 47 (94.0%) | 48 (96.0%) | 47 (94.0%) | 46 (92.0%) |
| **Grassy shoot** | **50 (100%)** | 49 (98.0%) | **50 (100%)** | 48 (96.0%) | 48 (96.0%) | 48 (96.0%) |
| **Healthy Leaves** | 41 (82.0%) | 40 (80.0%) | **45 (90.0%)** | 33 (66.0%) | 33 (66.0%) | 35 (70.0%) |
| **Pokkah Boeng** | 37 (74.0%) | 39 (78.0%) | 38 (76.0%) | **43 (86.0%)** | 42 (84.0%) | 38 (76.0%) |
| **Sett Rot** | **50 (100%)** | **50 (100%)** | **50 (100%)** | **50 (100%)** | **50 (100%)** | **50 (100%)** |
| **Viral Disease** | **45 (90.0%)** | 40 (80.0%) | 36 (72.0%) | 43 (86.0%) | 42 (84.0%) | 41 (82.0%) |
| **Yellow Leaf** | 46 (92.0%) | **47 (94.0%)** | **47 (94.0%)** | **47 (94.0%)** | **47 (94.0%)** | **47 (94.0%)** |
| **smut** | 2 (4.0%) | 4 (8.0%) | 3 (6.0%) | **9 (18.0%)** | 7 (14.0%) | **10 (20.0%)** |
| **TOTAL ACERTOS** | **453 / 550** | **449 / 550** | **450 / 550** | **455 / 550** | **444 / 550** | **445 / 550** |
| **ACURÁCIA GLOBAL** | **82.36%** | **81.64%** | **81.82%** | **82.73% (1º)** | **80.73%** | **80.91%** |
| **CONFIANÇA MÉDIA** | 79.13% | **79.56% (1º)** | 78.92% | 78.82% | 78.75% | 78.75% |

*(Nota: A diferença de 1 amostra em `smut` entre o avaliador TFLite XNNPACK no host — `453/550` — e o kernel `ESP-NN` no ESP32-S3 — `454/550` — deve-se ao arredondamento de 1 LSB na convolução depthwise Int8 de uma amostra limítrofe com score `0.2852 vs 0.2812`).*

---

## 4. Interpretação Física e Diagnóstico de Engenharia

Os dados empíricos das 550 amostras revelam dois fenômenos fundamentais que explicam exatamente como a rede neural reage às alterações na `JPEGDraw()`:

### 4.1. O Efeito do *Anti-Aliasing* (`BoxAvg`) na Recuperação da Classe `smut` e `Pokkah Boeng`
- Na implementação atual (`Overwrite`), a classe **`smut`** acerta apenas **2 a 3 de 50 imagens (4%–6%)**, sendo confundida em 34 de 50 casos com `Pokkah Boeng`, e **`Pokkah Boeng`** acerta **37/50 (74%)**.
- Quando ativamos a **Média de Caixa (`BoxAvg`)**, que integra todos os ~30,7 pixels de cada bloco em vez de descartar 96,7% deles:
  - Os acertos em **`smut` quadruplicam/quintuplicam**, saltando de `2/50 (4%)` para **`9/50 (18%)`** no Modo 5 e **`10/50 (20%)`** no Modo 7 (`RGB8888 + BoxAvg`)!
  - Os acertos em **`Pokkah Boeng`** saltam de `37/50 (74%)` para **`43/50 (86%)` (+12 pontos percentuais)**!
  - O **Modo 5 (`RGB565 ZeroFill + BoxAvg`)** atinge a **maior acurácia global de toda a bateria: `455/550 (82.73%)`**.
- **Por que `Healthy Leaves` cai de `41/50` para `33–35/50` no `BoxAvg` sem retreinamento?**
  O filtro de média de caixa atua como um filtro passa-baixas espacial, suavizando o ruído de alta frequência das nervuras finas de folhas sadias. Como os pesos atuais do arquivo `model_mbnet_int8.tflite` foram treinados/ajustados sobre imagens com bordas mais ruidosas (amostragem pontual sem filtro de área), uma folha sadia excessivamente suavizada passa a apresentar textura semelhante à clorose difusa de `Viral Disease`.

### 4.2. O Efeito da Conversão de Cor (`ZeroFill` vs `BitRep` vs `RGB8888`)
- Quando mantemos a amostragem espacial e trocamos `RGB565 ZeroFill` por **`RGB8888 Nativo`** (Modos 2 e 4):
  - **`Healthy Leaves`** sobe de `41/50 (82%)` para **`45/50 (90%)` (+8%)**;
  - **`Banded Chlorosis`** sobe de `43/50 (86%)` para **`46/50 (92%)` (+6%)**;
  - **`Yellow Leaf`** sobe de `46/50 (92%)` para **`47/50 (94%)` (+2%)**.
- Em contrapartida, **`Viral Disease`** cai de `45/50` para `36/50` quando removemos o viés negativo de `-2,90` LSB do `ZeroFill`. Isso ocorre porque as fotos de `Viral Disease` possuem fundo claro estourado; o escurecimento artificial de `-2,90` níveis causado pelo *bug* do `ZeroFill` compensava acidentalmente a superexposição dessas fotos específicas nos limiares quantizados atuais da rede.

---

## 5. Arquitetura das Soluções Recomendadas para `src/image_processor.cpp`

Dependendo do objetivo priorizado no projeto (máxima velocidade sem alterar o domínio, máxima acurácia global imediata com o modelo atual, ou máxima fidelidade física de cor 24-bit para futuros treinamentos), temos **3 opções técnicas comprovadas**:

```mermaid
flowchart TD
    A["JPEG Input (768x1024)"] --> B{"Escolha da Arquitetura JPEGDraw()"}
    B -->|"Opção 1: Máxima Acurácia Imediata (82.73%)"| C["Modo 5: RGB565 + Box Averaging\n- PSNR Global: 38.2 dB (+11.1 dB)\n- smut: 4.5x mais acertos (9/50)\n- Pokkah Boeng: +12% (43/50)"]
    B -->|"Opção 2: Cor 24-bit Pura + Alta Velocidade"| D["Modo 4: RGB8888 Nativo + FastLUT\n- Erro de Cor: 0.00 (24-bit exato)\n- Tempo CPU Decode: -18.0% mais rápido\n- Healthy Leaves: 90% | Banded Chlorosis: 92%"]
    B -->|"Opção 3: Fidelidade Física Ideal (Para Retreino)"| E["Modo 7: RGB8888 Nativo + Box Averaging\n- PSNR Global: Infinito (Sinal Perfeito)\n- smut: 5x mais acertos (10/50)\n- Ideal se a rede for retreinada com Area Interpolation"]
```

### Opção 1: `RGB565 + Box Averaging` (Modo 5 — Maior Acurácia Global Imediata: `82.73%`)
Elimina o *aliasing* espacial tirando a média aritmética exata de todos os ~30,7 pixels que compõem cada célula do tensor `160×160`. É a única opção que **aumenta a acurácia global imediatamente sem precisar retreinar a rede** (`82.36% -> 82.73%`), recuperando **4,5x mais acertos em `smut`** e **+12% em `Pokkah Boeng`**.

### Opção 2: `RGB8888 Nativo + FastLUT` (Modo 4 — Cor 24-bit Exata + Redução de ~18% a 31% no Tempo de CPU + Zero RAM Extra)
Ativa `jpeg.setPixelType(RGB8888)` para extrair os 24 bits reais do JPEG (eliminando 100% da conversão `RGB565`) e pré-calcula uma tabela `target_src_x[160]` / `target_src_y[160]` na stack (640 bytes) para que o `JPEGDraw()` processe **apenas os 25.600 pixels úteis** em vez de 786.432 pixels (**redução de 96,7% nas escritas em PSRAM**).
- *(Variante 2B: A mesma `FastLUT` pode ser usada com `RGB565 ZeroFill` ou `RGB565 BitRep`, mantendo **100% bit-a-bit os mesmos resultados atuais** ou com Bit-Replication, mas cortando mais de 30% do tempo de CPU da função `JPEGDraw`!)*.

### Opção 3: `RGB8888 Nativo + Box Averaging` (Modo 7 — Padrão Ouro Físico de Sinal)
Combina a decodificação `RGB8888` nativa de 24 bits com a interpolação por área (*Box Averaging*). Produz a imagem matematicamente perfeita (`RMSE = 0.00`, `Bias = 0.00`), elevando `smut` para `10/50 (20%)`. Caso o modelo `model_mbnet_int8.tflite` passe por um *fine-tuning* futuro usando `cv2.INTER_AREA` / `PIL.Image.BOX`, esta implementação garante **100% de paridade matemática entre o treinamento em Python e a inferência no ESP32-S3**.

---

## 6. Referências Cruzadas no Projeto

- **Planilha Completa do Experimento (4.400 inferências = 550 amostras $\times$ 8 métodos):** [`model_inference_tests/resultado_comparativo_jpegdraw.csv`](file:///home/victor/projects/sugarcane/model_inference_tests/resultado_comparativo_jpegdraw.csv)
- **Relatório Estatístico e Matrizes de Confusão dos Métodos:** [`model_inference_tests/RELATORIO_COMPARATIVO_JPEGDRAW.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_COMPARATIVO_JPEGDRAW.md)
- **Relatórios das Baterias de Hardware Anteriores:**
  - [`model_inference_tests/RELATORIO_DESEMPENHO.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_DESEMPENHO.md) (Single-Core Sequencial)
  - [`model_inference_tests/RELATORIO_DESEMPENHO_DUALCORE.md`](file:///home/victor/projects/sugarcane/model_inference_tests/RELATORIO_DESEMPENHO_DUALCORE.md) (Dual-Core Assíncrono Pipelined)
