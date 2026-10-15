// @Time    : 2026
// @Author  : 李涛
// @File    : ChatPage.vue
// @Desc    : ChatPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <div
    ref="inputAreaRef"
    class="chat-page"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <!-- 拖拽遮罩提示 -->
    <div v-if="isDragging" class="drag-overlay">
      <el-icon :size="48"><UploadFilled /></el-icon>
      <p>释放以上传图片</p>
    </div>

    <!-- ========== 消息主区 ========== -->
    <div ref="scrollRef" class="message-area" @scroll="onScroll">
      <!-- 空状态 -->
      <div v-if="store.bubbles.length === 0" class="empty-state">
        <el-icon :size="48" class="empty-icon"><ChatDotRound /></el-icon>
        <p>你好！我是 Snail Avatar 智能助手 🚗⚡</p>
        <p class="sub">可以帮你解答新能源汽车性能开发相关问题</p>
        <div class="quick-prompts">
          <el-button size="small" @click="sendQuick('请做自我介绍')">自我介绍</el-button>
          <el-button size="small" @click="sendQuick('什么是 VTS 和 SSTS？')">VTS/SSTS 解释</el-button>
          <el-button size="small" @click="sendQuick('电动车 CLTC 续航怎么算？')">CLTC 续航</el-button>
        </div>
      </div>

      <!-- 气泡 + 每轮过程事件 -->
      <template v-for="(bubble, idx) in store.bubbles" :key="bubble.id">
        <!-- 用户气泡 -->
        <div v-if="bubble.role === 'user'" class="bubble-row user">
          <el-avatar :size="32" class="avatar user-avatar">我</el-avatar>
          <div class="user-column">
            <div class="bubble user-bubble">{{ bubble.content || '(仅图片)' }}</div>
            <!-- 用户发送的图片预览 -->
            <div v-if="bubble.userImages && bubble.userImages.length" class="bubble-images user-images">
              <img
                v-for="(img, i) in bubble.userImages"
                :key="'u' + idx + '-' + i"
                :src="'data:image/png;base64,' + img"
                class="bubble-img"
                alt="用户图片"
              />
            </div>
          </div>
        </div>

        <!-- AI 气泡 -->
        <div v-else class="bubble-row assistant">
          <el-avatar :size="32" class="avatar ai-avatar">AI</el-avatar>

          <div class="assistant-column">
            <!-- 过程时间线（属于这个 AI 气泡的事件快照） -->
            <div v-if="bubble.events && bubble.events.length > 0" class="process-timeline">
              <el-collapse>
                <el-collapse-item name="events">
                  <template #title>
                    <span class="timeline-toggle">
                      <el-icon><Tickets /></el-icon>
                      本轮过程事件 ({{ bubble.events.length }})
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
                        <span v-if="ev.agentId" class="timeline-agent">· {{ ev.agentId }}</span>
                      </div>
                    </el-timeline-item>
                  </el-timeline>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- AI 回复气泡（Markdown） -->
            <div class="bubble ai-bubble">
              <div v-html="renderMarkdown(bubble.content)"></div>
              <!-- usage 信息 -->
              <div v-if="bubble.usageInfo" class="usage-info">
                tokens: {{ bubble.usageInfo.input_tokens }}↑ {{ bubble.usageInfo.output_tokens }}↓
              </div>
            </div>

            <!-- AI 返回的图片（图搜图/以文搜图结果） -->
            <div v-if="bubble.images && bubble.images.length" class="bubble-images ai-images">
              <img
                v-for="(img, i) in bubble.images"
                :key="'a' + idx + '-' + i"
                :src="'data:image/png;base64,' + img"
                class="bubble-img"
                alt="检索图片"
                @click="previewImage(img)"
              />
            </div>
          </div>
        </div>
      </template>

      <!-- Loading 指示器（AI 正在思考） -->
      <div v-if="store.isLoading" class="bubble-row assistant loading-row">
        <el-avatar :size="32" class="avatar ai-avatar">AI</el-avatar>
        <div class="bubble loading-bubble">
          <el-icon class="is-loading" :size="20"><Loading /></el-icon>
          <span>AI 正在思考...</span>
          <span v-if="latestEvent" class="loading-hint">{{ latestEvent.content }}</span>
        </div>
      </div>
    </div>

    <!-- ========== 底部输入栏 ========== -->
    <div class="input-area">
      <!-- 图片暂存区（用户已选但未发送） -->
      <div v-if="store.pendingImages.length > 0" class="pending-images">
        <div v-for="(img, idx) in store.pendingImages" :key="idx" class="pending-img-item">
          <img :src="'data:image/png;base64,' + img" class="pending-img" alt="待发送图片" />
          <el-icon class="remove-img" @click="store.removePendingImage(idx)"><Close /></el-icon>
        </div>
      </div>

      <div class="input-row">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="2"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="输入消息，或直接把图片拖到这里..."
          :disabled="store.isLoading"
          @keydown="onKeydown"
          resize="none"
        />
        <div class="input-actions">
          <!-- 文件选择按钮 -->
          <el-tooltip content="上传图片" placement="top" :show-after="300">
            <el-button size="small" :disabled="store.isLoading" @click="triggerFileSelect">
              <el-icon><Paperclip /></el-icon>
            </el-button>
          </el-tooltip>
          <!-- 清空 -->
          <el-button size="small" :disabled="store.isLoading" @click="onClear">
            <el-icon><Delete /></el-icon>
          </el-button>
          <!-- 发送 -->
          <el-button
            type="primary"
            size="small"
            :loading="store.isLoading"
            :disabled="!canSend"
            @click="onSend"
          >
            <el-icon><Promotion /></el-icon>发送
          </el-button>
        </div>
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
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import {
  ChatDotRound, Loading, Delete, Promotion, Tickets, Paperclip, Close, UploadFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useChat } from '../composables/useChat'
