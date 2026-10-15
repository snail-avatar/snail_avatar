// @Time    : 2026
// @Author  : 李涛
// @File    : WorkflowPage.vue
// @Desc    : WorkflowPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  WorkflowPage — 动力性/经济性 通用工作流计算页面

  配置驱动：不同 workflow_id + vehicle_type 显示不同内容：
    power_rwd      → 动力性（加速/最高速/爬坡）
    EV_ECO_CALC    → 经济性（纯电续航）
    REEV_ECO_CALC  → 经济性（增程续航）

  对齐 Flet BaseWorkflowTab UI 结构：
    顶部工具栏（车型选择 + 运行按钮）
    中部：DAG 节点图（SVG 绘制）
    底部：Tabs（数值信息 ←输入|输出→ | 图示信息 折线图）
-->
<template>
  <div class="wf-page">

    <!-- ❌ 未加载 Excel 时显示空态提示 -->
    <div v-if="!excelLoaded" class="wf-empty">
      <el-empty description="尚未载入项目数据">
        <template #image>
          <el-icon :size="64" color="#c0c4cc"><FolderOpened /></el-icon>
        </template>
        <div class="empty-tip">
          请点击顶部工具栏的 <strong>📂 打开按钮</strong>，选择项目配置 Excel 文件后开始工作流计算。
        </div>
      </el-empty>
    </div>

    <template v-else>

    <!-- ① 顶部工具栏已上移到 MainLayout 标题行右侧（通过 rightPanelHeaderExtra factory 注入） -->

    <!-- ② 中部 DAG 节点图 -->
    <div class="dag-box">
      <div class="dag-inner">
        <svg
          v-if="dagNodes.length > 0"
          :width="dagWidth"
          :height="dagHeight"
          class="dag-svg"
        >
          <!-- 连线（先画线，后画节点让节点在上） -->
          <g class="dag-edges">
            <path
              v-for="(e, i) in dagEdges"
              :key="'e'+i"
              :d="e.path"
              :stroke="edgeStroke(e)"
              :stroke-width="edgeWidth(e)"
              :stroke-opacity="edgeOpacity(e)"
              fill="none"
              :marker-end="edgeMarker(e)"
            />
          </g>
          <!-- 节点 -->
          <g class="dag-nodes">
            <g
              v-for="n in dagNodes"
              :key="n.node_id"
              :transform="`translate(${n.x}, ${n.y})`"
              class="dag-node"
              :class="{
                sel: selectedNode === n.node_id,
                running: n.state === 'running',
                success: n.state === 'completed',
                error: n.state === 'error',
                pending: !n.state || n.state === 'pending',
              }"
              @click="onSelectNode(n.node_id)"
            >
              <rect
                :width="NODE_W" :height="NODE_H" rx="6"
                :fill="n.bg_color"
                :stroke="nodeBorderColor(n)"
                stroke-width="1.5"
              />
              <!-- 注意：SVG <g transform> 内的 text 百分比坐标是相对 viewBox 不是 group！
                   必须用绝对像素 NODE_W/2, NODE_H*0.4 等 -->
              <text
                :x="NODE_W / 2" :y="NODE_H * 0.38"
                text-anchor="middle" dominant-baseline="middle"
                font-size="11" font-weight="600"
                :fill="nodeTextColor(n)"
              >{{ n.display_name }}</text>
              <text
                :x="NODE_W / 2" :y="NODE_H * 0.72"
                text-anchor="middle" dominant-baseline="middle"
                font-size="9"
                :fill="nodeSubColor(n)"
              >{{ n.node_id }}</text>
              <!-- 状态角标 -->
              <circle
                v-if="n.state"
                :cx="NODE_W - 8" cy="8" r="4"
                :fill="nodeStateColor(n)"
              />
            </g>
          </g>
          <defs>
            <!-- 三种箭头 marker，颜色与对应边保持一致 -->
            <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#409eff" />
            </marker>
            <marker id="arrow-normal" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#dcdfe6" />
            </marker>
            <marker id="arrow-dim" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#c0c4cc" fill-opacity="0.25" />
            </marker>
          </defs>
        </svg>
        <div v-else class="dag-empty">
          <el-empty description="暂无工作流节点" />
        </div>
      </div>
    </div>

    <!-- 可拖拽分割条 -->
    <div class="wf-splitter" @mousedown="onSplitterMouseDown" title="拖拽调整计算区/结果区高度">
      <div class="wf-splitter-bar"></div>
    </div>

    <!-- ③ 底部 Tabs：数值信息 | 图示信息 -->
    <el-tabs v-model="bottomTab" class="wf-bottom-tabs" :style="{ height: bottomTabsHeight + 'px' }">
      <!-- Tab 1: 数值信息（左输入 | 右输出） -->
      <el-tab-pane label="数值信息" name="numeric">
        <div class="numeric-row">
          <!-- 左：输入参数（固定宽度，可拖拽调整） -->
          <div class="io-panel io-left" :style="{ width: leftPanelWidth + 'px', flex: 'none' }">
            <div class="io-header">⬅ 输入参数</div>
            <div class="io-body">
              <!-- SSTS 节点：sandbox_snapshot 用树形组件显示零部件文件清单 -->
              <template v-if="isSstsNode && sandboxSnapshot">
                <CollapsibleJson :data="sandboxSnapshot" />
              </template>
              <!-- 其他所有变量（含 SSTS 节点的非 snapshot 变量）走通用 io-row -->
              <template v-for="v in inputVars" :key="v.name">
                <template v-if="!(isSstsNode && v.name === 'sandbox_snapshot')">
                  <div class="io-row">
                    <span class="io-name">{{ v.name }}</span>
                    <span class="io-val">{{ formatVal(v.value) }}</span>
                    <span class="io-unit" v-if="v.unit">{{ v.unit }}</span>
                  </div>
                </template>
              </template>
              <div v-if="!inputVars.length" class="io-empty">（未运行）</div>
            </div>
          </div>

          <!-- 可拖拽左右分割条 -->
          <div class="wf-vsplitter" @mousedown="onVSplitterMouseDown" title="拖拽调整输入/输出宽度" />

          <!-- 右：输出结果（自动填充剩余） -->
          <div class="io-panel io-right">
            <div class="io-header">➡ 输出结果</div>
            <div class="io-body">
              <!-- SSTS 节点：motor_variants 用方案对比表（按 axle 分组横向排方案列） -->
              <template v-if="isSstsNode && variantCompareTable">
                <div class="variant-table-wrap">
                  <table class="variant-compare-table">
                    <!-- 二级表头（axle 分组） -->
                    <thead>
                      <tr class="vt-header-axle">
                        <th class="vt-th-left" :rowspan="2"></th>
                        <template v-for="(g, gi) in variantCompareTable.headerGroups" :key="'g'+gi">
                          <th
                            :colspan="g.labels.length"
                            class="vt-th-axle"
                            :class="'vt-axle-' + g.axle"
                          >{{ g.axle === 'front' ? '前轴' : g.axle === 'rear' ? '后轴' : g.axle }}</th>
                        </template>
                      </tr>
                      <tr class="vt-header-variant">
                        <template v-for="(col, ci) in variantCompareTable.columns" :key="'c'+ci">
                          <th class="vt-th-variant" :class="'vt-axle-' + col.axle">{{ col.variantName }}</th>
                        </template>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, ri) in variantCompareTable.rows" :key="'r'+ri">
                        <td class="vt-td-label">
                          <span class="vt-label">{{ row.label }}</span>
                          <span v-if="row.unit" class="vt-unit">({{ row.unit }})</span>
                        </td>
                        <template v-for="(cell, ci) in row.cells" :key="'rc'+ri+'-'+ci">
                          <td class="vt-td-cell" :class="'vt-axle-' + cell.axle">{{ cell.display }}</td>
                        </template>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
              <!-- SSTS 节点：motor_variants 完整 intermediate（大数组做轻量摘要化） -->
              <template v-if="isSstsNode && motorVariantsSummarized">
                <CollapsibleJson :data="motorVariantsSummarized" />
              </template>
              <!-- 其他所有输出（含 SSTS 节点的 semantic_summary）走通用 io-row -->
              <template v-for="v in outputVars" :key="v.name">
                <template v-if="!(isSstsNode && v.name === 'motor_variants' && motorVariantsSummarized)">
                  <div class="io-row">
                    <span class="io-name">{{ v.name }}</span>
                    <!-- semantic_summary 是长 Markdown 文本，直接 pre-wrap 换行显示 -->
                    <span v-if="v.name === 'semantic_summary'" class="io-val io-md">
                      {{ v.value }}
                    </span>
                    <span v-else class="io-val">{{ formatVal(v.value) }}</span>
                    <span class="io-unit" v-if="v.unit">{{ v.unit }}</span>
                  </div>
                </template>
              </template>
              <div v-if="!outputVars.length" class="io-empty">（未运行）</div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 图示信息（折线图） -->
      <el-tab-pane label="图示信息" name="chart">
        <div class="chart-box">
          <div v-if="charts.length === 0" class="chart-empty">
            <el-alert type="info" :closable="false" show-icon>
              暂无可视化数据（当前 workflow 未提供图示）
            </el-alert>
          </div>
          <div v-else-if="filteredCharts.length === 0" class="chart-empty">
            <el-alert type="info" :closable="false" show-icon>
              请点击 DAG 上的节点查看该节点的图示
            </el-alert>
          </div>
          <div v-for="(c, i) in filteredCharts" :key="i" class="chart-item">
            <div class="chart-title">{{ c._node || '' }} · {{ c.title }}</div>
            <div ref="chartRefs" class="chart-canvas" :data-chart="i"></div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 参数浏览器（SSTS 专属） -->
      <el-tab-pane v-if="panelType === 'energy_regen'" label="参数浏览器" name="sandbox">
        <div class="sandbox-box">
          <div v-if="sandboxLoading" class="sandbox-empty">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else-if="!sandboxData || !sandboxData.is_project_loaded" class="sandbox-empty">
            <el-alert type="info" :closable="false" show-icon>
              沙箱未加载。请确保：① 已打开项目 Excel ② 项目根目录下有 Motor/Brake/Battery 等零部件文件夹
            </el-alert>
          </div>
          <div v-else class="sandbox-content">
            <!-- 项目元信息头部 -->
            <div class="sandbox-meta">
              <el-tag type="success" effect="dark" size="small">
                ✅ 已加载 {{ sandboxData.loaded_file_count }} 个文件
              </el-tag>
              <span class="meta-path" :title="currentSandboxFolder">
                📁 {{ currentSandboxFolder || sandboxData.project_folder }}
              </span>
              <span v-if="sandboxData.last_load_time" class="meta-time">
                加载时间: {{ formatSandboxTime(sandboxData.last_load_time) }}
              </span>
            </div>

            <!-- 两栏主体：左目录树 + 右详情面板 -->
            <div class="sandbox-body">
              <!-- 左栏：参数目录树 -->
              <div class="sandbox-tree-col" :style="{ width: treeColWidth + 'px' }">
                <el-tree
                  :data="sandboxTreeData"
                  node-key="key"
                  default-expand-all
                  :expand-on-click-node="false"
                  highlight-current
                  @node-click="onSandboxNodeClick"
                >
                  <template #default="{ node, data }">
                    <div class="tree-node" :class="data._kind || ''">
                      <span class="tree-label">{{ node.label }}</span>
                      <span v-if="data._badge" class="tree-badge" :class="data._badge_class || ''">
                        {{ data._badge }}
                      </span>
                      <span v-if="data._sub" class="tree-sub">{{ data._sub }}</span>
                    </div>
                  </template>
                </el-tree>
              </div>

              <!-- 可拖动分隔条 -->
              <div class="sandbox-splitter"
                   :class="{ dragging: splitterDragging }"
                   @mousedown="onSplitterDown"></div>

              <!-- 右栏：详情面板 -->
              <div class="sandbox-detail-col">
                <div v-if="!selectedSheet" class="detail-placeholder">
                  <el-empty description="点击左侧某个参数节点查看详情" />
                </div>
                <div v-else-if="sheetDetailLoading" class="detail-loading">
                  <el-skeleton :rows="5" animated />
                </div>
                <div v-else-if="sheetDetail?._error" class="detail-error">
                  <el-alert type="error" :title="sheetDetail._error" show-icon />
                </div>
                <div v-else class="detail-content">
                  <!-- 详情头部 -->
                  <div class="detail-header">
                    <span class="detail-title">{{ selectedSheet.sheet_name }}</span>
                    <el-tag size="small">{{ sheetDetail.type }}</el-tag>
                    <el-tag size="small" type="info">
                      {{ sheetDetail.type === 'curve_1d' ? `${(sheetDetail.x || []).length} 点` :
                         sheetDetail.type === 'map_2d' ? `${(sheetDetail.y || []).length}×${(sheetDetail.x || []).length}` :
                         sheetDetail.type === 'scalar_dict' ? `${Object.keys(sheetDetail.data || {}).length} 参数` :
                         '标量' }}
                    </el-tag>
                  </div>

                  <!-- curve_1d: ECharts 折线图 -->
                  <div v-if="sheetDetail.type === 'curve_1d'" ref="curveChartRef" class="echarts-box"></div>

                  <!-- map_2d: ECharts 热力图 -->
                  <div v-else-if="sheetDetail.type === 'map_2d'" ref="heatmapChartRef" class="echarts-box"></div>

                  <!-- scalar_dict: key-value 表格（减速器、电池参数组等） -->
                  <div v-else-if="sheetDetail.type === 'scalar_dict'" class="detail-scalar">
                    <el-table
                      :data="Object.entries(sheetDetail.data || {}).map(([k, v]) => ({ key: k, value: v }))"
                      border size="small" style="width: 100%"
                    >
                      <el-table-column prop="key" label="参数" width="180" />
                      <el-table-column prop="value" label="值" />
                    </el-table>
                  </div>

                  <!-- scalar -->
                  <div v-else class="detail-scalar">
                    <pre>{{ JSON.stringify(sheetDetail.value ?? sheetDetail, null, 2) }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    </template>  <!-- 关闭 v-else -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, h, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage, ElSelect, ElOption, ElButton } from 'element-plus'
