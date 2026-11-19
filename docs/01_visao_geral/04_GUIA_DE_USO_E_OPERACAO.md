# 🌿 Guia de Uso da Aplicação — Classificador de Doenças de Cana-de-Açúcar (ESP32-S3)

Este documento contém o passo a passo completo para utilizar o sistema após gravar o firmware e o modelo na memória do ESP32-S3.

---

## 📌 1. Checklist Pré-Inicialização

Antes de começar a usar, certifique-se de que foram gravados na placa:

1. **O Firmware compilado:**
   ```bash
   pio run -t upload
   ```
2. **O Sistema de Arquivos LittleFS (contendo o `data/model_mbnet_int8.tflite` e o Dashboard Web em `data/www/`):**
   ```bash
   pio run -t uploadfs
   ```

> [!IMPORTANT]
> Se o comando `uploadfs` não for executado, a ESP32 não encontrará o arquivo do modelo na partição de armazenamento `/storage` e o classificador não será inicializado. Caso deseje alterar os fontes do frontend Vue 3 (`frontend/`), recompile e comprima os assets antes do upload executando:
> ```bash
> python3 scripts/build_and_compress_frontend.py
> pio run -t uploadfs
> ```

---

## 🚀 2. Ligando a ESP32 e Modos de Conectividade (STA, SoftAP e mDNS)

O firmware implementa arquitetura de rede híbrida com redundância automática:

1. **Modo Station (STA):** Ao ligar, o microcontrolador tenta conectar à rede Wi-Fi configurada durante 5 segundos. Com a conexão estabelecida, o IP é exibido no monitor serial (`pio device monitor`) e o dispositivo anuncia o domínio mDNS **`http://sugarcane.local`**.
2. **Modo SoftAP Autônomo (Fallback para Operação em Campo):** Caso a rede STA não responda ou em operação isolada no canavial, a ESP32 ativa seu próprio Ponto de Acesso Wi-Fi:
   * **SSID:** `Sugarcane-AI-AP`
   * **Senha:** `sugarcane2026`
   * **IP Fixo:** `192.168.4.1` (com resolução via `http://sugarcane.local`)

Ao abrir o terminal serial (115200 baud), uma das mensagens abaixo será confirmada:

```text
=======================================================
 MODO STATION (STA) CONECTADO COM SUCESSO!
 Endereco IP: 192.168.1.150
 Acesse o Dashboard em: http://192.168.1.150 ou http://sugarcane.local
=======================================================
```
*(ou)*
```text
=======================================================
 MODO SOFTAP ATIVADO!
 Conecte seu celular/PC no Wi-Fi: Sugarcane-AI-AP
 Senha: sugarcane2026
 Acesse o Dashboard em: http://192.168.4.1 ou http://sugarcane.local
=======================================================
```

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

### Opção B: Via Dashboard Web Vue.js 3 Embarcado (Recomendado — Sem Dependências)

O ESP32-S3 hospeda sua própria Single Page Application (SPA) em **Vue.js 3 + Leaflet**, comprimida com gzip na partição LittleFS.

1. Conecte o computador ou celular à mesma rede Wi-Fi (ou ao SoftAP `Sugarcane-AI-AP`).
2. Abra qualquer navegador moderno e acesse:
   * **`http://sugarcane.local`** (resolução mDNS automática)
   * Ou o IP exibido no boot: `http://192.168.1.150` (STA) ou `http://192.168.4.1` (SoftAP).

#### Recursos Nativos do Dashboard:
* **Telemetria de Silício em Tempo Real (1 Hz):** Monitoramento contínuo de temperatura interna do chip, memória SRAM/PSRAM livre, frequência de clock, status de conexão Wi-Fi e RSSI.
* **Diagnóstico Foliar Interativo:** Upload por arrastar-e-soltar (*drag & drop*) ou seleção de fotos JPEG, cálculo instantâneo da latência (decodificação + inferência neural) e alerta visual de anomalia fitopatológica com barras de probabilidade.
* **Cartografia GPS e Heatmap:** Visualização interativa no Leaflet com georreferenciamento de cada foto inspecionada no talhão e mapa de calor dos focos infecciosos.
* **Auditoria de Missão e Exportação CSV:** Tabela histórica paginada com botão de download direto para `/api/export-csv`, gerando arquivo compatível com QGIS e Excel.

*(Nota: Um cliente HTML legado para testes manuais rápidos em ambiente isolado pode ser construído via script WebSocket direto apontando para `ws://<IP_DA_ESP32>/ws`).*

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
| **ESP32 não conecta no Wi-Fi STA** | Nome da rede ou senha divergentes. | O firmware ativará automaticamente o SoftAP `Sugarcane-AI-AP` (192.168.4.1). Para reconfigurar o roteador, altere `WIFI_STA_SSID` e `WIFI_STA_PASS` em [`src/wifi_setup.cpp`](file:///home/victor/projects/sugarcane/src/wifi_setup.cpp#L12-L13) e faça novo upload. |
| **`status: "erro", "Falha no classificador"`** | O arquivo do modelo não está na partição LittleFS. | Certifique-se de que o arquivo está em `data/model_mbnet_int8.tflite` e rode `pio run -t uploadfs`. |
| **Dashboard web não abre no navegador** | Assets web não gravados na partição LittleFS. | Execute `python3 scripts/build_and_compress_frontend.py` seguido de `pio run -t uploadfs` para enviar os assets gzip para `/storage/www/`. |
| **`status: "erro", "Falha ao ler JPEG"`** | Arquivo corrompido ou formato não suportado (ex: PNG, WebP). | Envie apenas imagens comprimidas em JPEG/JPG padrão. |
| **Conexão WebSocket recusada** | IP digitado incorretamente ou firewall bloqueando. | Verifique o IP no Monitor Serial ou utilize a resolução automática por mDNS em `http://sugarcane.local`. |
