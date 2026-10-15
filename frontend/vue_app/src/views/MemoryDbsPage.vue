// @Time    : 2026
// @Author  : 李涛
// @File    : MemoryDbsPage.vue
// @Desc    : MemoryDbsPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  MemoryDbsPage — 内存数据库查看面板（对齐 Flet 原版 MemoryDbsPanel）

  三个子 Tab，全部使用可折叠 JSON 展示。

  数据源：
    GET /api/memory-dbs     — 全量数据（Tab1 + Tab2）
    GET /api/llm-memory     — LLM 压缩记忆（Tab3）
-->
<template>
  <div class="mem-page">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <span class="status" v-if="lastUpdated">已更新：{{ lastUpdated }}</span>
      <span class="status" v-else>加载中...</span>
      <el-button size="small" @click="onRefresh" :loading="loading">刷新</el-button>
    </div>

    <!-- 顶层 Tab 切换（Excel / 内存库 / LLM） -->
    <el-tabs v-model="topTab" class="top-tabs">
      <el-tab-pane label="Excel 过渡数据" name="sheets" />
      <el-tab-pane label="内存数据库" name="dbs" />
      <el-tab-pane label="LLM 记忆压缩" name="llm" />
    </el-tabs>

    <!-- ========== Tab 1: Excel 过渡数据 ========== -->
    <div v-if="topTab === 'sheets'" class="tab-scroll">
      <div v-if="sheetsEmpty" class="empty-big">暂无 Excel 数据（加载后才可见）</div>
      <template v-for="(rows, sheetName) in data.sheets" :key="sheetName">
        <div class="sub-title">📊 {{ sheetName }}（{{ rows.length }} 行）</div>
        <div v-if="rows.length === 0" class="empty-small">空</div>
        <CollapsibleJson v-else :data="rows" />
      </template>
    </div>

    <!-- ========== Tab 2: 内存数据库 ========== -->
    <div v-else-if="topTab === 'dbs'" class="tab-scroll">
      <div class="sub-title">🗂️ VehSuffix（车辆配置后缀，{{ data.vehsuffix.length }} 项）</div>
      <div v-if="data.vehsuffix.length === 0" class="empty-small">（空）</div>
      <CollapsibleJson v-else :data="data.vehsuffix" />

      <div class="sub-title">🧩 MemoryCore（核心参数，{{ countKeys(data.memorycore) }} 顶层键）</div>
      <div v-if="isEmpty(data.memorycore)" class="empty-small">（空）</div>
      <CollapsibleJson v-else :data="data.memorycore" />

      <div class="sub-title">📈 EcoCycle（驾驶循环数据，{{ data.ecocycle.length }} 项）</div>
      <div v-if="data.ecocycle.length === 0" class="empty-small">（空）</div>
      <CollapsibleJson v-else :data="data.ecocycle" />

      <div class="sub-title">🔗 InterData（中间变量，{{ countKeys(data.inter_data) }} 顶层键）</div>
      <div v-if="isEmpty(data.inter_data)" class="empty-small">（空）</div>
      <CollapsibleJson v-else :data="data.inter_data" />
    </div>

    <!-- ========== Tab 3: LLM 记忆压缩 ========== -->
    <div v-else class="tab-scroll">
      <div class="sub-title">🧠 LLM 压缩记忆（{{ countKeys(llmData.current) }} 顶层键）</div>
      <div v-if="isEmpty(llmData.current)" class="empty-small">（空，发送对话让 MemoryCore 有数据后再刷新）</div>
      <CollapsibleJson v-else :data="llmData.current" />
      <div class="hint">💡 LLM 压缩会移除工程师技术前缀（base/target/memorycore/curve/ecocycle），参数值与单位合并成自然语言格式，Token 更省。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import CollapsibleJson from '../components/CollapsibleJson.vue'

// ========= 状态 =========
const topTab = ref('sheets')
const loading = ref(false)
const lastUpdated = ref('')

const data = reactive({
  sheets: {} as Record<string, any[]>,
  vehsuffix: [] as any[],
  memorycore: {} as Record<string, any>,
  ecocycle: [] as any[],
  inter_data: {} as Record<string, any>,
})

const llmData = reactive({
  ok: false,
  current: {} as Record<string, any>,
  error: '',
})

const sheetsEmpty = computed(() => Object.keys(data.sheets).length === 0)

// ========= 工具函数 =========
function isEmpty(v: any): boolean {
  if (v === null || v === undefined) return true
  if (Array.isArray(v)) return v.length === 0
  if (typeof v === 'object') return Object.keys(v).length === 0
  return false
}
function countKeys(obj: any): number {
  if (!obj || typeof obj !== 'object') return 0
  return Object.keys(obj).length
}

// ========= 刷新 =========
async function onRefresh() {
  loading.value = true
  const t = new Date().toLocaleTimeString()
  try {
    const r1 = await fetch('/api/memory-dbs')
    const d1 = await r1.json()
    if (d1.ok) {
      Object.assign(data, {
        sheets: d1.sheets || {},
        vehsuffix: d1.vehsuffix || [],
        memorycore: d1.memorycore || {},
        ecocycle: d1.ecocycle || [],
        inter_data: d1.inter_data || {},
      })
    }
    const r2 = await fetch('/api/llm-memory')
    const d2 = await r2.json()
    Object.assign(llmData, { ok: !!d2.ok, current: d2.current || {}, error: d2.error || '' })
    lastUpdated.value = t
  } catch (e: any) {
    lastUpdated.value = `${t}（请求失败：${e.message}）`
  } finally {
    loading.value = false
  }
}

onMounted(() => { onRefresh() })
</script>

<style scoped>
.mem-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  background: #fafbfc;
  border-bottom: 1px solid #e4e7ed;
}
.status { font-size: 12px; color: #909399; margin-right: auto; }

.top-tabs { flex-shrink: 0; }
.top-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 10px; }
.top-tabs :deep(.el-tabs__item) { font-size: 13px; }

.tab-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 14px 24px;
}

.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 14px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px dashed #dcdfe6;
}
.sub-title:first-child { margin-top: 0; }

.empty-big { color: #c0c4cc; text-align: center; padding: 40px 0; font-size: 13px; }
.empty-small { color: #909399; padding: 4px 0 6px; font-size: 12px; }

.hint {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  background: #f4f4f5;
  padding: 6px 10px;
  border-radius: 4px;
}
</style>
