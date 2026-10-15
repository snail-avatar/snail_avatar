// @Time    : 2026
// @Author  : 李涛
// @File    : VtsSstsPage.vue
// @Desc    : VtsSstsPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
VTS/SSTS 参数面板

功能（对齐 flet DataTablePanelBase + ParameterTableBuilder）：
1. 多车型切换（el-segmented）
2. SSTS/VTS Sheet 切换
3. 分类/分组联动筛选
4. 表格展示（el-table，不达标行红色加粗）
5. 当前值/目标值可编辑（点击 → 输入 → 失焦/回车保存）
6. 刷新按钮

数据来源：
  GET  /api/memory-dbs       → memorycore 嵌套 dict → 前端拍平
  PUT  /api/vts-ssts/param   → 写单个参数（db_key + value）
-->

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, inject, h } from 'vue'
import { ElSelect, ElOption, ElButton } from 'element-plus'
import { api } from '../api/request'
import ParamEdit from '../components/ParamEdit.vue'
import { useMemoryDbStore } from '../stores/useMemoryDbStore'

const memStore = useMemoryDbStore()

// ============ 常量 ============
const SHEET_KEYWORDS: Record<string, string> = {
  'SSTS 参数': 'target_ssts',
  'VTS 参数': 'target_vts',
}

// ============ 状态 ============
const vehicles = ref<{ name: string; suffix: string; mcKey: string }[]>([])
const memorycore = ref<Record<string, any>>({})

const activeVehicle = ref('')
const activeSheet = ref<'SSTS 参数' | 'VTS 参数'>('SSTS 参数')

const cat1Options = ref<string[]>([])
const cat2Options = ref<string[]>([])
const cat1Filter = ref('__ALL__')
const cat2Filter = ref('__ALL__')

const flatItems = ref<any[]>([])
const statusText = ref('')          // header 计算相关状态文字
const filterCount = ref('')         // 页面内筛选计数（"共 N 项"）
const loading = ref(false)
const calcLoading = ref(false)

// ============ VTS 全量计算 ============
async function runVtsCalc() {
  calcLoading.value = true
  statusText.value = 'VTS 计算中...'
  try {
    const res: any = await api.post('/vts-ssts/calculate')
    if (res?.ok) {
      statusText.value = res.message || 'VTS 计算完成'
      // 计算完成后刷新数据
      await loadData()
      refreshAll()
    } else {
      statusText.value = 'VTS 计算失败: ' + (res?.error || '未知错误')
    }
  } catch (e: any) {
    statusText.value = 'VTS 计算异常: ' + (e?.message || e)
  } finally {
    calcLoading.value = false
  }
}

// ========= 注册车型下拉到 MainLayout header =========
const headerExtra = inject<any>('rightPanelHeaderExtra', null)

function registerHeaderControls() {
  if (!headerExtra) return
  headerExtra.factory = () => {
    return h('div', {
      style: 'display:flex;align-items:center;gap:6px;font-size:12px;'
    }, [
      h('span', { style: 'color:#606266;' }, '车型：'),
      h(ElSelect, {
        modelValue: activeVehicle.value,
        'onUpdate:modelValue': (v: string) => { activeVehicle.value = v },
        size: 'small',
        style: 'width:180px',
      }, vehicles.value.map((v: any) =>
        h(ElOption, {
          key: v.mcKey,
          value: v.suffix || v.name,
          label: v.suffix ? `${v.name}__${v.suffix}` : v.name,
        })
      )),
      // VTS计算按钮
      h(ElButton, {
        size: 'small',
        type: 'primary',
        onClick: runVtsCalc,
        loading: calcLoading.value,
      }, { default: () => 'VTS计算' }),
      // 运行状态（条件渲染，有内容才显示）
      statusText.value ? h('span', { style: 'color:#67c23a;' }, statusText.value) : null,
    ].filter(Boolean))
  }
}

// ============ 初始化 ============
onMounted(async () => {
  memStore.startPolling()  // 启动 store 后台轮询（全局共享 timer）
  registerHeaderControls() // 注册 header 控件（factory 依赖 vehicles，loadData 后会重新触发渲染）
  await loadData()
})

onBeforeUnmount(() => {
  memStore.stopPolling()
  if (headerExtra) headerExtra.factory = null
})

// 监听文件变化：换 Excel 时自动重新加载
watch(() => memStore.fileChangeVersion, async () => {
  await loadData()
})

