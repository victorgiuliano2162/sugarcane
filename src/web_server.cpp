#include "web_server.h"
#include <cstring>
#include <cstdlib>
#include "esp_http_server.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

extern QueueHandle_t inference_queue;
static httpd_handle_t server = NULL;

static const char INDEX_HTML[] = R"rawliteral(<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sugarcane AI — Diagnóstico Foliar no ESP32-S3</title>
  <style>
    :root {
      --primary: #10b981;
      --primary-dark: #059669;
      --bg: #0f172a;
      --surface: #1e293b;
      --surface-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24px 16px;
    }
    .container {
      width: 100%;
      max-width: 680px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    header {
      text-align: center;
      padding: 12px 0;
    }
    header h1 {
      font-size: 1.6rem;
      font-weight: 700;
      color: #34d399;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }
    header p {
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-top: 6px;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      margin-top: 8px;
      background: #1e293b;
      border: 1px solid var(--surface-border);
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ef4444;
    }
    .dot.connected { background: #10b981; }
    .card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .upload-area {
      border: 2px dashed #475569;
      border-radius: 10px;
      padding: 28px 16px;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s;
      background: rgba(15, 23, 42, 0.4);
    }
    .upload-area:hover, .upload-area.dragover {
      border-color: var(--primary);
      background: rgba(16, 185, 129, 0.05);
    }
    .upload-icon {
      font-size: 2.2rem;
      margin-bottom: 8px;
    }
    .btn-row {
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }
    .btn {
      flex: 1;
      padding: 12px 18px;
      font-size: 0.95rem;
      font-weight: 600;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.2s;
    }
    .btn-primary {
      background: var(--primary);
      color: #022c22;
    }
    .btn-primary:hover:not(:disabled) {
      background: var(--primary-dark);
    }
    .btn-primary:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .btn-secondary {
      background: #334155;
      color: var(--text);
    }
    .btn-secondary:hover { background: #475569; }
    #previewImg {
      max-width: 100%;
      max-height: 260px;
      border-radius: 8px;
      margin-top: 12px;
      display: none;
      object-fit: contain;
      border: 1px solid var(--surface-border);
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 16px;
    }
    .metric-box {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 10px;
      text-align: center;
    }
    .metric-val {
      font-size: 1.25rem;
      font-weight: 700;
      color: #38bdf8;
    }
    .metric-lbl {
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 2px;
    }
    .result-section {
      margin-top: 16px;
      display: none;
    }
    .top-result {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.4);
      border-radius: 10px;
      padding: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .top-title {
      font-size: 1.15rem;
      font-weight: 700;
      color: #34d399;
    }
    .top-sub {
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .top-score {
      font-size: 1.5rem;
      font-weight: 800;
      color: #34d399;
    }
    .ranking-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .rank-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .rank-header {
      display: flex;
      justify-content: space-between;
      font-size: 0.85rem;
      font-weight: 500;
    }
    .bar-bg {
      background: #334155;
      height: 7px;
      border-radius: 4px;
      overflow: hidden;
    }
    .bar-fill {
      background: var(--primary);
      height: 100%;
      border-radius: 4px;
      width: 0%;
      transition: width 0.3s ease;
    }
    footer {
      text-align: center;
      font-size: 0.75rem;
      color: var(--text-muted);
      padding: 16px 0;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🌿 Sugarcane AI Classifier</h1>
      <p>Diagnóstico Foliar de Precisão em Borda • ESP32-S3 Dual-Core 240 MHz</p>
      <div class="status-badge" id="statusBadge">
        <span class="dot" id="statusDot"></span>
        <span id="statusText">Conectando ao WebSocket...</span>
      </div>
    </header>

    <div class="card">
      <div class="upload-area" id="dropArea" onclick="document.getElementById('fileInput').click()">
        <div class="upload-icon">📷</div>
        <div style="font-weight: 600; font-size: 1rem; margin-bottom: 4px;">Clique ou Arraste uma Foto da Folha</div>
        <div style="font-size: 0.8rem; color: var(--text-muted);">Formatos aceitos: JPEG / JPG</div>
        <input type="file" id="fileInput" accept="image/jpeg,image/jpg" style="display: none;">
      </div>
      <img id="previewImg" alt="Pré-visualização">

      <div class="btn-row">
        <button class="btn btn-secondary" onclick="document.getElementById('cameraInput').click()">
          📸 Câmera
        </button>
        <input type="file" id="cameraInput" accept="image/jpeg" capture="environment" style="display: none;">
        <button class="btn btn-primary" id="btnClassify" onclick="enviarImagem()" disabled>
          ⚡ Classificar no ESP32-S3
        </button>
      </div>

      <div class="result-section" id="resultSection">
        <div class="metrics-grid">
          <div class="metric-box">
            <div class="metric-val" id="valInf">-</div>
            <div class="metric-lbl">Inferência TFLite</div>
          </div>
          <div class="metric-box">
            <div class="metric-val" id="valDec">-</div>
            <div class="metric-lbl">Decodificação JPEG</div>
          </div>
          <div class="metric-box">
            <div class="metric-val" id="valTotal">-</div>
            <div class="metric-lbl">Tempo no ESP32</div>
          </div>
        </div>

        <div style="margin-top: 16px;">
          <div class="top-result">
            <div>
              <div class="top-title" id="topLabel">-</div>
              <div class="top-sub">Diagnóstico Fitossanitário Predominante</div>
            </div>
            <div class="top-score" id="topScore">-</div>
          </div>

          <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 8px;">
            Distribuição de Probabilidades (11 Classes):
          </div>
          <div class="ranking-list" id="rankingList"></div>
        </div>
      </div>
    </div>

    <footer>
      TCC Engenharia • MobileNetV3 Int8 v08 • Box Averaging Modo 7 • FreeRTOS
    </footer>
  </div>

  <script>
    let ws = null;
    let selectedBytes = null;

    function initWS() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host || '192.168.1.19';
      const url = `${proto}//${host}/ws`;

      ws = new WebSocket(url);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        document.getElementById('statusDot').className = 'dot connected';
        document.getElementById('statusText').innerText = `Online (${host})`;
        if (selectedBytes) document.getElementById('btnClassify').disabled = false;
      };

      ws.onclose = () => {
        document.getElementById('statusDot').className = 'dot';
        document.getElementById('statusText').innerText = 'Desconectado. Reconectando...';
        document.getElementById('btnClassify').disabled = true;
        setTimeout(initWS, 2000);
      };

      ws.onerror = (e) => {
        console.error('WS Error:', e);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          exibirResultados(data);
        } catch(e) {
          console.error('Falha ao processar resposta JSON:', e);
        }
      };
    }

    function carregarArquivo(file) {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        selectedBytes = e.target.result;
        const blob = new Blob([selectedBytes], { type: 'image/jpeg' });
        const img = document.getElementById('previewImg');
        img.src = URL.createObjectURL(blob);
        img.style.display = 'block';
        if (ws && ws.readyState === WebSocket.OPEN) {
          document.getElementById('btnClassify').disabled = false;
        }
      };
      reader.readAsArrayBuffer(file);
    }

    document.getElementById('fileInput').addEventListener('change', (e) => carregarArquivo(e.target.files[0]));
    document.getElementById('cameraInput').addEventListener('change', (e) => carregarArquivo(e.target.files[0]));

    const dropArea = document.getElementById('dropArea');
    ['dragenter', 'dragover'].forEach(eventName => {
      dropArea.addEventListener(eventName, (e) => { e.preventDefault(); dropArea.classList.add('dragover'); }, false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
      dropArea.addEventListener(eventName, (e) => { e.preventDefault(); dropArea.classList.remove('dragover'); }, false);
    });
    dropArea.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length) carregarArquivo(files[0]);
    });

    function enviarImagem() {
      if (!ws || ws.readyState !== WebSocket.OPEN || !selectedBytes) return;
      document.getElementById('btnClassify').disabled = true;
      document.getElementById('statusText').innerText = 'Processando no microcontrolador...';
      ws.send(selectedBytes);
    }

    function exibirResultados(data) {
      document.getElementById('statusText').innerText = `Online (${window.location.host})`;
      document.getElementById('btnClassify').disabled = false;

      const dec = data.decode_ms || 0;
      const inf = data.inferencia_ms || 0;
      document.getElementById('valDec').innerText = `${dec} ms`;
      document.getElementById('valInf').innerText = `${inf} ms`;
      document.getElementById('valTotal').innerText = `${dec + inf} ms`;

      const resultados = data.resultados || [];
      if (!resultados.length) return;

      resultados.sort((a, b) => b.score - a.score);
      const top = resultados[0];
      document.getElementById('topLabel').innerText = top.label;
      document.getElementById('topScore').innerText = `${(top.score * 100).toFixed(1)}%`;

      const rankingList = document.getElementById('rankingList');
      rankingList.innerHTML = '';

      resultados.forEach((item, index) => {
        const perc = (item.score * 100).toFixed(1);
        const div = document.createElement('div');
        div.className = 'rank-item';
        div.innerHTML = `
          <div class="rank-header">
            <span>${index + 1}. ${item.label}</span>
            <span>${perc}%</span>
          </div>
          <div class="bar-bg">
            <div class="bar-fill" style="width: ${perc}%"></div>
          </div>
        `;
        rankingList.appendChild(div);
      });

      document.getElementById('resultSection').style.display = 'block';
    }

    window.addEventListener('DOMContentLoaded', initWS);
  </script>
