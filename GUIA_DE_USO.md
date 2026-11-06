# 🌿 Guia de Uso da Aplicação — Classificador de Doenças de Cana-de-Açúcar (ESP32-S3)

Este documento contém o passo a passo completo para utilizar o sistema após gravar o firmware e o modelo na memória do ESP32-S3.

---

## 📌 1. Checklist Pré-Inicialização

Antes de começar a usar, certifique-se de que foram gravados na placa:

1. **O Firmware compilado:**
   ```bash
   pio run -t upload
   ```
2. **O Sistema de Arquivos LittleFS (contendo o `data/model_mbnet_int8.tflite`):**
   ```bash
   pio run -t uploadfs
   ```

> [!IMPORTANT]
> Se o comando `uploadfs` não for executado, a ESP32 não encontrará o arquivo do modelo na partição de armazenamento `/storage` e o classificador não será inicializado.

---

## 🚀 2. Ligando a ESP32 e Obtendo o Endereço IP

1. Conecte a placa à porta USB do computador.
2. Abra o **Monitor Serial** (taxa de transmissão: **115200 baud**):
   ```bash
   pio device monitor
   ```
   *(Ou clique no ícone de tomada/plugue na barra inferior do VS Code).*
3. Ao ligar ou reiniciar a placa (botão **EN / RST**), você verá no terminal a confirmação de conexão Wi-Fi com o IP atribuído pelo seu roteador:

```text
========================================
 Wi-Fi Conectado com sucesso!
 Endereco IP: 192.168.1.150
========================================
```

> [!NOTE]
> Anote o endereço IP exibido (neste exemplo, `192.168.1.150`). O serviço WebSocket estará rodando em:  
> **`ws://192.168.1.150/ws`**

---

## 📡 3. Como Enviar Imagens para Classificação

A ESP32 opera como um servidor **WebSocket** na porta **80** sob a rota `/ws`. Ela aceita pacotes binários contendo a imagem em formato **JPEG/JPG** e devolve um texto formatado em **JSON**.

Abaixo estão as três maneiras mais fáceis de utilizar a aplicação:

---

### Opção A: Via Script Python no Computador (Recomendado para Testes Rápidos)

Você pode enviar imagens direto do seu terminal utilizando um cliente Python simples:

1. Instale a biblioteca de WebSocket no seu ambiente (se ainda não tiver):
   ```bash
   pip install websockets
   ```
2. Crie ou utilize o script de envio (ex: `enviar_foto.py`):

```python
import asyncio
import websockets
import json
import sys

ESP32_IP = "192.168.1.150"  # <-- Substitua pelo IP da sua placa
WS_URL = f"ws://{ESP32_IP}/ws"

async def classificar(caminho_imagem):
    print(f"Lendo imagem: {caminho_imagem}...")
    with open(caminho_imagem, "rb") as f:
        image_bytes = f.read()

    print(f"Conectando a {WS_URL}...")
    async with websockets.connect(WS_URL) as ws:
        print(f"Enviando imagem ({len(image_bytes)} bytes)...")
        await ws.send(image_bytes)

        print("Aguardando resposta da ESP32...")
        resposta = await ws.recv()
        dados = json.loads(resposta)

        print("\n" + "=" * 55)
        print(" RESPOSTA DA INFERÊNCIA NA ESP32-S3")
        print("=" * 55)
        print(f"Status:             {dados.get('status')}")
        print(f"Decodificação JPEG: {dados.get('decode_ms')} ms")
        print(f"Inferência Neural:  {dados.get('inferencia_ms')} ms")
        print("-" * 55)

        for item in dados.get("resultados", []):
            label = item["label"]
            score = item["score"] * 100
            barra = "█" * int(score / 5)
            print(f"  {label:<18} [{score:5.1f}%] {barra}")

if __name__ == "__main__":
    img = sys.argv[1] if len(sys.argv) > 1 else "data_teste.jpg"
    asyncio.run(classificar(img))
```

3. Execute passando o caminho de uma foto:
   ```bash
   python enviar_foto.py /caminho/para/folha.jpg
   ```

---

### Opção B: Via Página Web no Navegador (Interface Gráfica)

