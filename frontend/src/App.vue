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
        <LiveInferenceCard :latest-diagnosis="latestDiagnosis" />
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

const latestDiagnosis = ref({
  id: 1,
  class_name: 'smut',
  confidence: 0.884,
  anomaly_alert: true,
  lat: -8.053891,
  lon: -34.881052,
  alt_m: 24.5,
  timing: {
    decode_ms: 102.7,
    inference_ms: 283.4,
    total_chip_ms: 386.1
  }
})

const inspections = ref([])

// Carrega dados iniciais simulados baseados na missão real de 55 waypoints do talhão
function loadInitialFieldData() {
  const baseLat = -8.05389
  const baseLon = -34.88105
  const sampleClasses = [
    { name: 'Healthy Leaves', conf: 0.96, alert: false },
    { name: 'Healthy Leaves', conf: 0.94, alert: false },
    { name: 'BrownRust', conf: 0.98, alert: true },
    { name: 'BrownRust', conf: 0.92, alert: true },
    { name: 'smut', conf: 0.84, alert: true },
    { name: 'smut', conf: 0.88, alert: true },
    { name: 'Pokkah Boeng', conf: 1.00, alert: true },
    { name: 'Sett Rot', conf: 1.00, alert: true },
    { name: 'Yellow Leaf', conf: 0.90, alert: true },
    { name: 'Grassy shoot', conf: 0.98, alert: true },
    { name: 'Banded Chlorosis', conf: 0.94, alert: true },
    { name: 'Healthy Leaves', conf: 0.98, alert: false }
  ]

  const list = []
  const now = Math.floor(Date.now() / 1000)

  for (let i = 0; i < 24; i++) {
    const row = Math.floor(i / 6)
    const col = i % 6
    const offsetLat = baseLat + (row * 0.00035) + (Math.random() * 0.00005)
    const offsetLon = baseLon + (col * 0.00045) + (Math.random() * 0.00005)
    const cls = sampleClasses[i % sampleClasses.length]

    list.push({
      id: i + 1,
      timestamp: now - (24 - i) * 12,
      class_name: cls.name,
      confidence: cls.conf,
      anomaly_alert: cls.alert,
      lat: offsetLat,
      lon: offsetLon,
      alt_m: 24.0 + Math.random() * 1.5,
      timing: {
        decode_ms: 101.5 + Math.random() * 3.0,
        inference_ms: 283.2 + Math.random() * 0.5,
        total_chip_ms: 384.7 + Math.random() * 3.5
      }
    })
  }

  inspections.value = list
  if (list.length > 0) {
    latestDiagnosis.value = list[list.length - 1]
  }
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
}

onMounted(() => {
  loadInitialFieldData()
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