import { api } from '../api/request'
import { useMemoryDbStore } from '../stores/useMemoryDbStore'
import CollapsibleJson from './CollapsibleJson.vue'
import * as echarts from 'echarts'
// echarts 用 UMD script 标签引入（index.html），全局 window.echarts
// 避开 Vite ESM 解析问题（echarts 6.x 没有标准 default export）
declare global { interface Window { echarts: any } }
const _echarts = () => window.echarts

// ========= Props =========
// panel_type: 面板类型（对应 Flet BaseWorkflowTab 中的 panel_id）
//   power       → 动力性面板
//   economy     → 经济性面板
//   energy_regen → 能量回收面板
// 后端会根据 vehicle_suffix（车型后缀）从 memory_db.vehsuffix 读能源形式/驱动形式，
// 自动匹配正确的 workflow YAML（EV_ECO_CALC / REEV_ECO_CALC / power_rwd 等）
interface Props {
  panelType: string       // Vue 自动把 panel-type 转成 panelType
  pageTitle?: string
}
const props = defineProps<Props>()

// 用 panel_type 作为请求 ID（直接传给后端，后端自动匹配 YAML）
const pageTitle = computed(() => props.pageTitle || props.panelType)

// ========= 状态 =========
// excelLoaded 从 memStore.computed 派生（见下方 L562），这里不再单独声明
const suffixLoading = ref(false)
const selectedSuffix = ref('')
const running = ref(false)
const runResult = ref<{ completed: number; errors: number; duration_sec: number } | null>(null)

// ============ localStorage 持久化 key ============
function _cacheKey() {
  return `wf:${props.panelType}:${selectedSuffix.value}`
}
function _saveCache() {
  if (!selectedSuffix.value || !runResult.value) return
  try {
    const cache = {
      runResult: runResult.value,
      nodeResults: nodeResults.value,
      dagNodes: dagNodes.value.map((n: any) => ({ node_id: n.node_id, state: n.state })),
      dagEdges: dagEdges.value.map((e: any) => ({ from: e.from, to: e.to, color: e.color })),
      selectedNode: selectedNode.value,
      ts: Date.now(),
    }
    localStorage.setItem(_cacheKey(), JSON.stringify(cache))
  } catch { /* ignore */ }
}
function _loadCache() {
  if (!selectedSuffix.value) return
  try {
    const raw = localStorage.getItem(_cacheKey())
    if (!raw) return
    const cache = JSON.parse(raw)
    if (cache.runResult) runResult.value = cache.runResult
    if (cache.nodeResults) nodeResults.value = cache.nodeResults
    // 恢复节点 state（拓扑已经从 loadTopology 渲染好了）
    const stateMap = new Map((cache.dagNodes || []).map((n: any) => [n.node_id, n.state]))
    for (const n of dagNodes.value) {
      if (stateMap.has(n.node_id)) n.state = stateMap.get(n.node_id)
    }
    // 恢复边颜色
    const edgeMap = new Map((cache.dagEdges || []).map((e: any) => [`${e.from}->${e.to}`, e.color]))
    for (const e of dagEdges.value) {
      const c = edgeMap.get(`${e.from}->${e.to}`)
      if (c) e.color = c
    }
    if (cache.selectedNode) selectedNode.value = cache.selectedNode
  } catch { /* ignore */ }
}

// DAG 拓扑
const dagNodes = ref<any[]>([])
const dagEdges = ref<any[]>([])
const selectedNode = ref<string | null>(null)
const NODE_W = 140
const NODE_H = 54

// 底部 Tabs
const bottomTab = ref('numeric')

// ===== 参数浏览器（原沙箱内存）Tab 状态 =====
const sandboxLoading = ref(false)
const sandboxData = ref<any>(null)

// 右侧详情面板状态
const selectedSheet = ref<any>(null)          // 当前点击的 sheet 节点
const sheetDetailLoading = ref(false)         // 详情加载中
const sheetDetail = ref<any>(null)            // 后端 /sandbox/sheet 返回的 data 字段

// ===== sandbox 两栏左右拖拽 splitter =====
const TREE_COL_MIN = 180
const TREE_COL_MAX = 700
const treeColWidth = ref(320)                 // 左栏初始宽度 px
const splitterDragging = ref(false)
let _splitStartX = 0
let _splitStartW = 0
function onSplitterDown(e: MouseEvent) {
  splitterDragging.value = true
  _splitStartX = e.clientX
  _splitStartW = treeColWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', _onSplitMove)
  document.addEventListener('mouseup', _onSplitUp)
}
function _onSplitMove(e: MouseEvent) {
  const dx = e.clientX - _splitStartX
  treeColWidth.value = Math.min(TREE_COL_MAX, Math.max(TREE_COL_MIN, _splitStartW + dx))
}
function _onSplitUp() {
  splitterDragging.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', _onSplitMove)
  document.removeEventListener('mouseup', _onSplitUp)
  // 拖拽结束后重新 resize 两个 ECharts 实例
  curveChart?.resize()
  heatmapChart?.resize()
}

