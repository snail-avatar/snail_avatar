// @Time    : 2026
// @Author  : 李涛
// @File    : ExpertPanel.vue
// @Desc    : ExpertPanel
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  ExpertPanel — 专家面板（通用组件，配置驱动）

  agent_id 不同 → 不同的 Tab 配置和数据源：
    aero_expert_agent → 空气动力学专家
    pe_expert_agent   → PE专家

  4 种 Tab 类型对齐 Flet GenericExpertPanel + 对应 TabBase：
    knowledge_base    → TabKnowledgeBaseBase    （建库管理：向量库状态 + 待处理文件 + 进度条）
    knowledge_graph   → TabKnowledgeGraphBase   （知识图谱：左右分栏）
    rules             → TabRulesBase            （规则卡片列表）
    cases             → TabCasesBase            （案例卡片列表）
-->
<template>
  <div class="expert-page">
    <!-- Tab 切换（动态，从后端 config 读） -->
    <el-tabs v-model="activeTab" class="top-tabs">
      <el-tab-pane
        v-for="t in tabs"
        :key="t.type"
        :label="t.label"
        :name="t.type"
      />
    </el-tabs>

    <!-- 内容区 -->
    <div class="tab-scroll">

      <!-- ================================================================
           Tab 1: knowledge_base（建库管理）— 对齐 Flet TabKnowledgeBaseBase
           三个区域：待处理文件 → 开始入库/进度 → 向量库状态
           ================================================================ -->
      <div v-if="activeTab === 'knowledge_base'" class="kb-tab">

        <!-- ① 待处理文件区 -->
        <div class="kb-section">
          <div class="section-header">
            <span class="section-title">📂 待处理文件</span>
            <span class="section-meta">{{ pendingFiles.length }} 个文件</span>
          </div>
          <div class="kb-list-box">
            <div v-if="pendingFiles.length === 0" class="empty-hint">暂无待处理文件</div>
            <div v-for="(f, i) in pendingFiles" :key="i" class="kb-file-row">
              <span class="kb-file-name">{{ f }}</span>
              <el-button type="danger" size="small" link @click="removePending(i)">删除</el-button>
            </div>
          </div>
          <div class="kb-actions">
            <el-button size="small" :icon="Upload" @click="pickFiles">选择文件</el-button>
            <el-button size="small" :icon="FolderOpened" @click="pickFolder">选择文件夹</el-button>
            <el-button size="small" :disabled="pendingFiles.length === 0" @click="clearPending">清空列表</el-button>
          </div>
        </div>

        <el-divider />

        <!-- ② 进度区 -->
        <div class="kb-section">
          <div class="kb-progress-row">
            <el-button
              size="small"
              type="primary"
              :disabled="pendingFiles.length === 0 || importing"
              :loading="importing"
              :icon="VideoPlay"
            >
              {{ importing ? '入库中...' : '开始入库' }}
            </el-button>
            <el-progress
              v-if="importing || importProgress > 0"
              :percentage="importProgress"
              :status="importStatus"
              class="kb-progress"
            />
            <span class="kb-status" :class="{ error: importError }">{{ importStatusText }}</span>
          </div>
        </div>

        <el-divider />

        <!-- ③ 向量库状态区（从后端 kb-stats 读真实数据） -->
        <div class="kb-section">
          <div class="section-header">
            <span class="section-title">💾 向量库状态</span>
            <el-button size="small" :icon="Refresh" @click="loadKbStats">刷新</el-button>
            <span class="kb-stats-summary" v-if="kbStats.ok">
              <el-tag v-if="kbStats.persist_dir_exists" type="success" effect="plain" size="small">
                已存在 · {{ kbStats.vector_file_count }} 个文件 · {{ formatSize(kbStats.vector_total_size) }}
              </el-tag>
              <el-tag v-else type="info" effect="plain" size="small">目录不存在</el-tag>
            </span>
          </div>
          <div class="kb-list-box">
            <div v-if="!kbStats.ok" class="empty-hint">读取失败：{{ kbStats.reason }}</div>
            <template v-else-if="kbStats.persist_dir_exists">
              <div v-if="kbStats.vector_files.length === 0" class="empty-hint">向量库目录为空</div>
              <div v-for="f in kbStats.vector_files" :key="f.name" class="kb-file-row">
                <span class="kb-file-name">{{ f.name }}</span>
                <span class="kb-file-meta">{{ formatSize(f.size) }}</span>
              </div>
            </template>
            <div v-else class="empty-hint">向量库目录尚未创建（{{ kbStats.persist_dir }}）</div>
          </div>
          <div class="kb-path-hint">向量库路径：{{ kbStats.persist_dir || '（未配置）' }}</div>
          <div class="kb-path-hint" v-if="kbStats.collection_name">集合名：{{ kbStats.collection_name }}</div>
        </div>

      </div>

      <!-- ================================================================
           Tab 2: knowledge_graph（知识图谱）— 对齐 Flet TabKnowledgeGraphBase
           左右分栏：左节点列表 / 右节点详情 + 关联关系
           ================================================================ -->
      <div v-else-if="activeTab === 'knowledge_graph'" class="kg-tab">
        <div class="btn-row">
          <el-button size="small" @click="onExport('knowledge_graph')" :icon="Download">导出Excel</el-button>
          <el-button size="small" @click="triggerImport('knowledge_graph')" :icon="Upload">导入Excel</el-button>
          <el-button size="small" :disabled="!hasVectorIndex" type="primary" plain :icon="MagicStick">构建向量索引</el-button>
        </div>
        <!-- 隐藏的 file input -->
        <input type="file" ref="importFileRef" accept=".xlsx" style="display:none" @change="onImportFile" />
        <div v-if="graphError" class="err-text">{{ graphError }}</div>

        <div class="split-row">
          <!-- 左：节点列表 -->
          <div class="split-col split-left">
            <div class="sub-title">🧩 节点列表（{{ nodes.length }}）</div>
            <div class="card-list" v-if="nodes.length > 0">
              <div
                v-for="n in nodes"
                :key="n.id"
                class="kg-node-btn"
                :class="{ selected: selectedNodeId === n.id }"
                @click="onSelectNode(n)"
              >
                {{ n.name }}
                <span v-if="n.type" class="kg-node-type">[{{ n.type }}]</span>
              </div>
            </div>
            <div v-else class="empty-big">无节点</div>
          </div>

          <!-- 右：节点详情 + 关联关系 -->
          <div class="split-col split-right">
            <div class="sub-title">📋 节点详情</div>
            <div class="detail-card">
              <template v-if="selectedNode">
                <div class="detail-row"><span class="dl">ID</span><span class="dv">{{ selectedNode.id }}</span></div>
                <div class="detail-row"><span class="dl">名称</span><span class="dv">{{ selectedNode.name }}</span></div>
                <div class="detail-row"><span class="dl">类型</span><span class="dv">{{ selectedNode.type }}</span></div>
                <div class="detail-row detail-desc"><span class="dl">描述</span><span class="dv">{{ selectedNode.desc || '（无）' }}</span></div>
              </template>
              <div v-else class="empty-small">选择左侧节点查看详情</div>
            </div>

            <div class="sub-title mt-lg">🔗 关联关系（{{ selectedRelations.length }}）</div>
            <div class="card-list" v-if="selectedRelations.length > 0">
              <div v-for="(r, i) in selectedRelations" :key="i" class="kg-rel-item">
                {{ r.from_name }} → <b>{{ r.relation }}</b> → {{ r.to_name }}
              </div>
            </div>
            <div v-else class="empty-small">无关联关系</div>
          </div>
        </div>
      </div>

      <!-- ================================================================
           Tab 3: rules（规则管理）— 对齐 Flet TabRulesBase
           ================================================================ -->
      <div v-else-if="activeTab === 'rules'" class="rules-tab">
        <div class="btn-row">
          <el-button size="small" @click="onExport('rules')" :icon="Download">导出Excel</el-button>
          <el-button size="small" @click="triggerImport('rules')" :icon="Upload">导入Excel</el-button>
          <el-button size="small" :disabled="!hasVectorIndex" type="primary" plain :icon="MagicStick">构建向量索引</el-button>
        </div>
        <div v-if="rulesError" class="err-text">{{ rulesError }}</div>
        <div class="card-list" v-if="rules.length > 0">
          <div v-for="rule in rules" :key="rule.id" class="item-card">
            <div class="item-header">
              <el-tag v-if="rule.category" size="small" type="primary" effect="plain">{{ rule.category }}</el-tag>
              <span class="item-name">{{ rule.name }}</span>
            </div>
            <div class="item-desc">{{ truncate(rule.description, 200) }}</div>
            <div v-if="rule.formula" class="item-meta"><span class="meta-label">公式:</span> {{ truncate(rule.formula, 150) }}</div>
            <div v-if="rule.source" class="item-meta"><span class="meta-label">来源:</span> {{ rule.source }}</div>
          </div>
        </div>
        <div v-else class="empty-big">无规则</div>
      </div>

      <!-- ================================================================
           Tab 4: cases（案例库）— 对齐 Flet TabCasesBase
           ================================================================ -->
      <div v-else-if="activeTab === 'cases'" class="cases-tab">
        <div class="btn-row">
          <el-button size="small" @click="onExport('cases')" :icon="Download">导出Excel</el-button>
          <el-button size="small" @click="triggerImport('cases')" :icon="Upload">导入Excel</el-button>
          <el-button size="small" :disabled="!hasVectorIndex" type="primary" plain :icon="MagicStick">构建向量索引</el-button>
        </div>
        <div v-if="casesError" class="err-text">{{ casesError }}</div>
        <div class="card-list" v-if="cases.length > 0">
          <div v-for="cs in cases" :key="cs.id" class="item-card">
            <div class="item-header">
              <el-tag v-if="cs.category" size="small" type="primary" effect="plain">{{ cs.category }}</el-tag>
              <span class="item-name">{{ cs.title }}</span>
            </div>
            <div v-if="cs.vehicle_type" class="item-meta"><span class="meta-label">车型:</span> {{ cs.vehicle_type }}</div>
            <div class="item-desc">{{ truncate(cs.description, 200) }}</div>
            <div v-if="cs.key_params" class="item-meta"><span class="meta-label">关键参数:</span> {{ truncate(cs.key_params, 150) }}</div>
            <div v-if="cs.results" class="item-meta"><span class="meta-label">效果:</span> {{ truncate(cs.results, 150) }}</div>
            <div v-if="cs.source" class="item-meta"><span class="meta-label">来源:</span> {{ cs.source }}</div>
          </div>
        </div>
        <div v-else class="empty-big">无案例</div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Download, MagicStick, Upload, FolderOpened, Refresh, VideoPlay,
} from '@element-plus/icons-vue'

