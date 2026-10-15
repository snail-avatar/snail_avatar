// @Time    : 2026
// @Author  : 李涛
// @File    : TargetDefinitionPage.vue
// @Desc    : TargetDefinitionPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <div class="process-page">

    <!-- ========== ① 紧凑进度面板（StepProgressBar.create_compact()） ========== -->
    <div v-if="store.statesTree.length > 0" class="progress-compact">
      <!-- 行1: 专业标签（当前循环 + 已完成标记） -->
      <div class="progress-line chip-line">
        <template v-if="store.allLoopItems.length > 0">
          <span class="chip-label">专业:</span>
          <div
            v-for="cat in store.allLoopItems"
            :key="cat"
            :class="['category-chip', chipClassForItem(cat)]"
          >
            <el-icon :size="12"><component :is="chipIconForItem(cat)" /></el-icon>
            <span>{{ cat }}</span>
          </div>
          <div class="chip-spacer" />
          <span class="chip-stats">
            进度: {{ store.completedLoopItems.length }}{{ store.currentLoopItem ? '+1' : '' }}/{{ store.allLoopItems.length }}
          </span>
        </template>
        <template v-else>
          <span class="chip-wait">专业分类: 等待检测</span>
        </template>
      </div>

      <!-- 行2: 外层流程步骤（水平） — 直接从 statesTree 顶层节点渲染 -->
      <div class="progress-line outer-line">
        <span class="line-label">阶段:</span>
        <div
          v-for="(step, idx) in store.outerStepList"
          :key="step.step_id"
          class="step-item-outer"
        >
          <el-icon :size="14" :color="stepColor(step.status)">
            <component :is="outerStepIcon(step.status)" />
          </el-icon>
          <span :style="{ color: stepColor(step.status) }">{{ step.step_name }}</span>
          <span v-if="idx < store.outerStepList.length - 1" class="arrow">→</span>
        </div>
      </div>

      <!-- 行3: 内层步骤（当前活跃 loop 下的子步骤） -->
      <div class="progress-line inner-line">
        <span class="line-label">步骤:</span>
        <template v-if="store.innerStepList.length > 0">
          <div
            v-for="(st, idx) in store.innerStepList"
            :key="st.step_id"
            class="step-item-inner"
          >
            <el-icon :size="12" :color="stepColor(st.status)">
              <component :is="innerStepIcon(st.status)" />
            </el-icon>
            <span :style="{ color: stepColor(st.status) }" class="inner-step-label">
              2.{{ idx + 1 }} {{ shortName(st.step_name) }}
            </span>
            <span v-if="idx < store.innerStepList.length - 1" class="arrow">→</span>
          </div>
        </template>
        <template v-else>
          <span class="chip-wait">等待开始...</span>
        </template>
      </div>
    </div>

    <!-- ========== ③ 按钮行 ========== -->
    <div class="buttons-row">
      <!-- 区域1：执行控制（蓝色 primary） -->
      <el-button size="small" type="primary" :icon="Promotion" :disabled="!selectedInstanceKey || store.isStreaming" :loading="isLoading" @click="onStart">连续执行</el-button>
      <el-button size="small" type="primary" :icon="store.isPaused ? VideoPlay : VideoPause" :disabled="!store.isStreaming" @click="store.isPaused ? onResume() : onPause()">{{ store.isPaused ? '继续' : '暂停' }}</el-button>
      <el-button size="small" type="primary" :icon="CircleCloseFilled" :disabled="!store.isStreaming" @click="onStop">停止</el-button>
      <el-button size="small" type="primary" :icon="Delete" :disabled="!hasAnyData" @click="onReset">重置</el-button>
      <span class="btn-sep" />
      <!-- 区域2：单步操作（绿色 success） -->
      <el-button size="small" type="success" :icon="VideoPlay" :disabled="!canStep" @click="onStep">单步执行</el-button>
      <el-button size="small" type="success" :icon="RefreshRight" :disabled="!canRepeat" @click="onRepeat">重复本步</el-button>
    </div>

    <el-divider :margin="0" />

    <!-- ========== ④ 执行状态行（INFO 图标 + 动态颜色文本） ========== -->
    <div class="exec-status-row">
      <el-icon :size="14" :color="execStatusColor"><InfoFilled /></el-icon>
      <span :style="{ color: execStatusColor }" class="exec-status-text">{{ executionStatusText }}</span>
    </div>

    <el-divider :margin="0" />

    <!-- ========== ⑤ Sheet Tab 栏（顺序严格对齐 flet） ========== -->
    <div class="sheet-tab-row">
      <div
        v-for="s in sheetTabs"
        :key="s.key"
        :class="['sheet-tab-item', { active: activeSheet === s.key }]"
        @click="onSheetChanged(s.key)"
      >{{ s.label }}</div>
    </div>

    <el-divider :margin="0" />

    <!-- ========== ⑥ 内容区（两套容器 visible 切换） ========== -->
    <div class="content-area">

      <!-- StepResultViewer（activeSheet === 'STEP_RESULTS' 时可见） -->
      <div v-if="activeSheet === 'STEP_RESULTS'" class="result-viewer-container">
        <!-- 复制按钮行 -->
        <div class="copy-row">
          <span class="copy-label">步骤执行结果</span>
          <el-icon :size="16" class="copy-icon" @click="copyResults"><CopyDocument /></el-icon>
          <span v-if="copyResultsStatus" class="copy-status">{{ copyResultsStatus }}</span>
        </div>

        <!-- StepResultViewer 主体 -->
        <div class="viewer-main">
          <div class="viewer-nav-row">
            <div class="nav-buttons">
              <el-icon
                :size="18"
                :class="{ disabled: resultViewerIndex <= 0 || !filteredStepResults.length }"
                @click="navViewer(-1)"
              ><ArrowLeft /></el-icon>
              <el-icon
                :size="18"
                :class="{ disabled: resultViewerIndex >= filteredStepResults.length - 1 || !filteredStepResults.length }"
                @click="navViewer(1)"
              ><ArrowRight /></el-icon>
            </div>
            <span class="viewer-title">步骤执行结果: {{ resultViewerTitle }}</span>
            <span class="viewer-nav-info">{{ viewerNavInfo }}</span>
          </div>
          <div class="viewer-scroll">
            <div v-if="currentStepResult" class="viewer-content">
              <el-tree
                :data="stepResultTreeNodes"
                :props="{ label: 'label', children: 'children' }"
                node-key="path"
                default-expand-all
                :expand-on-click-node="false"
              >
                <template #default="{ data }">
                  <span class="tree-node" :class="{ 'tree-leaf': data.isLeaf }">
                    <span class="tree-key">{{ data.key }}</span>
                    <span v-if="data.isLeaf" class="tree-value">
                      <el-tag v-if="data.type === 'null'" type="info" size="small" effect="plain">null</el-tag>
                      <el-tag v-else-if="data.type === 'boolean'" :type="data.value ? 'success' : 'danger'" size="small">{{ data.value }}</el-tag>
                      <span v-else class="tree-leaf-val">{{ String(data.value) }}</span>
                    </span>
                  </span>
                </template>
              </el-tree>
            </div>
            <div v-else-if="store.isStreaming" class="viewer-wait">执行中，等待步骤完成...</div>
            <div v-else class="viewer-wait">等待执行...</div>
          </div>
        </div>

        <!-- 最终总结报告（如果有） -->
        <div v-if="store.finalSummary" class="summary-section">
          <div class="section-title">
            <el-icon><Document /></el-icon>
            最终总结报告
            <el-tag :type="store.finalStatus === 'success' ? 'success' : 'warning'" size="small">
              {{ finalStatusLabel }}
            </el-tag>
          </div>
          <div class="summary-content" v-html="renderMarkdown(store.finalSummary)"></div>
        </div>
      </div>

      <!-- 数据表格容器（其他 sheet 可见） -->
      <div v-else class="table-container" v-loading="tabLoading">
        <!-- 流程数据 tab 时显示复制按钮 -->
        <div v-if="activeSheet === 'FLOW_DATA'" class="copy-row">
          <span class="copy-label">流程数据</span>
          <el-icon :size="16" class="copy-icon" @click="copyFlowData"><CopyDocument /></el-icon>
          <span v-if="copyFlowDataStatus" class="copy-status">{{ copyFlowDataStatus }}</span>
        </div>

        <!-- 产品定义（3 列：参数名称 / 值 / 备注） -->
        <div v-show="activeSheet === 'PRODUCT_DEF'">
          <div v-if="store.productDef.length > 0">
            <el-table :data="store.productDef" stripe border size="small" fit="false">
              <el-table-column prop="名称" label="参数名称" show-overflow-tooltip>
                <template #default="{ row }">{{ row.名称 ?? row.name ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="值">
                <template #default="{ row }">{{ formatProductValue(row) }}</template>
              </el-table-column>
              <el-table-column prop="备注" label="备注" show-overflow-tooltip>
                <template #default="{ row }">{{ row.备注 ?? row.remark ?? '' }}</template>
              </el-table-column>
            </el-table>
            <div class="table-footer">共 {{ store.productDef.length }} 项</div>
          </div>
          <el-empty v-else :description="productEmptyDesc" />
        </div>

        <!-- 流程数据（沙箱 JSON 树） -->
        <div v-show="activeSheet === 'FLOW_DATA'">
          <div v-if="store.sandboxData != null && !isSandboxEmpty" class="json-tree">
            <el-tree
              :data="sandboxTreeNodes"
              :props="{ label: 'label', children: 'children' }"
              node-key="path"
              default-expand-all
              :expand-on-click-node="false"
            >
              <template #default="{ node, data }">
                <span class="tree-node" :class="{ 'tree-leaf': data.isLeaf }">
                  <span class="tree-key">{{ data.key }}</span>
                  <span v-if="data.isLeaf" class="tree-value">
                    <el-tag v-if="data.type === 'null'" type="info" size="small" effect="plain">null</el-tag>
                    <el-tag v-else-if="data.type === 'boolean'" :type="data.value ? 'success' : 'danger'" size="small">{{ data.value }}</el-tag>
                    <span v-else class="tree-leaf-val">{{ String(data.value) }}</span>
                  </span>
                </span>
              </template>
            </el-tree>
          </div>
          <el-empty v-else :description="sandboxEmptyDesc" />
        </div>

        <!-- SSTS 参数 -->
        <div v-show="activeSheet === 'SSTS'">
          <SstsVtsPanel :data="store.sstsSheet" title="SSTS 参数表" type="ssts" />
        </div>

        <!-- VTS 参数 -->
        <div v-show="activeSheet === 'VTS'">
          <SstsVtsPanel :data="store.vtsSheet" title="VTS 参数表" type="vts" />
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-if="store.errorMessage"
      :title="store.errorMessage"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 8px"
    />

    <el-empty
      v-if="store.vehicles.length === 0"
      description="后端未就绪，先启动 FastAPI 服务"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, defineAsyncComponent, inject, h } from 'vue'
