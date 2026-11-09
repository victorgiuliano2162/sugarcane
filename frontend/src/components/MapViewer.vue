<template>
  <div class="card map-card">
    <div class="card-header">
      <div class="header-left">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
          Mapeamento Espacial de Focos (Talhão Georreferenciado)
        </span>
        <span class="badge" :class="isOnline ? 'badge-info' : 'badge-neutral'">
          {{ isOnline ? (mapType === 'osm' ? 'Mapa Vetorial (OSM)' : 'Satélite (Esri)') : 'Modo Offline (Grid)' }}
        </span>
      </div>

      <div class="map-controls">
        <button v-if="isOnline" class="btn btn-secondary btn-sm" @click="toggleMapType">
          {{ mapType === 'osm' ? 'Alternar para Satélite' : 'Alternar para Mapa Vetorial' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="toggleHeatmap" :class="{ 'btn-active': showHeatmap }">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
          {{ showHeatmap ? 'Ocultar Heatmap' : 'Exibir Heatmap' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="fitAllPoints" title="Ajustar enquadramento">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M21 3l-7 7"/><path d="M3 21l7-7"/></svg>
          Centralizar
        </button>
      </div>
    </div>

    <!-- Filtros por Patologia na Legenda -->
    <div class="filter-legend">
      <span class="legend-title">Filtros:</span>
      <button 
        v-for="(color, cls) in classColors" 
        :key="cls" 
        class="legend-pill"
        :class="{ 'pill-dimmed': activeFilter && activeFilter !== cls }"
        @click="toggleFilter(cls)"
      >
        <span class="legend-dot" :style="{ background: color }"></span>
        <span class="legend-name">{{ cls }}</span>
        <span class="legend-count">{{ countByClass(cls) }}</span>
      </button>
      <button v-if="activeFilter" class="btn-clear-filter" @click="activeFilter = null">
        Limpar Filtro
      </button>
    </div>

    <!-- Container do Mapa Leaflet -->
    <div ref="mapContainer" class="leaflet-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import L from 'leaflet'
import 'leaflet.heat'

const props = defineProps({
  points: {
    type: Array,
    default: () => []
  }
})

const mapContainer = ref(null)
let map = null
let markersLayer = null
let heatLayer = null
let baseTileLayer = null

const isOnline = ref(false)
const showHeatmap = ref(false)
const activeFilter = ref(null)
const mapType = ref('osm') // 'osm' (vetorial padrão) ou 'satellite'

const classColors = {
  'smut': '#dc2626',            // Carvão (Vermelho intenso)
  'BrownRust': '#ea580c',        // Ferrugem Marrom (Laranja ferro)
  'Pokkah Boeng': '#3b82f6',     // Complexo Fusarium (Azul)
  'Sett Rot': '#7c3aed',         // Podridão de Toletes (Roxo escuro)
  'Yellow Leaf': '#eab308',      // Amarelinho (Amarelo)
  'Banded Chlorosis': '#d97706', // Clorose em Faixas (Âmbar)
  'Brown Spot': '#9333ea',       // Mancha Parda (Violeta)
  'Grassy shoot': '#06b6d4',     // Touceira (Ciano)
  'Dried Leaves': '#78716c',     // Folha Seca (Cinza quente)
  'Viral Disease': '#ec4899',    // Virose (Rosa)
  'Healthy Leaves': '#10b981'    // Sadia (Verde esmeralda)
}

function countByClass(cls) {
  return props.points.filter(p => p.class_name === cls).length
}

function toggleFilter(cls) {
  if (activeFilter.value === cls) {
    activeFilter.value = null
  } else {
    activeFilter.value = cls
  }
  renderPoints()
}

function toggleHeatmap() {
  showHeatmap.value = !showHeatmap.value
  renderPoints()
}

function toggleMapType() {
  mapType.value = mapType.value === 'satellite' ? 'osm' : 'satellite'
  updateBaseLayer()
}

function updateBaseLayer() {
  if (!map) return
  if (baseTileLayer) {
    map.removeLayer(baseTileLayer)
    baseTileLayer = null
  }

  if (isOnline.value) {
    if (mapType.value === 'satellite') {
      // Esri World Imagery (Satélite Agrícola de Alta Resolução - 100% Livre de Chave)
      baseTileLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 19,
        attribution: 'Esri World Imagery'
      }).addTo(map)
    } else {
      // OpenStreetMap Padrão (Sem chave de API)
      baseTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap contributors'
      }).addTo(map)
    }
  } else {
    // Grid Cartesiano Escuro Procedural Offline (para operação sem internet no talhão)
    const GridLayer = L.GridLayer.extend({
      createTile: function(coords) {
        const tile = document.createElement('canvas')
        tile.width = 256
        tile.height = 256
        const ctx = tile.getContext('2d')
        ctx.fillStyle = '#0b1120'
        ctx.fillRect(0, 0, 256, 256)
        ctx.strokeStyle = '#1e293b'
        ctx.lineWidth = 1
        ctx.strokeRect(0, 0, 256, 256)
        ctx.fillStyle = '#475569'
        ctx.font = '10px monospace'
        ctx.fillText(`Talhão [${coords.x}, ${coords.y}]`, 12, 20)
        return tile
      }
    })
    baseTileLayer = new GridLayer().addTo(map)
  }

  if (baseTileLayer) {
    baseTileLayer.bringToBack()
  }
}

