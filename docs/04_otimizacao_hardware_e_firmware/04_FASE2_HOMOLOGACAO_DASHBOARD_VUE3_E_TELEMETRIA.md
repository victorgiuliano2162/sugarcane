# Relatório de Engenharia — Fase 2: Dashboard Web Vue.js 3, Telemetria Assíncrona e Persistência LittleFS no ESP32-S3

**Data de Conclusão:** 08 de Novembro de 2026  
**Dispositivo Físico:** ESP32-S3 DevKitM-1 (Xtensa Dual-Core LX7 @ 240 MHz, 8 MB Octal PSRAM @ 80 MHz DDR, 16 MB Flash LittleFS)  
**Endereço IP em Operação:** `192.168.1.19` (STA) / `192.168.4.1` (SoftAP)  
**Hostname mDNS:** `http://sugarcane.local`  
**Status do Firmware:** Gravado e Homologado em Hardware Físico com Sucesso  

---

## 1. Resumo Executivo das Entregas

A Fase 2 do projeto dotou o sistema de uma **interface gráfica moderna em Single Page Application (SPA) desenvolvida em Vue.js 3**, projetada para operar tanto em bancada de laboratório quanto **100% offline em campo** (no meio do talhão de cana-de-açúcar) sem qualquer dependência de sinal de celular ou servidores externos.

O firmware nativo do ESP32-S3 foi aprimorado com concorrência segura multitarefa, entregando:
1. **Modo Híbrido de Rede com Fallback Automático:** O dispositivo tenta associação à rede Station (STA) por 5 segundos; em caso de ausência de rede, inicializa imediatamente como **SoftAP autônomo** (`Sugarcane-AI-AP`, senha `sugarcane2026`) com resolução **mDNS** (`http://sugarcane.local`);
2. **Servidor Web Assíncrono de Baixa Prioridade no Core 0:** Configurado com **Prioridade 2 no FreeRTOS**, assegurando que requisições HTTP e streaming de assets nunca degradem a decodificação JPEG e a inferência neural (que operam na **Prioridade 5**);
3. **Pipeline de Compressão Gzip dos Assets Vue.js 3:** Todo o frontend compilado (Vue 3, Vite, Leaflet, Leaflet.heat, estilos e scripts) foi comprimido com Gzip nível 9, reduzindo o volume de 271,4 KB para **89,1 KB** e gravado na partição LittleFS de 10 MB (`/storage/www/`);
4. **Telemetria de Sistema a 1 Hz via WebSocket:** Transmissão contínua em tempo real de temperatura interna do chip (`driver/temperature_sensor.h`), memória livre na Octal PSRAM e SRAM interna, RSSI e cadência do pipeline;
5. **Auditoria Espacial Persistente em Flash (`/storage/inspections.csv`):** Cada classificação foliar realizada é automaticamente anexada ao arquivo CSV no LittleFS, com endpoint dedicado para download direto (`GET /api/export-csv`) compatível com software SIG (QGIS) e planilhas eletrônicas;
6. **Thread-Safety e Concorrência Serializada:** Implementação de mutex FreeRTOS (`s_ws_mutex`) para evitar corrupção de frames no protocolo WebSocket durante transmissões concorrentes entre a tarefa de telemetria e o pipeline de inferência.

---

## 2. Métricas de Hardware e Validação Empírica no ESP32-S3

A validação física foi executada diretamente na placa conectada via USB (`/dev/ttyUSB0`) em comunicação com o rádio Wi-Fi ativo.

### 2.1. Alocação de Memória no Boot
```
I (354) esp_psram: Found 8MB PSRAM device
I (358) esp_psram: Speed: 80MHz
I (835) cpu_start: cpu freq: 240000000 Hz
I (958) MAIN: LittleFS montado com sucesso em /storage
I (965) MAIN: Sensor termico interno ativado com sucesso.
I (1100) wifi:Set ps type: 0, coexist: 0
```
* **Octal PSRAM Livre:** **5,81 MB** (após carregar o modelo de 639 KB, buffers de arena TFLite e double buffer);
* **SRAM Interna Livre:** **120,2 KB** (com buffers SIMD de convolução mantidos em SRAM de alta velocidade);
* **Temperatura Interna da CPU:** **56,3 °C** a **57,3 °C** (estável sob clock máximo de 240 MHz e rádio contínuo `WIFI_PS_NONE`).

