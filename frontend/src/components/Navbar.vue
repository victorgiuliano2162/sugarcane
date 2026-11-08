<template>
  <header class="navbar">
    <div class="nav-brand">
      <div class="brand-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div>
        <h1 class="brand-title">Sugarcane AI</h1>
        <p class="brand-subtitle">ESP32-S3 Dual-Core Edge Telemetry</p>
      </div>
    </div>

    <div class="nav-metrics">
      <!-- Status Conexão WS -->
      <div class="metric-pill">
        <span class="status-dot" :class="wsConnected ? 'dot-online' : 'dot-offline'"></span>
        <span class="metric-label">{{ wsConnected ? 'WS Conectado' : 'WS Desconectado' }}</span>
      </div>

      <!-- Modo de Rede -->
      <div class="metric-pill">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
        <span class="metric-value">{{ telemetry.wifi_mode || 'STA' }}</span>
        <span class="metric-dim" v-if="telemetry.rssi_dbm">{{ telemetry.rssi_dbm }} dBm</span>
      </div>

      <!-- Temperatura da CPU -->
      <div class="metric-pill" :class="tempClass">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/></svg>
        <span class="metric-value">{{ telemetry.chip_temp_c ? telemetry.chip_temp_c.toFixed(1) : '--' }} °C</span>
      </div>

      <!-- IP / Host -->
      <div class="metric-pill host-pill">
        <span class="metric-mono">{{ hostDisplay }}</span>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  wsConnected: Boolean,
  telemetry: {
    type: Object,
    default: () => ({})
  }
})

const hostDisplay = computed(() => {
  return window.location.hostname || 'sugarcane.local'
})

const tempClass = computed(() => {
  const t = props.telemetry.chip_temp_c || 0
  if (t > 65) return 'pill-danger'
  if (t > 55) return 'pill-warning'
  return 'pill-success'
})
</script>

<style scoped>
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: #111827;
  border-bottom: 1px solid #1f293d;
  flex-wrap: wrap;
  gap: 1rem;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.brand-icon {
  width: 40px;
  height: 40px;
  border-radius: 0.5rem;
  background: rgba(16, 185, 129, 0.15);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #10b981;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #f8fafc;
}

.brand-subtitle {
  font-size: 0.75rem;
  color: #94a3b8;
}

.nav-metrics {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.metric-pill {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  background: #172136;
  border: 1px solid #273654;
  padding: 0.35rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8rem;
  color: #e2e8f0;
}

.metric-value {
  font-weight: 600;
}

.metric-dim {
  color: #64748b;
  font-size: 0.75rem;
}

.metric-mono {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #38bdf8;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-online {
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: pulse-slow 2s infinite;
}

.dot-offline {
  background: #ef4444;
  box-shadow: 0 0 8px #ef4444;
}

.pill-success { border-color: rgba(16, 185, 129, 0.4); color: #34d399; }
.pill-warning { border-color: rgba(245, 158, 11, 0.4); color: #fbbf24; }
.pill-danger  { border-color: rgba(239, 68, 68, 0.4);  color: #f87171; }
</style>
