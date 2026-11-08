<template>
  <div class="card live-card">
    <div class="card-header">
      <span class="card-title">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M2 12h20"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-6"/><path d="m4 8 16-4"/><path d="m4 16 16-4"/></svg>
        Último Diagnóstico em Tempo Real
      </span>
      <span class="badge" :class="alertBadgeClass">
        {{ latestDiagnosis.anomaly_alert ? 'Foco Detectado' : 'Folha Saudável' }}
      </span>
    </div>

    <div class="diagnosis-body" v-if="latestDiagnosis.class_name">
      <div class="diagnosis-primary">
        <div class="diag-header">
          <span class="diag-pt">{{ classTranslation(latestDiagnosis.class_name) }}</span>
          <span class="diag-en">({{ latestDiagnosis.class_name }})</span>
        </div>
        <div class="confidence-badge" :style="{ borderColor: confColor, color: confColor }">
          {{ (latestDiagnosis.confidence * 100).toFixed(1) }}%
        </div>
      </div>

      <!-- Barra de Confiança -->
      <div class="conf-meter">
        <div class="conf-fill" :style="{ width: `${latestDiagnosis.confidence * 100}%`, background: confColor }"></div>
      </div>

      <!-- Métricas de Latência On-Chip -->
      <div class="timing-grid">
        <div class="timing-item">
          <span class="timing-label">Decodificação JPEG</span>
          <span class="timing-val">{{ latestDiagnosis.timing?.decode_ms?.toFixed(1) || '102.7' }} ms</span>
        </div>
        <div class="timing-item">
          <span class="timing-label">Inferência INT8</span>
          <span class="timing-val">{{ latestDiagnosis.timing?.inference_ms?.toFixed(1) || '283.4' }} ms</span>
        </div>
        <div class="timing-item">
          <span class="timing-label">Ciclo no Chip</span>
          <span class="timing-val highlight">{{ latestDiagnosis.timing?.total_chip_ms?.toFixed(1) || '386.1' }} ms</span>
        </div>
      </div>

      <!-- Metadados de Posição -->
      <div class="geo-footer">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>
        <span>Lat: {{ latestDiagnosis.lat?.toFixed(5) || '-8.05389' }} | Lon: {{ latestDiagnosis.lon?.toFixed(5) || '-34.88105' }} | Alt: {{ latestDiagnosis.alt_m?.toFixed(1) || '24.5' }}m</span>
      </div>
    </div>

    <div class="diagnosis-empty" v-else>
      <div class="empty-icon pulse">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
      </div>
      <p class="empty-text">Aguardando rajada de inferência do pipeline...</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  latestDiagnosis: {
    type: Object,
    default: () => ({})
  }
})

const classTranslations = {
  'Healthy Leaves': 'Folha Sadia',
  'smut': 'Carvão da Cana',
  'BrownRust': 'Ferrugem Marrom',
  'Pokkah Boeng': 'Complexo Fusarium',
  'Yellow Leaf': 'Vírus do Amarelinho',
  'Sett Rot': 'Podridão de Toletes',
  'Grassy shoot': 'Proliferação em Touceira',
  'Banded Chlorosis': 'Clorose em Faixas',
  'Brown Spot': 'Mancha Parda',
  'Dried Leaves': 'Folha Seca / Senescência',
  'Viral Disease': 'Virose / Mosaico'
}

function classTranslation(name) {
  return classTranslations[name] || name || 'Diagnóstico'
}

const alertBadgeClass = computed(() => {
  return props.latestDiagnosis.anomaly_alert ? 'badge-danger' : 'badge-success'
})

const confColor = computed(() => {
  const c = props.latestDiagnosis.confidence || 0
  if (c >= 0.85) return '#10b981'
  if (c >= 0.70) return '#f59e0b'
  return '#ef4444'
})
</script>

<style scoped>
.live-card {
  display: flex;
  flex-direction: column;
}

.diag-header {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.diag-pt {
  font-size: 1.4rem;
  font-weight: 700;
  color: #f8fafc;
}

.diag-en {
  font-size: 0.85rem;
  color: #94a3b8;
  font-style: italic;
}

.diagnosis-primary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.25rem;
}

.confidence-badge {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  padding: 0.2rem 0.65rem;
  border-radius: 0.5rem;
  border: 1px solid;
  background: rgba(0, 0, 0, 0.2);
}

.conf-meter {
  width: 100%;
  height: 6px;
  background: #1e293b;
  border-radius: 9999px;
  margin: 0.85rem 0;
  overflow: hidden;
}

.conf-fill {
  height: 100%;
  border-radius: 9999px;
  transition: width 0.4s ease, background 0.4s ease;
}

.timing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
  background: #0f1626;
  border: 1px solid var(--border-card);
  border-radius: 0.5rem;
  padding: 0.75rem;
  margin-top: 0.5rem;
}

.timing-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.timing-label {
  font-size: 0.7rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.timing-val {
  font-size: 0.95rem;
  font-weight: 600;
  font-family: var(--font-mono);
  color: #cbd5e1;
}

.timing-val.highlight {
  color: #38bdf8;
}

.geo-footer {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
  margin-top: 0.85rem;
  padding-top: 0.65rem;
  border-top: 1px solid #1a253c;
}

.diagnosis-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2.5rem 1rem;
  color: var(--text-dim);
  gap: 0.75rem;
}

.empty-text {
  font-size: 0.875rem;
}
</style>