async function loadData() {
  loading.value = true
  try {
    const res: any = await api.get('/memory-dbs')
    if (!res?.ok) { statusText.value = '内存数据库未加载'; return }
    memorycore.value = res.memorycore || {}

    // 从 vehsuffix 构建车型列表，兼容 memorycore.keys() 兜底
    const vehsuffix: any[] = res.vehsuffix || []
    const list: { name: string; suffix: string; mcKey: string }[] = []

    if (vehsuffix.length > 0) {
      for (const v of vehsuffix) {
        const name = v['车型'] || v['车型名称']
        const suffix = v['车型后缀'] || ''
        if (!name) continue
        const candidate = suffix ? `${name}_${suffix}` : name
        const actualKey = memorycore.value[candidate]
          ? candidate
          : Object.keys(memorycore.value).find(k =>
              k.includes(name) && (!suffix || k.includes(suffix))) || candidate
        list.push({ name, suffix, mcKey: actualKey })
      }
    } else {
      for (const key of Object.keys(memorycore.value)) list.push({ name: key, suffix: '', mcKey: key })
    }

    vehicles.value = list
    if (list.length > 0 && !activeVehicle.value) activeVehicle.value = list[0].suffix || list[0].name
    refreshAll()
  } catch (e: any) {
    statusText.value = `加载失败: ${e.message || e}`
  } finally {
    loading.value = false
  }
}

// ============ Sheet 数据提取 ============
function getCurrentSheetData(): Record<string, any> {
  const veh = vehicles.value.find(v => (v.suffix || v.name) === activeVehicle.value)
  if (!veh) return {}
  const mc = memorycore.value[veh.mcKey] || {}
  const keyword = SHEET_KEYWORDS[activeSheet.value]

  for (const sheetName of Object.keys(mc)) {
    if (keyword && sheetName.toLowerCase().includes(keyword)) {
      const data = mc[sheetName]
      if (!data || typeof data !== 'object') return {}
      return data
    }
  }
  return {}
}

// ============ 拍平（对齐 flet VehicleDataCollector.flatten_items）============
function flattenItems(sheetData: Record<string, any>): any[] {
  if (!sheetData) return []
  const out: any[] = []

  for (const cat1 of Object.keys(sheetData)) {
    const cat1Data = sheetData[cat1]
    if (Array.isArray(cat1Data)) {
      for (const item of cat1Data) if (typeof item === 'object') out.push({ ...item, cat1, cat2: '<未分类>' })
      continue
    }
    if (!cat1Data || typeof cat1Data !== 'object') continue

    for (const cat2 of Object.keys(cat1Data)) {
      const items = cat1Data[cat2]
      if (!items) continue

      if (Array.isArray(items)) {
        for (const item of items) {
          if (typeof item !== 'object') continue
          const pv = item['参数值']
          if (Array.isArray(pv) && pv.length > 0) {
            out.push(mergeMultiValue(item, pv, cat1, cat2))
          } else {
            out.push({ ...item, cat1, cat2 })
          }
        }
      } else if (typeof items === 'object') {
        for (const sub of Object.keys(items)) {
          const subItems = items[sub]
          if (Array.isArray(subItems))
            for (const si of subItems)
              if (typeof si === 'object') out.push({ ...si, cat1, cat2: `${cat2}/${sub}` })
        }
      }
    }
  }
  return out
}

const NAME_TO_FIELD_PREFIX: Record<string, string> = {
  '当前值': '当前值', '实际值': '当前值', '现在值': '当前值',
  '目标值': '目标值', '标准值': '目标值', '基准值': '目标值',
  '达标标识': '达标标识', '是否达标': '达标标识', '状态': '达标标识',
}

function mergeMultiValue(item: any, paramValues: any[], cat1: string, cat2: string): any {
  const entry: any = { ...item, cat1, cat2 }
  for (const p of paramValues) {
    if (typeof p !== 'object') continue
    const subName = String(p['名称'] || '').trim()
    const prefix = NAME_TO_FIELD_PREFIX[subName]
    if (!prefix) continue
    entry[prefix] = p['值']
    entry[`${prefix}_db_key`] = p['db_key']
  }
  entry['_has_multi_values'] = true
  return entry
}

// ============ 筛选 ============
const filteredItems = computed(() => {
  let items = flatItems.value
  if (cat1Filter.value !== '__ALL__') items = items.filter(i => i.cat1 === cat1Filter.value)
  if (cat2Filter.value !== '__ALL__') items = items.filter(i => i.cat2 === cat2Filter.value)
  return items
})