import {
  Promotion, VideoPause, VideoPlay, RefreshRight, Connection, Document, Loading,
  CircleCheckFilled, CircleCloseFilled, MoreFilled, Tickets, ArrowLeft, ArrowRight,
  Check, CircleCheck,
  InfoFilled, CopyDocument, Delete, WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElSelect, ElOption } from 'element-plus'
import { useProcess } from '../composables/useProcess'
import { renderMarkdown } from '../utils/markdown'

// 延迟加载 SSTS/VTS 子面板组件
const SstsVtsPanel = defineAsyncComponent(() => import('../components/SstsVtsPanel.vue'))

const { store, isLoading, loadingMessage, loadVehicles, loadSteps, loadStatus, startProcess, stopProcess,
  pauseProcess, resumeProcess, stepProcess, repeatProcess,
  loadAllAfterDone, loadProductDef, loadSandbox, loadStepResults, loadVehicleSheets } = useProcess()

// ==================================================================
// 状态
// ==================================================================

const selectedInstanceKey = ref('')
const tabLoading = ref(false)     // tab 数据加载中（v-loading 用）

// Sheet Tab（替代 activeTab，顺序严格对齐 flet _sheet_tab_bar）
const activeSheet = ref('STEP_RESULTS')

// StepResultViewer 状态
const resultViewerIndex = ref(-1)
const copyResultsStatus = ref('')
const copyFlowDataStatus = ref('')

