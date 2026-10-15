// @Time    : 2026
// @Author  : 李涛
// @File    : ChatPanel.vue
// @Desc    : ChatPanel
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  ChatPanel — 常驻中间列的 AI 聊天面板
  内容从 ChatPage.vue 提取，始终渲染在三栏布局的中间。
-->
<template>
  <div
    ref="panelRef"
    class="chat-panel"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!-- ========== 拖拽遮罩提示 ========== -->
    <div v-if="isDragging" class="drag-overlay">
      <el-icon :size="40"><UploadFilled /></el-icon>
      <span>释放以上传图片</span>
    </div>

    <!-- ========== 顶部状态栏（左：Excel 项目名 / 右：模型名） ========== -->
    <div class="top-status-bar">
      <!-- 左：Excel 项目名（未加载时整块不渲染） -->
      <template v-if="excelStatus.loaded">
        <el-tag type="success" size="small" effect="plain" :title="excelStatus.file_path">
          项目：{{ excelStatus.file_name }}
        </el-tag>
      </template>
      <!-- 右：模型状态 -->
      <el-tag :type="modelConnected ? 'success' : 'danger'" size="small" effect="plain">
        模型：{{ modelName }}
      </el-tag>
    </div>

    <!-- ========== 消息主区（拖拽条控制分配比例，显式像素高度） ========== -->
    <div
      ref="scrollRef"
      class="message-area"
      :style="{ height: messageAreaHeight + 'px' }"
    >
      <!-- 空状态 -->
      <div v-if="store.bubbles.length === 0" class="empty-state">
        <el-icon :size="48" class="empty-icon"><ChatDotRound /></el-icon>
        <p class="empty-title">你好！我是 Snail Avatar 智能助手</p>
        <p class="empty-sub">新能源汽车性能开发助手，支持技术问答、参数查询、VTS 计算</p>
      </div>

      <!-- 气泡 + 每轮过程事件 -->
      <template v-for="(bubble, idx) in store.bubbles" :key="bubble.id">
        <!-- 用户气泡 -->
        <div v-if="bubble.role === 'user'" class="bubble-row user-row">
          <img src="/icons/LLMchat/User.png" class="avatar user-avatar" alt="user" />
          <div class="user-content">
            <div v-if="bubble.content" class="bubble user-bubble">{{ bubble.content }}</div>
            <!-- 用户发送的图片（完整 dataURL，直接用） -->
            <div v-if="bubble.userImages && bubble.userImages.length" class="bubble-images user-images">
              <img
                v-for="(img, i) in bubble.userImages"
                :key="'u' + idx + '-' + i"
                :src="img"
                class="bubble-img"
                alt="用户图片"
              />
            </div>
          </div>
        </div>

        <!-- AI 气泡 -->
        <div v-else class="bubble-row">
          <img src="/icons/LLMchat/Snail_Avatar.png" class="avatar ai-avatar" alt="ai" />
          <div class="ai-content">
            <!-- 过程时间线（上） -->
            <div v-if="bubble.events && bubble.events.length > 0" class="process-timeline">
              <el-collapse>
                <el-collapse-item name="events">
                  <template #title>
                    <span class="timeline-toggle">
                      <el-icon><Tickets /></el-icon>
                      过程事件 ({{ bubble.events.length }})
                    </span>
                  </template>
                  <el-timeline>
                    <el-timeline-item
                      v-for="ev in bubble.events"
                      :key="ev.id"
                      :timestamp="ev.timestamp"
                      :type="eventColor(ev.type)"
                      :size="'small'"
                    >
                      <div class="timeline-item">
                        <el-tag :type="eventTagType(ev.type)" size="small" effect="plain">
                          {{ eventLabel(ev.type) }}
                        </el-tag>
                        <span class="timeline-content">{{ ev.content }}</span>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- AI 回复气泡（下） -->
            <div class="bubble ai-bubble">
              <div v-html="renderMarkdown(bubble.content)"></div>
              <div v-if="bubble.usageInfo" class="usage-info">
                tokens: {{ bubble.usageInfo.input_tokens }}↑ {{ bubble.usageInfo.output_tokens }}↓
              </div>
            </div>

            <!-- AI 返回的图片 — 原生 img + 全局 el-image-viewer（避免循环内多个 viewer 实例导致 GPU 合成层抖动） -->
            <div v-if="bubble.images && bubble.images.length" class="bubble-images ai-images">
              <img
                v-for="(img, i) in bubble.images"
                :key="'a' + idx + '-' + i"
                :src="img"
                class="bubble-img ai-retrieved-img"
                alt="检索图片"
                @click="openImageViewer(bubble.images, i)"
              />
            </div>
          </div>
        </div>
      </template>

      <!-- Loading 指示器（仅 isLoading 时显示） -->
      <div v-if="store.isLoading" class="bubble-row">
        <img src="/icons/LLMchat/Snail_Avatar.png" class="avatar ai-avatar" alt="ai" />
        <div class="bubble loading-bubble">
          <el-icon class="is-loading" :size="20"><Loading /></el-icon>
          <span>AI 正在思考...</span>
          <span v-if="latestEvent" class="loading-hint">{{ latestEvent.content }}</span>
        </div>
      </div>

      <!-- 实时过程时间线（仅 AI 执行中显示；final 到达后每个气泡自带 snapshot 时间线，不需要全局这份） -->
      <div v-if="store.isLoading && store.events.length > 0" class="bubble-row">
        <img src="/icons/LLMchat/Snail_Avatar.png" class="avatar ai-avatar" alt="ai" />
        <div class="ai-content">
          <div class="process-timeline live-timeline">
            <el-collapse>
              <el-collapse-item name="live">
                <template #title>
                  <span class="timeline-toggle">
                    <el-icon><Tickets /></el-icon>
                    执行过程 ({{ store.events.length }})
                  </span>
                </template>
                <el-timeline>
                  <el-timeline-item
                    v-for="ev in store.events"
                    :key="ev.id"
                    :timestamp="ev.timestamp"
                    :type="eventColor(ev.type)"
                  >
                    <div class="timeline-item">
                      <el-tag :type="eventTagType(ev.type)" size="small" effect="plain">
                        {{ eventLabel(ev.type) }}
                      </el-tag>
                      <span class="timeline-content">{{ ev.content }}</span>
                    </div>
                  </el-timeline-item>
                </el-timeline>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </div>
    </div>

    <!-- ========== 水平拖拽分割条 ========== -->
    <div
      class="h-resizer"
      @mousedown="startHDrag"
    ></div>

    <!-- ========== 底部输入栏 ========== -->
    <div class="input-area-wrapper" :style="{ height: inputAreaHeight + 'px' }">
      <!-- 暂存图片预览区 -->
      <div v-if="store.pendingImages.length > 0" class="pending-images">
        <div v-for="(img, pidx) in store.pendingImages" :key="pidx" class="pending-img-item">
          <!-- pendingImages 存完整 dataURL，直接用 -->
          <img :src="img" class="pending-img" alt="待发送图片" />
          <el-icon class="remove-img" @click="store.removePendingImage(pidx)"><Close /></el-icon>
        </div>
      </div>

      <!-- input-area: flex:1 自动填充 wrapper 剩余空间 -->
      <div class="input-area">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          class="native-textarea"
          :placeholder="store.pendingImages.length > 0 ? '已添加图片，可补充描述文字... (Ctrl+Enter 发送)' : '输入消息... (Ctrl+Enter 发送)'"
          :disabled="store.isLoading"
          @keydown="onKeydown"
        ></textarea>
        <div class="input-actions">
          <!-- 📎 上传图片按钮（发送按钮左侧） -->
          <button
            class="icon-btn"
            type="button"
            :disabled="store.isLoading"
            @click="triggerFileSelect"
            title="上传图片"
          >
            <el-icon :size="25"><Paperclip /></el-icon>
          </button>
          <!-- 发送按钮 -->
          <button
            class="send-btn"
            type="button"
            :disabled="!canSend"
            @click="onSend"
            title="发送 (Ctrl+Enter)"
          >
            <img src="/icons/LLMchat/send.png" alt="发送" class="send-icon" />
          </button>
        </div>

        <!-- 隐藏的文件选择器 -->
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          multiple
          hidden
          @change="handleFileSelect"
        />
      </div>
    </div>

    <!-- 全局唯一的 el-image-viewer —— 所有 AI 返回图片共用这一个，避免循环内多实例 -->
    <el-image-viewer
      v-if="viewerVisible"
      :url-list="viewerImages"
      :initial-index="viewerIndex"
      :mask-closable="true"
      z-index="9999"
      @close="viewerVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import {
  ChatDotRound, Loading, Tickets, Paperclip, Close, UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useChat } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const { store, sendMessage, disconnect } = useChat()

const scrollRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const inputText = ref('')
const isDragging = ref(false)

// 全局唯一的 el-image-viewer 状态
const viewerVisible = ref(false)
const viewerImages = ref<string[]>([])
const viewerIndex = ref(0)

function openImageViewer(images: string[], index: number) {
  viewerImages.value = images
  viewerIndex.value = index
  viewerVisible.value = true
}

// 模型连接状态（Phase 8 接入后端 health 后改成真实值）
const modelConnected = ref(true)
const modelName = ref('加载中...')

// Excel 项目加载状态（顶部状态栏左侧显示）
const excelStatus = reactive({
  ok: false,
  loaded: false,
  file_path: '',
  file_name: '',
  sheet_count: 0,
})
async function fetchExcelStatus() {
  try {
    const r = await fetch('/api/files/status')
    const d = await r.json()
    Object.assign(excelStatus, d)
  } catch { /* 后端没启动时静默 */ }
}

// ========== 水平拖拽：消息区 ↔ 输入栏 ==========
// 方案：message-area 和 input-area 都是显式像素高度
// input-area 高度由 calc 算出（panel总高 - statusBar - resizer - messageAreaHeight）
// 这样拖拽 message-area → input-area 必然此消彼长，加起来永远等于总高
const STATUS_BAR_H = 34   // status bar 实际高度（含 border）
const RESIZER_H = 6       // h-resizer 实际高度（5px + 1px border）
const LS_MSG_H = 'snail_msg_area_h'
const DEFAULT_MSG_H = 360
const MIN_MSG_H = 120
const MIN_INPUT_H = 60

