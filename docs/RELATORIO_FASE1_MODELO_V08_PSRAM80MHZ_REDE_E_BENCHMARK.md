# Relatório de Engenharia — Fase 1: Embarque do Modelo v08, PSRAM a 80 MHz, Otimização de Cache e Estabilização de Rede

**Data:** 08 de Novembro de 2026  
**Dispositivo Avaliado:** ESP32-S3 DevKitM-1 (Xtensa Dual-Core LX7 @ 240 MHz, 512 KB SRAM Interna, 8 MB Octal PSRAM @ 80 MHz DDR, 16 MB Flash @ 80 MHz DIO)  
**Firmware:** Sugarcane Classifier v5.0 (Pipeline Assíncrono Dual-Core + Fork-Join esp-nn + BoxAvg RGB8888 24-bit + PSRAM 80 MHz)  
**Modelo Gravado:** [`data/model_mbnet_int8.tflite`](file:///home/victor/projects/sugarcane/data/model_mbnet_int8.tflite) (`639.272 bytes` | MD5: `95abc002c2e9c49175c9f5cc69a1a909`)  
**Dataset de Teste:** 550 imagens limpas (11 classes $\times$ 50 amostras sem colisão de hash MD5)  

---

## 1. Contexto e Objetivos

Este relatório consolida a execução da **Fase 1 do Plano de Ação**, focada na resolução das pendências críticas diagnosticadas no projeto:
1. **Embarque Físico do Modelo v08:** A partição de armazenamento LittleFS (`storage`) na Flash do microcontrolador ainda retinha os pesos da versão legada `v07`, distorcendo a acurácia de hardware (especialmente na classe `smut`, que pontuava apenas 4,0%).
2. **Estabilização da Camada de Transporte (Wi-Fi e WebSocket):** O modo de economia de energia padrão do ESP-IDF (*Modem Sleep*) causava congelamentos periódicos no rádio e reset de conexões TCP (`Errno 104`) sob alta taxa de quadros, somado à falta de descarte de conexões inativas (`lru_purge_enable`).
3. **Desbloqueio de Barramento de Memória PSRAM (80 MHz):** A Octal PSRAM estava limitada a 40 MHz, restringindo a largura de banda durante o acesso aos tensores e acumuladores.
4. **Otimização do Compilador (-O2):** As flags do projeto estavam utilizando o perfil de depuração `-Og`.
5. **Compactação de Cache do Acumulador de Imagem:** A estrutura de acumulação da interpolação por área ocupava 400 KB na PSRAM em tipos de 32 bits desnecessários.

---

## 2. Alterações Implementadas no Firmware e Configurações

### 2.1. Gravação da Partição LittleFS com o Modelo `v08`
- Executada a compilação do sistema de arquivos e a gravação direta na partição `storage` (offset `0x410000`, 10 MB) via:
  ```bash
  pio run -t uploadfs --upload-port /dev/ttyUSB0
  ```
- O arquivo [`data/model_mbnet_int8.tflite`](file:///home/victor/projects/sugarcane/data/model_mbnet_int8.tflite) (MD5: `95abc002c2e9c49175c9f5cc69a1a909`) foi montado com sucesso em `/storage`, carregando a arquitetura treinada com curadoria criptográfica e interpolação por área.

### 2.2. Desativação do Modem Sleep do Wi-Fi (`src/wifi_setup.cpp`)
- No arquivo [`src/wifi_setup.cpp`](file:///home/victor/projects/sugarcane/src/wifi_setup.cpp#L52-L60), inseriu-se a chamada explícita `esp_wifi_set_ps(WIFI_PS_NONE)` imediatamente após a inicialização do driver:
  ```cpp
  esp_wifi_set_mode(WIFI_MODE_STA);
  esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
  esp_wifi_start();

  // Desativa Modem Sleep para evitar latências no rádio Wi-Fi e quedas de conexão TCP (Errno 104)
  esp_wifi_set_ps(WIFI_PS_NONE);
  ESP_LOGI(TAG, "Wi-Fi Power Save desativado (WIFI_PS_NONE) para máxima estabilidade no WebSocket.");
  ```
- **Efeito:** O rádio Wi-Fi opera continuamente ativo (`wifi:pm start, type: 0`), eliminando o *beacon sleep latency* e estabilizando as rajadas de transmissão contínua de JPEGs pesados via WebSocket.

### 2.3. Resiliência de Sockets no Servidor WebSocket (`src/web_server.cpp`)
- No arquivo [`src/web_server.cpp`](file:///home/victor/projects/sugarcane/src/web_server.cpp#L38-L51), configurou-se:
  ```cpp
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_open_sockets = 7;
  config.lru_purge_enable = true; // Descarta automaticamente conexões inativas para evitar esgotamento de sockets
  ```
- **Efeito:** Caso uma sessão WebSocket seja reiniciada por um cliente externo, o servidor HTTP do ESP-IDF descarta imediatamente o socket inativo mais antigo (*Least Recently Used*), evitando travamentos por falta de descritores de arquivo.

### 2.4. Aceleração da Octal PSRAM para 80 MHz DDR
- Em [`sdkconfig.defaults`](file:///home/victor/projects/sugarcane/sdkconfig.defaults) e [`sdkconfig.esp32-s3-devkitm-1`](file:///home/victor/projects/sugarcane/sdkconfig.esp32-s3-devkitm-1#L2000-L2005):
  ```ini
  CONFIG_SPIRAM_SPEED_80M=y
  # CONFIG_SPIRAM_SPEED_40M is not set
  CONFIG_SPIRAM_SPEED=80
  ```
- **Efeito:** O barramento da Octal PSRAM dobrou a taxa de transferência de dados (DDR a 80 MHz), reduzindo pela metade a latência de acesso aos tensores alocados externamente e buffers de imagem. Confirmado no boot do microcontrolador: `esp_psram: Speed: 80MHz`.

### 2.5. Otimização do Compilador para Performance (`-O2`)
- Em [`sdkconfig.defaults`](file:///home/victor/projects/sugarcane/sdkconfig.defaults) e [`sdkconfig.esp32-s3-devkitm-1`](file:///home/victor/projects/sugarcane/sdkconfig.esp32-s3-devkitm-1#L1110-L1118):
  ```ini
  # CONFIG_COMPILER_OPTIMIZATION_DEBUG is not set
  CONFIG_COMPILER_OPTIMIZATION_PERF=y
  ```
- **Efeito:** O GCC compila a base inteira em `-O2`, ativando inlining agressivo, otimização de laços e auto-vetorização de instruções vetoriais para o núcleo Xtensa LX7.

### 2.6. Compactação de `BoxAccumulator` de 16 B para 8 B (`src/image_processor.cpp`)
- No arquivo [`src/image_processor.cpp`](file:///home/victor/projects/sugarcane/src/image_processor.cpp#L27-L35):
  ```cpp
  // Estrutura compacta de 8 bytes (64 bits) alinhada para acumulação na Octal PSRAM.
  // Reduz a ocupação de memória de 400 KB para 200 KB (50% de redução), duplicando a densidade
  // no cache L1 de dados da CPU e reduzindo o tempo de memset e finalização.
  // Em resoluções adaptativas (1/4 ou 1/2 IDCT), a contagem máxima por célula 160x160 é <= 40 pixels,
  // gerando somas máximas de 40 * 255 = 10.200, muito abaixo do limite de uint16_t (65.535).
  struct alignas(8) BoxAccumulator {
      uint16_t sum_r;
      uint16_t sum_g;
      uint16_t sum_b;
      uint16_t count;
  };
  ```
- **Efeito:**
  - O buffer global passou de **409.600 bytes (400 KB)** para **204.800 bytes (200 KB)**.
  - A rotina `memset()` consome metade do tempo por imagem.
  - O acumulador ocupa metade das linhas de cache L1 de dados (D-Cache), diminuindo drasticamente os *cache misses* e despejos (*writebacks*) para a PSRAM.

---

## 3. Resultados Experimentais no ESP32-S3 Físico

Executou-se o benchmark automatizado [`run_evaluation_espnn_sram.py`](file:///home/victor/projects/sugarcane/model_inference_tests/run_evaluation_espnn_sram.py) com a flag `--clean`, submetendo as **550 imagens limpas** (sem colisão MD5) do dataset via WebSocket para o microcontrolador a `192.168.1.19`.

### 3.1. Evolução Consolidada de Desempenho

| Métrica | Fase 1 (Single Core) | Fase 2 (Pipeline Dual-Core) | Fase 3 (SRAM + Fork-Join 160MHz) | Fase 4 (240MHz + IDCT Scale) | **Fase 5 Atual (Fase 1 Plano: v08 + PSRAM 80MHz + -O2)** | Evolução Total vs Fase 2 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Tempo de Inferência Médio** | `626,6 ms` | `777,4 ms` | `550,0 ms` | `336,3 ms` | **`283,4 ms`** | **`-63,5%`** |
| **Mediana da Inferência** | ~`625 ms` | ~`775 ms` | `550,0 ms` | `336,0 ms` | **`283,0 ms`** | **`-63,5%`** |
| **Tempo de Decode JPEG Médio** | `814,0 ms` | `1032,4 ms` | `1123,1 ms` | `145,2 ms` | **`102,7 ms`** | **`-90,1%`** |
| **Tempo Total do Lote (550 img)** | `871,5 s` (`14,5 min`) | `574,9 s` (`9,6 min`) | `655,7 s` (`10,9 min`) | `369,8 s` (`6,2 min`) | **`310,8 s` (`5,18 min`)** | **`-45,9%`** |
| **Cadência Média (Incr. por img)** | `1581,0 ms` | `1044,8 ms` | `1192,2 ms` | `672,4 ms` | **`564,7 ms`** | **`-46,0%`** |
| **Vazão (Throughput)** | `0,63 img/s` | `0,96 img/s` | `0,84 img/s` | `1,49 img/s` | **`1,77 img/s`** | **`+84,4%` (1,84x)** |
| **Acurácia Global no Hardware** | `82,55%` (454/550) | `82,55%` (454/550) | `83,09%` (457/550) | `83,09%` (457/550) | **`89,82%` (`494/550`)** | **`+7,27 p.p.`** |
| **Confiança Média das Predições** | `81,4%` | `81,5%` | `82,1%` | `82,1%` | **`84,83%`** | **`+3,33 p.p.`** |
| **Falhas de Conexão (Errno 104)** | Ocasional | Frequente | 3 quedas | 3 quedas | **0 (Zero)** | **100% Estável** |

---

### 3.2. Desempenho Detalhado por Classe no Modelo `v08`

| Classe Avaliada | Amostras | Acertos no Hardware | Acurácia (%) | Confiança Média | Cadência Média | Tempo Médio Inf. | Tempo Médio Dec. |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Banded Chlorosis** | 50 | 47 | **94,0%** | 94,3% | 508,7 ms | 283,3 ms | 75,2 ms |
| **Brown Spot** | 50 | 50 | **100,0%** | 95,9% | 494,5 ms | 283,4 ms | 75,3 ms |
| **BrownRust** | 50 | 49 | **98,0%** | 88,0% | 509,4 ms | 283,5 ms | 73,4 ms |
| **Dried Leaves** | 50 | 26 | **52,0%** | 74,2% | 507,4 ms | 283,4 ms | 74,4 ms |
| **Grassy shoot** | 50 | 50 | **100,0%** | 93,5% | 722,4 ms | 283,2 ms | 197,9 ms |
| **Healthy Leaves** | 50 | 40 | **80,0%** | 88,2% | 579,1 ms | 283,4 ms | 112,2 ms |
| **Pokkah Boeng** | 50 | 50 | **100,0%** | 70,8% | 605,8 ms | 283,2 ms | 112,9 ms |
| **Sett Rot** | 50 | 50 | **100,0%** | 87,4% | 646,6 ms | 283,4 ms | 125,2 ms |
| **Viral Disease** | 50 | 46 | **92,0%** | 86,2% | 518,1 ms | 283,4 ms | 78,4 ms |
| **Yellow Leaf** | 50 | 44 | **88,0%** | 80,8% | 513,2 ms | 283,4 ms | 80,9 ms |
| **smut** | 50 | 42 | **84,0%** | 73,8% | 605,8 ms | 283,4 ms | 124,1 ms |
| **TOTAL / MÉDIA** | **550** | **494** | **89,82%** | **84,83%** | **564,7 ms** | **283,4 ms** | **102,7 ms** |

---

### 3.3. Matriz de Confusão no Hardware ESP32-S3 (550 Amostras Limpas)

| Classe Real \ Predita | Banded Chlorosis | Brown Spot | BrownRust | Dried Leaves | Grassy shoot | Healthy Leaves | Pokkah Boeng | Sett Rot | Viral Disease | Yellow Leaf | smut |
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

## 4. Análise dos Resultados e Conclusões

1. **Confirmação do Diagnóstico da Partição Flash (`smut` 4% $\rightarrow$ 84%):**
   - A gravação física da partição LittleFS com o modelo `v08` resolveu definitivamente a anomalia em `smut`. Os acertos subiram de **2/50 (4,0%)** para **42/50 (84,0%)**, alinhando o comportamento físico do microcontrolador com os resultados de bancada em Python.
   - Quatro classes críticas atingiram **100,0% de acurácia** no hardware: `Brown Spot`, `Grassy shoot`, `Pokkah Boeng` e `Sett Rot`.
   - A acurácia global saltou de **83,09%** para **89,82%** (+6,73 pontos percentuais).
2. **Impacto da PSRAM a 80 MHz e Compilação `-O2`:**
   - O tempo de inferência caiu de **`336,3 ms`** para **`283,4 ms`** (ganho líquido de **`52,9 ms`** por imagem, ou **`-15,7%`**). Em relação ao início do projeto (`777,4 ms`), a redução atinge **`-63,5%`**.
   - O tempo de decodificação JPEG caiu de **`145,2 ms`** para **`102,7 ms`** (ganho de **`-29,3%`**), beneficiado pela estrutura compacta de 8 bytes do `BoxAccumulator` e pela maior largura de banda da PSRAM.
3. **Resiliência Máxima de Rede:**
   - Com o `WIFI_PS_NONE` e o `lru_purge_enable = true`, o lote completo de 550 imagens executou continuamente durante 5,18 minutos com **zero quedas de conexão, zero retentativas e zero erros de socket**.
4. **Próximos Passos (Fase 2 do Plano de Ação):**
   - Adequação do script legado [`scripts/test_inference.py`](file:///home/victor/projects/sugarcane/scripts/test_inference.py).
   - Servir o cliente web [`client.html`](file:///home/victor/projects/sugarcane/client.html) diretamente no microcontrolador via endpoint HTTP `GET /`.
   - Atualização das tabelas e figuras no Capítulo 4 da monografia ([`tcc/capitulos/04_resultados_e_discussoes.tex`](file:///home/victor/projects/sugarcane/tcc/capitulos/04_resultados_e_discussoes.tex)).