// Sheet Tab 定义（key 对齐 flet SHEET_KEYS）
const sheetTabs = [
  { key: 'STEP_RESULTS', label: '步骤执行结果' },
  { key: 'FLOW_DATA', label: '流程数据' },
  { key: 'PRODUCT_DEF', label: '产品定义' },
  { key: 'SSTS', label: 'SSTS 参数' },
  { key: 'VTS', label: 'VTS 参数' },
]

/** 当前选中车型的 suffix（VTS/SSTS API 需要） */
const selectedSuffix = computed(() => {
  const v = store.vehicles.find(x => x.instance_key === selectedInstanceKey.value)
  return v?.suffix || ''
})

// ==================================================================
// 组件挂载
// ==================================================================

onMounted(async () => {
  registerHeaderControls()
  await Promise.all([loadVehicles(), loadSteps()])
  if (store.vehicles.length > 0) {
    selectedInstanceKey.value = store.vehicles[0].instance_key
    // 刷新后恢复状态：从后端拉 states_tree + is_running
    await loadStatus(selectedInstanceKey.value)
  }
})

onBeforeUnmount(() => {
  if (headerExtra) headerExtra.factory = null
})

// ========= 注册车型下拉到 MainLayout 页面标题栏右侧 =========
const headerExtra = inject<any>('rightPanelHeaderExtra', null)

