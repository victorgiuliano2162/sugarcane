<template>
  <div class="grid grid-cols-4">
    <!-- Card 1: Processador & Térmico -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>
          ESP32-S3 Dual-Core
        </span>
        <span class="badge badge-info">{{ telemetry.cpu_freq_mhz || 240 }} MHz</span>
      </div>
      <div class="stat-main">
        <span class="stat-value">{{ telemetry.chip_temp_c ? telemetry.chip_temp_c.toFixed(1) : '--' }}</span>
        <span class="stat-unit">°C</span>
      </div>
      <p class="stat-desc">Uptime: {{ formatUptime(telemetry.uptime_s) }}</p>
      <div class="meter-bar">
        <div class="meter-fill" :style="{ width: `${tempPercent}%`, background: tempColor }"></div>
      </div>
    </div>

    <!-- Card 2: Memória SRAM & PSRAM -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M6 19v-3"/><path d="M10 19v-3"/><path d="M14 19v-3"/><path d="M18 19v-3"/><path d="M6 5v3"/><path d="M10 5v3"/><path d="M14 5v3"/><path d="M18 5v3"/><rect x="2" y="8" width="20" height="8" rx="2"/></svg>
          Hierarquia de RAM
        </span>
        <span class="badge badge-success">80 MHz DDR</span>
      </div>
      <div class="stat-main">
        <span class="stat-value">{{ psramMbFree }}</span>
        <span class="stat-unit">MB livres (PSRAM)</span>
      </div>
      <div class="memory-row">
        <span>SRAM Interna (SIMD):</span>
        <span class="stat-bold">{{ sramKbFree }} KB</span>
      </div>
      <div class="meter-bar">
        <div class="meter-fill" :style="{ width: `${psramPercent}%`, background: '#38bdf8' }"></div>
      </div>
    </div>

    <!-- Card 3: Posicionamento GPS -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>
          Receptor GPS (NEO-6M)
        </span>
        <span class="badge" :class="gpsFix ? 'badge-success' : 'badge-warning'">
          {{ gpsFix ? 'Fix Válido' : 'Buscando' }}
        </span>
      </div>
      <div class="stat-main">
        <span class="stat-value">{{ telemetry.gps?.satellites || 0 }}</span>
        <span class="stat-unit">satélites ativos</span>
      </div>
      <p class="stat-coords" v-if="gpsFix">
        {{ telemetry.gps.lat.toFixed(5) }}, {{ telemetry.gps.lon.toFixed(5) }}
      </p>
      <p class="stat-desc" v-else>Aguardando visada da constelação</p>
      <p class="stat-desc" v-if="gpsFix">Alt: {{ telemetry.gps.alt_m?.toFixed(1) }}m</p>
    </div>

    <!-- Card 4: Taxa de Vazão e Pipeline TinyML -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>
          Cadência TinyML
        </span>
        <span class="badge badge-info">Modo 7 (24-bit)</span>
      </div>
      <div class="stat-main">
        <span class="stat-value">{{ (telemetry.fps_throughput || 1.77).toFixed(2) }}</span>
        <span class="stat-unit">img/s</span>
      </div>
      <p class="stat-desc">Ciclo Médio On-Chip: ~386 ms</p>
      <div class="pipeline-pills">
        <span class="pill-mini">Dec: ~102ms</span>
        <span class="pill-mini">Inf: ~283ms</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  telemetry: {
    type: Object,
    default: () => ({})
  }
})

const psramMbFree = computed(() => {
  const bytes = props.telemetry.psram_free_bytes || 7184320
  return (bytes / (1024 * 1024)).toFixed(2)
})

const psramPercent = computed(() => {
  const total = 8 * 1024 * 1024
  const free = props.telemetry.psram_free_bytes || 7184320
  return Math.min(100, Math.max(0, (free / total) * 100))
})

const sramKbFree = computed(() => {
  const bytes = props.telemetry.sram_free_bytes || 284160
  return (bytes / 1024).toFixed(0)
})

const gpsFix = computed(() => {
  return props.telemetry.gps?.fix ?? false
})

const tempPercent = computed(() => {
  const t = props.telemetry.chip_temp_c || 45
  return Math.min(100, Math.max(0, (t / 85) * 100))
})

const tempColor = computed(() => {
  const t = props.telemetry.chip_temp_c || 45
  if (t > 65) return '#ef4444'
  if (t > 55) return '#f59e0b'
  return '#10b981'
})

function formatUptime(seconds) {
  if (!seconds) return '00:00:00'
  const h = Math.floor(seconds / 3600).toString().padStart(2, '0')
  const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0')
  const s = Math.floor(seconds % 60).toString().padStart(2, '0')
  return `${h}:${m}:${s}`
}
</script>

<style scoped>
.stat-main {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
  margin: 0.5rem 0 0.25rem 0;
}

.stat-value {
  font-size: 1.85rem;
  font-weight: 700;
  color: #f8fafc;
  line-height: 1;
}

.stat-unit {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.stat-desc {
  font-size: 0.8rem;
  color: var(--text-dim);
  margin-top: 0.25rem;
}

.stat-coords {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #38bdf8;
  margin-top: 0.25rem;
}

.stat-bold {
  font-weight: 600;
  color: #f8fafc;
}

.memory-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.4rem;
}

.meter-bar {
  width: 100%;
  height: 4px;
  background: #1e293b;
  border-radius: 9999px;
  margin-top: 0.75rem;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  border-radius: 9999px;
  transition: width 0.3s ease;
}

.pipeline-pills {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.6rem;
}

.pill-mini {
  background: #1e293b;
  border: 1px solid var(--border-card);
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  color: #94a3b8;
  font-family: var(--font-mono);
}
</style>