const messageAreaHeight = ref<number>(
  Number(localStorage.getItem(LS_MSG_H)) || DEFAULT_MSG_H
)
const panelTotalHeight = ref<number>(0)
const panelRef = ref<HTMLElement | null>(null)

// 输入区高度 = panel 总高 - status - resizer - message
const inputAreaHeight = computed(() => {
  const h = panelTotalHeight.value - STATUS_BAR_H - RESIZER_H - messageAreaHeight.value
  return Math.max(MIN_INPUT_H, h)
})

let hDragStartY = 0
let hDragStartH = 0
let resizeObserver: ResizeObserver | null = null

// 根据 panel 总高自动修正 messageAreaHeight，防止挤掉 input 区
function clampMessageHeight() {
  const total = panelTotalHeight.value
  if (total <= 0) return
  const maxMsg = total - STATUS_BAR_H - RESIZER_H - MIN_INPUT_H
  if (messageAreaHeight.value > maxMsg) messageAreaHeight.value = Math.max(MIN_MSG_H, maxMsg)
  if (messageAreaHeight.value < MIN_MSG_H) messageAreaHeight.value = Math.min(maxMsg, MIN_MSG_H)
}

function startHDrag(e: MouseEvent) {
  e.preventDefault()
  hDragStartY = e.clientY
  hDragStartH = messageAreaHeight.value
  window.addEventListener('mousemove', onHDrag)
  window.addEventListener('mouseup', stopHDrag)
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
}