function registerHeaderControls() {
  if (!headerExtra) return
  headerExtra.factory = () => {
    return h('div', {
      style: 'display:flex;align-items:center;gap:6px;font-size:12px;'
    }, [
      h('span', { style: 'color:#606266;' }, '车型：'),
      h(ElSelect, {
        modelValue: selectedInstanceKey.value,
        'onUpdate:modelValue': (v: string) => { selectedInstanceKey.value = v },
        placeholder: '选择车型',
        size: 'small',
        style: 'width:200px',
        disabled: store.isStreaming,
        filterable: true,
        onChange: onVehicleChanged,
      }, store.vehicles.map((v: any) =>
        h(ElOption, {
          key: v.instance_key,
          value: v.instance_key,
          label: v.suffix ? `${v.name}_${v.suffix}` : v.name,
        })
      )),
    ])
  }
}

// loopItems 变化 → 重置 viewer 索引（新的结果列表）
watch(
  () => store.stepResults.length,
  () => {
    const list = filteredStepResults.value
    if (list.length > 0 && resultViewerIndex.value < 0) {
      resultViewerIndex.value = list.length - 1
    } else if (resultViewerIndex.value >= list.length) {
      resultViewerIndex.value = Math.max(0, list.length - 1)
    }
  },
)

// ==================================================================
// 过滤后的 stepResults（对齐 flet StepResultViewer.restore_from_controller_results）
//   - 跳过 INIT 步骤（框架级初始化）
//   - 跳过 "条件判断" 前缀的步骤（框架级条件分支）
// ==================================================================
const filteredStepResults = computed(() => {
  const SKIP_IDS = new Set(['INIT'])
  const SKIP_PREFIXES = ['条件判断']
  return store.stepResults.filter(r => {
    if (SKIP_IDS.has(r.step_id)) return false
    const cr = r.step_result?.content || ''
    if (typeof cr === 'string' && SKIP_PREFIXES.some(p => cr.startsWith(p))) return false
    return true
  })
})

// StepResultViewer 当前显示的记录
const currentStepResult = computed(() => {
  const list = filteredStepResults.value
  if (!list.length) return null
  if (resultViewerIndex.value < 0 || resultViewerIndex.value >= list.length) {
    resultViewerIndex.value = list.length - 1
  }
  return list[resultViewerIndex.value]
})

const viewerNavInfo = computed(() => {
  const total = filteredStepResults.value.length
  if (!total) return ''
  const idx = resultViewerIndex.value + 1
  return `${idx}/${total}`
})

const resultViewerTitle = computed(() => {
  const r = currentStepResult.value
  if (!r) return '等待执行...'
  const cat = r.loop_item || ''
  const name = r.step_name || r.step_id || ''
  return cat ? `[${cat}] ${name}` : name
})

// 是否有任何数据（重置按钮 disabled 判断）
const hasAnyData = computed(() =>
  filteredStepResults.value.length > 0 ||
  store.sandboxData != null ||
  store.productDef.length > 0
)

/** 单步执行是否可用：
 *   场景A 主循环已暂停 → 可以点（让主循环走一步再自动 pause）
 *   场景B 流程未启动/已结束 → 可以点（新开线程跑一个 run_single_step）
 *   正在 running（未暂停）→ 不允许（后端会拒绝）
 */
const canStep = computed(() => {
  // 正在 streaming 且没 paused → 不允许
  if (store.isStreaming && !store.isPaused) return false
  // 有 instance_key 就行
  return !!selectedInstanceKey.value
})

/** 重复本步是否可用：
 *   流程运行中 → 不允许（快照会被覆盖）
 *   无历史步骤 → 不允许（后端无 snapshot 可恢复）
 */
const canRepeat = computed(() => {
  // 流程存活态 → 不允许
  if (store.isStreaming) return false
  if (store.isPaused) return false
  // 必须至少执行过一步（snapshot 的前端 proxy）
  if (filteredStepResults.value.length === 0) return false
  return !!selectedInstanceKey.value
})

// ==================================================================
// 紧凑进度面板 — 辅助计算（全部从 store 新 computed 取）
// ==================================================================

/** 当前活跃的 loop item（直接从 store statesTree 取） */
const activeLoopItem = computed(() => store.currentLoopItem)

// ===== 旧的 currentLoopSteps / allLoopSteps / doneLoopCount 已删掉 =====
// 新方案直接从 store.innerStepList / store.allLoopItems / store.completedLoopItems 取