Você pode salvar o código HTML abaixo como `cliente.html` no seu computador e abri-lo com um duplo clique no Google Chrome ou Firefox:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Classificador de Doenças da Cana (ESP32-S3)</title>
  <style>
    body { font-family: sans-serif; max-width: 650px; margin: 30px auto; padding: 20px; }
    .card { border: 1px solid #ccc; border-radius: 8px; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    button { padding: 10px 20px; font-size: 16px; cursor: pointer; background: #28a745; color: white; border: none; border-radius: 4px; }
    .bar-container { background: #e9ecef; border-radius: 4px; height: 18px; margin: 4px 0 12px 0; }
    .bar { background: #007bff; height: 100%; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="card">
    <h2>🌿 Diagnóstico Foliar de Cana-de-Açúcar</h2>
    <label>IP da ESP32: </label>
    <input type="text" id="espIp" value="192.168.1.150" style="padding: 5px;"><br><br>
    
    <input type="file" id="fileInput" accept="image/jpeg"><br><br>
    <button onclick="enviar()">Enviar para Diagnóstico</button>

    <div id="status" style="margin-top: 15px; font-weight: bold;"></div>
    <div id="metricas" style="margin-top: 10px; color: #555;"></div>
    <div id="resultados" style="margin-top: 15px;"></div>
  </div>

  <script>
    function enviar() {
      const ip = document.getElementById('espIp').value;
      const file = document.getElementById('fileInput').files[0];
      if (!file) return alert("Selecione uma imagem JPEG primeiro!");

      const status = document.getElementById('status');
      status.innerText = "Conectando ao ESP32...";

      const ws = new WebSocket(`ws://${ip}/ws`);
      
      ws.onopen = () => {
        status.innerText = "Enviando imagem via WebSocket...";
        file.arrayBuffer().then(buffer => ws.send(buffer));
      };

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        status.innerText = "Diagnóstico Concluído!";
        document.getElementById('metricas').innerHTML = 
          `Tempo Decodificação JPEG: <b>${data.decode_ms} ms</b> | Tempo Inferência: <b>${data.inferencia_ms} ms</b>`;
        
        let html = "<h3>Probabilidades:</h3>";
        data.resultados.sort((a,b) => b.score - a.score);
        data.resultados.forEach(r => {
          const pct = (r.score * 100).toFixed(1);
          html += `<div><strong>${r.label}</strong>: ${pct}%</div>
                   <div class="bar-container"><div class="bar" style="width: ${pct}%"></div></div>`;
        });
        document.getElementById('resultados').innerHTML = html;
        ws.close();
      };

      ws.onerror = () => { status.innerText = "Erro ao conectar com a ESP32."; };
    }
  </script>
</body>
</html>
```

---

### Opção C: Via Ferramentas de Teste (Postman)

1. No Postman, crie uma nova requisição do tipo **WebSocket Request**.
2. No campo de endereço, informe: `ws://<IP_DA_ESP32>/ws`.
3. Clique em **Connect**.
4. Na aba de mensagem, selecione **Binary** $\rightarrow$ escolha um arquivo `.jpg` do seu computador.
5. Clique em **Send**. A resposta JSON será exibida no painel de mensagens recebidas.

---

## 📊 4. Estrutura do Retorno JSON

Quando a inferência é concluída, a ESP32 responde no seguinte formato:

```json
{
  "status": "sucesso",
  "decode_ms": 38,
  "inferencia_ms": 172,
  "resultados": [
    { "label": "Banded Chlorosis", "score": 0.0012 },
    { "label": "Brown Spot",       "score": 0.0150 },
    { "label": "BrownRust",        "score": 0.0005 },
    { "label": "Dried Leaves",     "score": 0.0031 },
    { "label": "Grassy shoot",     "score": 0.0008 },
    { "label": "Healthy Leaves",   "score": 0.9654 },
    { "label": "Pokkah Boeng",     "score": 0.0020 },
    { "label": "Sett Rot",         "score": 0.0003 },
    { "label": "Viral Disease",    "score": 0.0011 },
    { "label": "Yellow Leaf",      "score": 0.0082 },
    { "label": "smut",             "score": 0.0024 }
  ]
}
```

* **`decode_ms`:** Tempo em milissegundos gasto pela biblioteca `JPEGDEC` para decodificar o JPEG e redimensioná-lo para 160x160 pixels diretamente na PSRAM.
* **`inferencia_ms`:** Tempo em milissegundos gasto pela CPU do ESP32-S3 executando a rede neural no TensorFlow Lite Micro.
* **`score`:** Nível de certeza da rede neural para a respectiva doença (varia de `0.0000` a `1.0000`).

---

## 🛠️ 5. Resolução de Problemas Frequentes

| Sintoma / Mensagem | Causa Provável | Solução |
| :--- | :--- | :--- |
| **ESP32 não conecta no Wi-Fi** | Nome da rede ou senha divergentes. | Altere `WIFI_SSID` e `WIFI_PASS` em [`src/wifi_setup.cpp`](file:///home/victor/projects/sugarcane/src/wifi_setup.cpp#L11-L12) e faça novo upload. |
| **`status: "erro", "Falha no classificador"`** | O arquivo do modelo não está na partição LittleFS. | Certifique-se de que o arquivo está em `data/model_mbnet_int8.tflite` e rode `pio run -t uploadfs`. |
| **`status: "erro", "Falha ao ler JPEG"`** | Arquivo corrompido ou formato não suportado (ex: PNG, WebP). | Envie apenas imagens comprimidas em JPEG/JPG padrão. |
| **Conexão WebSocket recusada** | IP digitado incorretamente ou firewall bloqueando. | Verifique o IP impresso no Monitor Serial e garanta que o computador e a ESP32 estão no mesmo roteador/rede local. |