const props = defineProps<{ agentId: string }>()

// ========= 状态 =========
const loading = ref(false)
const panelName = ref('')
const tabs = ref<{ type: string; label: string; has_vector_index: boolean }[]>([])
const tabsRaw = ref<any[]>([])
const activeTab = ref('')

// 导入相关：当前导入的 tab + 文件 input ref
const importTargetTab = ref('')
const importFileRef = ref<HTMLInputElement | null>(null)

// --- 建库管理 ---
const pendingFiles = ref<string[]>([])
const importing = ref(false)
const importProgress = ref(0)
const importStatus = ref<'' | 'success' | 'exception'>('')
const importStatusText = ref('')
const importError = ref(false)

const kbStats = reactive({
  ok: false,
  reason: '',
  persist_dir: '',
  persist_dir_exists: false,
  collection_name: '',
  vector_files: [] as { name: string; size: number; mtime: number }[],
  vector_file_count: 0,
  vector_total_size: 0,
})

// --- 知识图谱 ---
const nodes = ref<any[]>([])
const relations = ref<any[]>([])
const graphError = ref('')
const selectedNodeId = ref<string | null>(null)
const selectedNode = computed(() =>
  selectedNodeId.value ? nodes.value.find(n => n.id === selectedNodeId.value) : null
)
const selectedRelations = computed(() => {
  if (!selectedNodeId.value) return []
  const id = selectedNodeId.value
  return relations.value.filter(r => r.from === id || r.to === id)
})