function onHDrag(e: MouseEvent) {
  const dy = e.clientY - hDragStartY
  let h = hDragStartH + dy
  // 上限：message-area 不能让 input-area < MIN_INPUT_H
  const maxMsgH = panelTotalHeight.value - STATUS_BAR_H - RESIZER_H - MIN_INPUT_H
  h = Math.max(MIN_MSG_H, Math.min(h, maxMsgH))
  messageAreaHeight.value = h
}

function stopHDrag() {
  window.removeEventListener('mousemove', onHDrag)
  window.removeEventListener('mouseup', stopHDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  localStorage.setItem(LS_MSG_H, String(messageAreaHeight.value))
}

// Excel 状态定时刷新 + 模型状态定时刷新（mount 时后端可能还没起来）
let excelPollTimer: ReturnType<typeof setInterval> | null = null
let modelPollTimer: ReturnType<typeof setInterval> | null = null

async function fetchModelInfo() {
  try {
    const resp = await fetch('/api/chat/info')
    const data = await resp.json()
    if (data.ok && data.model_name) {
      modelName.value = data.model_name
      modelConnected.value = true
      if (modelPollTimer) {
        clearInterval(modelPollTimer)   // 拿到模型名就停轮询
        modelPollTimer = null
      }
    }
  } catch {
    modelConnected.value = false
  }
}

// 刷新后轮询 /api/agent-messages，增量恢复 events + 检测 final
let msgPollTimer: ReturnType<typeof setInterval> | null = null
let msgPollLastIndex = 0

function startMessagePolling() {
  if (msgPollTimer) return
  msgPollLastIndex = store.events.length
  msgPollTimer = setInterval(async () => {
    try {
      const resp = await fetch('/api/agent-messages')
      const d = await resp.json()
      if (!d.ok || !Array.isArray(d.messages)) return

      const fresh = d.messages.slice(msgPollLastIndex)
      for (const m of fresh) {
        // done = 流程结束（chat_service SSE 循环退出 = main_agent 线程退出）
        if (m.message_type === 'done') {
          // 找 done 之前最后一条 agent_response 当最终回复（优先取 extra.response_full 完整内容）
          let finalResp = null
          for (let i = d.messages.length - 1; i >= 0; i--) {
            const candidate = d.messages[i]
            if (candidate.message_type === 'agent_response') { finalResp = candidate; break }
            if (candidate.message_type === 'done') continue
            if (finalResp) break
          }
          if (finalResp && !store.bubbles.some(b => b.role === 'assistant')) {
            const fullContent = finalResp.extra?.response_full || finalResp.content || '(无回复)'
            store.pushAssistantBubble({
              content: fullContent,
              agentId: finalResp.agent_id,
              events: [...store.events],
            })
            store.setLoading(false)
          }
          stopMessagePolling()
          return
        }
        if (['round_separator', 'system', 'final', 'error'].includes(m.message_type)) continue

        const typeMap: Record<string, string> = {
          user_input: 'user_input', router_decision: 'routing',
          context_build: 'context', agent_receive: 'agent_receive',
          tool_call: 'tool_call', tool_result: 'tool_result',
          agent_response: 'agent_response', flow_progress: 'flow_progress',
        }
        const mappedType = typeMap[m.message_type] || m.message_type

        // agent_response：extra.response_full 是完整回复，content 只是摘要
        const displayContent = (m.message_type === 'agent_response' && m.extra?.response_full)
          ? m.extra.response_full
          : (m.content || '')

        store.pushEvent({
          type: mappedType as any, content: displayContent,
          agentId: m.agent_id || '', timestamp: m.timestamp || '',
        })
      }
      msgPollLastIndex = d.messages.length
    } catch { /* 静默 */ }
  }, 2000)
}

function stopMessagePolling() {
  if (msgPollTimer) { clearInterval(msgPollTimer); msgPollTimer = null }
}

onMounted(async () => {
  // 刷新后如果 events 有残留但没 assistant 气泡，启动 agent-messages 轮询
  if (store.events.length > 0 && store.bubbles.some(b => b.role === 'user') && !store.bubbles.some(b => b.role === 'assistant')) {
    startMessagePolling()
  }

  // 拉取真实模型名 + 启动轮询（mount 时后端可能还没起来）
  await fetchModelInfo()
  if (!modelPollTimer) modelPollTimer = setInterval(fetchModelInfo, 3000)

  // Excel 状态：立即拉一次 + 每 3s 轮询（AppHeader 打开/保存后同步）
  fetchExcelStatus()
  excelPollTimer = setInterval(fetchExcelStatus, 3000)

  // nextTick 确保 DOM 真正渲染完再拿 panel 总高
  await nextTick()
  if (panelRef.value) {
    panelTotalHeight.value = panelRef.value.getBoundingClientRect().height
    clampMessageHeight()  // 首次挂载时修正 localStorage 里残留的过大值
    // ResizeObserver 观察自身（窗口 resize 时 panel 高度变化）
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        panelTotalHeight.value = entry.contentRect.height
        clampMessageHeight()  // 窗口变小时自动缩小 messageAreaHeight
      }
    })
    resizeObserver.observe(panelRef.value)
  }
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (excelPollTimer) { clearInterval(excelPollTimer); excelPollTimer = null }
})

