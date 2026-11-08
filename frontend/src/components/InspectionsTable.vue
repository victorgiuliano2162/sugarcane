<template>
  <div class="card table-card">
    <div class="card-header">
      <div class="header-left">
        <span class="card-title">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          Histórico de Inspeções no Talhão (CSV LittleFS)
        </span>
        <span class="badge badge-neutral">{{ filteredList.length }} registros</span>
      </div>

      <div class="table-actions">
        <!-- Input de Busca -->
        <input 
          v-model="searchQuery" 
          type="text" 
          placeholder="Filtrar por patologia..." 
          class="input search-input"
        />

        <!-- Seletor de itens por página -->
        <select v-model="pageSize" class="input select-input">
          <option :value="10">10 / pág</option>
          <option :value="25">25 / pág</option>
          <option :value="50">50 / pág</option>
        </select>

        <!-- Botão Exportar CSV -->
        <a :href="exportCsvUrl" download="inspecoes_sugarcane_talhao.csv" class="btn btn-primary btn-sm">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Exportar CSV (QGIS)
        </a>

        <!-- Botão Limpar Histórico -->
        <button class="btn btn-danger btn-sm" @click="confirmClearHistory" title="Limpar arquivo CSV na Flash">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
          Limpar
        </button>
      </div>
    </div>

    <!-- Tabela Responsiva Paginada -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th @click="sortBy('id')" class="cursor-pointer">ID ↕</th>
            <th @click="sortBy('timestamp')" class="cursor-pointer">Horário ↕</th>
            <th @click="sortBy('class_name')" class="cursor-pointer">Patologia Diagnosticada ↕</th>
            <th @click="sortBy('confidence')" class="cursor-pointer">Confiança ↕</th>
            <th>Coordenadas GPS</th>
            <th>Altitude</th>
            <th @click="sortBy('total_ms')" class="cursor-pointer">Latência Chip ↕</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in paginatedList" :key="item.id">
            <td class="font-mono">#{{ item.id }}</td>
            <td class="font-mono text-dim">{{ formatTimestamp(item.timestamp) }}</td>
            <td>
              <div class="class-cell">
                <span class="class-dot" :style="{ background: getClassColor(item.class_name) }"></span>
                <span class="class-name">{{ item.class_name }}</span>
              </div>
            </td>
            <td>
              <span class="badge" :class="getConfidenceBadge(item.confidence)">
                {{ (item.confidence * 100).toFixed(1) }}%
              </span>
            </td>
            <td class="font-mono text-dim">
              {{ item.lat ? `${item.lat.toFixed(5)}, ${item.lon.toFixed(5)}` : '--' }}
            </td>
            <td class="font-mono text-dim">
              {{ item.alt_m ? `${item.alt_m.toFixed(1)} m` : '--' }}
            </td>
            <td class="font-mono text-dim">
              {{ item.timing?.total_chip_ms ? `${item.timing.total_chip_ms.toFixed(1)} ms` : (item.inference_ms ? `${(item.inference_ms + (item.decode_ms || 102)).toFixed(1)} ms` : '~386 ms') }}
            </td>
          </tr>
          <tr v-if="paginatedList.length === 0">
            <td colspan="7" class="empty-row">
              Nenhuma inspeção encontrada no filtro atual.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Paginação Inferior -->
    <div class="pagination-footer">
      <span class="page-info">
        Mostrando {{ startIndex + 1 }} a {{ Math.min(startIndex + pageSize, filteredList.length) }} de {{ filteredList.length }} registros
      </span>
      <div class="page-controls">
        <button class="btn btn-secondary btn-xs" :disabled="currentPage === 1" @click="currentPage--">
          Anterior
        </button>
        <span class="page-current">{{ currentPage }} / {{ totalPages || 1 }}</span>
        <button class="btn btn-secondary btn-xs" :disabled="currentPage >= totalPages" @click="currentPage++">
          Próxima
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  inspections: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['clear-history'])

const searchQuery = ref('')
const pageSize = ref(10)
const currentPage = ref(1)
const sortKey = ref('id')
const sortOrder = ref('desc') // 'asc' ou 'desc'

// Reseta para a página 1 ao alterar o tamanho da página ou filtrar
watch([pageSize, searchQuery], () => {
  currentPage.value = 1
})

const exportCsvUrl = computed(() => {
  return '/api/export-csv'
})

const classColors = {
  'smut': '#dc2626',
  'BrownRust': '#ea580c',
  'Pokkah Boeng': '#3b82f6',
  'Sett Rot': '#7c3aed',
  'Yellow Leaf': '#eab308',
  'Banded Chlorosis': '#d97706',
  'Brown Spot': '#9333ea',
  'Grassy shoot': '#06b6d4',
  'Dried Leaves': '#78716c',
  'Viral Disease': '#ec4899',
  'Healthy Leaves': '#10b981'
}

function getClassColor(name) {
  return classColors[name] || '#10b981'
}

function getConfidenceBadge(c) {
  if (c >= 0.85) return 'badge-success'
  if (c >= 0.70) return 'badge-warning'
  return 'badge-danger'
}

function formatTimestamp(epoch) {
  if (!epoch) return '--:--:--'
  const date = new Date(epoch > 1e11 ? epoch : epoch * 1000)
  return date.toLocaleTimeString('pt-BR', { hour12: false })
}

function sortBy(key) {
  if (sortKey.value === key) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = 'desc'
  }
}

const filteredList = computed(() => {
  let list = props.inspections || []
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(item => 
      (item.class_name && item.class_name.toLowerCase().includes(q)) ||
      (item.id && item.id.toString().includes(q))
    )
  }

  return list.slice().sort((a, b) => {
    let va = a[sortKey.value]
    let vb = b[sortKey.value]
    if (va === undefined) va = 0
    if (vb === undefined) vb = 0
    if (sortOrder.value === 'asc') return va > vb ? 1 : -1
    return va < vb ? 1 : -1
  })
})

const totalPages = computed(() => {
  return Math.ceil(filteredList.value.length / pageSize.value) || 1
})

watch(totalPages, (newTotal) => {
  if (currentPage.value > newTotal) {
    currentPage.value = newTotal
  }
})

const startIndex = computed(() => {
  return (currentPage.value - 1) * pageSize.value
})

const paginatedList = computed(() => {
  return filteredList.value.slice(startIndex.value, startIndex.value + pageSize.value)
})

function confirmClearHistory() {
  if (window.confirm('Deseja realmente limpar todos os registros do arquivo CSV na Flash?')) {
    emit('clear-history')
  }
}
</script>

<style scoped>
.table-card {
  display: flex;
  flex-direction: column;
}

.table-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.search-input {
  width: 180px;
  font-size: 0.8rem;
}

.select-input {
  font-size: 0.8rem;
  cursor: pointer;
}

.btn-sm {
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
}

.btn-xs {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.cursor-pointer {
  cursor: pointer;
  user-select: none;
}

.cursor-pointer:hover {
  color: #38bdf8;
}

.font-mono {
  font-family: var(--font-mono);
}

.text-dim {
  color: var(--text-dim);
}

.class-cell {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.class-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.class-name {
  font-weight: 600;
}

.empty-row {
  text-align: center;
  padding: 2rem;
  color: var(--text-dim);
}

.pagination-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-card);
  font-size: 0.8rem;
  color: var(--text-muted);
}

.page-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.page-current {
  font-family: var(--font-mono);
  font-weight: 600;
  color: #f8fafc;
}
</style>