async function checkOnlineConnectivity() {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 1000)
    await fetch('https://tile.openstreetmap.org/0/0/0.png', {
      method: 'HEAD',
      mode: 'no-cors',
      signal: controller.signal
    })
    clearTimeout(timeoutId)
    isOnline.value = true
  } catch (err) {
    isOnline.value = false
  }
}

onMounted(async () => {
  await checkOnlineConnectivity()
  initMap()
  renderPoints()
})

watch(() => props.points, () => {
  renderPoints()
}, { deep: true })

function initMap() {
  if (!mapContainer.value) return

  // Coordenadas iniciais padrão (Talhão Pernambuco / Zona da Mata)
  const defaultCenter = [-8.05389, -34.88105]
  map = L.map(mapContainer.value, {
    center: defaultCenter,
    zoom: 16,
    zoomControl: true,
    attributionControl: false
  })

  updateBaseLayer()
  markersLayer = L.layerGroup().addTo(map)
}

function renderPoints() {
  if (!map || !markersLayer) return

  markersLayer.clearLayers()
  if (heatLayer) {
    map.removeLayer(heatLayer)
    heatLayer = null
  }

  const filtered = activeFilter.value
    ? props.points.filter(p => p.class_name === activeFilter.value)
    : props.points

  const heatPoints = []

  filtered.forEach(p => {
    if (!p.lat || !p.lon) return

    const color = classColors[p.class_name] || '#10b981'
    const isAnomaly = p.class_name !== 'Healthy Leaves'

    // Adiciona ao Heatmap
    if (isAnomaly) {
      heatPoints.push([p.lat, p.lon, (p.confidence || 0.8) * 1.2])
    }

    // Marcador Circular
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: isAnomaly ? 8 : 5,
      fillColor: color,
      color: '#ffffff',
      weight: 1.5,
      opacity: 0.9,
      fillOpacity: 0.85
    })

    const popupHtml = `
      <div style="font-size: 13px; line-height: 1.4;">
        <strong style="color: ${color}; font-size: 14px;">${p.class_name}</strong><br/>
        <b>Confiança:</b> ${(p.confidence * 100).toFixed(1)}%<br/>
        <b>Posição:</b> ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}<br/>
        <b>Altitude:</b> ${p.alt_m?.toFixed(1) || '25.0'} m<br/>
        <b>Latência Chip:</b> ${p.timing?.total_chip_ms?.toFixed(1) || '386.1'} ms
      </div>
    `
    marker.bindPopup(popupHtml)
    markersLayer.addLayer(marker)
  })

  // Ativa Heatmap se selecionado
  if (showHeatmap.value && heatPoints.length > 0 && typeof L.heatLayer === 'function') {
    heatLayer = L.heatLayer(heatPoints, {
      radius: 25,
      blur: 18,
      maxZoom: 18,
      gradient: {
        0.2: '#10b981',
        0.5: '#eab308',
        0.8: '#ea580c',
        1.0: '#dc2626'
      }
    }).addTo(map)
  }
}

function fitAllPoints() {
  if (!map || !props.points.length) return
  const validPoints = props.points.filter(p => p.lat && p.lon)
  if (!validPoints.length) return
  const bounds = L.latLngBounds(validPoints.map(p => [p.lat, p.lon]))
  map.fitBounds(bounds, { padding: [40, 40] })
}
</script>

<style scoped>
.map-card {
  display: flex;
  flex-direction: column;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.map-controls {
  display: flex;
  gap: 0.5rem;
}

.btn-sm {
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
}

.btn-active {
  background: rgba(220, 38, 38, 0.2);
  border-color: #dc2626;
  color: #f87171;
}

.filter-legend {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  margin-bottom: 0.85rem;
  padding-bottom: 0.65rem;
  border-bottom: 1px solid var(--border-card);
}

.legend-title {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: 600;
  margin-right: 0.25rem;
}

.legend-pill {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: #111827;
  border: 1px solid var(--border-card);
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  color: #cbd5e1;
  cursor: pointer;
  transition: all 0.2s;
}

.legend-pill:hover {
  border-color: #475569;
  background: #1e293b;
}

.pill-dimmed {
  opacity: 0.35;
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.legend-count {
  font-weight: 700;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: #94a3b8;
}

.btn-clear-filter {
  background: transparent;
  border: none;
  color: #38bdf8;
  font-size: 0.7rem;
  cursor: pointer;
  text-decoration: underline;
  margin-left: 0.5rem;
}
</style>