// ========== 最后一个事件 ==========
const latestEvent = computed(() => {
  const evts = store.events
  return evts.length > 0 ? evts[evts.length - 1] : null
})

// ========== SSE 事件 → UI 映射 ==========
function eventColor(type: string): string {
  const map: Record<string, string> = {
    routing: 'primary', tool_call: 'warning', tool_result: 'success',
    llm_call: '', agent_response: 'info', error: 'danger',
    flow_progress: 'primary',
  }
  return map[type] || ''
}
function eventTagType(type: string): string {
  const map: Record<string, string> = {
    routing: 'primary', tool_call: 'warning', tool_result: 'success',
    llm_call: 'info', agent_response: '', error: 'danger',
    flow_progress: 'primary',
  }
  return map[type] || 'info'
}
function eventLabel(type: string): string {
  const map: Record<string, string> = {
    user_input: '用户输入', routing: '路由决策', context: '上下文',
    agent_receive: 'Agent 接收', tool_call: '工具调用', tool_result: '工具结果',
    llm_call: 'LLM 调用', agent_response: 'Agent 回复', final: '最终回复',
    error: '错误', done: '完成', flow_progress: '执行进度',
  }
  return map[type] || type
}

// ========== 是否可发送 ==========
const canSend = computed(() => {
  return (inputText.value.trim().length > 0 || store.pendingImages.length > 0) && !store.isLoading
})

// ========== 拖拽上传 ==========
function onDragOver() { isDragging.value = true }
function onDragLeave() { isDragging.value = false }
function onDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
  if (imageFiles.length === 0) {
    ElMessage.warning('只支持图片文件')
    return
  }
  loadFilesToPreview(imageFiles)
}

// ========== 📎 文件选择 ==========
function triggerFileSelect() { fileInputRef.value?.click() }
function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  loadFilesToPreview(Array.from(files))
  input.value = ''  // 清空，确保下次选同一个文件也能触发 change
}

