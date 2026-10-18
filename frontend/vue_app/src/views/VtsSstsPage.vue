// @Time    : 2026
// @Author  : 李涛
// @File    : VtsSstsPage.vue
// @Desc    : VtsSstsPage — VTS/SSTS 参数手动管理面板
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
VTS/SSTS 参数手动管理面板

功能：
1. 多车型切换（从 MainLayout header 下拉）
2. SSTS/VTS Sheet 切换（segmented）
3. cat1/cat2 分类筛选
4. VTS 计算按钮（重新触发 SSTS→VTS 计算）
5. 参数当前值/目标值可编辑（ParamEdit 组件）→ PUT /api/vts-ssts/param 写回
6. 刷新按钮

数据来源：GET /api/memory-dbs → 嵌套 dict → flattenSheetData() 拍平

与 a101 TargetDefinitionPage 共享 SstsVtsPanel.vue 组件，
通过 editable=true 开启可编辑模式（a101 不传 → 默认 false 只读）。
-->

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, inject, h } from 'vue'
import { ElSelect, ElOption, ElButton } from 'element-plus'
import { api } from '../api/request'
import SstsVtsPanel from '../components/SstsVtsPanel.vue'
import { useMemoryDbStore } from '../stores/useMemoryDbStore'
import { flattenSheetData, type FlattenResult, type VtsRow } from '../composables/useVtsFlatItems'

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

const fullData = ref<FlattenResult>({ categories: [], flatItems: [], total: 0 })
const statusText = ref('')          // header 计算相关状态文字
const filterCount = ref('')         // 页面内筛选计数（"共 N 项"）
const loading = ref(false)
const calcLoading = ref(false)

// ============ 筛选后的 FlattenResult（直接喂给 SstsVtsPanel） ============
const filteredData = computed<FlattenResult>(() => {
  const f = cat1Filter.value
  const f2 = cat2Filter.value
  if (f === '__ALL__' && f2 === '__ALL__') {
    return fullData.value
  }
  const flatItems = fullData.value.flatItems.filter(i =>
    (f === '__ALL__' || i.cat1 === f) && (f2 === '__ALL__' || i.cat2 === f2)
  )
  // 按 cat1 重新分组为 categories
  const catMap = new Map<string, VtsRow[]>()
  for (const item of flatItems) {
    if (!catMap.has(item.cat1)) catMap.set(item.cat1, [])
    catMap.get(item.cat1)!.push(item)
  }
  const categories = Array.from(catMap.entries()).map(([name, params]) => ({ name, params }))
  return { categories, flatItems, total: flatItems.length }
})

// ============ VTS 全量计算 ============
async function runVtsCalc() {
  calcLoading.value = true
  statusText.value = 'VTS 计算中...'
  try {
    const res: any = await api.post('/vts-ssts/calculate')
    if (res?.ok) {
      statusText.value = res.message || 'VTS 计算完成'
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

// ============ Sheet 数据提取 + 拍平（走共享 flattenSheetData） ============
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

// ============ 刷新 ============
function refreshAll() {
  const sheetData = getCurrentSheetData()
  fullData.value = flattenSheetData(sheetData)

  const c1Set = new Set<string>()
  for (const i of fullData.value.flatItems) if (i.cat1) c1Set.add(i.cat1)
  cat1Options.value = ['__ALL__', ...c1Set]
  if (!cat1Options.value.includes(cat1Filter.value)) cat1Filter.value = '__ALL__'

  refreshCat2()
  filterCount.value = fullData.value.total > 0 ? `共 ${fullData.value.total} 项` : ''
  // statusText 不受筛选变化影响（它只放计算相关状态）
}

function refreshCat2() {
  const c2Set = new Set<string>()
  for (const i of fullData.value.flatItems) {
    if (cat1Filter.value !== '__ALL__' && i.cat1 !== cat1Filter.value) continue
    if (i.cat2) c2Set.add(i.cat2)
  }
  cat2Options.value = ['__ALL__', ...c2Set]
  if (!cat2Options.value.includes(cat2Filter.value)) cat2Filter.value = '__ALL__'
}

watch(cat1Filter, refreshCat2)
watch(activeVehicle, refreshAll)
watch(activeSheet, refreshAll)

// ============ 编辑保存 ============
async function saveEdit(payload: { row: VtsRow; field: '当前值' | '目标值'; dbKey: string; newValue: string }) {
  const { row, field, dbKey, newValue } = payload
  try {
    const res: any = await api.put('/vts-ssts/param', { db_key: dbKey, value: newValue })
    if (res?.ok) {
      // 更新前端行（flattenSheetData 拍平后 row 是引用 fullData.flatItems[i] 的对象）
      row[field] = res.value
      // 同步更新 categories 里的那份引用（指向同一个 row 对象）
      statusText.value = `已更新: ${dbKey} = ${res.value}`
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

    <!-- 共享组件：可编辑模式 -->
    <div class="panel-wrap">
      <SstsVtsPanel
        :data="filteredData"
        :type="activeSheet === 'SSTS 参数' ? 'ssts' : 'vts'"
        :editable="true"
        @edit-save="saveEdit"
      />
    </div>
  </div>
</template>

<style scoped>
.vts-ssts-page {
  padding: 10px 14px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
}
.panel-wrap { flex: 1; min-height: 0; overflow: auto; }

.tabs-row { display: flex; gap: 24px; align-items: center; }
.filter-inline {
  display: flex; gap: 8px; align-items: center; margin-left: auto;
}
.status-text { font-size: 12px; color: #909399; margin-left: 8px; }
</style>
