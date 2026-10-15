// @Time    : 2026
// @Author  : 李涛
// @File    : useChatStore.ts
// @Desc    : useChatStore
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { defineStore } from 'pinia'
import { ref } from 'vue'

// =========================================================================
// 类型定义
// =========================================================================

/** 聊天气泡 — 用户输入或最终 AI 回复（大卡片） */
export interface ChatBubble {
  id: string
  role: 'user' | 'assistant'
  content: string              // markdown 源文本
  structuredData?: any         // 计算结果的结构化数据（图表等）
  respondingAgentId?: string   // 最终回答的 agent_id
  usageInfo?: { input_tokens: number; output_tokens: number; total_tokens: number }
  timestamp: number
  /** 这个 AI 气泡产生时的过程事件快照（多轮对话后不会丢失） */
  events?: ProcessEvent[]
  /** AI 回复中包含的图片 base64 列表（图搜图/以文搜图返回的图片） */
  images?: string[]
  /** 用户发送时附带的图片 base64 列表 */
  userImages?: string[]
}

/** 过程事件 — Agent 内部路由/工具调用/LLM 调用等（时间线上的小灰条） */
export interface ProcessEvent {
  id: string
  type: EventType              // SSE 事件类型
  content: string              // 事件描述
  agentId: string              // 哪个 agent 产生的
  timestamp: string            // SSE 里带的时间戳 HH:mm:ss
}

/** SSE 事件类型（后端 chat_service.py 发送的 type 字段） */
export type EventType =
  | 'user_input'
  | 'routing'
  | 'context'
  | 'agent_receive'
  | 'tool_call'
  | 'tool_result'
  | 'llm_call'
  | 'agent_response'
  | 'final'
  | 'error'
  | 'done'

// =========================================================================
// Store
// =========================================================================

export const useChatStore = defineStore('chat', () => {
  /** 气泡数组 — 用户/AI 交替 */
  const bubbles = ref<ChatBubble[]>(loadBubbles())
  /** 当前这轮的过程事件（每轮之间清空） */
  const events = ref<ProcessEvent[]>(loadEvents())
  /** 是否正在等待 AI 回复 */
  const isLoading = ref(loadLoading())

  /** 当前选中的 agent（main_agent 或子 agent） */
  const currentAgentId = ref('main_agent')
  /** 用户已选择但尚未发送的图片（base64 预览图） */
  const pendingImages = ref<string[]>([])

  // --- sessionStorage 持久化 ---
  // 需求：刷新页面保留历史，但关闭软件/浏览器后清空（作为全新对话）。
  // sessionStorage 在同 tab 刷新时保留，关闭 tab/浏览器后自动清空，正好符合。
  function loadBubbles(): ChatBubble[] {
    try {
      // 顺便清理可能残留的旧 localStorage 键（迁移清理）
      localStorage.removeItem('chat_bubbles')
      const raw = sessionStorage.getItem('chat_bubbles')
      if (raw) return JSON.parse(raw)
    } catch { /* ignore */ }
    return []
  }

  function saveBubbles() {
    try {
      sessionStorage.setItem('chat_bubbles', JSON.stringify(bubbles.value))
    } catch { /* ignore */ }
  }

  // --- events / isLoading 持久化（刷新页面恢复执行中的进度显示） ---
  function loadEvents(): ProcessEvent[] {
    try {
      const raw = sessionStorage.getItem('chat_events')
      if (raw) return JSON.parse(raw)
    } catch { /* ignore */ }
    return []
  }
  function loadLoading(): boolean {
    try {
      return sessionStorage.getItem('chat_is_loading') === '1'
    } catch { /* ignore */ }
    return false
  }
  function saveRuntimeState() {
    try {
      sessionStorage.setItem('chat_events', JSON.stringify(events.value))
      sessionStorage.setItem('chat_is_loading', isLoading.value ? '1' : '0')
    } catch { /* ignore */ }
  }

  // 每次 push/clear 后自动持久化
  function pushUserBubble(content: string, userImages?: string[]) {
    bubbles.value.push({
      id: Math.random().toString(36).slice(2),
      role: 'user',
      content,
      userImages: userImages?.length ? userImages : undefined,
      timestamp: Date.now(),
    })
    saveBubbles()
  }

  function pushAssistantBubble(data: {
    content: string
    agentId?: string
    usage?: any
    structuredData?: any
    events?: ProcessEvent[]
    images?: string[]
  }) {
    bubbles.value.push({
      id: Math.random().toString(36).slice(2),
      role: 'assistant',
      content: data.content,
      respondingAgentId: data.agentId,
      usageInfo: data.usage,
      structuredData: data.structuredData,
      events: data.events?.length ? data.events : undefined,
      images: data.images?.length ? data.images : undefined,
      timestamp: Date.now(),
    })
    saveBubbles()
  }

  function clearAll() {
    bubbles.value = []
    events.value = []
    pendingImages.value = []
    saveBubbles()
    saveRuntimeState()
  }

  // --- Pending Images（用户暂存的未发送图片） ---
  function addPendingImage(base64: string) {
    pendingImages.value.push(base64)
  }

  function removePendingImage(index: number) {
    pendingImages.value.splice(index, 1)
  }

  function clearPendingImages() {
    pendingImages.value = []
  }

  // --- Event ---
  function pushEvent(ev: Omit<ProcessEvent, 'id'>) {
    events.value.push({
      ...ev,
      id: Math.random().toString(36).slice(2),
    })
    saveRuntimeState()
  }

  function clearEvents() {
    events.value = []
    saveRuntimeState()
  }

  // --- Loading ---
  function setLoading(v: boolean) {
    isLoading.value = v
    saveRuntimeState()
  }

  return {
    bubbles,
    events,
    isLoading,
    currentAgentId,
    pendingImages,
    pushUserBubble,
    pushAssistantBubble,
    pushEvent,
    clearEvents,
    clearAll,
    setLoading,
    addPendingImage,
    removePendingImage,
    clearPendingImages,
  }
})