### 2.2. Teste de Classificação em Tempo Real via WebSocket
Submeteu-se uma amostra foliar real do dataset via WebSocket para avaliação do pipeline de ponta a ponta:
```json
{
  "status": "sucesso",
  "decode_ms": 86,
  "inferencia_ms": 283,
  "resultados": [
    {"label": "Brown Spot", "score": 0.4766},
    {"label": "Pokkah Boeng", "score": 0.2109},
    {"label": "Viral Disease", "score": 0.1523},
    {"label": "Yellow Leaf", "score": 0.1250},
    {"label": "Sett Rot", "score": 0.0156},
    {"label": "Healthy Leaves", "score": 0.0078},
    {"label": "smut", "score": 0.0078},
    {"label": "Grassy shoot", "score": 0.0039},
    {"label": "Banded Chlorosis", "score": 0.0000},
    {"label": "BrownRust", "score": 0.0000},
    {"label": "Dried Leaves", "score": 0.0000}
  ]
}
```
* **Tempo de Decodificação JPEG (Modo 7 Box-Averaging):** **86 ms**;
* **Tempo de Inferência TFLite Micro (Fork-Join Dual-Core):** **283 ms**;
* **Tempo Total de Processamento no Chip:** **369 ms**;
* **Vazão Teórica de Inferência:** **2,71 imagens por segundo**.

### 2.3. Auditoria Física do Arquivo CSV Gravado na Flash
Verificou-se o conteúdo gerado em `/storage/inspections.csv` via chamada HTTP `GET /api/export-csv`:
```csv
id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms
1,34,-8.053890,-34.881050,24.5,Brown Spot,0.4766,57.3,283,86
```
O registro comprovou a gravação atômica na partição Flash, preservando as métricas temporais, térmicas e de classificação.

---

## 3. Arquitetura do Frontend Vue.js 3 e Otimização Offline

### 3.1. Estrutura Modular dos Componentes
```
frontend/
├── index.html                   # HTML base com dark mode nativo (#0b0f19)
├── vite.config.js               # Empacotamento em bundle único sem fragmentação
├── package.json                 # Vue 3.5+, Vite 6, Leaflet 1.9, Leaflet.heat
└── src/
    ├── main.js                  # Ponto de entrada e injeção do CSS
    ├── style.css                # Design system responsivo sem frameworks pesados
    ├── App.vue                  # Gestor reativo global e auto-reconexão WebSocket
    └── components/
        ├── Navbar.vue           # Header com telemetria básica, IP e alerta térmico
        ├── TelemetryCards.vue   # Indicadores visuais de PSRAM, SRAM, CPU e GPS
        ├── LiveInferenceCard.vue# Diagnóstico recente com barra de confiança e tempos
        ├── MapViewer.vue        # Mapa híbrido (OSM Online / Dark Grid Offline) + Heatmap
        └── InspectionsTable.vue # Tabela com paginação, busca e download de CSV
```

### 3.2. Estatísticas de Compressão de Assets
| Arquivo | Tamanho Original | Tamanho Gzip | Taxa de Redução |
| :--- | :---: | :---: | :---: |
| `index.html` | 0,9 KB | 0,6 KB | **-35,7%** |
| `assets/style.css` | 25,8 KB | 8,9 KB | **-65,7%** |
| `assets/index.js` (com Leaflet) | 244,7 KB | 79,7 KB | **-67,4%** |
| **TOTAL CONSOLIDADO** | **271,4 KB** | **89,1 KB** | **-67,2%** |

Com cabeçalhos HTTP `Cache-Control: public, max-age=86400, immutable`, o navegador do smartphone ou computador realiza o download dos 89,1 KB apenas na primeira conexão, consumindo **zero bytes de banda de assets** nas interações subsequentes.

---

## 4. Camada de Comunicação e Rotas HTTP do Firmware

| Rota / Protocolo | Método | Tipo de Retorno | Finalidade no Sistema |
| :--- | :---: | :---: | :--- |
| `/` | `GET` | `text/html` (gzip) | Serve a aplicação SPA do Vue.js 3 |
| `/assets/*` | `GET` | `application/javascript` / `text/css` | Entrega os arquivos estáticos minificados com cache agressivo |
| `/api/status` | `GET` | `application/json` | Retorna status de conectividade, memória livre e RSSI do rádio |
| `/api/export-csv` | `GET` | `text/csv` | Realiza streaming direto do arquivo `/storage/inspections.csv` como anexo |
| `/ws` | `WebSocket` | Binário / Texto | Transporte bidirecional full-duplex de imagens, telemetria a 1 Hz e comandos |

---

## 5. Próximos Passos (Fase 3)

1. **Recepção e Soldagem do Módulo GPS NEO-6M:** Conexão aos pinos `GPIO 17` (RX) e `GPIO 18` (TX) na UART1 para substituir as coordenadas simuladas pelas coordenadas físicas de voo por satélite.
2. **Ensaios de Campo em Voo:** Acoplamento ao suporte do drone para avaliação da estabilidade do sinal Wi-Fi SoftAP e geração de mapas de infestação em talhões canavieiros de Pernambuco.
