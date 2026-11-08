# Especificação Técnica de Engenharia: Dashboard Web Vue.js 3, Telemetria Assíncrona e Cartografia GPS no ESP32-S3

**Documento:** Arquitetura de Software e Especificação de Requisitos  
**Projeto:** Sistema Autônomo de Diagnóstico Fitossanitário em Cana-de-Açúcar via TinyML  
**Alvo:** ESP32-S3 DevKitM-1 (Xtensa Dual-Core LX7 @ 240 MHz, 8 MB Octal PSRAM @ 80 MHz, 16 MB Flash LittleFS)  
**Data:** 08 de Novembro de 2026  
**Status:** Aprovado para Implementação  

---

## 1. Visão Geral e Objetivos do Sistema

O presente documento define a arquitetura, os protocolos de rede, o fluxo de dados em tempo real, a infraestrutura de armazenamento e os padrões de interface do **Dashboard Web Embarcado de Observabilidade e Controle de Missão**.

O sistema tem como finalidade fornecer ao operador de campo (via smartphone ou notebook) e à banca examinadora acadêmica uma interface moderna, responsiva, georreferenciada e autônoma, capaz de:
1. Operar **100% offline em campo** (meio do canavial sem cobertura celular) através de **SoftAP autônomo**, com fallback transparente para conexão à rede local (**Station/STA**) e resolução **mDNS** em ambiente de laboratório;
2. Servir uma **Single Page Application (SPA) em Vue.js 3** compactada diretamente a partir da partição Flash LittleFS de 10 MB, com consumo desprezível de banda;
3. Monitorar a saúde e telemetria da placa em tempo real (temperatura interna do chip, memória PSRAM/SRAM livre, status do rádio e cadência de quadros);
4. Integrar coordenadas espaciais oriundas de um módulo **GPS NEO-6M** conectado via UART à câmera e ao pipeline TinyML, indexando cada diagnóstico a uma coordenada geográfica `(latitude, longitude, altitude, timestamp)`;
5. Plotar os focos epidêmicos em mapa interativo **Leaflet** com alternância entre marcadores pontuais e mapas de calor (*Heatmap*), operando com camada híbrida inteligente (tiles online quando houver conexão ou malha cartesiana offline quando em campo);
6. Registrar o histórico contínuo em formato estruturado **CSV (`/storage/inspections.csv`)**, oferecendo visualização tabular paginada na interface e botão para download direto compatível com QGIS e Microsoft Excel;
7. Garantir **impacto nulo ou estritamente controlado sobre a inferência neural**, isolando a pilha web em tarefas de **baixa prioridade no FreeRTOS** e alocando buffers dinâmicos na **Octal PSRAM externa (80 MHz)** para blindar a SRAM interna dos aceleradores vetoriais SIMD.

---

## 2. Arquitetura de Conectividade e Camada de Rede

```
             +-----------------------------------------+
             |       Inicialização Wi-Fi (Boot)        |
             +-----------------------------------------+
                                  |
                                  v
             +-----------------------------------------+
             | Tenta conectar em modo Station (STA)    |
             | Credenciais salvas no NVS (Timeout: 5s) |
             +-----------------------------------------+
                                  |
                  +---------------+---------------+
                  |                               |
          [Conectado com Sucesso]          [Falha / Timeout]
                  |                               |
                  v                               v
   +------------------------------+ +------------------------------+
   |   Modo Station Ativo (STA)   | |  Modo SoftAP Autônomo Ativo  |
   |   IP atribuído via DHCP      | |  SSID: "Sugarcane-AI-AP"     |
   |   mDNS: "sugarcane.local"    | |  IP Fixo: 192.168.4.1        |
   |   Acesso via Rede Local      | |  DNS Captive Portal Ativo    |
   +------------------------------+ +------------------------------+
```