</body>
</html>)rawliteral";

static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t ws_handler(httpd_req_t *req) {
    if (req->method == HTTP_GET) return ESP_OK;

    httpd_ws_frame_t ws_pkt;
    memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
    ws_pkt.type = HTTPD_WS_TYPE_BINARY;
    
    esp_err_t ret = httpd_ws_recv_frame(req, &ws_pkt, 0);
    if (ret != ESP_OK) return ret;

    if (ws_pkt.len > 0) {
        uint8_t* buf = (uint8_t*)heap_caps_malloc(ws_pkt.len, MALLOC_CAP_SPIRAM);
        if (buf) {
            ws_pkt.payload = buf;
            ret = httpd_ws_recv_frame(req, &ws_pkt, ws_pkt.len);
            if (ret == ESP_OK) {
                InferenceRequest request = { buf, ws_pkt.len, httpd_req_to_sockfd(req) };
                xQueueSend(inference_queue, &request, portMAX_DELAY);
            } else {
                free(buf);
            }
        }
    }
    return ESP_OK;
}

void web_server_start() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_open_sockets = 7;
    config.lru_purge_enable = true; // Descarta automaticamente conexões inativas para evitar esgotamento de sockets
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t index_uri = {
            .uri        = "/",
            .method     = HTTP_GET,
            .handler    = index_handler,
            .user_ctx   = NULL,
            .is_websocket = false
        };
        httpd_register_uri_handler(server, &index_uri);

        httpd_uri_t ws_uri = {
            .uri        = "/ws",
            .method     = HTTP_GET,
            .handler    = ws_handler,
            .user_ctx   = NULL,
            .is_websocket = true
        };
        httpd_register_uri_handler(server, &ws_uri);
    }
}

void web_server_send_ws_text(int fd, const char* text) {
    if (!server) return;
    httpd_ws_frame_t ws_pkt;
    memset(&ws_pkt, 0, sizeof(httpd_ws_frame_t));
    ws_pkt.payload = (uint8_t*)text;
    ws_pkt.len = strlen(text);
    ws_pkt.type = HTTPD_WS_TYPE_TEXT;
    httpd_ws_send_frame_async(server, fd, &ws_pkt);
}