// ==================================================================
// 执行状态（动态颜色 + 文本，对齐 flet _set_execution_status）
// ==================================================================
const executionStatusText = computed(() => {
  if (store.errorMessage) return `错误: ${store.errorMessage}`
  if (store.isPaused) return '流程已暂停（点击继续恢复）'
  if (store.isStreaming) {
    if (loadingMessage.value) return loadingMessage.value
    return '正在执行流程...'
  }
  if (store.finalStatus === 'success') return '流程执行完成'
  if (store.finalStatus === 'stopped') return '流程已停止'
  if (store.finalStatus === 'error') return '流程执行失败'
  return '等待操作...'
})

const execStatusColor = computed(() => {
  if (store.errorMessage) return '#f56c6c'
  if (store.isPaused) return '#e6a23c'
  if (store.isStreaming) return '#409eff'
  if (store.finalStatus === 'success') return '#67c23a'
  if (store.finalStatus === 'error') return '#f56c6c'
  return '#909399'
})

// ==================================================================
// 其他计算属性（保留旧代码）
// ==================================================================

const activeOuterStepIndex = computed(() => {
  const runningIdx = store.outerStepList.findIndex(s => s.status === 'running')
  if (runningIdx >= 0) return runningIdx
  const doneCount = store.outerStepList.filter(s => s.status === 'done').length
  return Math.min(doneCount, store.outerStepList.length - 1)
})

const progressStatus = computed(() => {
  if (store.finalStatus === 'error') return 'exception'
  if (store.finalStatus === 'success') return 'success'
  return ''
})

const finalStatusLabel = computed(() => {
  const map: Record<string, string> = {
    success: '流程执行完成 ✅',
    stopped: '流程已停止 ⏹',
    error: '流程执行失败 ❌',
    paused: '流程已暂停 ⏸',
  }
  return store.finalStatus ? (map[store.finalStatus] || `流程状态: ${store.finalStatus}`) : ''
})

const productEmptyDesc = computed(() => {
  if (!selectedInstanceKey.value) return '请先选择车型'
  return store.isStreaming ? '流程执行中...请稍后刷新' : '未加载产品定义数据（先启动流程或检查 Excel）'
})

const sandboxEmptyDesc = computed(() => {
  if (!selectedInstanceKey.value) return '请先选择车型'
  if (store.isStreaming) return '流程执行中...沙箱数据在流程结束后可用'
  if (store.sandboxData === null) return '尚未加载流程数据，点击「刷新」重试'
  return '沙箱数据为空（流程未产生中间数据）'
})

const isSandboxEmpty = computed(() => {
  const d = store.sandboxData
  if (d === null || d === undefined) return true
  if (typeof d === 'object') return Object.keys(d).length === 0
  if (Array.isArray(d)) return d.length === 0
  return false
})

// ==================================================================
// Sandbox → el-tree 节点（保留旧代码）
// ==================================================================

interface TreeNode {
  path: string
  key: string
  label: string
  value?: any
  type?: string
  isLeaf?: boolean
  children?: TreeNode[]
}

const sandboxTreeNodes = computed<TreeNode[]>(() => {
  const data = store.sandboxData
  if (data == null) return []
  return buildTree(data, 'root', 'root')
})

const stepResultTreeNodes = computed<TreeNode[]>(() => {
  const r = currentStepResult.value
  if (!r) return []
  // 和 formatStepResultForViewer 一样的聚合逻辑，但输出原始对象给 buildTree
  const sr = r.step_result || {}
  const parts: any[] = []
  if (sr.content) parts.push({ '最终结果（post_process）': sr.content })
  const msgs = sr.debug_info?.messages
  if (msgs?.length) parts.push({ 'LLM 原始对话历史': msgs })
  const data = parts.length ? parts : sr
  return buildTree(data, 'root', 'root')
})