const MIN_BOTTOM_H = 200
const MAX_BOTTOM_H = 800
const bottomTabsHeight = ref(520)
let _dragStartY = 0
let _dragStartH = 0
function onSplitterMouseDown(e: MouseEvent) {
  _dragStartY = e.clientY
  _dragStartH = bottomTabsHeight.value
  document.addEventListener('mousemove', onSplitterMouseMove)
  document.addEventListener('mouseup', onSplitterMouseUp)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
}
function onSplitterMouseMove(e: MouseEvent) {
  const dy = _dragStartY - e.clientY  // 鼠标上移 → bottom 变高
  const h = Math.max(MIN_BOTTOM_H, Math.min(MAX_BOTTOM_H, _dragStartH + dy))
  bottomTabsHeight.value = h
}
function onSplitterMouseUp() {
  document.removeEventListener('mousemove', onSplitterMouseMove)
  document.removeEventListener('mouseup', onSplitterMouseUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// ===== 左右分割条（输入参数 / 输出结果）=====
const MIN_LEFT_W = 120
const MAX_LEFT_W = 600
const leftPanelWidth = ref(260)
let _vDragStartX = 0
let _vDragStartW = 0
function onVSplitterMouseDown(e: MouseEvent) {
  _vDragStartX = e.clientX
  _vDragStartW = leftPanelWidth.value
  document.addEventListener('mousemove', onVSplitterMouseMove)
  document.addEventListener('mouseup', onVSplitterMouseUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}
function onVSplitterMouseMove(e: MouseEvent) {
  const dx = e.clientX - _vDragStartX
  leftPanelWidth.value = Math.max(MIN_LEFT_W, Math.min(MAX_LEFT_W, _vDragStartW + dx))
}
function onVSplitterMouseUp() {
  document.removeEventListener('mousemove', onVSplitterMouseMove)
  document.removeEventListener('mouseup', onVSplitterMouseUp)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// 运行结果
const inputVars = ref<any[]>([])
const outputVars = ref<any[]>([])
const charts = ref<any[]>([])

// SSTS 节点判别：inputVars 里有 sandbox_snapshot → 是 SSTS 节点
// sandbox_snapshot 是后端 workflow_service 专门为 SSTS 节点注入的，常规节点永远不会有
const isSstsNode = computed(() =>
  inputVars.value.some((v: any) => v.name === 'sandbox_snapshot')
)

// 从 inputVars 里取 sandbox_snapshot 的值（SSTS 节点才会有）
const sandboxSnapshot = computed(() => {
  const item = inputVars.value.find((v: any) => v.name === 'sandbox_snapshot')
  return item ? item.value : null
})

// 从 outputVars 里取 motor_variants 的值
const motorVariantsValue = computed(() => {
  const item = outputVars.value.find((v: any) => v.name === 'motor_variants')
  return item ? item.value : null
})

// 方案对比表的行定义（由 node_ssts_MotorAnalysis.py 的数值输出字段固定决定）
// key 支持嵌套路径，getNested 取值
const VARIANT_TABLE_ROWS: { key: string; label: string; unit?: string }[] = [
  { key: 'stats.max_torque_Nm',   label: 'Tmax',        unit: 'Nm' },
  { key: 'stats.max_power_kw',    label: 'Pmax',        unit: 'kW' },
  { key: 'stats.speed_range_rpm', label: '转速范围',     unit: 'rpm' },
  { key: 'stats.avg_efficiency',  label: 'η_avg' },
  { key: 'stats.max_efficiency',  label: 'η_max' },
  { key: 'stats.eff_std',         label: 'η_std' },
  { key: 'reducer.gear_ratio',    label: '减速器 i0' },
  { key: 'reducer.gear_eff',      label: '减速器 η' },
]

function getNested(obj: any, path: string): any {
  return path.split('.').reduce((o, k) => (o ? o[k] : undefined), obj)
}

/**
 * 把 motor_variants（后端三层嵌套 dict）转成"指标行 × 方案列"的表格结构。
 *
 * 输入：variants[suffix] = {"front/motor_parameter": {...}, "rear/motor_AAA": {...}}
 * 输出：
 *   rows: [{ label, unit, cells: [{ axle, variantName, val }] }]
 *   columns: [{ axle, variantName, headerLabel }]
 */
function buildVariantCompareTable(variants: any) {
  if (!variants || typeof variants !== 'object') return null
  // 取第一个 suffix 的数据（前端当前选中节点时 suffix 已由后端固定为 run 参数）
  const suffix = Object.keys(variants)[0]
  if (!suffix) return null
  const suffixVars = variants[suffix]
  if (!suffixVars || typeof suffixVars !== 'object') return null

  // 按 axle 分组收集方案
  const frontCols: { variantKey: string; variantName: string; axle: string }[] = []
  const rearCols:  { variantKey: string; variantName: string; axle: string }[] = []
  const otherCols: { variantKey: string; variantName: string; axle: string }[] = []
  for (const vk of Object.keys(suffixVars)) {
    const entry = suffixVars[vk]
    const axle = (entry && entry.axle) || (vk.includes('/') ? vk.split('/')[0] : '')
    const variantName = vk.includes('/') ? vk.split('/')[1] : vk
    const col = { variantKey: vk, variantName, axle }
    if (axle === 'front') frontCols.push(col)
    else if (axle === 'rear') rearCols.push(col)
    else otherCols.push(col)
  }
  // 排列顺序：前轴方案 → 后轴方案 → 其他；同类内按 variantName 字母序
  frontCols.sort((a, b) => a.variantName.localeCompare(b.variantName))
  rearCols.sort((a, b) => a.variantName.localeCompare(b.variantName))
  otherCols.sort((a, b) => a.variantName.localeCompare(b.variantName))
  const columns = [...frontCols, ...rearCols, ...otherCols]
  if (columns.length === 0) return null

  const rows = VARIANT_TABLE_ROWS.map((rowDef) => {
    const cells = columns.map((col) => {
      const entry = suffixVars[col.variantKey]
      const rawVal = getNested(entry, rowDef.key)
      const display = formatCompareCell(rawVal, rowDef.unit)
      return {
        axle: col.axle,
        variantName: col.variantName,
        rawVal,
        display,
      }
    })
    return { label: rowDef.label, unit: rowDef.unit, cells }
  })

  // 生成表头（方案名）：带 axle 分组
  const headerGroups: { axle: string; labels: string[] }[] = []
  for (const col of columns) {
    let group = headerGroups.find((g) => g.axle === col.axle)
    if (!group) {
      group = { axle: col.axle, labels: [] }
      headerGroups.push(group)
    }
    group.labels.push(col.variantName)
  }

  return { columns, headerGroups, rows }
}

function formatCompareCell(val: any, unit?: string): string {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'number') {
    // 转速范围是数组 [min, max]
    if (Array.isArray(val)) return val.map((n) => String(n)).join(' ~ ')
    // 整数保留整数，浮点保留 4 位
    const s = Number.isInteger(val) ? String(val) : val.toFixed(4)
    return unit ? `${s} ${unit}` : s
  }
  if (Array.isArray(val)) return val.map((n) => String(n)).join(', ')
  return String(val)
}

// 当前 motor_variants 转出来的方案对比表（SSTS 节点专用）
const variantCompareTable = computed(() => {
  const v = motorVariantsValue.value
  return v ? buildVariantCompareTable(v) : null
})

// ---------- motor_variants 完整 intermediate 的摘要化 ----------
// CollapsibleJson 渲染大数组（eff_map.z: 136×78 二维数组、curve_1d.y: 1800+ 点）会 DOM 爆炸，
// 这里做轻量摘要：数组保留前 5 个元素 + 总数；对象递归；其他原样。
// 完整层级结构保留，用户能看到"有哪些 sheet、每个 sheet 有哪些字段、数组多长"。
function _summarizeBigArrays(obj: any, depth = 0): any {
  if (depth > 20) return "[MAX_DEPTH]"   // 防循环引用
  if (Array.isArray(obj)) {
    const len = obj.length
    if (len > 5) {
      return { __array_preview: obj.slice(0, 5), __array_len: len }
    }
    return obj.map((item) => _summarizeBigArrays(item, depth + 1))
  }
  if (obj !== null && typeof obj === 'object') {
    const out: Record<string, any> = {}
    for (const k of Object.keys(obj)) {
      out[k] = _summarizeBigArrays(obj[k], depth + 1)
    }
    return out
  }
  return obj
}
const motorVariantsSummarized = computed(() => {
  const v = motorVariantsValue.value
  return v ? _summarizeBigArrays(v) : null
})

// 按选中节点过滤——只渲染选中节点的图表（避免一次渲染20+个echarts实例）
const filteredCharts = computed(() => {
  if (!selectedNode.value) return []
  return charts.value.filter(c => c._node_id === selectedNode.value)
})
const nodeResults = ref<Record<string, any>>({})

// ========= 计算 DAG 画布尺寸 =========
const dagWidth = computed(() => {
  if (!dagNodes.value.length) return 800
  const maxX = Math.max(...dagNodes.value.map(n => n.x + NODE_W))
  return Math.max(maxX + 40, 800)
})
const dagHeight = computed(() => {
  if (!dagNodes.value.length) return 300
  const maxY = Math.max(...dagNodes.value.map(n => n.y + NODE_H))
  return Math.max(maxY + 40, 300)
})

// ========= 颜色工具 =========
const NODE_BG_COLORS: Record<string, string> = {
  pending: '#f4f4f5',
  running: '#ecf5ff',
  completed: '#f0f9eb',
  error: '#fef0f0',
}
function nodeBorderColor(n: any): string {
  if (n.state === 'error') return '#f56c6c'
  if (n.state === 'completed') return '#67c23a'
  if (n.state === 'running') return '#409eff'
  return '#dcdfe6'
}
function nodeTextColor(n: any): string {
  if (n.state === 'error') return '#c45656'
  if (n.state === 'completed') return '#529b2e'
  return '#303133'
}
function nodeSubColor(n: any): string { return '#909399' }
function nodeStateColor(n: any): string {
  if (n.state === 'error') return '#f56c6c'
  if (n.state === 'completed') return '#67c23a'
  if (n.state === 'running') return '#409eff'
  return '#c0c4cc'
}
function formatVal(v: any): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'number') return Number.isInteger(v) ? v.toString() : v.toFixed(4)
  if (typeof v === 'boolean') return v ? 'True' : 'False'
  if (typeof v === 'string') return v
  // dict / list → 压缩 JSON 显示，避免 [object Object]
  if (typeof v === 'object') {
    try {
      const s = JSON.stringify(v)
      // 太长则截断
      return s.length > 120 ? s.slice(0, 117) + '...' : s
    } catch {
      return String(v)
    }
  }
  return String(v)
}

// ========= 构建带位置的节点 =========
// 根据 from / to 两个节点的相对位置，选最佳锚点（side）并计算贝塞尔曲线
// 返回: { path }   端点在节点边缘向外偏移 2px，保证箭头不被节点遮挡
function buildEdgePath(from: any, to: any): string {
  const cx1 = from.x + NODE_W / 2, cy1 = from.y + NODE_H / 2
  const cx2 = to.x + NODE_W / 2,   cy2 = to.y + NODE_H / 2
  const dx = cx2 - cx1   // 正 = to 在 from 右边
  const dy = cy2 - cy1   // 正 = to 在 from 下边

  // 选 from 的出口侧、to 的入口侧
  let fromSide: 'top'|'bottom'|'left'|'right'
  let toSide:   'top'|'bottom'|'left'|'right'
  if (Math.abs(dx) > Math.abs(dy) * 0.6) {
    // 横向为主 → 用左/右锚点
    fromSide = dx >= 0 ? 'right' : 'left'
    toSide   = dx >= 0 ? 'left'  : 'right'
  } else {
    // 纵向为主 → 用上/下锚点
    fromSide = dy >= 0 ? 'bottom' : 'top'
    toSide   = dy >= 0 ? 'top'    : 'bottom'
  }

  // 锚点坐标（节点边缘 + 向外 2px 偏移，避开节点矩形遮挡箭头）
  const PAD = 2
  const anchorPos = (node: any, side: string) => {
    switch (side) {
      case 'top':    return { x: node.x + NODE_W / 2,  y: node.y - PAD }
      case 'bottom': return { x: node.x + NODE_W / 2,  y: node.y + NODE_H + PAD }
      case 'left':   return { x: node.x - PAD,         y: node.y + NODE_H / 2 }
      case 'right':  return { x: node.x + NODE_W + PAD, y: node.y + NODE_H / 2 }
    }
    return { x: node.x + NODE_W / 2, y: node.y + NODE_H / 2 }
  }
  const p1 = anchorPos(from, fromSide)
  const p2 = anchorPos(to, toSide)

  // 控制点：沿锚点方向外推，形成平滑曲线
  const ctrlOffset = 40
  const ctrlPos = (p: any, side: string, sign: number) => {
    switch (side) {
      case 'top':    return { x: p.x, y: p.y + sign * ctrlOffset }
      case 'bottom': return { x: p.x, y: p.y + sign * ctrlOffset }
      case 'left':   return { x: p.x + sign * ctrlOffset, y: p.y }
      case 'right':  return { x: p.x + sign * ctrlOffset, y: p.y }
    }
    return { x: p.x, y: p.y }
  }
  // from 侧控制点方向与 fromSide 相同；to 侧与 toSide 相反
  const signFrom = 1
  const signTo   = -1
  const cp1 = ctrlPos(p1, fromSide, signFrom)
  const cp2 = ctrlPos(p2, toSide, signTo)

  return `M ${p1.x} ${p1.y} C ${cp1.x} ${cp1.y}, ${cp2.x} ${cp2.y}, ${p2.x} ${p2.y}`
}

// ========= 自动拓扑分层布局 =========
// 算法：Kahn 拓扑排序分层 + median 启发式同层排序（Sugiyama 简化版）
// 不依赖任何 yaml position，纯靠 upstream/downstream 关系
function autoLayout(nodes: any[]): any[] {
  if (!nodes.length) return []
  const MARGIN_X = 20, MARGIN_Y = 20
  const GAP_X = 60, GAP_Y = 28

  // ① 为每个节点分配层号 (layer)
  //    node.layer = max(up.layer for up in upstream) + 1；无 upstream → layer 0
  const layerOf = new Map<string, number>()
  const idToNode = new Map<string, any>()
  for (const n of nodes) idToNode.set(n.node_id, n)

  // 先给无 upstream 的节点 layer = 0
  const queue: string[] = []
  for (const n of nodes) {
    if (!n.upstream || n.upstream.length === 0) {
      layerOf.set(n.node_id, 0)
      queue.push(n.node_id)
    }
  }
  // BFS 推进
  const visited = new Set<string>()
  while (queue.length) {
    const id = queue.shift()!
    if (visited.has(id)) continue
    visited.add(id)
    const n = idToNode.get(id)!
    const curLayer = layerOf.get(id) ?? 0
    // 找所有把当前节点当作 upstream 的下游节点
    for (const other of nodes) {
      if (other.upstream?.includes(id)) {
        const newLayer = curLayer + 1
        const existing = layerOf.get(other.node_id)
        if (existing === undefined || existing < newLayer) {
          layerOf.set(other.node_id, newLayer)
        }
        if (!visited.has(other.node_id)) queue.push(other.node_id)
      }
    }
  }
  // 处理孤立节点（不在任何连通图里）
  for (const n of nodes) {
    if (!layerOf.has(n.node_id)) layerOf.set(n.node_id, 0)
  }

  // ② 分桶：layer → [nodes]
  const buckets = new Map<number, any[]>()
  for (const n of nodes) {
    const l = layerOf.get(n.node_id)!
    if (!buckets.has(l)) buckets.set(l, [])
    buckets.get(l)!.push(n)
  }

  // ③ 同层内排序：median 启发式（按下游节点位置的中位数排，减少边交叉）
  //    从最末层往回扫（先给最末层编号，上层根据下游中位数排）
  const orderInLayer = new Map<string, number>()
  const layers = [...buckets.keys()].sort((a, b) => b - a)   // 从大到小

  for (const layer of layers) {
    const bucket = buckets.get(layer)!
    // 收集每个节点的"下游索引中位数"
    bucket.sort((a, b) => {
      const aDown = nodes.filter(x => x.upstream?.includes(a.node_id)).map(x => orderInLayer.get(x.node_id) ?? 0)
      const bDown = nodes.filter(x => x.upstream?.includes(b.node_id)).map(x => orderInLayer.get(x.node_id) ?? 0)
      const aMed = aDown.length ? median(aDown) : orderInLayer.get(a.node_id) ?? 0
      const bMed = bDown.length ? median(bDown) : orderInLayer.get(b.node_id) ?? 0
      return aMed - bMed
    })
    bucket.forEach((n, i) => orderInLayer.set(n.node_id, i))
  }

  // ④ 生成坐标
  const maxLayer = Math.max(...buckets.keys())
  // 让主链从左向右走 —— 但如果只有 1 层（所有节点同 layer 0），则纵向排列
  return nodes.map(n => {
    const l = layerOf.get(n.node_id)!
    const idx = orderInLayer.get(n.node_id)!
    let x: number, y: number
    if (maxLayer === 0) {
      // 单层 → 纵向
      x = MARGIN_X
      y = MARGIN_Y + idx * (NODE_H + GAP_Y)
    } else {
      // 多层 → 左到右，每层内纵向排列
      x = MARGIN_X + l * (NODE_W + GAP_X)
      y = MARGIN_Y + idx * (NODE_H + GAP_Y)
    }
    return { ...n, x, y }
  })
}

function median(arr: number[]): number {
  const sorted = [...arr].sort((a, b) => a - b)
  const m = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2
}

function buildDag(nodes: any[]): { nodes: any[]; edges: any[] } {
  // 统一用自动拓扑布局（不依赖 yaml ui_config.node_layout 中的 x/y）
  const positioned = autoLayout(nodes).map(n => ({
    ...n,
    bg_color: NODE_BG_COLORS[n.state || 'pending'],
    display_name: n.node_display_name || n.node_id,
  }))

  // 构建 edges：用 buildEdgePath 动态选锚点，曲线不穿节点
  const edges: any[] = []
  const nodePos = new Map(positioned.map(n => [n.node_id, n]))
  for (const n of positioned) {
    for (const up of n.upstream || []) {
      const from = nodePos.get(up)
      if (!from) continue
      const path = buildEdgePath(from, n)
      edges.push({ from: up, to: n.node_id, path, color: '#c0c4cc' })
    }
  }

  return { nodes: positioned, edges }
}

// ========= 加载拓扑 =========
async function loadTopology() {
  try {
    const url = `/api/workflows/${props.panelType}/nodes`
      + (selectedSuffix.value ? `?vehicle_suffix=${encodeURIComponent(selectedSuffix.value)}` : '')
    const r = await fetch(url)
    const d = await r.json()
    const { nodes, edges } = buildDag(d.nodes || [])
    dagNodes.value = nodes
    dagEdges.value = edges
    // 保存边引用方便 run 后更新颜色
    edgeFromTo.clear()
    for (const e of edges) edgeFromTo.set(`${e.from}→${e.to}`, e)
  } catch (e: any) {
    console.error('[DEBUG loadTopology] ERROR:', e)
    ElMessage.error(`加载拓扑失败: ${e.message}`)
  }
}
const edgeFromTo = new Map<string, any>()

// ========= 全局 MemoryDatabase Store =========
const memStore = useMemoryDbStore()
const excelLoaded = computed(() => memStore.loaded)

// ========= 加载车型后缀（直接 fetch /memory-dbs，和 VtsSstsPage 统一）=========
interface VehOpt { name: string; suffix: string; label: string }
const vehicleOptions = ref<VehOpt[]>([])

async function loadSuffixes() {
  suffixLoading.value = true
  try {
    const res: any = await api.get('/memory-dbs')
    const vehsuffix: any[] = res?.vehsuffix || []
    const list: VehOpt[] = vehsuffix
      .map((v: any) => {
        const name = v['车型'] || v['车型名称'] || ''
        const suffix = v['车型后缀'] || ''
        return {
          name,
          suffix,
          label: suffix ? `${name}_${suffix}` : name,
        }
      })
      .filter((v: VehOpt) => v.suffix || v.name)
    vehicleOptions.value = list
    // 保持用户之前的选择（如果还在列表里）
    const stillExists = list.some(v => v.suffix === selectedSuffix.value)
    if (!stillExists) {
      selectedSuffix.value = list[0]?.suffix || ''
    }
  } catch (e: any) {
    console.warn('[WorkflowPage] loadSuffixes failed:', e?.message)
  } finally {
    suffixLoading.value = false
    // 关键：数据加载完后重新赋值 factory → 引用变了 → MainLayout ExtraControls 重渲染
    // 原因：registerHeaderControls 早于 loadSuffixes 执行，factory 闭包里 vehicleOptions 是空数组
    if (headerExtra && headerExtra.factory) headerExtra.factory = registerHeaderControls()
  }
}

// ========= 沙箱内存 fetch + el-tree 数据构建 =========
async function loadSandbox() {
  if (!selectedSuffix.value || !excelLoaded.value) {
    sandboxData.value = null
    return
  }
  sandboxLoading.value = true
  try {
    const url = `/api/workflows/${props.panelType}/sandbox?vehicle_suffix=${encodeURIComponent(selectedSuffix.value)}`
    const r = await fetch(url)
    const data = await r.json()
    sandboxData.value = data.ok ? data.sandbox : null
  } catch (e: any) {
    console.warn('[Sandbox] load failed:', e?.message)
    sandboxData.value = null
  } finally {
    sandboxLoading.value = false
  }
}

function formatSandboxTime(iso: string): string {
  if (!iso) return ''
  try {
    // 后端返回 "2026-10-09T12:00:00"，截到秒
    const d = new Date(iso)
    const pad = (n: number) => n.toString().padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return iso
  }
}

// 当前选中车型对应的子目录完整路径（用于顶部 meta-info 动态显示）
const currentSandboxFolder = computed<string>(() => {
  const map: Record<string, string> = sandboxData.value?.suffix_subfolder_map || {}
  return (selectedSuffix.value && map[selectedSuffix.value]) || ''
})

// 将 snapshot.data 嵌套 dict 转 el-tree 节点数组
// 每一级: suffix → component → instance → variant → sheet
// 按顶部 selectedSuffix 过滤，只展示当前选中车型
const sandboxTreeData = computed<any[]>(() => {
  if (!sandboxData.value?.data) return []
  const snapData = sandboxData.value.data
  const result: any[] = []

  // suffix 层（只取当前选中的车型）
  const selected = selectedSuffix.value
  const suffixEntries = Object.entries(snapData).filter(([s]) => !selected || s === selected)
  for (const [suffix, suffixData] of suffixEntries) {
    const suffixNode: any = {
      key: `sfx_${suffix}`,
      label: suffix,
      _kind: 'suffix',
      _badge: '',
      children: [],
    }
    if (!suffixData || typeof suffixData !== 'object') continue

    // component 层
    for (const [comp, compData] of Object.entries(suffixData)) {
      if (comp.startsWith('_')) continue   // 跳过 _flat_params 等
      const compNode: any = {
          key: `comp|||${suffix}|||${comp}`,
          label: comp,
          _kind: 'component',
          _badge: '',
          children: [],
        }
      if (!compData || typeof compData !== 'object') continue

      // instance 层
      for (const [instName, _instData] of Object.entries(compData)) {
        if (instName.startsWith('_')) continue
        const instData: any = _instData
        const axleText = instData._axle || ''
        const instNode: any = {
          key: `inst|||${suffix}|||${comp}|||${instName}`,
          label: instName,
          _kind: 'instance',
          _badge: axleText ? `${axleText}` : '',
          _badge_class: axleText === 'front' ? 'badge-front' : axleText === 'rear' ? 'badge-rear' : '',
          children: [],
        }
        const variants = instData._variants || {}
        if (!variants || typeof variants !== 'object') {
          compNode.children.push(instNode)
          continue
        }

        // variant 层
        for (const [vname, _vdata] of Object.entries(variants)) {
          const vdata: any = _vdata
          const sheets = vdata?.sheets || {}
          const vNode: any = {
            key: `var|||${suffix}|||${comp}|||${instName}|||${vname}`,
            label: vname,
            _kind: 'variant',
            // variant 的 label 已经是文件名（去扩展名），_badge 冗余 → 不显示
            _badge: '',
            children: [],
          }
          if (sheets && typeof sheets === 'object') {
            for (const [sn, sdata] of Object.entries(sheets)) {
              const s = sdata as any
              vNode.children.push({
                key: `sheet|||${suffix}|||${comp}|||${instName}|||${vname}|||${sn}`,
                label: sn,
                _kind: 'sheet',
                _sub: `${s.type || '?'}  ${s.shape || '-'}`,
              })
            }
          }
          instNode.children.push(vNode)
        }
        compNode.children.push(instNode)
      }
      if (compNode.children.length) suffixNode.children.push(compNode)
    }
    if (suffixNode.children.length) result.push(suffixNode)
  }
  return result
})

// ========= 参数浏览器：点击树节点 → fetch sheet 详情 =========
async function fetchSheetDetail(suffix: string, component: string, instance: string, variant: string, sheet_name: string) {
  sheetDetailLoading.value = true
  sheetDetail.value = null
  try {
    const url = `/api/workflows/${props.panelType}/sandbox/sheet?` +
      new URLSearchParams({ vehicle_suffix: suffix, component, instance, variant, sheet_name })
    const resp = await fetch(url)
    const json = await resp.json()
    if (json.ok) {
      sheetDetail.value = json.data
    } else {
      sheetDetail.value = { _error: json.error || '未找到该 sheet' }
    }
  } catch (e: any) {
    sheetDetail.value = { _error: String(e?.message || e) }
  } finally {
    sheetDetailLoading.value = false
  }
}

function onSandboxNodeClick(data: any) {
  if (data._kind !== 'sheet') return
  // key 格式: sheet|||suffix|||comp|||instName|||vname|||sn
  const parts: string[] = (data.key || '').split('|||')
  if (parts.length < 6) return
  const [_, suffix, comp, inst, variant, sheet_name] = parts
  selectedSheet.value = { suffix, component: comp, instance: inst, variant, sheet_name }
  fetchSheetDetail(suffix, comp, inst, variant, sheet_name)
}

// ===== ECharts refs & 实例 =====
const curveChartRef = ref<HTMLElement | null>(null)
const heatmapChartRef = ref<HTMLElement | null>(null)
let curveChart: echarts.ECharts | null = null
let heatmapChart: echarts.ECharts | null = null

// ===== ECharts option 生成 =====
function buildCurveOption(d: any) {
  if (!d) return {}

  // 如果后端返回了 series 多系列（drive + generation），优先用
  const seriesArr: any[] = d.series?.length
    ? d.series
    : [{ name: '', x: d.x || [], y: d.y_abs || d.y || [] }]   // 单系列向后兼容

  // 颜色区分 drive / generation
  const COLORS = ['#409eff', '#e6a23c']  // 蓝=generation, 橙=drive

  return {
    grid: { left: 70, right: 20, top: 30, bottom: 60 },
    tooltip: { trigger: 'axis' },
    legend: seriesArr.length > 1 ? { top: 0, right: 10, textStyle: { fontSize: 11 } } : undefined,
    xAxis: {
      type: 'value',
      name: d.x_label || '',
      nameLocation: 'middle', nameGap: 32,
      nameTextStyle: { fontSize: 10 },
      axisLabel: { fontSize: 10 },
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#ebeef5' } },
    },
    yAxis: {
      type: 'value',
      name: d.y_label || '',
      nameTextStyle: { fontSize: 10 },
      axisLabel: { fontSize: 10 },
      splitLine: { show: true, lineStyle: { type: 'dashed', color: '#ebeef5' } },
    },
    series: seriesArr.map((s, i) => ({
      type: 'line',
      name: s.name || undefined,
      data: s.x.map((v: number, idx: number) => [v, Math.abs(s.y[idx] ?? 0)]),
      smooth: false,
      symbol: 'circle', symbolSize: 3, showSymbol: false,
      lineStyle: { width: 1.5, color: COLORS[i % COLORS.length] },
      itemStyle: { color: COLORS[i % COLORS.length] },
      connectNulls: true,
    })),
  }
}

function buildHeatmapOption(d: any) {
  const x: number[] = d.x || [], y: number[] = d.y || [], z: number[][] = d.z || []
  if (!x.length || !y.length) return {}

  // 收集所有非零值 → 算分位数断点
  const nonZero: number[] = z.flat().filter((v: any) => typeof v === 'number' && v !== 0)
  if (!nonZero.length) return {}
  nonZero.sort((a, b) => a - b)
  const n = nonZero.length

  const NUM_BINS = 10
  const breakpoints: number[] = []
  for (let i = 1; i < NUM_BINS; i++) {
    const idx = Math.min(n - 1, Math.floor((i * n) / NUM_BINS))
    breakpoints.push(nonZero[idx])
  }

  // 10 色离散色阶 (红=大数值在上 → 绿=小数值在下)
  // pieces 数组倒序：bin 9(大/红) first → bin 0(小/绿) last
  const BIN_COLORS = [
    '#d50000',   // bin 9  鲜红（大数值，顶部）
    '#f44336',   // bin 8
    '#ff5722',   // bin 7
    '#ff9800',   // bin 6
    '#ffc107',   // bin 5
    '#ffeb3b',   // bin 4
    '#cddc39',   // bin 3
    '#8bc34a',   // bin 2
    '#4caf50',   // bin 1
    '#00c853',   // bin 0  鲜绿（小数值，底部）
  ]

  // 构建 heatmap data：itemStyle.color 由前端分桶
  const data: any[] = []
  for (let yi = 0; yi < y.length; yi++) {
    for (let xi = 0; xi < x.length; xi++) {
      const raw = z[yi]?.[xi]
      if (typeof raw !== 'number' || raw === 0) continue

      let bin = NUM_BINS - 1
      for (let b = 0; b < breakpoints.length; b++) {
        if (raw <= breakpoints[b]) { bin = b; break }
      }
      // BIN_COLORS 倒序用：大 bin → 红，小 bin → 绿
      data.push({
        value: [xi, yi, raw],
        itemStyle: { color: BIN_COLORS[bin], borderWidth: 0 },
      })
    }
  }

  // visualMap 用 inRange 线性渐变（红→绿，手动反转确保顶部红大数值）
  // series 颜色由 data[].itemStyle.color 独立控制，visualMap 只负责 colorbar 显示
  const EFF_MIN = nonZero[0]
  const EFF_MAX = nonZero[n - 1]

  // 智能取整步长：根据数据范围自动选 nice step（1,2,5,10,20,50,100,200,500,1000,...）
  function _niceStep(values: number[], targetTicks = 6): number {
    const lo = Math.min(...values), hi = Math.max(...values)
    const range = hi - lo
    if (range <= 0) return 1
    const rawStep = range / targetTicks
    const pow10 = Math.pow(10, Math.floor(Math.log10(rawStep)))
    const norm = rawStep / pow10        // 归一化到 [1, 10)
    const niceMults = [1, 2, 5, 10]
    const niceStep = niceMults.find(m => m >= norm) ?? 10
    return niceStep * pow10
  }
  const xStep = _niceStep(x)
  const yStep = _niceStep(y)

  // 闭包：track 上次显示的取整值，相同就跳过（避免 category 轴 interval + step 取整的重复数字）
  let _lastXLabel = NaN
  let _lastYLabel = NaN

  return {
    grid: { left: 70, right: 120, top: 20, bottom: 60 },
    tooltip: {
      position: 'top',
      formatter: (p: any) => {
        const xv = x[p.value[0]], yv = y[p.value[1]], zv = p.value[2]
        return `${d.x_label || 'x'}=${xv}<br/>${d.y_label || 'y'}=${yv}<br/>${d.z_label || 'z'}=${zv.toFixed(3)}`
      },
    },
    xAxis: {
      type: 'category', data: x,
      name: d.x_label || '', nameLocation: 'middle', nameGap: 32,
      splitArea: { show: true },
      axisLabel: {
        interval: Math.max(1, Math.floor(x.length / 8)),
        formatter: (v: number) => {
          const nice = Math.round(v / xStep) * xStep
          if (nice === _lastXLabel) return ''       // 重复就不显示
          _lastXLabel = nice
          return nice
        },
        fontSize: 10,
      },
    },
    yAxis: {
      type: 'category', data: y,
      name: d.y_label || '', nameLocation: 'middle', nameGap: 32,
      splitArea: { show: true },
      axisLabel: {
        interval: Math.max(1, Math.floor(y.length / 6)),
        formatter: (v: number) => {
          const nice = Math.round(v / yStep) * yStep
          if (nice === _lastYLabel) return ''
          _lastYLabel = nice
          return nice
        },
        fontSize: 10,
      },
    },
    visualMap: {
      type: 'continuous',              // 明确 continuous → 支持 height 属性
      min: EFF_MIN,
      max: EFF_MAX,
      calculable: true, orient: 'vertical',
      right: 15, top: 'center',
      height: '90%',                   // ★ 关键：continuous 模式直接指定 colorbar 高度
      inRange: {
        color: ['#00c853', '#4caf50', '#8bc34a', '#cddc39', '#ffeb3b',
                '#ffc107', '#ff9800', '#ff5722', '#f44336', '#d50000'],
      },
      textStyle: { fontSize: 11 },
      text: ['大', '小'],
    },
    series: [{
      type: 'heatmap',
      data,
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  }
}

// ===== chart 初始化 / 更新 / 销毁 =====
function initCharts() {
  // 关键：dispose 旧实例，因为 v-if 切换会销毁旧 DOM + 创建新 DOM
  // 旧 ECharts 实例还指向已销毁的节点，必须重建
  curveChart?.dispose(); curveChart = null
  heatmapChart?.dispose(); heatmapChart = null
  if (curveChartRef.value)   curveChart   = echarts.init(curveChartRef.value)
  if (heatmapChartRef.value) heatmapChart = echarts.init(heatmapChartRef.value)
}

function updateCharts() {
  const d = sheetDetail.value
  if (!d) return
  nextTick(() => {
    initCharts()  // 每次都重建，确保实例指向当前活着的 DOM

    // DEBUG: 看看容器实际高度是多少
    const hh = heatmapChartRef.value?.clientHeight ?? 0
    const hw = heatmapChartRef.value?.clientWidth ?? 0
    console.log('[DEBUG ECharts] heatmap-box size:', hw, 'x', hh, 'type=', d?.type)

    if (d.type === 'curve_1d' && curveChart) {
      curveChart.setOption(buildCurveOption(d), true)
      curveChart.resize()
    } else if (d.type === 'map_2d' && heatmapChart) {
      heatmapChart.setOption(buildHeatmapOption(d), true)
      heatmapChart.resize()
    }
  })
}

function disposeCharts() {
  curveChart?.dispose(); curveChart = null
  heatmapChart?.dispose(); heatmapChart = null
}

// sheetDetail 变化 → 更新图
watch(sheetDetail, updateCharts, { deep: true })

// ========= 运行计算 =========
async function onRun() {
  if (!selectedSuffix.value) { ElMessage.warning('请先选择车型'); return }
  running.value = true
  runResult.value = null
  selectedNode.value = null
  inputVars.value = []
  outputVars.value = []
  charts.value = []
  nodeResults.value = {}
  // 重置节点状态
  for (const n of dagNodes.value) n.state = 'running'
  for (const e of dagEdges.value) e.color = '#409eff'

  try {
    const r = await fetch('/api/workflows/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ panel_or_wfid: props.panelType, vehicle_suffix: selectedSuffix.value }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    const d = await r.json()
    runResult.value = { completed: d.completed, errors: d.errors, duration_sec: Number(d.duration_sec).toFixed(2) as any }

    // 更新节点状态 + 提取输入/输出
    const idToN = new Map(dagNodes.value.map(n => [n.node_id, n]))
    for (const nr of d.nodes || []) {
      const dn = idToN.get(nr.node_id)
      if (dn) dn.state = nr.state || 'pending'
      nodeResults.value[nr.node_id] = nr
    }
    for (const e of dagEdges.value) {
      const fromN = nodeResults.value[e.from]
      const toN = nodeResults.value[e.to]
      e.color = (fromN?.state === 'completed' && toN?.state === 'completed') ? '#67c23a' : '#c0c4cc'
    }

    // 收集第一个节点的输入变量 + 所有节点的输出变量
    const firstNode = d.nodes?.find((n: any) => n.upstream?.length === 0)
    if (firstNode?.input_vars) {
      inputVars.value = flattenVars(firstNode.input_vars)
    }
    const outs: any[] = []
    for (const nr of d.nodes || []) {
      if (nr.output_vars && Object.keys(nr.output_vars).length) {
        outs.push(...flattenVars(nr.output_vars, nr.display_name || nr.node_id))
      }
    }
    outputVars.value = outs

    // 收集所有节点的图示数据（只存数据，不在 onRun 里 render——canvas 在隐藏 Tab 里尺寸为 0）
    const allCharts: any[] = []
    for (const nr of d.nodes || []) {
      if (nr.visualizations && Array.isArray(nr.visualizations)) {
        for (const v of nr.visualizations) {
          allCharts.push({ ...v, _node: nr.node_display_name || nr.node_id, _node_id: nr.node_id })
        }
      }
    }
    charts.value = allCharts
    // 切节点时如果在 chart Tab 会自动触发 render（watch selectedNode 里处理）

    ElMessage.success(`计算完成：${d.completed} OK / ${d.errors} 失败`)
    _saveCache()
  } catch (e: any) {
    ElMessage.error(`运行失败: ${e.message}`)
    // 把 running 的节点置回 pending
    for (const n of dagNodes.value) if (n.state === 'running') n.state = 'pending'
  } finally {
    running.value = false
  }
}

function flattenVars(obj: any, group?: string): any[] {
  if (!obj || typeof obj !== 'object') return []
  const out: any[] = []
  for (const [name, v] of Object.entries(obj)) {
    const val = typeof v === 'object' && v !== null && 'value' in v ? (v as any) : { value: v, unit: '' }
    out.push({ name: group ? `${group}.${name}` : name, value: val.value ?? val, unit: val.unit || '' })
  }
  return out
}

// ========= ECharts 图示渲染 =========
const _chartInstances: any[] = []

async function renderCharts() {
  _chartInstances.forEach(inst => inst.dispose?.())
  _chartInstances.length = 0

  const echarts = _echarts()
  if (!echarts) { console.error('[Chart] window.echarts not ready'); return }

  const canvases = document.querySelectorAll<HTMLElement>('.chart-box .chart-canvas')
  filteredCharts.value.forEach((cv, i) => {
    const canvas = canvases[i]
    if (!canvas) return
    try {
      const inst = echarts.init(canvas)
      inst.setOption(buildEChartsOption(cv))
      _chartInstances.push(inst)
    } catch (e) {
      console.warn('echarts render failed', e)
    }
  })
}

function buildEChartsOption(cv: any): any {
  const seriesList = cv.series || []
  const echartsSeries: any[] = []

  // 收集所有 x 值做共享 x 轴
  const allX: any[] = []
  for (const s of seriesList) {
    if (s.x) allX.push(...s.x)
  }
  const uniqueX = Array.from(new Set(allX)).sort((a, b) => a - b)
  const isNumericX = uniqueX.every(v => typeof v === 'number')

  for (const s of seriesList) {
    const xArr: any[] = s.x || []
    const yArr: any[] = s.y || []
    // 按 x 值对齐
    const data: [any, number][] = []
    for (let j = 0; j < xArr.length; j++) {
      const xVal = isNumericX ? Number(xArr[j]) : xArr[j]
      const yVal = Number(yArr[j])
      if (!isNaN(yVal)) data.push([xVal, yVal])
    }
    const color = s.color || undefined
    echartsSeries.push({
      name: s.name || cv.title || '',
      type: cv.chart_type === 'bar' ? 'bar' : 'line',
      data,
      smooth: true,
      showSymbol: false,                 // 不显示数据点
      lineStyle: color ? { color } : undefined,
      itemStyle: color ? { color } : undefined,
    })
  }

  // Y 轴 name：优先用后端 y_label，否则从 title 里提取括号里的单位（如 "vel (m/s)" → "m/s"）
  let yName = cv.y_label || ''
  if (!yName && cv.title) {
    const m = cv.title.match(/\(([^)]+)\)/)
    if (m) yName = m[1]
  }

  return {
    title: { text: cv.title || '', left: 10, top: 4, textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { data: echartsSeries.map(s => s.name), top: 24, textStyle: { fontSize: 11 } },
    grid: { left: 48, right: 12, top: 50, bottom: 30 },   // left 加大留给 y 轴 name
    xAxis: {
      type: isNumericX ? 'value' : 'category',
      name: cv.x_label || '',
      axisLabel: { fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: yName,
      nameLocation: 'middle',
      nameGap: 32,
      axisLabel: { fontSize: 11 },
    },
    series: echartsSeries,
  }
}

// ========= 选节点 =========
// ========= 边的高亮逻辑（选中节点时，相关边高亮，其他变淡）=========
function edgeIsRelated(e: any): boolean {
  if (!selectedNode.value) return true   // 没选中时全部正常显示
  return e.from === selectedNode.value || e.to === selectedNode.value
}
function edgeStroke(e: any): string {
  if (!edgeIsRelated(e)) return '#c0c4cc'   // 不相关的灰色淡化
  // 高亮相关边统一用主题蓝，忽略数据里的 e.color
  if (selectedNode.value) return '#409eff'
  // 无选中节点时，用数据原色（如有）
  return e.color || '#409eff'
}
function edgeWidth(e: any): number {
  if (!selectedNode.value) return 1.5
  return edgeIsRelated(e) ? 2.5 : 1.0
}
function edgeOpacity(e: any): number {
  if (!selectedNode.value) return 1
  return edgeIsRelated(e) ? 1 : 0.25
}
function edgeMarker(e: any): string {
  // 无选中节点 → 普通灰
  if (!selectedNode.value) return 'url(#arrow-normal)'
  // 选中且相关 → 主题蓝（高亮）
  if (edgeIsRelated(e)) return 'url(#arrow-active)'
  // 选中但不相关 → 淡化灰（与 edgeOpacity 0.25 呼应）
  return 'url(#arrow-dim)'
}

function onSelectNode(id: string) {
  // 再次点击同一节点 → 取消选中（恢复全部正常显示）
  if (selectedNode.value === id) {
    selectedNode.value = null
    inputVars.value = []
    outputVars.value = []
    return
  }
  selectedNode.value = id
  // 把该节点的 input/output 显示到底部
  const nr = nodeResults.value[id]
  if (nr?.input_vars) inputVars.value = flattenVars(nr.input_vars)
  if (nr?.output_vars) outputVars.value = flattenVars(nr.output_vars)
}

// 车型后缀变化 → 重新加载 DAG（不同后缀 → 不同 YAML → 不同布局）
watch(selectedSuffix, (suffix) => {
  if (suffix && excelLoaded.value) {
    runResult.value = null
    inputVars.value = []
    outputVars.value = []
    nodeResults.value = {}
    loadTopology()
    // 如果当前在 sandbox Tab，车型变化 → 重新加载沙箱
    if (bottomTab.value === 'sandbox') {
      loadSandbox()
    }
  }
})

// Excel 状态变化 —— 监听 memStore.fileChangeVersion（换文件时 store 会 +1）
watch(() => memStore.fileChangeVersion, () => {
  if (excelLoaded.value) {
    runResult.value = null
    inputVars.value = []
    outputVars.value = []
    charts.value = []
    nodeResults.value = {}
    selectedNode.value = null
    loadSuffixes()
    loadTopology()
    // Excel 文件切换 → 沙箱肯定要 reload
    if (bottomTab.value === 'sandbox') {
      loadSandbox()
    }
  }
})

// 切到 chart Tab 时渲染 echarts（隐藏容器里初始化尺寸为 0）
watch(bottomTab, async (tab) => {
  if (tab === 'chart' && filteredCharts.value.length > 0) {
    await nextTick()
    renderCharts()
  }
  // 切到 sandbox Tab 时加载沙箱数据
  if (tab === 'sandbox') {
    loadSandbox()
  }
})

// 选中节点变化时，如果在 chart Tab 也重新渲染（只渲染该节点的图表）
watch(selectedNode, async () => {
  if (bottomTab.value === 'chart' && filteredCharts.value.length > 0) {
    await nextTick()
    renderCharts()
  }
})

// ========= 注册动态控件到 MainLayout 页面标题栏右侧 =========
// 把 车型下拉 + 运行按钮 + 运行结果状态 上移一行，节省纵向空间
const headerExtra = inject<any>('rightPanelHeaderExtra', null)

// 用于 onRun 点击的包装（h 函数里 onClick 不能直接写 template 风格的 @click）
async function _onRunFromHeader() {
  await onRun()
}

function registerHeaderControls() {
  if (!headerExtra) return null
  const factory = () => {
    // h 函数返回 VNode 数组（flex 容器里横向排列）
    return h('div', {
      class: 'wf-header-controls',
      style: 'display:flex;align-items:center;gap:6px;font-size:12px;'
    }, [
      // 车型 label
      h('span', { class: 'tb-label' }, '车型：'),
      // el-select（直接用 Vue 组件的 h 调用）
      // 注意：不要传 loading prop——factory 可能在 vehicleOptions 加载前就被调用，
      // MainLayout ExtraControls 只对 factory 引用变化敏感，对内部 ref 变化不敏感
      h(ElSelect, {
        modelValue: selectedSuffix.value,
        'onUpdate:modelValue': (v: string) => { selectedSuffix.value = v },
        style: 'width:140px',
        size: 'small',
        placeholder: '请选择车型',
      }, vehicleOptions.value.map(opt =>
        h(ElOption, {
          key: opt.suffix,
          value: opt.suffix,
          label: opt.label,
        })
      )),
      // 运行按钮
      h(ElButton, {
        size: 'small',
        type: 'primary',
        loading: running.value,
        disabled: !selectedSuffix.value,
        onClick: _onRunFromHeader,
      }, { default: () => '运行计算' }),
      // 运行结果状态文本（条件渲染）
      runResult.value ? h('span', {
        class: ['tb-result', runResult.value.errors > 0 ? 'err' : '']
      }, `完成 ${runResult.value.completed} / 失败 ${runResult.value.errors} · ${runResult.value.duration_sec}s`) : null,
    ].filter(Boolean))
  }
  headerExtra.factory = factory
  return factory
}

onBeforeUnmount(() => {
  // 清理 MainLayout header 注册
  if (headerExtra) headerExtra.factory = null
  _chartInstances.forEach(inst => inst.dispose())
  _chartInstances.length = 0
  // 沙箱详情 ECharts
  disposeCharts()
  window.removeEventListener('resize', resizeCharts)
  memStore.stopPolling()
})

function resizeCharts() {
  curveChart?.resize()
  heatmapChart?.resize()
}

onMounted(async () => {
  // 注册动态控件到 MainLayout 标题行右侧
  registerHeaderControls()
  // 沙箱详情 echarts 初始化
  initCharts()
  window.addEventListener('resize', resizeCharts)
  // 启动 store 后台轮询（全局只启动一次，多组件共享同一个 timer）
  memStore.startPolling()
  // 车型下拉：直接 fetch，不等轮询
  await loadSuffixes()
  // 拓扑图：store 已有缓存数据时立即加载首次数据；否则等 watcher 触发
  if (excelLoaded.value) {
    await loadTopology()
    // 刷新后恢复计算状态（localStorage）
    _loadCache()
  }
})
</script>

<style scoped>
/* ========= 设计基准 =========
  字号: 13 = 工具栏标题 / 分区标题
        12 = 常规
        11 = 节点标题 / 次要
  颜色: #303133/#606266/#909399/#c0c4cc/#e4e7ed
  ============================= */

.wf-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  min-height: 0;
}

/* 未加载 Excel 空态 */
.wf-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.empty-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #909399;
}

/* header 控件注册到 MainLayout，此处只保留被 h() 函数引用的类 */
.tb-label { font-size: 12px; color: #606266; }
.tb-warn { font-size: 12px; color: #e6a23c; }
.tb-result { font-size: 12px; color: #67c23a; }
.tb-result.err { color: #f56c6c; }

/* DAG 区 */
.dag-box {
  flex: 1;
  min-height: 0;
  padding: 10px;
  background: #f5f5f5;
  border-bottom: 1px solid #e4e7ed;
  overflow: hidden;
}
.dag-inner {
  width: 100%; height: 100%;
  overflow: auto;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
}
.dag-svg { display: block; padding: 10px; }
.dag-empty {
  display: flex; align-items: center; justify-content: center;
  height: 100%; min-height: 200px;
}

/* 节点 hover/选中 */
.dag-node { cursor: pointer; transition: filter 0.15s; }
.dag-node:hover { filter: drop-shadow(0 0 3px rgba(64,158,255,0.5)); }
.dag-node.sel rect { stroke: #409eff !important; stroke-width: 2.5 !important; }
.dag-node.sel { filter: drop-shadow(0 0 6px rgba(64,158,255,0.7)); }
.dag-node.running rect { stroke: #409eff; stroke-width: 1.5; }
.dag-node.success rect { stroke: #67c23a; }
.dag-node.error rect { stroke: #f56c6c; }

/* 底部 Tabs — 高度由 bottomTabsHeight 控制，splitter 上方有 border */
.wf-bottom-tabs { flex-shrink: 0; overflow: hidden; }
.wf-bottom-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 10px; }
.wf-bottom-tabs :deep(.el-tabs__item) { font-size: 13px; }
.wf-bottom-tabs :deep(.el-tabs__content) { padding: 0; height: calc(100% - 36px); }
.wf-bottom-tabs :deep(.el-tab-pane) { height: 100%; overflow: hidden; }

/* 可拖拽分割条 */
.wf-splitter {
  flex-shrink: 0;
  height: 2px;
  cursor: row-resize;
  background: #e4e7ed;
  transition: background 0.15s;
}
.wf-splitter:hover { background: #409eff; }

/* 可拖拽左右分割条 */
.wf-vsplitter {
  flex-shrink: 0;
  width: 2px;
  cursor: col-resize;
  background: #e4e7ed;
  transition: background 0.15s;
}
.wf-vsplitter:hover { background: #409eff; }

/* 数值信息：左右两栏 */
.numeric-row {
  display: flex; height: 100%;
}
.io-panel {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column;
}
.io-header {
  flex-shrink: 0;
  font-size: 13px; font-weight: 600; color: #303133;
  padding: 6px 14px;
  border-bottom: 1px solid #e4e7ed;
  background: #fafbfc;
}
.io-body {
  flex: 1; overflow-y: auto;
  padding: 4px 14px;
}
.io-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0;
  font-size: 12px;
  border-bottom: 1px dashed #ebeef5;
}
.io-name { color: #606266; flex: 1; }
.io-val { color: #303133; font-weight: 500; font-family: ui-monospace, Consolas, monospace; }
.io-val.io-md {
  font-family: inherit;
  font-weight: 400;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
}
.io-unit { color: #909399; font-size: 11px; }
.io-empty { color: #c0c4cc; text-align: center; padding: 30px 0; font-size: 12px; }

/* =====================================================================
 * SSTS 节点专用样式
 * ===================================================================== */
.ssts-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #409eff;
  padding: 6px 0 4px 0;
  border-bottom: 1px dashed #dcdfe6;
  margin-bottom: 6px;
}

/* ---------- 方案对比表 ---------- */
.variant-table-wrap {
  overflow-x: auto;
  margin-bottom: 8px;
}
.variant-compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-family: ui-monospace, Consolas, monospace;
}
.variant-compare-table th,
.variant-compare-table td {
  border: 1px solid #e4e7ed;
  padding: 4px 8px;
  text-align: center;
  vertical-align: middle;
  white-space: nowrap;
}
.variant-compare-table .vt-th-left {
  border: none;
  background: transparent;
}
.variant-compare-table .vt-header-axle .vt-th-axle {
  font-weight: 700;
  font-size: 11px;
}
.variant-compare-table .vt-header-variant .vt-th-variant {
  font-weight: 600;
  font-size: 11px;
  color: #303133;
}
.variant-compare-table .vt-axle-front { background: #ecf5ff; color: #409eff; }
.variant-compare-table .vt-axle-rear  { background: #fdf6ec; color: #e6a23c; }
.variant-compare-table .vt-axle-      { background: #f4f4f5; color: #606266; }
.variant-compare-table tbody tr:hover td { background: #f5f7fa; }
.variant-compare-table .vt-td-label {
  text-align: left;
  background: #fafafa;
  font-family: inherit;
  white-space: normal;
  min-width: 90px;
}
.variant-compare-table .vt-label { font-weight: 600; color: #303133; }
.variant-compare-table .vt-unit { color: #909399; font-size: 10px; margin-left: 3px; }

/* 可拖拽左右分割条 */
.wf-vsplitter {
  flex-shrink: 0;
  width: 4px;
  cursor: col-resize;
  background: #e4e7ed;
  transition: background 0.15s;
}
.wf-vsplitter:hover { background: #409eff; }

/* 图示信息 */
.chart-box { padding: 10px 14px; height: 100%; overflow-y: auto; }
.chart-empty { max-width: 480px; }
.chart-item { margin-bottom: 12px; }
.chart-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.chart-canvas { width: 100%; height: 240px; border: 1px solid #e4e7ed; border-radius: 4px; }

/* ========= 参数浏览器（原沙箱内存）Tab ========= */
.sandbox-box { padding: 10px 14px; height: 100%; overflow: hidden; display: flex; flex-direction: column; }
.sandbox-empty { flex: 1; max-width: 480px; padding: 20px 0; display: flex; align-items: center; justify-content: center; }

.sandbox-content { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }

.sandbox-meta {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; margin-bottom: 8px; flex-shrink: 0;
  background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.meta-path { flex: 1; font-family: ui-monospace, Consolas, monospace; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta-time { color: #909399; font-size: 11px; }

/* 两栏 flex 主体 */
.sandbox-body {
  display: flex;
  gap: 0;               /* splitter 自己就是分隔，去掉 gap */
  flex: 1;
  min-height: 0;
}
.sandbox-tree-col {
  /* width 由内联 style 动态控制 (treeColWidth)，CSS 不再设 */
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
  padding: 8px;
  overflow-y: auto;
  overflow-x: hidden;
  flex-shrink: 0;
}
.sandbox-splitter {
  width: 4px;
  margin: 0 4px;        /* 左右各留 4px 呼吸空间 → 实际感应区 12px */
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s;
  flex-shrink: 0;
  position: relative;
}
.sandbox-splitter::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 20%;
  bottom: 20%;
  width: 1px;
  background: #dcdfe6;
  transform: translateX(-50%);
  transition: background 0.15s, width 0.15s;
}
.sandbox-splitter:hover::before,
.sandbox-splitter.dragging::before {
  width: 2px;
  background: #409eff;
}
.sandbox-detail-col {
  flex: 1;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
  padding: 12px;
  /* 去掉 overflow: auto —— 让内部 echarts-box 能撑满；detail-header 不参与撑高 */
  overflow: hidden;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* detail-content 必须是 flex item，否则 .echarts-box height:100% collapse */
/* overflow-y: auto 让内容超出时出现滚动条，避免 ECharts 底部坐标轴被裁 */
.detail-content {
  flex: 1;
  min-height: 0;               /* flex item 必须有 min-height:0 才能让子元素 shrink */
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
}

/* 详情头部 */
.detail-header { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #ebeef5; flex-wrap: wrap; flex-shrink: 0; }
.detail-title { font-weight: 600; color: #303133; font-size: 13px; }

/* ECharts 统一容器 —— flex:1 充满剩余空间；min-height 设 260px 保证可读性，
   当父级 detail-content 空间不够时会触发 overflow-y 滚动 */
.echarts-box { width: 100%; flex: 1; min-height: 260px; }

/* scalar */
.detail-scalar pre { background: #fafbfc; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px; font-size: 12px; max-height: 400px; overflow: auto; white-space: pre-wrap; margin: 0; }

/* 关键：用 !important 压过 el-tree 默认的 display:block，
   让图标 / 文字 / badge 在一行里排成紧凑节点 */
.tree-node,
.tree-node > * {
  display: inline-flex !important;
  align-items: center !important;
  flex-wrap: nowrap;
  white-space: nowrap;
}
.tree-node {
  gap: 6px;
  font-size: 12px; line-height: 1.4;
}
.tree-icon { font-size: 13px; }
.tree-label { color: #303133; font-weight: 500; }
.tree-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: #f0f2f5; color: #909399;
}
.tree-badge.badge-front { background: #e1f3d8; color: #67c23a; }
.tree-badge.badge-rear  { background: #d9ecff; color: #409eff; }
.tree-sub {
  font-size: 11px; color: #909399; margin-left: 2px;
  font-family: ui-monospace, Consolas, monospace;
}
</style>
