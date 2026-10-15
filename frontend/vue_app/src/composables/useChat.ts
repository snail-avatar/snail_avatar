// @Time    : 2026
// @Author  : 李涛
// @File    : useChat.ts
// @Desc    : useChat
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

/**
 * useChat composable — 封装聊天的所有交互逻辑
 *
 * 职责：
 *   1. 通过 fetch POST 连接后端 SSE 端点（支持图片 base64 传参）
 *   2. 用 ReadableStream 手动解析 SSE 事件流
 *   3. 解析 SSE 事件 → 分发到 ChatStore（气泡 + 过程事件）
 *   4. 处理连接生命周期（断开 / 完成 / 错误 / 60s 超时保护）
 *   5. 提供 sendMessage / disconnect 方法
 */
import { ref } from 'vue'
import { useChatStore } from '../stores/useChatStore'

// 后端 baseURL — 包含 /api 前缀
const BASE_URL = 'http://localhost:8000/api'

/** SSE 超时保护（秒）— 与后端 done_event.wait 的 3600s 一致 */
const SSE_TIMEOUT_SECONDS = 3600

export function useChat() {
  const store = useChatStore()
  let abortController: AbortController | null = null
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null

  /** 是否显示过程事件面板（可折叠） */
  const showEvents = ref(true)

  /**
   * 发送消息（fetch POST + SSE 流式）
   *
   * @param message  用户文字（可空，纯图片发送时为空字符串）
   * @param images  用户上传的图片 base64 列表（可空）
   */
  async function sendMessage(message: string, images: string[] = []) {
    if (!message.trim() && images.length === 0) return
    if (store.isLoading) return

    // 1. 用户气泡立即显示（附带上传的图片）
    store.pushUserBubble(message.trim(), images.length ? images : undefined)
    store.setLoading(true)
    store.clearEvents()
    store.clearPendingImages()

    // 2. 关闭可能存在的旧连接 + 清除旧超时
    disconnect()

    // 3. 准备 fetch 请求
    const url = `${BASE_URL}/chat/stream`
    abortController = new AbortController()

    const payload = {
      message: message.trim(),
      context_prefix: '',
      reset_history: false,
      images: images,
    }

    // 4. 60s 超时保护（改为 120s 适配图片处理耗时）
    timeoutTimer = setTimeout(() => {
      if (store.isLoading) {
        console.warn('[SSE] timeout after', SSE_TIMEOUT_SECONDS, 's')
        store.pushEvent({
          type: 'error',
          content: `请求超时（${SSE_TIMEOUT_SECONDS}s），请检查后端或网络后重试`,
          agentId: '',
          timestamp: '',
        })
        store.setLoading(false)
        disconnect()
      }
    }, SSE_TIMEOUT_SECONDS * 1000)

    // 5. 发起 POST 请求并解析 SSE 事件流
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify(payload),
        signal: abortController.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      if (!response.body) {
        throw new Error('响应没有 body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // SSE 事件之间用 \n\n 分隔
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? '' // 最后一个可能不完整，保留在 buffer 里

        for (const rawEvent of events) {
          if (!rawEvent.trim()) continue

          // 提取 data: 行
          const lines = rawEvent.split('\n')
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim())
            }
          }
          if (dataLines.length === 0) continue

          // 多个 data: 行拼接（SSE 规范）
          const jsonStr = dataLines.join('\n')
          if (!jsonStr || jsonStr === '[DONE]') continue

          try {
            const payload = JSON.parse(jsonStr)
            handleSSEEvent(payload)
          } catch (e) {
            console.warn('[SSE] JSON parse failed:', jsonStr, e)
          }
        }
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        // 正常断开
      } else {
        console.error('[SSE] fetch error:', e)
        store.pushEvent({
          type: 'error',
          content: `网络请求失败: ${e.message || e}`,
          agentId: '',
          timestamp: '',
        })
        store.setLoading(false)
      }
    }
  }

  /** 关闭 SSE 连接 + 清除超时定时器 */
  function disconnect() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
  }

  /** 处理单个 SSE 事件 */
  function handleSSEEvent(payload: any) {
    const type: string = payload.type || ''

    switch (type) {
      case 'user_input':
      case 'routing':
      case 'context':
      case 'agent_receive':
      case 'tool_call':
      case 'tool_result':
      case 'llm_call':
      case 'agent_response':
      case 'flow_progress':
        // 过程事件 → 时间线
        store.pushEvent({
          type: type as any,
          content: payload.content || '',
          agentId: payload.agent_id || '',
          timestamp: payload.timestamp || '',
        })
        break

      case 'final': {
        // 最终 AI 回复：把当前 events 快照存进气泡，多轮对话后不会丢失
        const eventSnapshot = [...store.events]
        store.pushAssistantBubble({
          content: payload.response || '(无回复)',
          agentId: payload.agent_id,
          usage: payload.usage,
          structuredData: payload.structured_data,
          images: payload.images || [],
          events: eventSnapshot,
        })
        store.setLoading(false)
        disconnect()
        break
      }

      case 'error':
        store.pushEvent({
          type: 'error',
          content: payload.message || '未知错误',
          agentId: '',
          timestamp: '',
        })
        store.setLoading(false)
        disconnect()
        break

      case 'done':
        store.setLoading(false)
        disconnect()
        break

      default:
        if (type) {
          store.pushEvent({
            type: type as any,
            content: JSON.stringify(payload).slice(0, 200),
            agentId: payload.agent_id || '',
            timestamp: '',
          })
        }
    }
  }

  return {
    store,
    showEvents,
    sendMessage,
    disconnect,
  }
}