function buildTree(val: any, key: string, path: string): TreeNode[] {
  if (val === null || val === undefined) {
    return [{ path, key, label: key, value: null, type: 'null', isLeaf: true }]
  }
  // JSON 字符串自动解析（后端 content 经常是 JSON.stringify 后的字符串）
  if (typeof val === 'string') {
    const trimmed = val.trim()
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try {
        const parsed = JSON.parse(trimmed)
        return buildTree(parsed, key, path)
      } catch { /* 不是合法 JSON，继续当字符串处理 */ }
    }
  }
  if (Array.isArray(val)) {
    if (val.length === 0) return [{ path, key, label: `${key} (空数组)`, isLeaf: true }]
    const items = val.map((item, i) => {
      const childPath = `${path}[${i}]`
      return buildTree(item, String(i), childPath)
    })
    return items.flat()
  }
  if (typeof val === 'object') {
    const entries = Object.entries(val)
    if (entries.length === 0) return [{ path, key, label: `${key} (空对象)`, isLeaf: true }]
    return entries.map(([k, v]) => {
      const childPath = path === 'root' ? k : `${path}.${k}`
      const childNodes = buildTree(v, k, childPath)
      if (childNodes.length === 1 && childNodes[0].isLeaf) {
        const leaf = childNodes[0]
        return {
          path: childPath,
          key: k,
          label: `${k}: ${leaf.value ?? ''}`,
          value: leaf.value,
          type: leaf.type,
          isLeaf: true,
        }
      }
      return { path: childPath, key: k, label: k, children: childNodes }
    })
  }
  const type = typeof val
  return [{ path, key, label: `${key}: ${val}`, value: val, type, isLeaf: true }]
}

// ==================================================================
// UI 辅助函数（紧凑进度面板专用）
// ==================================================================

function stepColor(status: string): string {
  if (status === 'done') return '#67c23a'
  if (status === 'running') return '#409eff'
  return '#c0c4cc'
}

function outerStepIcon(status: string) {
  if (status === 'done') return CircleCheck
  // running / pending 都用 MoreFilled（三圆点），靠颜色区分
  return MoreFilled
}

function innerStepIcon(status: string) {
  if (status === 'done') return Check
  return MoreFilled
}

function chipClassForItem(cat: string): string {
  if (cat === activeLoopItem.value) return 'chip-current'
  if (store.completedLoopItems.includes(cat)) return 'chip-done'
  return 'chip-pending'
}

function chipIconForItem(cat: string) {
  if (cat === activeLoopItem.value) return MoreFilled
  if (store.completedLoopItems.includes(cat)) return Check
  return MoreFilled
}

function shortName(name: string): string {
  if (!name) return ''
  return name.length > 6 ? name.slice(0, 6) : name
}

// ==================================================================
// StepResultViewer 格式化 + 导航（对齐 flet format_result_content）
// ==================================================================

function navViewer(delta: number) {
  const total = filteredStepResults.value.length
  if (!total) return
  resultViewerIndex.value = Math.max(0, Math.min(total - 1, resultViewerIndex.value + delta))
}

function formatStepResultForViewer(r: any): string {
  if (!r) return '等待执行...'
  const sr = r.step_result || {}
  const parts: any[] = []

  // Part 1: 框架最终结果（result.content）
  const content = sr.content
  if (content) {
    parts.push({ label: '最终结果（post_process 修正后）', data: content })
  }

  // Part 2: LLM 原始对话历史（debug_info.messages）
  const debug = sr.debug_info
  const messages = debug?.messages
  if (messages && messages.length) {
    parts.push({ label: 'LLM 原始对话历史', data: messages })
  }

  if (parts.length) return safeJson(parts)
  return safeJson(sr)
}

// ==================================================================
// 复制函数
// ==================================================================

async function copyResults() {
  try {
    const json = safeJson(filteredStepResults.value.map(r => ({
      step_name: r.step_name,
      category: r.loop_item,
      result: r.step_result,
    })))
    await navigator.clipboard.writeText(json)
    copyResultsStatus.value = '✓ 已复制到剪贴板'
    setTimeout(() => { copyResultsStatus.value = '' }, 3000)
  } catch {
    copyResultsStatus.value = '✗ 复制失败'
    setTimeout(() => { copyResultsStatus.value = '' }, 3000)
  }
}

async function copyFlowData() {
  try {
    const json = safeJson(store.sandboxData)
    await navigator.clipboard.writeText(json)
    copyFlowDataStatus.value = '✓ 已复制到剪贴板'
    setTimeout(() => { copyFlowDataStatus.value = '' }, 3000)
  } catch {
    copyFlowDataStatus.value = '✗ 复制失败'
    setTimeout(() => { copyFlowDataStatus.value = '' }, 3000)
  }
}

// ==================================================================
// UI 辅助函数（保留旧代码）
// ==================================================================

function stepElStatus(s: string) {
  const map: Record<string, any> = {
    pending: 'wait', running: 'process', done: 'finish', error: 'error', skipped: 'wait',
  }
  return map[s] || 'wait'
}

function timelineType(s: string) {
  const map: Record<string, string> = {
    running: 'primary', done: 'success', error: 'danger', pending: 'info',
  }
  return map[s] || 'info'
}

function safeJson(v: any): string {
  try {
    if (typeof v === 'string') return v
    return JSON.stringify(v, null, 2)
  } catch { return String(v) }
}