import { renderMarkdown } from '../utils/markdown'

const { store, sendMessage, disconnect } = useChat()

const scrollRef = ref<HTMLElement | null>(null)
const inputAreaRef = ref<HTMLElement | null>(null)
const inputText = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

// ========== 是否可以发送 ==========
const canSend = computed(() => {
  return (inputText.value.trim().length > 0 || store.pendingImages.length > 0) && !store.isLoading
})

// ========== 最后一个事件（loading 提示用） ==========
const latestEvent = computed(() => {
  const evts = store.events
  return evts.length > 0 ? evts[evts.length - 1] : null
})

// ========== SSE 事件 → UI 颜色/标签映射 ==========
function eventColor(type: string): string {
  const map: Record<string, string> = {
    routing: 'primary',
    tool_call: 'warning',
    tool_result: 'success',
    llm_call: '',
    agent_response: 'info',
    error: 'danger',
  }
  return map[type] || ''
}

function eventTagType(type: string): string {
  const map: Record<string, string> = {
    routing: 'primary',
    tool_call: 'warning',
    tool_result: 'success',
    llm_call: 'info',
    agent_response: '',
    error: 'danger',
  }
  return map[type] || 'info'
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    user_input: '用户输入',
    routing: '路由决策',
    context: '上下文',
    agent_receive: 'Agent 接收',
    tool_call: '工具调用',
    tool_result: '工具结果',
    llm_call: 'LLM 调用',
    agent_response: 'Agent 回复',
    final: '最终回复',
    error: '错误',
    done: '完成',
  }
  return map[type] || type
}

// ========== 文件选择 & 拖拽 ==========
function triggerFileSelect() {
  fileInputRef.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return

  loadFilesToPreview(Array.from(files))
  // 清空 input，确保下次选同一个文件也能触发 change
  input.value = ''
}

function onDragOver(e: DragEvent) {
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return

  // 过滤只保留图片
  const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
  if (imageFiles.length === 0) {
    ElMessage.warning('只支持图片文件')
    return
  }
  loadFilesToPreview(imageFiles)
}

function loadFilesToPreview(files: File[]) {
  files.forEach(file => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const result = e.target?.result as string
      if (result && result.startsWith('data:image/')) {
        // 去掉 data:image/xxx;base64, 前缀，只保留纯 base64
        const base64 = result.split(',', 1)[1]
        store.addPendingImage(base64)
      }
    }
    reader.readAsDataURL(file)
  })
}