// ============ 合并单元格 span 计算 ============
// 返回每行列 cat1/cat2 应该 rowspan 几（首行）或 0（被合并掉）
function computeSpans(items: any[]): { cat1: number[]; cat2: number[] } {
  const cat1 = new Array(items.length).fill(0)
  const cat2 = new Array(items.length).fill(0)
  for (let i = 0; i < items.length; i++) {
    if (i === 0 || items[i].cat1 !== items[i - 1].cat1) {
      // 找连续相同 cat1 的行数
      let count = 1
      while (i + count < items.length && items[i + count].cat1 === items[i].cat1) count++
      cat1[i] = count
    }
    if (i === 0 || items[i].cat2 !== items[i - 1].cat2) {
      let count = 1
      while (i + count < items.length && items[i + count].cat2 === items[i].cat2) count++
      cat2[i] = count
    }
  }
  return { cat1, cat2 }
}

function spanMethod({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) {
  const spans = computeSpans(filteredItems.value)
  // columnIndex: 0=cat1, 1=cat2, 其余列不合并
  if (columnIndex === 0) {
    const rs = spans.cat1[rowIndex]
    return rs > 0 ? { rowspan: rs, colspan: 1 } : { rowspan: 0, colspan: 0 }
  }
  if (columnIndex === 1) {
    const rs = spans.cat2[rowIndex]
    return rs > 0 ? { rowspan: rs, colspan: 1 } : { rowspan: 0, colspan: 0 }
  }
  return { rowspan: 1, colspan: 1 }
}

// ============ 刷新 ============
function refreshAll() {
  const sheetData = getCurrentSheetData()
  flatItems.value = flattenItems(sheetData)

  const c1Set = new Set<string>()
  for (const i of flatItems.value) if (i.cat1) c1Set.add(i.cat1)
  cat1Options.value = ['__ALL__', ...c1Set]
  if (!cat1Options.value.includes(cat1Filter.value)) cat1Filter.value = '__ALL__'

  refreshCat2()
  filterCount.value = flatItems.value.length > 0 ? `共 ${flatItems.value.length} 项` : ''
  // statusText 不再受筛选变化影响（它只放计算相关状态）
}

function refreshCat2() {
  const c2Set = new Set<string>()
  for (const i of flatItems.value) {
    if (cat1Filter.value !== '__ALL__' && i.cat1 !== cat1Filter.value) continue
    if (i.cat2) c2Set.add(i.cat2)
  }
  cat2Options.value = ['__ALL__', ...c2Set]
  if (!cat2Options.value.includes(cat2Filter.value)) cat2Filter.value = '__ALL__'
}

watch(cat1Filter, refreshCat2)
watch(activeVehicle, refreshAll)
watch(activeSheet, refreshAll)

// ============ 达标判断 ============
function isNotPassed(row: any): boolean {
  const p = row['达标标识']
  return p !== undefined && p !== null && Number(p) === 0
}

// ============ 显示/编辑辅助 ============
function displayVal(v: any): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'number') {
    if (Math.abs(v) < 1e-10 && v !== 0) return v.toExponential(6)
    return parseFloat(v.toPrecision(12)).toString()
  }
  return String(v)
}

async function saveEdit(row: any, field: '当前值' | '目标值', dbKey: string, newVal: string) {
  if (!dbKey) return
  try {
    const res: any = await api.put('/vts-ssts/param', { db_key: dbKey, value: newVal })
    if (res?.ok) {
      row[field] = res.value
      statusText.value = `已更新: ${dbKey} = ${displayVal(res.value)}`
    } else {
      statusText.value = `写入失败: ${res?.error || '未知'}`
    }
  } catch (e: any) {
    statusText.value = `写入异常: ${e.message || e}`
  }
}
</script>