function formatProductValue(row: any): string {
  const val = row.值 ?? row.value
  if (val === null || val === undefined || val === '') return '-'
  // 对齐 SSTS/VTS 的 .2f 格式
  let display: string
  if (typeof val === 'number') {
    display = String(Math.round(val * 100) / 100)
  } else if (typeof val === 'object') {
    try { display = JSON.stringify(val) } catch { display = String(val) }
  } else {
    display = String(val)
  }
  const unit = row.单位 ?? row.unit
  if (unit && unit !== 'Null' && unit !== '') return `${display} ${unit}`
  return display
}

// ==================================================================
// Sheet 切换（对齐 flet _on_sheet_changed visible 切换逻辑）
// ==================================================================
function onSheetChanged(sheetKey: string) {
  if (activeSheet.value === sheetKey) return
  activeSheet.value = sheetKey
  onRefreshCurrentTab(sheetKey)
}

// ==================================================================
// 事件处理
// ==================================================================

async function onStart() {
  if (!selectedInstanceKey.value) return
  try {
    await startProcess(selectedInstanceKey.value, 'ALL')
  } catch (e: any) {
    ElMessage.error(e?.message || '启动失败')
  }
}

async function onStop() { await stopProcess() }
async function onPause() { await pauseProcess() }
async function onResume() { await resumeProcess() }
async function onStep() { await stepProcess() }
async function onRepeat() { await repeatProcess() }

async function onReset() {
  // 先清后端锁（如果有）
  if (selectedInstanceKey.value && store.isStreaming) {
    try {
      await stopProcess()
    } catch { /* 后端可能已经不在执行，忽略 */ }
  }
  store.reset()
  resultViewerIndex.value = -1
  copyResultsStatus.value = ''
  copyFlowDataStatus.value = ''
  selectedInstanceKey.value = ''
}

function onVehicleChanged() {
  // 车型切换时，清除所有已加载的数据 + 暂停状态 + viewer 索引
  store.stepResults = []
  store.productDef = []
  store.sandboxData = null
  store.vtsSheet = null
  store.sstsSheet = null
  store.isPaused = false
  resultViewerIndex.value = -1
  // 同时刷新当前 tab
  onRefreshCurrentTab(activeSheet.value)
}

async function onRefreshCurrentTab(sheetKey?: string) {
  const sheet = sheetKey || activeSheet.value
  const ik = selectedInstanceKey.value
  const suffix = selectedSuffix.value
  if (!ik) return
  tabLoading.value = true
  try {
    let res: any = null
    switch (sheet) {
      case 'STEP_RESULTS': res = await loadStepResults(ik); break
      case 'PRODUCT_DEF': res = await loadProductDef(ik); break
      case 'FLOW_DATA': res = await loadSandbox(ik); break
      case 'SSTS':
      case 'VTS': res = await loadVehicleSheets(ik); break
    }
    // eslint-disable-next-line no-console
    console.log(`[DEBUG][Tab refresh] sheet=${sheet} ik=${ik} suffix=${suffix} productDef.length=${store.productDef.length} sandboxData=${store.sandboxData ? 'ok' : 'null'} stepResults.length=${store.stepResults.length}`)
  } finally {
    tabLoading.value = false
  }
}

/** 监听 store.finalStatus — 流程结束后触发所有 tab 数据加载 */
watch(
  () => store.finalStatus,
  (status) => {
    if (status && store.instanceKey) {
      loadAllAfterDone(store.instanceKey, selectedSuffix.value)
    }
  },
  { immediate: false },
)
</script>

<style scoped>
/* 覆盖 Element Plus divider 默认的 margin: 16px 0 */
:deep(.el-divider--horizontal) {
  margin: 2px 0 !important;
}
/* 表头不换行 */
:deep(.el-table th.el-table__cell) {
  white-space: nowrap;
}

.process-page {
  padding: 2px 2px;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: white;
  border-radius: 4px;
}

/* ========== ① 车型选择行 ========== */
.vehicle-tab-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.vehicle-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