// --- 规则 ---
const rules = ref<any[]>([])
const rulesError = ref('')

// --- 案例 ---
const cases = ref<any[]>([])
const casesError = ref('')

const hasVectorIndex = computed(() => {
  const t = tabs.value.find(x => x.type === activeTab.value)
  return !!t?.has_vector_index
})

// ========= 工具函数 =========
function truncate(s: string | undefined, max: number): string {
  if (!s) return ''
  return s.length > max ? s.slice(0, max) + '...' : s
}
function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

// ========= 建库管理：待处理文件 =========
function pickFiles() {
  ElMessage.info('选择文件对话框（Phase 9：调用后端 multipart 上传）')
}
function pickFolder() {
  ElMessage.info('选择文件夹对话框（Phase 9：遍历后端 data_dir）')
}
function clearPending() { pendingFiles.value = [] }
function removePending(i: number) { pendingFiles.value.splice(i, 1) }

// ========= 节点选中 =========
function onSelectNode(n: any) { selectedNodeId.value = n.id }

// ========= 导出 Excel（真实下载） =========
function onExport(tabType: string) {
  const url = `/api/expert/${props.agentId}/${tabType}/export`
  // 用 a标签 触发浏览器下载（绕过 axios 二进制处理）
  const a = document.createElement('a')
  a.href = url
  a.download = `${tabType}_${props.agentId}.xlsx`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  ElMessage.success('已开始下载 Excel')
}