function loadFilesToPreview(files: File[]) {
  files.forEach(file => {
    const reader = new FileReader()
    reader.onload = (ev) => {
      const result = ev.target?.result as string
      if (result && result.startsWith('data:image/')) {
        // 存完整 dataURL（自带正确 MIME：image/jpeg、image/png、image/webp 等）
        store.addPendingImage(result)
      }
    }
    reader.readAsDataURL(file)
  })
}

// ========== 图片预览（大图查看） ==========
function previewImage(src: string) {
  // 所有图片（待发送预览、用户气泡、AI 返回）都是完整 dataURL，直接用
  window.open(src, '_blank')
}

// ========== 发送 ==========
function onSend() {
  const text = inputText.value.trim()
  const images = [...store.pendingImages]
  if (!text && images.length === 0) return
  if (store.isLoading) return

  stopMessagePolling()  // 发新消息时停止轮询，SSE 会接管
  store.clearEvents()
  sendMessage(text, images)
  store.clearPendingImages()
  inputText.value = ''
  nextTick(scrollToBottom)
}
function sendQuick(text: string) {
  inputText.value = text
  onSend()
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    onSend()
  }
}
function onClear() {
  store.clearAll()
  disconnect()
  ElMessage.success('已清空对话')
}
function scrollToBottom() {
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

// 监听消息列表变化 → 自动滚到底部
// flush:'post' 确保 DOM 先更新完再滚，nextTick 双重保险
watch(
  () => store.bubbles.length,
  () => { nextTick(scrollToBottom) },
  { flush: 'post' }
)
// 流式回复过程中 loading 状态变化也要滚（AI 回复未完成时显示 loading 指示器）
watch(
  () => store.isLoading,
  () => { nextTick(scrollToBottom) }
)

onBeforeUnmount(() => {
  disconnect()
})
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  position: relative;
}

/* ========== 拖拽遮罩 ========== */
.drag-overlay {
  position: absolute;
  inset: 0;
  background: rgba(64, 158, 255, 0.08);
  border: 2px dashed #409eff;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #409eff;
  font-size: 15px;
  z-index: 50;
  pointer-events: none;
}

/* 顶部状态栏：左侧 Excel 项目名 + 右侧模型名 */
.top-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
  font-size: 12px;
  color: #909399;
}