// ========== 发送 ==========
function onSend() {
  const text = inputText.value.trim()
  const images = [...store.pendingImages]

  if (!text && images.length === 0) return
  if (store.isLoading) return

  store.clearEvents()
  sendMessage(text, images)
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

// ========== 图片预览（大图查看） ==========
function previewImage(base64: string) {
  window.open(`data:image/png;base64,${base64}`, '_blank')
}

// ========== 滚动 ==========
function scrollToBottom() {
  const el = scrollRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

function onScroll() {
  // 预留：检测用户是否滚到了底部，新消息来时不强制滚动
}

// 监听 bubbles 变化自动滚动到底部
watch(() => store.bubbles.length, () => {
  nextTick(scrollToBottom)
})

// ========== 清理 ==========
onBeforeUnmount(() => {
  disconnect()
})
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 900px;
  margin: 0 auto;
  position: relative;
}

/* ========== 拖拽遮罩 ========== */
.drag-overlay {
  position: absolute;
  inset: 0;
  background: rgba(64, 158, 255, 0.08);
  border: 2px dashed #409eff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #409eff;
  z-index: 10;
  pointer-events: none;
}
.drag-overlay p {
  margin-top: 12px;
  font-size: 16px;
}

/* ========== 消息区 ========== */
.message-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #909399;
}
.empty-icon {
  color: #409eff;
  margin-bottom: 12px;
}
.empty-state p {
  margin: 4px 0;
}
.empty-state .sub {
  font-size: 13px;
}
.quick-prompts {
  margin-top: 20px;
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

/* 气泡行 */
.bubble-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.bubble-row.user {
  flex-direction: row-reverse;
}
.bubble-row.assistant {
  flex-direction: row;
}

.user-column, .assistant-column {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 70%;
}
.user-column {
  align-items: flex-end;
}

/* 气泡 */
.bubble {
  max-width: 100%;
  padding: 10px 14px;
  border-radius: 10px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}
.user-bubble {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 2px;
}
.ai-bubble {
  background: #fff;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-top-left-radius: 2px;
}
.loading-bubble {
  background: #fff;
  border: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
}
.loading-hint {
  font-size: 12px;
  color: #c0c4cc;
  margin-left: 8px;
}

/* Avatar */
.avatar {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}
.user-avatar {
  background: #409eff;
  color: #fff;
}
.ai-avatar {
  background: #67c23a;
  color: #fff;
}

/* ========== 图片显示（AI返回 / 用户发送） ========== */
.bubble-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bubble-img {
  max-width: 200px;
  max-height: 150px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  cursor: zoom-in;
  object-fit: contain;
  background: #fff;
  transition: transform 0.15s ease;
}
.bubble-img:hover {
  transform: scale(1.02);
}
.user-images .bubble-img {
  border-color: rgba(255, 255, 255, 0.5);
  cursor: default;
}

/* ========== 过程时间线 ========== */
.process-timeline {
  width: 100%;
  max-width: 700px;
  margin: 4px 0;
}
.timeline-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
}
.timeline-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.timeline-content {
  flex: 1;
  color: #606266;
}
.timeline-agent {
  color: #c0c4cc;
  font-size: 11px;
}

/* ========== usage ========== */
.usage-info {
  margin-top: 8px;
  font-size: 11px;
  color: #c0c4cc;
  border-top: 1px dashed #ebeef5;
  padding-top: 6px;
}

/* ========== Markdown 样式 ========== */
.ai-bubble :deep(h1), .ai-bubble :deep(h2), .ai-bubble :deep(h3) {
  margin: 12px 0 6px;
  font-weight: 600;
}
.ai-bubble :deep(p) {
  margin: 6px 0;
}
.ai-bubble :deep(code) {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}
.ai-bubble :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}
.ai-bubble :deep(pre code) {
  background: transparent;
  padding: 0;
}
.ai-bubble :deep(ul), .ai-bubble :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}
.ai-bubble :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding-left: 10px;
  color: #606266;
  margin: 8px 0;
}
.ai-bubble :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}
.ai-bubble :deep(th), .ai-bubble :deep(td) {
  border: 1px solid #ebeef5;
  padding: 6px 10px;
  text-align: left;
}
.ai-bubble :deep(a) {
  color: #409eff;
  text-decoration: none;
}
.ai-bubble :deep(a:hover) {
  text-decoration: underline;
}

/* ========== 输入栏 ========== */
.input-area {
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.input-area :deep(.el-textarea__inner) {
  border-radius: 8px;
}
.input-actions {
  display: flex;
  flex-direction: row;
  gap: 6px;
  flex-shrink: 0;
}

/* ========== 暂存图片预览 ========== */
.pending-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0;
}
.pending-img-item {
  position: relative;
  width: 60px;
  height: 60px;
}
.pending-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
}
.remove-img {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  background: #f56c6c;
  color: #fff;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  z-index: 1;
}
.remove-img:hover {
  background: #e0443e;
}
</style>