<template>
  <div class="vts-ssts-page">
    <!-- 顶部：Sheet 切换 + 筛选 + 刷新（合并到同一行） -->
    <div class="tabs-row">
      <el-segmented v-model="activeSheet" :options="['SSTS 参数', 'VTS 参数']" size="default" />
      <div class="filter-inline">
        <el-select v-model="cat1Filter" size="small" style="width: 160px">
          <el-option v-for="v in cat1Options" :key="v" :value="v" :label="v === '__ALL__' ? '全部' : v" />
        </el-select>
        <el-select v-model="cat2Filter" size="small" style="width: 160px">
          <el-option v-for="v in cat2Options" :key="v" :value="v" :label="v === '__ALL__' ? '全部' : v" />
        </el-select>
        <el-button size="small" @click="refreshAll" :loading="loading">刷新</el-button>
        <span v-if="filterCount" style="color:#606266;font-size:12px;">{{ filterCount }}</span>
      </div>
    </div>

    <el-divider style="margin: 8px 0" />

    <!-- 表格（flex:1 占满剩余高度） -->
    <div class="table-wrap">
    <el-table
      :data="filteredItems"
      height="100%"
      border stripe size="small"
      fit="false"
      :span-method="spanMethod"
      :row-class-name="({ row }) => isNotPassed(row) ? 'row-not-passed' : ''"
      empty-text="暂无匹配的参数"
    >
      <el-table-column prop="cat1" label="分类" width="70" />
      <el-table-column prop="cat2" label="分组" width="70" />
      <el-table-column prop="名称" label="参数名称" min-width="110" show-overflow-tooltip />
      <el-table-column prop="单位" label="单位" width="60" />
      <el-table-column prop="达标判据" label="达标判据" width="80" />

      <!-- 当前值（可编辑） -->
      <el-table-column label="当前值" width="110">
        <template #default="{ row }">
          <ParamEdit
            v-if="row['当前值_db_key'] || row['db_key']"
            :model-value="displayVal(row['当前值'] ?? row['值'])"
            :is-warn="isNotPassed(row)"
            @save="(v: string) => saveEdit(row, '当前值', row['当前值_db_key'] || row['db_key'], v)"
          />
          <span v-else>{{ displayVal(row['当前值'] ?? row['值']) }}</span>
        </template>
      </el-table-column>

      <!-- 目标值（可编辑） -->
      <el-table-column label="目标值" width="110">
        <template #default="{ row }">
          <ParamEdit
            v-if="row['目标值_db_key']"
            :model-value="displayVal(row['目标值'])"
            :is-warn="isNotPassed(row)"
            @save="(v: string) => saveEdit(row, '目标值', row['目标值_db_key'], v)"
          />
          <span v-else>{{ displayVal(row['目标值']) }}</span>
        </template>
      </el-table-column>

      <!-- 达标标识 -->
      <el-table-column label="达标标识" width="80">
        <template #default="{ row }">
          <el-tag
            v-if="row['达标标识'] !== undefined && row['达标标识'] !== null"
            :type="isNotPassed(row) ? 'danger' : 'success'"
            size="small"
            effect="light"
          >
            {{ Number(row['达标标识']) === 1 ? '达标' : '不达标' }}
          </el-tag>
          <span v-else class="muted">-</span>
        </template>
      </el-table-column>
    </el-table>
    </div><!-- /.table-wrap -->
  </div>
</template>

<style scoped>
/* 外层：flex column 填满 MainLayout 给的剩余空间 */
.vts-ssts-page {
  padding: 10px 14px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
}
/* 表格容器：flex:1 吃掉 tabs-row + divider 之外的所有高度 */
.table-wrap { flex: 1; min-height: 0; overflow: hidden; }

.tabs-row { display: flex; gap: 24px; align-items: center; }
.tab-group { display: flex; align-items: center; gap: 8px; }
.tab-label { font-size: 12px; color: #606266; }
.filter-inline {
  display: flex; gap: 8px; align-items: center; margin-left: auto;
}
.filter-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.status-text { font-size: 12px; color: #909399; margin-left: 8px; }
.muted { color: #c0c4cc; }

/* 表格整体缩小字体 + 强化网格线 */
:deep(.el-table) { font-size: 11px; --el-table-border-color: #b4bccc; }
:deep(.el-table th.el-table__cell) { font-size: 11px; padding: 5px 0; white-space: nowrap; }
:deep(.el-table td.el-table__cell) { font-size: 11px; padding: 3px 0; }
:deep(.el-table .el-table__inner-wrapper::before) { background-color: #b4bccc; }
:deep(.el-table--border .el-table__inner-wrapper::after) { background-color: #b4bccc; }
:deep(.el-segmented) { font-size: 12px; }
:deep(.el-select) { font-size: 12px; }

:deep(.row-not-passed) { background: #fef0f0 !important; }
:deep(.row-not-passed td.el-table__cell) { color: #f56c6c; font-weight: 500; }
</style>
