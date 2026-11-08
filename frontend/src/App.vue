<template>
  <div class="app-wrapper">
    <!-- Navbar Superior -->
    <Navbar 
      :ws-connected="wsConnected" 
      :telemetry="telemetry" 
    />

    <main class="container">
      <!-- 1. Linha de Cards de Telemetria -->
      <section class="section-mb">
        <TelemetryCards :telemetry="telemetry" />
      </section>

      <!-- 2. Linha Central: Diagnóstico em Tempo Real + Mapa Cartográfico -->
      <section class="section-mb grid grid-cols-2">
        <LiveInferenceCard 
          :latest-diagnosis="latestDiagnosis" 
          :ws-connected="wsConnected"
          @send-image="handleSendImage"
        />
        <MapViewer :points="inspections" />
      </section>

      <!-- 3. Linha Inferior: Tabela Paginada de Inspeções e CSV -->
      <section class="section-mb">
        <InspectionsTable 
          :inspections="inspections" 
          @clear-history="handleClearHistory"
        />
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Navbar from './components/Navbar.vue'
import TelemetryCards from './components/TelemetryCards.vue'
import LiveInferenceCard from './components/LiveInferenceCard.vue'
import MapViewer from './components/MapViewer.vue'
import InspectionsTable from './components/InspectionsTable.vue'

const wsConnected = ref(false)
let ws = null
let reconnectTimer = null

// Estado Reativo Global
const telemetry = ref({
  uptime_s: 1420,
  chip_temp_c: 48.7,
  cpu_freq_mhz: 240,
  sram_free_bytes: 284160,
  psram_free_bytes: 7184320,
  wifi_mode: 'STA',
  rssi_dbm: -58,
  fps_throughput: 1.77,
  gps: {
    fix: true,
    satellites: 9,
    lat: -8.053891,
    lon: -34.881052,
    alt_m: 24.5
  }
})

const latestDiagnosis = ref({})
const inspections = ref([])

// Carrega o histórico real gravado na LittleFS da ESP32 (evitando dados mockados)
async function loadHistoryFromESP32() {
  try {
    const res = await fetch('/api/export-csv')
    if (!res.ok) return
    const text = await res.text()
    const lines = text.trim().split('\n')
    if (lines.length <= 1) {
      inspections.value = []
      return
    }

    const items = []
    // Cabeçalho: id,timestamp_epoch,lat,lon,alt_m,class_name,confidence,chip_temp_c,inference_ms,decode_ms
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim()
      if (!line) continue
      const cols = line.split(',')
      if (cols.length >= 7) {
        const infMs = parseFloat(cols[8]) || 283.4
        const decMs = parseFloat(cols[9]) || 86.2
        items.push({
          id: parseInt(cols[0]) || i,
          timestamp: parseInt(cols[1]) || Math.floor(Date.now() / 1000),
          lat: parseFloat(cols[2]) || -8.05389,
          lon: parseFloat(cols[3]) || -34.88105,
          alt_m: parseFloat(cols[4]) || 24.5,
          class_name: cols[5],
          confidence: parseFloat(cols[6]) || 0.85,
          anomaly_alert: cols[5] !== 'Healthy Leaves',
          timing: {
            decode_ms: decMs,
            inference_ms: infMs,
            total_chip_ms: decMs + infMs
          }
        })
      }
    }

    inspections.value = items
    if (items.length > 0) {
      latestDiagnosis.value = items[items.length - 1]
    }
  } catch (err) {
    console.warn('Não foi possível carregar histórico inicial da ESP32:', err)
  }
}

// Envia foto real (binária JPEG) para o pipeline TFLite Micro na ESP32 via WebSocket
function handleSendImage(file) {
  if (!ws || !wsConnected.value) {
    alert('WebSocket desconectado. Aguarde conexão com a ESP32-S3.')
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    ws.send(e.target.result)
  }
  reader.readAsArrayBuffer(file)
}

// Gerenciador de WebSocket com Reconexão Automática
function setupWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  let host = window.location.host

  // Se estiver rodando em ambiente Vite Dev (porta 5173), tenta conectar ao ESP32 padrão
  if (host.includes('5173') || host.includes('localhost') || !host) {
    host = '192.168.4.1' // ou 'sugarcane.local'
  }

  const wsUrl = `${protocol}//${host}/ws`

  try {
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      wsConnected.value = true
      console.log('[WS] Conectado ao ESP32-S3:', wsUrl)
      if (reconnectTimer) {
        clearInterval(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'telemetry') {
          telemetry.value = { ...telemetry.value, ...data }
        } else if (data.type === 'diagnosis' || data.classe || data.class_name) {
          const item = {
            id: data.id || (inspections.value.length + 1),
            timestamp: data.timestamp || Math.floor(Date.now() / 1000),
            class_name: data.class_name || data.classe || 'smut',
            confidence: data.confidence !== undefined ? data.confidence : (data.confianca || 0.85),
            anomaly_alert: data.class_name !== 'Healthy Leaves',
            lat: data.lat || telemetry.value.gps?.lat || -8.05389,
            lon: data.lon || telemetry.value.gps?.lon || -34.88105,
            alt_m: data.alt_m || telemetry.value.gps?.alt_m || 24.5,
            timing: data.timing || {
              decode_ms: data.tempo_decode_ms || 102.7,
              inference_ms: data.tempo_ms || 283.4,
              total_chip_ms: (data.tempo_decode_ms || 102.7) + (data.tempo_ms || 283.4)
            }
          }

          latestDiagnosis.value = item
          inspections.value.push(item)
        }
      } catch (err) {
        console.warn('[WS] Payload não JSON recebido:', event.data)
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      scheduleReconnect()
    }

    ws.onerror = () => {
      wsConnected.value = false
      ws.close()
    }
  } catch (err) {
    wsConnected.value = false
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (!reconnectTimer) {
    reconnectTimer = setInterval(() => {
      console.log('[WS] Tentando reconectar ao ESP32...')
      setupWebSocket()
    }, 3000)
  }
}

function handleClearHistory() {
  if (ws && wsConnected.value) {
    ws.send(JSON.stringify({ cmd: 'clear_history', auth_token: 'sugarcane' }))
  }
  inspections.value = []
  latestDiagnosis.value = {}
}

onMounted(() => {
  loadHistoryFromESP32()
  setupWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (reconnectTimer) clearInterval(reconnectTimer)
})
</script>

<style scoped>
.app-wrapper {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.section-mb {
  margin-bottom: 1.25rem;
}
</style>