// ========= 导入 Excel =========
function triggerImport(tabType: string) {
  importTargetTab.value = tabType
  importFileRef.value?.click()
}

async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  // 清空，确保下次选同文件也触发 change
  input.value = ''
  if (!file) return

  const tabType = importTargetTab.value
  ElMessage.info(`正在导入 ${file.name} ...`)

  try {
    const fd = new FormData()
    fd.append('file', file)
    const resp = await fetch(`/api/expert/${props.agentId}/${tabType}/import`, {
      method: 'POST',
      body: fd,
    })
    const data = await resp.json()
    if (resp.ok && data.ok) {
      ElMessage.success('导入成功')
      // 重新加载当前 tab 数据
      await loadTabData(tabType)
    } else {
      ElMessage.error(`导入失败: ${data.detail || data.message || '未知错误'}`)
    }
  } catch (err: any) {
    ElMessage.error(`导入异常: ${err.message}`)
  }
}

// ========= 加载 kb-stats =========
async function loadKbStats() {
  try {
    const r = await fetch(`/api/expert/${props.agentId}/kb-stats`)
    const d = await r.json()
    Object.assign(kbStats, d)
  } catch (e: any) {
    kbStats.ok = false
    kbStats.reason = e.message
  }
}

// ========= 刷新（主入口） =========
async function onRefresh() {
  loading.value = true
  graphError.value = ''
  rulesError.value = ''
  casesError.value = ''

  try {
    // 1. 面板配置
    const rc = await fetch(`/api/expert/${props.agentId}/config`)
    const dc = await rc.json()
    if (dc.ok) {
      panelName.value = dc.panel_name || ''
      tabs.value = dc.tabs
      tabsRaw.value = dc.tabs_raw || []
      if (!activeTab.value && tabs.value.length > 0) {
        activeTab.value = tabs.value[0].type
      }
    }

    // 2. 当前 tab 数据
    await loadTabData(activeTab.value)
  } catch (e: any) {
    ElMessage.error(`加载失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

// tab 切换时懒加载
watch(activeTab, (tab) => { loadTabData(tab) })

async function loadTabData(tabType: string) {
  if (!tabType) return

  // 建库管理：加载 kb-stats
  if (tabType === 'knowledge_base') {
    await loadKbStats()
    return
  }

  // 其他 tab：按 type 请求对应端点
  try {
    const r = await fetch(`/api/expert/${props.agentId}/${tabType}`)
    const d = await r.json()
    if (tabType === 'knowledge_graph') {
      nodes.value = d.nodes || []
      relations.value = d.relations || []
      selectedNodeId.value = nodes.value.length > 0 ? nodes.value[0]?.id || null : null
    } else if (tabType === 'rules') {
      rules.value = d.rules || []
    } else if (tabType === 'cases') {
      cases.value = d.cases || []
    }
  } catch (e: any) {
    const errMsg = `加载失败: ${e.message}`
    if (tabType === 'knowledge_graph') graphError.value = errMsg
    if (tabType === 'rules') rulesError.value = errMsg
    if (tabType === 'cases') casesError.value = errMsg
  }
}

onMounted(() => { onRefresh() })
</script>

<style scoped>
/* ============ 统一设计基准（对齐 MemoryDbsPage） ============
  字号: 13 = 分区标题 / 大空提示
        12 = 常规内容（树节点、JSON、按钮、次要文字）
  字重: 600 = 分区标题, 400 = 常规
  颜色: #303133 = 主文字, #606266 = 常规, #909399 = 次要, #c0c4cc = 空提示
  边框: 1px solid #e4e7ed  圆角: 4px
  背景: #fff / #fafbfc
  ==================================== */

.expert-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

/* 顶层 Tab */
.top-tabs { flex-shrink: 0; }
.top-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 10px; }
.top-tabs :deep(.el-tabs__item) { font-size: 13px; }

/* 内容滚动区 */
.tab-scroll {
  flex: 1;
  overflow: hidden;            /* 滚动下放到子容器 */
  padding: 10px 14px 24px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 每个 tab 的外层容器（占满 tab-scroll） */
.tab-scroll > [class$="-tab"] {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 按钮行 */
.btn-row {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  padding: 4px 0 6px;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 10px;
}

/* 分区标题 */
.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 14px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px dashed #dcdfe6;
}
.sub-title:first-child { margin-top: 0; }
.mt-lg { margin-top: 16px; }

/* 空提示 */
.empty-big { color: #c0c4cc; text-align: center; padding: 40px 0; font-size: 13px; }
.empty-small { color: #909399; padding: 4px 0 6px; font-size: 12px; }
.empty-hint { color: #c0c4cc; padding: 20px 0; font-size: 12px; text-align: center; }

/* ============ 建库管理（3 个 section，flex 垂直拉伸） ============ */
.kb-tab { /* 继承 flex column */ }
.kb-tab .kb-section {
  flex-shrink: 0;
  padding: 2px 0;
}
/* 让①待处理文件 和 ③向量库状态 两个 section 平分剩余高度 */
.kb-tab > .kb-section:first-child,
.kb-tab > .kb-section:last-child {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.section-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.section-title { font-size: 13px; font-weight: 600; color: #303133; }
.section-meta { font-size: 12px; color: #909399; }
.kb-stats-summary { margin-left: auto; }

/* 文件列表框 / 向量库文件列表 — 占满 section 剩余高度 */
.kb-list-box {
  flex: 1;
  background: #fafbfc;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 4px 8px;
  overflow-y: auto;
  min-height: 0;
}
.kb-file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  font-size: 12px;
  border-bottom: 1px dashed #ebeef5;
}
.kb-file-row:last-child { border-bottom: none; }
.kb-file-name { color: #303133; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-file-meta { color: #909399; font-size: 11px; flex-shrink: 0; margin-left: 10px; }

/* 按钮组 */
.kb-actions {
  display: flex;
  gap: 8px;
  padding: 8px 0 2px;
}

/* 进度条行 */
.kb-progress-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 4px 0;
}
.kb-progress { flex: 1; max-width: 360px; }
.kb-status { font-size: 12px; color: #606266; }
.kb-status.error { color: #f56c6c; }

/* 路径提示 */
.kb-path-hint {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
  font-family: ui-monospace, Consolas, monospace;
}

/* ============ 知识图谱：左右分栏 ============ */
.kg-tab { /* 继承自 .tab-scroll > [class$="-tab"] 的 flex column */ }
.kg-tab .split-row {
  flex: 1;
  display: flex;
  gap: 10px;
  min-height: 0;
  overflow: hidden;
}
.split-col { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.split-left { flex: 0 0 45%; }

.card-list {
  flex: 1;
  background: #fafbfc;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 6px 8px;
  overflow-y: auto;
  min-height: 0;
}
.kg-node-btn {
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: 6px;
}
.kg-node-btn:hover { background: #ecf5ff; }
.kg-node-btn.selected {
  background: #ecf5ff;
  border-color: #409eff;
  font-weight: 600;
  color: #409eff;
}
.kg-node-type { color: #909399; font-size: 11px; }

/* 详情卡片（固定高度，不拉伸） */
.detail-card {
  flex-shrink: 0;
  background: #fafbfc;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 10px;
}
.detail-row {
  display: flex;
  gap: 10px;
  font-size: 12px;
  line-height: 1.6;
}
.detail-row + .detail-row { border-top: 1px dashed #ebeef5; padding-top: 4px; margin-top: 4px; }
.detail-row .dl { color: #909399; width: 40px; flex-shrink: 0; font-weight: 500; }
.detail-row .dv { color: #303133; flex: 1; word-break: break-all; white-space: pre-wrap; }
.detail-desc .dv { line-height: 1.7; }

/* 关联关系列表占满剩余空间 */
.split-col .card-list { flex: 1; }

.kg-rel-item {
  padding: 4px 8px;
  font-size: 12px;
  color: #303133;
  border-bottom: 1px dashed #ebeef5;
  font-family: ui-monospace, Consolas, monospace;
}
.kg-rel-item:last-child { border-bottom: none; }

/* ============ 规则/案例：卡片列表 ============ */
.rules-tab .card-list,
.cases-tab .card-list {
  flex: 1;
}
.item-card {
  border-bottom: 1px solid #ebeef5;
  padding: 8px 4px;
  line-height: 1.6;
}
.item-card:last-child { border-bottom: none; }
.item-header { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.item-name { font-size: 13px; font-weight: 600; color: #303133; }
.item-desc { font-size: 12px; color: #606266; margin: 3px 0; }
.item-meta { font-size: 11px; color: #909399; margin-top: 2px; }
.meta-label { color: #c0c4cc; margin-right: 4px; }

/* 错误提示 */
.err-text { font-size: 12px; color: #f56c6c; padding: 6px 0; }
</style>