/* 消息区 — 显式像素高度，由拖拽条控制 */
.message-area {
  flex-shrink: 0;
  overflow-y: auto;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 50px 16px;
  color: #909399;
}
.empty-icon { color: #409eff; margin-bottom: 10px; }
.empty-title { font-size: 15px; font-weight: 600; color: #303133; margin: 4px 0; }
.empty-sub { font-size: 13px; }
.quick-prompts {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

/* 气泡行 */
.bubble-row { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 10px; }

/* AI 消息右侧内容区 — 过程事件（上）+ 消息气泡（下）垂直排列 */
.ai-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

/* 气泡 */
.bubble {
  padding: 10px 14px;
  border-radius: 10px;
  line-height: 1.6;
  font-size: 12px;
  word-break: break-word;
}
.user-bubble {
  /* 去掉第二重 75% 限制，改用 inline-block 让气泡随内容自适应，
     max-width: 100% 防止撑破父容器 */
  display: inline-block;
  max-width: 100%;
  background: #409eff; color: #fff; border-top-left-radius: 2px;
}
/* 用户气泡行：头像靠左 + user-content（气泡文字 + 用户图片）垂直排列 */
.user-row { flex-direction: row-reverse; }
.user-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  /* 从 75% 增大到 85%，给三栏布局中被挤压的聊天面板更多空间 */
  max-width: 85%;
}
.ai-bubble {
  width: 100%;
  background: #fff; color: #303133; border: 1px solid #e4e7ed; border-top-left-radius: 2px;
}

/* ========== 图片渲染（用户发送 / AI 返回） ========== */
.bubble-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bubble-img {
  max-width: 180px;
  max-height: 130px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  object-fit: contain;
  background: #fff;
  display: block;
}
.ai-retrieved-img {
  cursor: zoom-in;
  transition: transform 0.15s ease;
}
.ai-retrieved-img:hover {
  transform: scale(1.02);
}
.user-images .bubble-img {
  border-color: rgba(64, 158, 255, 0.5);
}
.loading-bubble {
  background: #fff; border: 1px solid #e4e7ed;
  display: flex; align-items: center; gap: 8px; color: #909399;
}
.loading-hint { font-size: 10px; color: #c0c4cc; margin-left: 6px; }

/* Avatar */
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  object-fit: contain;
  background: transparent;
}
/* 过程时间线 */
.process-timeline { width: 100%; max-width: 680px; margin: 4px 0; font-size: 9px; }
.timeline-toggle { display: flex; align-items: center; gap: 4px; font-size: 9px; color: #909399; }
.timeline-item { display: flex; align-items: center; gap: 8px; font-size: 9px; }
.timeline-content { flex: 1; color: #606266; font-size: 9px; }
.process-timeline :deep(.el-timeline-item__timestamp) { font-size: 8px; }
.process-timeline :deep(.el-timeline-item__content) { font-size: 9px; }
.process-timeline :deep(.el-tag) { font-size: 8px; height: 20px; line-height: 18px; padding: 0 6px; }

/* usage */
.usage-info {
  margin-top: 6px; font-size: 9px; color: #c0c4cc;
  border-top: 1px dashed #ebeef5; padding-top: 6px;
}

/* Markdown 样式 — 统一 13px 基准字号（基础 12px + Markdown 正文 13px） */
.ai-bubble :deep(p),
.ai-bubble :deep(li),
.ai-bubble :deep(blockquote),
.ai-bubble :deep(td),
.ai-bubble :deep(th) {
  font-size: 13px;
}
/* 标题：字号差异控制在 1~3px 内，主要靠 font-weight 区分层级 */
.ai-bubble :deep(h1) { font-size: 1.20em; font-weight: 700; margin: 12px 0 6px; color: #1a1a1a; }
.ai-bubble :deep(h2) { font-size: 1.15em; font-weight: 600; margin: 10px 0 5px; }
.ai-bubble :deep(h3) { font-size: 1.10em; font-weight: 600; margin: 8px 0 4px; }
.ai-bubble :deep(h4),
.ai-bubble :deep(h5),
.ai-bubble :deep(h6) { font-size: 1.00em; font-weight: 600; margin: 6px 0 4px; }
.ai-bubble :deep(code) {
  background: #f0f2f5; color: #c7254e;
  padding: 2px 6px; border-radius: 3px; font-size: 11px;
}
.ai-bubble :deep(pre) {
  background: #f5f7fa; color: #303133; padding: 12px;
  border-radius: 6px; overflow-x: auto; margin: 6px 0; font-size: 11px;
  border: 1px solid #e4e7ed;
}
.ai-bubble :deep(pre code) { background: transparent; padding: 0; color: inherit; font-size: inherit; }
.ai-bubble :deep(ul), .ai-bubble :deep(ol) { padding-left: 20px; margin: 4px 0; }
.ai-bubble :deep(blockquote) {
  border-left: 3px solid #409eff; padding-left: 10px; color: #606266; margin: 6px 0;
}
.ai-bubble :deep(table) { border-collapse: collapse; width: 100%; margin: 6px 0; }
.ai-bubble :deep(th), .ai-bubble :deep(td) {
  border: 1px solid #ebeef5; padding: 6px 10px; text-align: left;
}
.ai-bubble :deep(a) { color: #409eff; text-decoration: none; }
.ai-bubble :deep(a:hover) { text-decoration: underline; }
.ai-bubble :deep(strong) { font-weight: 600; }
.ai-bubble :deep(em) { font-style: italic; }

/* ========== KaTeX 公式渲染 — 隔离外部 CSS 干扰 ========== */
/* 公式基础容器：给一个稳定的绝对字号基准，不受 .bubble 12px / p 13px 的影响 */
.ai-bubble :deep(.katex) {
  font-size: 15px;
}
/* 块级公式：独立成块，允许横向滚动 */
.ai-bubble :deep(.katex-display) {
  margin: 10px 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 0;
}
/* 只重置行内 span 的 line-height，不影响 KaTeX 内部用于垂直堆叠的容器
   （.vlist-t / .vlist-r / .munder 等需要正常 line-height 来正确定位上下标） */
.ai-bubble :deep(.katex span) {
  line-height: inherit;
}
/* KaTeX 原生 scriptstyle（reset-size6）上标下标字号：KaTeX 默认 0.666em，
   这里额外缩小约 20%（→ 0.533em），让上下标视觉更紧凑 */
.ai-bubble :deep(.katex .sizing.reset-size6.size1) { font-size: 0.5em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size2) { font-size: 0.6em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size3) { font-size: 0.533em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size4) { font-size: 0.6em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size5) { font-size: 0.72em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size6) { font-size: 0.8em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size7) { font-size: 0.96em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size8) { font-size: 1.152em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size9) { font-size: 1.38em; }
.ai-bubble :deep(.katex .sizing.reset-size6.size10) { font-size: 1.66em; }

/* 水平拖拽分割条 */
.h-resizer {
  flex-shrink: 0;
  height: 5px;
  background: transparent;
  cursor: row-resize;
  position: relative;
  z-index: 10;
  transition: background 0.15s;
}
.h-resizer:hover,
.h-resizer:active {
  background: #409eff;
}
.h-resizer::after {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 100%;
  height: 1px;
  background: #e4e7ed;
  pointer-events: none;
}
.h-resizer:hover::after {
  background: #409eff;
  height: 2px;
}

/* 输入栏 — 固定总高度（inputAreaHeight），内部 flex column：
   pending-images（flex-shrink:0，不压缩）+ input-area（flex:1 自适应剩余）
   这样 pending-images 出现时，textarea 自动缩小但不会被遮挡 */
.input-area-wrapper {
  flex-shrink: 0;
  border-top: 1px solid #e4e7ed;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

/* 暂存图片预览区 — flex-shrink:0 保证不被压缩 */
.pending-images {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 10px;
}
.pending-img-item {
  position: relative;
  width: 50px;
  height: 50px;
}
.pending-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
}
.remove-img {
  position: absolute;
  top: -5px;
  right: -5px;
  width: 16px;
  height: 16px;
  background: #f56c6c;
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  z-index: 1;
}
.remove-img:hover { background: #e0443e; }

.input-area {
  flex: 1 1 auto;
  min-height: 40px;
  padding: 8px 10px;
  background: #fff;
  display: flex;
  gap: 10px;
  align-items: stretch;
  overflow: hidden;
  box-sizing: border-box;
}

/* 原生 textarea — 填满 input-area，用 height:100% 覆盖一切 inline style */
.native-textarea {
  flex: 1;
  width: 100%;
  height: 100% !important;  /* 关键！压制任何 inline style autosize */
  min-height: 0;            /* 关键！允许被压缩 */
  padding: 6px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  outline: none;
  box-sizing: border-box;
  background: #fff;
  color: #303133;
  overflow-y: auto;
}
.native-textarea:focus {
  border-color: #409eff;
}
.native-textarea:disabled {
  background: #f5f7fa;
  color: #c0c4cc;
}

.input-actions {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: 4px;
}
.icon-btn {
  padding: 4px;
  width: 42px;
  height: 42px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #606266;
  transition: all 0.15s;
}
.icon-btn:hover:not(:disabled) {
  color: #409eff;
  background: #ecf5ff;
}
.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send-btn {
  padding: 4px;
  width: 42px;
  height: 42px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.send-btn:hover:not(:disabled) {
  background: #ecf5ff;
}
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}
</style>