### 2.1. Algoritmo de Inicialização com Fallback Automático
O driver de rede ([`src/wifi_setup.cpp`](file:///home/victor/projects/sugarcane/src/wifi_setup.cpp)) deve executar o seguinte fluxo durante a inicialização:
1. **Fase 1 (Tentativa STA):** O ESP32 inicializa em modo `WIFI_MODE_STA` e tenta associar-se ao ponto de acesso configurado no NVS/código por uma janela máxima de **5,0 segundos**.
2. **Fase 2A (Sucesso STA):**
   * Registra o serviço mDNS no LwIP com o hostname `sugarcane.local`;
   * Registra o serviço `_http._tcp` na porta 80 e `_ws._tcp` na porta 80;
   * Imprime o endereço IP dinâmico atribuído pelo roteador.
3. **Fase 2B (Fallback para SoftAP):**
   * Se o timeout expirar sem obtenção de IP, o driver desliga o modo STA e inicializa em `WIFI_MODE_AP`;
   * Configuração do SoftAP:
     * **SSID:** `Sugarcane-AI-AP`
     * **Canal:** 6 (para mitigar interferências industriais)
     * **Autenticação:** `WIFI_AUTH_WPA2_PSK` (senha padrão: `sugarcane2026`) ou `WIFI_AUTH_OPEN` (configurável);
     * **IP Local Fixo:** `192.168.4.1` (Máscara: `255.255.255.0`);
     * **Servidor DHCP:** Ativo na faixa `192.168.4.2` a `192.168.4.10`;
     * **mDNS:** Ativo também no SoftAP respondendo em `http://sugarcane.local`.
4. **Captive Portal DNS (Opcional no SoftAP):** Um socket UDP na porta 53 responde a qualquer requisição de domínio não resolvido com o IP `192.168.4.1`, permitindo que smartphones abram o painel automaticamente ao conectar à rede Wi-Fi.

---

## 3. Frontend SPA em Vue.js 3 e Pipeline de Empacotamento Offline

### 3.1. Stack Tecnológico do Frontend
* **Framework:** Vue.js 3.4+ com Composition API (`<script setup>`);
* **Build Tool:** Vite 5+ (geração de bundle estático e tree-shaking agressivo);
* **Estilização:** CSS utilitário enxuto / TailwindCSS compilado com purga rigorosa (restando apenas classes utilizadas) ou PicoCSS minimalista (<10 KB);
* **Biblioteca Cartográfica:** Leaflet 1.9.4 embutido no bundle (sem requisição a CDN externa) + plugin `leaflet.heat`;
* **Ícones:** Lucide Icons em SVG inline (zero requisições de fontes externas como FontAwesome ou Google Fonts);
* **Totalmente Offline:** Nenhum recurso (estilos, fontes, scripts) depende de servidores externos.

### 3.2. Estratégia de Build, Compressão Gzip e LittleFS
1. O comando `npm run build` na pasta do frontend (`frontend/`) gera a pasta `dist/` com:
   * `index.html` (~2 KB);
   * `assets/app.[hash].js` (~110 KB minificado);
   * `assets/style.[hash].css` (~18 KB minificado);
   * `assets/leaflet.[hash].js` (~140 KB minificado).
2. Um script de pós-build (`scripts/compress_assets.py`) comprime todos os arquivos estáticos utilizando Gzip em nível máximo (nível 9):
   * `index.html` $\to$ `index.html.gz` (~0,8 KB);
   * `app.js` $\to$ `app.js.gz` (~28 KB);
   * `style.css` $\to$ `style.css.gz` (~4,5 KB);
   * `leaflet.js` $\to$ `leaflet.js.gz` (~38 KB);
   * **Tamanho total transferido via rede:** **< 75 KB**!
3. Os arquivos comprimidos são copiados para a pasta `data/www/` e gravados na partição LittleFS de 10 MB pelo PlatformIO:
   ```bash
   pio run -t uploadfs
   ```

### 3.3. Cabeçalhos de Resposta HTTP do Servidor Web
O servidor HTTP do ESP32 ([`src/web_server.cpp`](file:///home/victor/projects/sugarcane/src/web_server.cpp)) intercepta requisições a `/` e `/assets/*`, servindo diretamente o conteúdo `.gz` do LittleFS com os cabeçalhos:
```http
HTTP/1.1 200 OK
Content-Type: text/html (ou application/javascript / text/css)
Content-Encoding: gzip
Cache-Control: public, max-age=86400, immutable
Connection: close
```
**Impacto Operacional:** O navegador do operador armazena o aplicativo inteiro no cache local da primeira vez que carrega a página. Nas sessões seguintes, a carga na rede e na CPU do ESP32 para servir páginas é **zero**.

---

## 4. Camada de Comunicação: WebSocket Unificado e Endpoints REST

```
+---------------------------------------------------------------------------------------+
|                                    ESP32-S3 (Core 0)                                  |
|                                                                                       |
|  [ESP-IDF httpd Server (Prioridade 2)]                                                |
|       |                                                                               |
|       +---> GET /                   ---> Entrega index.html.gz (LittleFS)             |
|       +---> GET /assets/*           ---> Entrega JS/CSS comprimidos (LittleFS)        |
|       +---> GET /api/export-csv     ---> Streaming linha a linha de inspections.csv   |
|       |                                                                               |
|       +---> /ws (WebSocket Full-Duplex)                                               |
|                 ^                                                                     |
|                 |-- Telemetria Periódica (1 Hz JSON) ------------------------> [Vue]  |
|                 |-- Evento de Diagnóstico Foliar (JSON pós-inferência) -----> [Vue]  |
|                 |<-- Comandos de Missão (clear_history, trigger_shot, etc.) -- [Vue]  |
+---------------------------------------------------------------------------------------+
```

### 4.1. Canal WebSocket Unificado (`/ws`)
O mesmo servidor WebSocket atualmente utilizado para transporte de imagens bidirecionais atenderá a comunicação do dashboard no Core 0:

#### A. Pacote de Telemetria de Sistema (Enviado pelo ESP a cada 1.000 ms)
```json
{
  "type": "telemetry",
  "uptime_s": 1420,
  "chip_temp_c": 49.3,
  "cpu_freq_mhz": 240,
  "sram_free_bytes": 284160,
  "psram_free_bytes": 7184320,
  "wifi_mode": "STA",
  "rssi_dbm": -58,
  "fps_throughput": 1.77,
  "gps": {
    "fix": true,
    "satellites": 9,
    "lat": -8.053891,
    "lon": -34.881052,
    "alt_m": 24.5
  }
}
```

#### B. Pacote de Evento de Diagnóstico (Enviado imediatamente após cada inferência)
```json
{
  "type": "diagnosis",
  "id": 142,
  "timestamp": 1731070800,
  "class_id": 10,
  "class_name": "smut",
  "class_pt": "Carvão",
  "confidence": 0.884,
  "anomaly_alert": true,
  "lat": -8.053891,
  "lon": -34.881052,
  "alt_m": 24.5,
  "timing": {
    "decode_ms": 102.7,
    "inference_ms": 283.4,
    "total_chip_ms": 386.1
  }
}
```

#### C. Mensagens de Comando Vindo do Dashboard Web (Vue $\to$ ESP32)
```json
// Resetar / truncar arquivo de histórico na Flash
{ "cmd": "clear_history", "auth_token": "sugarcane" }

// Disparar captura e classificação sob demanda (se habilitado)
{ "cmd": "trigger_capture" }

// Alterar frequência de streaming de telemetria
{ "cmd": "set_telemetry_interval", "interval_ms": 2000 }
```

### 4.2. Endpoints REST Complementares
1. `GET /api/export-csv`:  
   * Abre o arquivo `/storage/inspections.csv` em modo somente leitura;
   * Transmite o conteúdo via streaming com chunks de 1.024 bytes alocados na PSRAM;
   * Define cabeçalhos:
     ```http
     Content-Type: text/csv; charset=utf-8
     Content-Disposition: attachment; filename="inspecoes_sugarcane_talhao.csv"
     ```
2. `GET /api/status`:  
   * Endpoint de saúde simples retornando JSON compacto caso o cliente queira verificar a conectividade antes de abrir o WebSocket.

---

## 5. Subsistema de Posicionamento Geográfico (GPS NEO-6M)

```
+----------------------------------------------------------------------------------+
|                              ESP32-S3 Hardware Layer                             |
|                                                                                  |
|   +-------------------+    UART1 (9600 8N1)     +----------------------------+   |
|   |  Módulo NEO-6M    |------------------------>|  GPIO 17 (U1_RXD)          |   |
|   |  Antena Ativa     |<------------------------|  GPIO 18 (U1_TXD - Opcional|   |
|   +-------------------+                         +----------------------------+   |
|                                                                |                 |
|                                                                v                 |
|                                                  +----------------------------+  |
|                                                  | gps_task (Core 0, Prio 3)  |  |
|                                                  | Ring Buffer na PSRAM       |  |
|                                                  | Parser NMEA ($GPRMC/$GPGGA)|  |
|                                                  +----------------------------+  |
|                                                                |                 |
|                                                                v                 |
|                                                  [gps_data_t Atômico / Mutex]    |
+----------------------------------------------------------------------------------+
```

### 5.1. Alocação de Pinos GPIO e Evitação de Conflitos
No ESP32-S3 DevKitM-1, os barramentos da Octal PSRAM/Flash (GPIOs 26 a 37) e do conector DVP da câmera OV3660 (D0-D7, PCLK, VSYNC, HREF, XCLK, I2C) consomem pinos específicos.
* **UART1 RX:** `GPIO 17` (não conflitante);
* **UART1 TX:** `GPIO 18` (não conflitante, utilizado apenas se for enviado comando de taxa UBX ao módulo);
* **Baud Rate:** `9600 bps` (padrão NMEA) ou configurável para `38400 bps` via comando de inicialização binário UBX.

### 5.2. Parser NMEA Assíncrono (`src/gps_driver.cpp`)
* Uma tarefa FreeRTOS de baixa prioridade (`gps_task`, prioridade 3, no Core 0) lê bytes da UART via driver de interrupção do ESP-IDF (`uart_driver_install`);
* Decodifica sentenças padrão **$GPGGA** (para latitude, longitude, altitude e número de satélites) e **$GPRMC** (para velocidade e validação de fix de posição);
* Mantém uma estrutura global protegida por *spinlock* ou leitura atômica:
  ```cpp
  typedef struct {
      bool fix_valid;
      uint8_t satellites;
      double latitude;
      double longitude;
      float altitude_m;
      uint32_t last_update_epoch;
  } gps_state_t;
  ```
* **Sincronização com o Diagnóstico Foliar:** No momento em que uma imagem chega para decodificação ou é capturada pelo sensor, o sistema realiza uma leitura atômica da estrutura `gps_state_t`, garantindo que as coordenadas correspondem exatamente à posição física do drone no instante da foto.

---

## 6. Persistência de Dados em Flash LittleFS: Formato e Ciclo de Vida do CSV

### 6.1. Esquema do Arquivo `/storage/inspections.csv`
Cada inferência realizada gera o acréscimo de uma linha formatada no arquivo CSV gravado na partição LittleFS:

```csv
id,timestamp_epoch,lat,lon,alt_m,satellites,class_id,class_name,confidence,chip_temp_c,inference_ms,decode_ms
1,1731070800,-8.053891,-34.881052,24.5,9,10,smut,0.840,49.2,283.4,102.7
2,1731070802,-8.053915,-34.881060,24.6,9,3,BrownRust,0.980,49.4,283.5,101.8
```

### 6.2. Gerenciamento de Memória Flash e Mitigação de Desgaste (*Wear-Leveling*)
* O LittleFS possui algoritmo nativo de nivelamento de desgaste (*Dynamic Wear-Leveling*), protegendo a vida útil dos blocos da memória SPI Flash;
* **Bufferização Inteligente na PSRAM:** Em vez de executar `fopen()`, `fprintf()` e `fclose()` a cada foto (o que causaria I/O de disco excessivo no barramento SPI durante o voo), o firmware acumula os registros em um buffer estático alocado na PSRAM (`inspections_write_buf`, 4 KB). O despejo em disco (*flush*) ocorre a cada 10 registros ou a cada 10 segundos de inatividade, minimizando os acessos à Flash.
* **Capacidade de Armazenamento:** Com 8 MB líquidos disponíveis no LittleFS e cada registro consumindo ~115 bytes, a memória comporta mais de **70.000 pontos georreferenciados**, o equivalente a centenas de missões de voo sem necessidade de limpeza.

---

## 7. Cartografia Interativa no Leaflet: Arquitetura Híbrida Online/Offline

```
+------------------------------------------------------------------------------------+
|                         Frontend Leaflet (Navegador Cliente)                       |
|                                                                                    |
|                     [Verifica Conectividade Externa (Probe)]                       |
|                                         |                                          |
|                +------------------------+------------------------+                 |
|                |                                                 |                 |
|     [Internet Disponível (STA)]                       [Sem Internet (SoftAP)]      |
|                |                                                 |                 |
|                v                                                 v                 |
|   +--------------------------+                      +--------------------------+   |
|   | Camada Base:             |                      | Camada Base:             |   |
|   | OpenStreetMap Tiles      |                      | Canvas / Dark Grid       |   |
|   | tile.openstreetmap.org   |                      | Eixos Métricos Cartesiano|   |
|   +--------------------------+                      +--------------------------+   |
|                \                                                 /                 |
|                 +-----------------------+-----------------------+                  |
|                                         |                                          |
|                                         v                                          |
|                     +---------------------------------------+                      |
|                     |     Camada Vetorial de Sobreposição   |                      |
|                     |  - Polígono Perimetral do Talhão      |                      |
|                     |  - Rota de Amostragem (Polyline)      |                      |
|                     |  - Marcadores Coloridos por Classe    |                      |
|                     |  - Mapa de Calor Dinâmico (Leaflet.heat)                     |
|                     +---------------------------------------+                      |
+------------------------------------------------------------------------------------+
```

### 7.1. Detecção Automática de Ambiente e Fallback de Camada Base
1. Na inicialização do componente de mapa (`MapViewer.vue`), o frontend dispara um *probe* assíncrono para carregar uma imagem leve (ex.: um tile do OSM) com timeout estrito de **800 ms**.
2. **Cenário Online (Modo STA com Acesso à Internet):** O Leaflet ativa a camada `L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')` convencional, permitindo visualização de ruas, relevo ou imagens de satélite.
3. **Cenário Offline (Modo SoftAP em Campo):** Se o probe falhar ou der timeout, o Leaflet instancia uma camada base em **Canvas vetorial estilizado (Dark Grid)**:
   * Fundo escuro profissional (`#0f172a`) com linhas de grade graduadas em intervalos de latitude/longitude e escala métrica;
   * Sobreposição do polígono perimetral do Talhão canavieiro (obtido a partir do arquivo GeoJSON de planejamento da missão);
   * **Zero chamadas externas, zero erros 404 e zero sobrecarga para o ESP32-S3.**

### 7.2. Camadas Interativas de Diagnóstico
O mapa disponibiliza ao operador um painel de controle de camadas (*Layer Control*):
1. **Camada de Marcadores Pontuais (*Markers*):** Círculos coloridos dispostos no ponto exato da amostragem:
   * **Verde:** Folha Saudável (*Healthy*);
   * **Vermelho/Preto:** Foco de Carvão (*smut*) ou Podridão de Toletes (*Sett Rot*);
   * **Laranja:** Ferrugem Marrom (*BrownRust*);
   * **Amarelo:** *Yellow Leaf* ou *Banded Chlorosis*;
   * **Azul:** *Pokkah Boeng*;
   * **Ao clicar no marcador:** Abre popup contendo a foto miniatura do diagnóstico, nome científico da doença, acurácia em percentual, altitude do voo, lat/lon e horário do evento.
2. **Camada de Mapa de Calor (*Heatmap*):**
   * Utiliza a biblioteca compacta `leaflet.heat` (embutida no bundle);
   * Agrupa as detecções patológicas e pondera os núcleos com base no score de confiança (`[lat, lon, confidence]`);
   * Gera gradiente visual instantâneo (verde $\to$ amarelo $\to$ vermelho) destacando visualmente as reboleiras de infestação no talhão para tomada rápida de decisão agronômica.
3. **Filtro Rápido por Legenda:** O usuário pode clicar em uma classe na legenda (ex.: ocultar todas as folhas sadias) para isolar visualmente apenas os focos de Carvão ou Ferrugem.

---

## 8. Componente de Exibição Tabular com Paginação e Exportação

### 8.1. Arquitetura de Paginação no Cliente (*Client-Side Pagination*)
Para o volume típico de missões de inspeção (50 a 500 fotos), todo o histórico do dia é transmitido via JSON na abertura do WebSocket ou via requisição REST única e mantido reativamente no estado do Vue 3 (`Pinia` ou `reactive state`):
* **Renderização Otimizada:** A tabela exibe apenas o subconjunto ativo (10, 25 ou 50 itens por página);
* **Recursos do Componente:**
  * Seletor de quantidade de linhas por página;
  * Botões de navegação: *Primeira*, *Anterior*, *Página Atual / Total*, *Próxima*, *Última*;
  * Campo de busca textual rápida (filtra instantaneamente por ID, classe ou data);
  * Ordenação clicável nos cabeçalhos da tabela (ex.: ordenar por confiança decrescente ou por maior latência);
  * Badges visuais de confiança com código de cores:
    * **Verde:** Confiança $\ge 85\%$;
    * **Amarelo:** Confiança entre $70\%$ e $84\%$;
    * **Vermelho:** Confiança $< 70\%$.
* **Botão de Exportação Direta:** Dispara chamada ao endpoint `/api/export-csv`, realizando o download do arquivo de auditoria física sem qualquer reprocessamento no browser.

---

## 9. Arquitetura de Concorrência FreeRTOS e Isolamento de Recursos na PSRAM

```
===================================================================================
                             MAPA DE PRIORIDADES FREERTOS
===================================================================================
Prioridade 5 (Crítica)  : [decode_task (Core 0)]     [inference_task (Core 1)]
Prioridade 3 (Média)    : [gps_task (Core 0)]
Prioridade 2 (Baixa)    : [httpd_server (Core 0 - Web, Sockets, CSV Streaming)]
===================================================================================

===================================================================================
                             POLÍTICA DE ALOCAÇÃO DE MEMÓRIA
===================================================================================
SRAM Interna (512 KB)   : RESERVADA para SIMD Xtensa LX7 (48 KB Scratch Buffers)
                          e Pilha de DMA de Rede / Câmera
-----------------------------------------------------------------------------------
Octal PSRAM (8 MB @ 80M): Alocação de Tensores TFLite (~550 KB)
                          Double Buffering de Imagem ($2 \times 76,8$ KB)
                          Acumuladores Box-Averaging (~200 KB)
                          Buffers WebSocket e Chunks HTTP/CSV (Dedicado)
===================================================================================
```

### 9.1. Alocação Exclusiva em PSRAM para a Camada Web
Para assegurar conformidade com a diretriz do projeto (onde as atividades web são assíncronas e não prioritárias), **toda e qualquer estrutura de dados do servidor web, do WebSocket e dos buffers de streaming de CSV será alocada na Octal PSRAM externa**:
```c
// Alocação de buffer de streaming de CSV (1.024 bytes)
char* csv_chunk = (char*)heap_caps_malloc(1024, MALLOC_CAP_SPIRAM);

// Alocação de buffer do frame JSON de telemetria
char* telemetry_json = (char*)heap_caps_malloc(512, MALLOC_CAP_SPIRAM);
```

### 9.2. Ajuste de Prioridade no `esp_http_server`
No arquivo [`src/web_server.cpp`](file:///home/victor/projects/sugarcane/src/web_server.cpp), a configuração do servidor HTTP será ajustada com:
```cpp
httpd_config_t config = HTTPD_DEFAULT_CONFIG();
config.task_priority = 2;              // Baixa prioridade (abaixo de decode e inferência, que rodam em 5)
config.core_id = 0;                    // Fixado no Core 0 (preserva o Core 1 100% livre para inferência)
config.stack_size = 8192;
config.max_open_sockets = 7;
config.lru_purge_enable = true;        // Descarta sockets inativos automaticamente
```
**Resultado de Engenharia:** Caso o ESP32-S3 esteja processando um bloco de decodificação JPEG com média de caixa ou executando o pipeline de amostragem em voo, a entrega da página web ou a atualização do gráfico é temporariamente preterida em favor da tarefa de visão computacional, eliminando qualquer risco de atraso na cadeia de inferência em tempo real.

---

## 10. Matriz de Pendências e Decisões em Aberto

| Item | Descrição da Pendência | Status Atual | Ação Futura Planejada |
| :--- | :--- | :---: | :--- |
| **P-01** | **Modo de Operação de Missão: Disparo Manual vs. Autônomo Contínuo** | **Pendente de Decisão** | A interface conterá modularidade no componente de controle para expor botão de disparo pontual (*Single Shot*) ou chave de modo contínuo (*Periodic Scan*) assim que os testes de bancada definirem a dinâmica operacional preferida pelo usuário. |
| **P-02** | **Taxa de Amostragem do GPS NEO-6M** | Em validação | O padrão NMEA é 1 Hz (1 atualização/segundo). Avaliar se comandos binários UBX para 5 Hz trazem ganhos à velocidade de cruzeiro do drone. |
| **P-03** | **Polígono Geográfico do Talhão Oficial (GeoJSON)** | Aguardando coordenadas | O componente Leaflet aceitará a injeção do arquivo GeoJSON do polígono real do talhão da Zona da Mata pernambucana para plotagem do perímetro. |

---

## 11. Cronograma de Implementação em Fases

```
[Fase 2.1: Infraestrutura de Firmware C++]
  ├── Driver GPS UART1 com parser NMEA assíncrono (GPIO 17/18)
  ├── Gerenciador de armazenamento LittleFS (/storage/inspections.csv)
  └── Ajuste do Wi-Fi (Modo STA com fallback para SoftAP) e mDNS

[Fase 2.2: Camada de API e WebSocket no Core 0]
  ├── Stream de telemetria periódica (JSON a 1 Hz com dados de GPS e sensores)
  ├── Endpoints HTTP GET /api/export-csv e handlers de assets comprimidos
  └── Alocação de buffers em MALLOC_CAP_SPIRAM e prioridade 2 no FreeRTOS

[Fase 2.3: Desenvolvimento do Frontend Vue.js 3]
  ├── Setup do projeto Vite + Vue 3 (Composition API) + TailwindCSS
  ├── Componente TelemetryCards.vue (temperatura, RAM, satélites, FPS)
  ├── Componente MapViewer.vue (Leaflet híbrido com marcadores e heatmap)
  └── Componente InspectionsTable.vue (paginação no cliente, busca, download CSV)

[Fase 2.4: Empacotamento, Gravação na Flash e Homologação Física]
  ├── Pipeline de build + compressão Gzip dos assets estáticos
  ├── Gravação na partição LittleFS (uploadfs)
  └── Ensaio completo em bancada: validação de fallback AP/STA, GPS e inferência
```

---

## 12. Conclusão

Esta especificação assegura o equilíbrio exato entre sofisticação visual, utilidade agronômica de campo e respeito rigoroso às limitações de tempo real do microcontrolador ESP32-S3. Com a segregação das tarefas web na PSRAM em baixa prioridade e o empacotamento offline do Vue 3, o sistema alcança status de produto de engenharia completo, robusto e perfeitamente demonstrável na banca de defesa do TCC no IFPE.