/* ========== ② 紧凑进度面板 ========== */
.progress-compact {
  background: #f5f5f5;
  border-radius: 4px;
  padding: 1px 1px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.progress-line {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  white-space: nowrap;
  font-size: 11px;
}
.line-label {
  color: #606266;
  flex-shrink: 0;
  font-weight: 500;
}

/* Chip 行 */
.chip-line { gap: 6px; }
.chip-label { color: #606266; flex-shrink: 0; font-size: 11px; }
.category-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  border: 1px solid;
  border-radius: 3px;
  font-size: 11px;
}
.chip-current {
  color: #409eff;
  border-color: #409eff;
  background: #ecf5ff;
}
.chip-done {
  color: #67c23a;
  border-color: #67c23a;
  background: #f0f9eb;
}
.chip-pending {
  color: #c0c4cc;
  border-color: #dcdfe6;
  background: transparent;
}
.chip-spacer { flex: 1; }
.chip-stats { color: #909399; font-size: 11px; }
.chip-wait { color: #909399; font-size: 11px; }

/* 外层步骤行 */
.outer-line { gap: 8px; }
.step-item-outer {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  flex-shrink: 0;
}
.arrow { color: #c0c4cc; margin: 0 2px; }

/* 内层步骤行 */
.inner-line { gap: 6px; }
.step-item-inner {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  flex-shrink: 0;
}
.inner-step-label { font-size: 10px; }

/* ========== ③ 按钮行 ========== */
.buttons-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0;
  align-items: center;
}
.btn-sep {
  display: inline-block;
  width: 1px;
  height: 16px;
  background: #dcdfe6;
  margin: 0 6px;
}

/* ========== ④ 执行状态行 ========== */
.exec-status-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: #f5f5f5;
  border-radius: 3px;
  font-size: 11px;
}
.exec-status-text { font-weight: 500; }

/* ========== ⑤ Sheet Tab 栏 ========== */
.sheet-tab-row {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #e4e7ed;
  margin-bottom: 0;
}
.sheet-tab-item {
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
  color: #606266;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  user-select: none;
}
.sheet-tab-item:hover {
  color: #409eff;
}
.sheet-tab-item.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 600;
}

/* ========== ⑥ 内容区 ========== */
.content-area {
  min-height: 400px;
}

/* StepResultViewer */
.result-viewer-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.copy-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}
.copy-label { font-size: 12px; font-weight: 600; color: #303133; }
.copy-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.copy-icon:hover { color: #409eff; }
.copy-status { font-size: 11px; color: #67c23a; }

.viewer-main {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: white;
}
.viewer-nav-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 1px 2px;
  border-bottom: 1px solid #f0f0f0;
}
.nav-buttons {
  display: flex;
  align-items: center;
  gap: 4px;
}
.nav-buttons .el-icon {
  cursor: pointer;
  color: #409eff;
  transition: opacity 0.2s;
}
.nav-buttons .el-icon.disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.viewer-title {
  font-size: 12px;
  font-weight: bold;
  color: #409eff;
}
.viewer-nav-info {
  margin-left: auto;
  font-size: 11px;
  color: #909399;
}
.viewer-scroll {
  max-height: 420px;
  overflow-y: auto;
  padding: 4px;
}
.viewer-content {
  border-left: 3px solid #93c5fd;
  padding-left: 10px;
}
.viewer-content pre {
  font-size: 11px;
  font-family: Consolas, 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #303133;
  line-height: 1.6;
}
.viewer-wait {
  color: #909399;
  font-size: 12px;
  padding: 2px 2px;
}

/* 数据表格容器 */
.table-container {
  min-height: 400px;
}

/* 产品定义 3 列表格 */
.table-footer { margin-top: 8px; font-size: 11px; color: #909399; }

/* 流程数据 JSON 树 */
.json-tree {
  padding: 2px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  max-height: 520px;
  overflow: auto;
}
.tree-node { font-size: 11px; white-space: normal; word-break: break-all; line-height: 1.5; }
.tree-key { color: #303133; font-weight: 500; }
.tree-value { margin-left: 8px; }
.tree-leaf .tree-leaf-val {
  color: #67c23a; font-family: Consolas, 'Courier New', monospace;
  white-space: normal;
  word-break: break-all;
}

/* EP el-tree 默认 26px 固定高度 + nowrap 会截断长文本。
   只改高度为自适应 + 允许换行，不动其他 EP 内部布局。 */
:deep(.el-tree-node__content) {
  height: auto !important;
  min-height: 26px;
  white-space: normal !important;
}
:deep(.el-tree-node__content .el-tree-node__label) {
  white-space: normal !important;
}

/* 最终总结报告（保留旧样式） */
.summary-section { margin-top: 16px; }
.summary-content { padding: 12px 4px; }
.summary-content :deep(h3) { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
.summary-content :deep(ul), .summary-content :deep(ol) { padding-left: 20px; }
.summary-content :deep(p) { margin: 6px 0; line-height: 1.7; }

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 12px;
  color: #303133;
  margin-bottom: 1px;
  margin-top: 1px;
}
</style>
