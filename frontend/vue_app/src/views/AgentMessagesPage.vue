// @Time    : 2026
// @Author  : 李涛
// @File    : AgentMessagesPage.vue
// @Desc    : AgentMessagesPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  AgentMessagesPage — Agent 交互消息面板（对齐 Flet 原版 AgentMessagePanel）

  双 Tab 页：
    Tab 1: 流式工作信息 — AgentMessageLogger 队列实时消费 + 按 message_type 从 extra 取详情渲染
    Tab 2: 多agent上下文 — Agent 标签栏 + 每个 Agent 的 system_prompt/summary/history
-->
<template>
  <div class="agent-msg-page">
    <el-tabs v-model="activeTopTab" class="top-tabs" @tab-change="onTopTabChange">
      <el-tab-pane label="流式工作信息" name="stream" />
      <el-tab-pane label="多agent上下文" name="context" />
    </el-tabs>

    <!-- ============ Tab 1: 流式工作信息 ============ -->
    <div v-if="activeTopTab === 'stream'" class="tab-content">
      <div class="toolbar">
        <span class="count" v-if="messages.length > 0">共 {{ messages.length }} 条</span>
        <div class="toolbar-right">
          <el-switch v-model="autoScroll" active-text="自动滚动" size="small" />
          <el-button type="danger" size="small" :disabled="messages.length === 0" @click="onClearMessages">清空消息</el-button>
        </div>
      </div>
      <div ref="scrollRef" class="msg-list">
        <div v-if="messages.length === 0" class="empty-hint">暂无消息（发送一条对话即可看到交互过程）</div>

        <!-- ===== round_separator：醒目分隔线 ===== -->
        <template v-for="(msg, idx) in messages" :key="idx">

          <!-- round_separator -->
          <div v-if="msg.message_type === 'round_separator'" class="msg-round-sep">
            <div>────────────────────────────────────────────</div>
            <div class="sep-text">{{ msg.timestamp }} {{ msg.content }}</div>
            <div>────────────────────────────────────────────</div>
          </div>

          <!-- token 消息（extra.token_phase 存在） -->
          <div v-else-if="msg.extra && msg.extra.token_phase" class="msg-token-card">
            <div class="token-header">
              <span class="token-label">{{ tokenPhaseLabel(msg.extra) }}</span>
              <span>输入: {{ msg.extra.input_tokens }} | 输出: {{ msg.extra.output_tokens }} | 总计: {{ msg.extra.total_tokens }}</span>
            </div>
            <div v-if="msg.extra.cumulative_total" class="token-cum">（累计到本轮: {{ msg.extra.cumulative_total }} token）</div>
            <div class="token-extra">{{ msg.content }}</div>
          </div>

          <!-- router_decision -->
          <div v-else-if="msg.message_type === 'router_decision'" class="msg-detail msg-router">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="mode-icon">{{ msg.extra?.used_llm ? '🟢' : '🟠' }}</span>
              <span class="mode-label">{{ msg.extra?.used_llm ? '[路由器决策 · LLM路由]' : '[路由器决策 · 关键词匹配]' }}</span>
              <span>{{ msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}<span v-if="msg.extra?.trust_level"> | trust_level={{ msg.extra.trust_level }}</span></div>
            <div v-if="!msg.extra?.used_llm && msg.extra?.fallback_reason" class="warn-box">⚠ WARNING: {{ msg.extra.fallback_reason }}</div>
            <div v-if="msg.extra?.llm_input_system_prompt" class="detail-block">
              <div class="block-title">━━━ LLM 输入: System Prompt ━━━</div>
              <pre class="detail-pre">{{ msg.extra.llm_input_system_prompt }}</pre>
            </div>
            <div v-if="msg.extra?.llm_input_user_message" class="detail-block">
              <div class="block-title">━━━ LLM 输入: User Message ━━━</div>
              <pre class="detail-pre">{{ msg.extra.llm_input_user_message }}</pre>
            </div>
            <div v-if="msg.extra?.llm_raw_output" class="detail-block">
              <div class="block-title">━━━ LLM 原始输出 (Raw Output) ━━━</div>
              <pre class="detail-pre">{{ msg.extra.llm_raw_output }}</pre>
            </div>
            <div v-if="msg.extra?.llm_parsed_output" class="detail-block">
              <div class="block-title">━━━ LLM 解析结果 (Parsed JSON) ━━━</div>
              <CollapsibleJson :data="toJsonObj(msg.extra.llm_parsed_output) ?? msg.extra.llm_parsed_output" />
            </div>
            <div v-if="hasUsage(msg.extra)" class="token-row">🔴 【TOKEN】{{ usageText(msg.extra) }}</div>
          </div>

          <!-- tool_call / tool_result -->
          <div v-else-if="msg.message_type === 'tool_call' || msg.message_type === 'tool_result'" class="msg-detail" :class="msgTypeClass(msg.message_type)">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span>{{ msg.extra?.tool_name || msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}<span v-if="msg.extra?.tool_call_id"> | tool_call_id: {{ msg.extra.tool_call_id }}</span></div>
            <div v-if="msg.extra?.tool_arguments" class="detail-block">
              <div class="block-title">参数 (arguments):</div>
              <CollapsibleJson :data="toJsonObj(msg.extra.tool_arguments) ?? msg.extra.tool_arguments" />
            </div>
            <div v-if="msg.message_type === 'tool_result' && msg.extra?.tool_result" class="detail-block">
              <div class="block-title">结果 (返回给 LLM 的内容):</div>
              <pre class="detail-pre">{{ msg.extra.tool_result }}</pre>
            </div>
            <div v-if="msg.content && (!msg.extra?.tool_name || msg.content !== msg.extra.tool_name)" class="detail-summary">{{ msg.content }}</div>
          </div>

          <!-- context_build -->
          <div v-else-if="msg.message_type === 'context_build'" class="msg-detail msg-context">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span>{{ msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}</div>
            <div v-if="msg.extra?.full_input" class="detail-block">
              <div class="block-title">子Agent实际收到的完整输入:</div>
              <pre class="detail-pre">{{ msg.extra.full_input }}</pre>
            </div>
            <div v-else-if="msg.extra?.context_full" class="detail-block">
              <div class="block-title">完整上下文内容:</div>
              <pre class="detail-pre">{{ msg.extra.context_full }}</pre>
            </div>
          </div>

          <!-- llm_call -->
          <div v-else-if="msg.message_type === 'llm_call'" class="msg-detail msg-llm">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span>{{ msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}</div>
            <div v-if="msg.extra?.tools_schema" class="detail-block">
              <div class="block-title">可用工具 Schema:</div>
              <CollapsibleJson :data="toJsonObj(msg.extra.tools_schema) ?? msg.extra.tools_schema" />
            </div>
          </div>

          <!-- agent_receive -->
          <div v-else-if="msg.message_type === 'agent_receive'" class="msg-detail msg-receive">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span>{{ msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}</div>
            <div v-if="msg.extra?.tools_catalog" class="detail-block">
              <div class="block-title">工具目录（Phase 1）:</div>
              <pre class="detail-pre">{{ msg.extra.tools_catalog }}</pre>
            </div>
          </div>

          <!-- agent_response -->
          <div v-else-if="msg.message_type === 'agent_response'" class="msg-detail msg-response">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span>{{ msg.content }}</span>
            </div>
            <div class="detail-meta">来源: {{ msg.agent_id }}</div>
            <div v-if="hasUsage(msg.extra)" class="token-row">🔴 【TOKEN】{{ usageText(msg.extra) }}</div>
            <div v-if="msg.extra?.response_full" class="detail-block">
              <div class="block-title">完整回复:</div>
              <pre class="detail-pre">{{ msg.extra.response_full }}</pre>
            </div>
          </div>

          <!-- 通用（system / user_input / summary_fallback / 其他） -->
          <div v-else class="msg-detail" :class="msgTypeClass(msg.message_type)">
            <div class="detail-title">
              <span class="msg-ts">{{ msg.timestamp }}</span>
              <span class="msg-type">[{{ msgTypeLabel(msg.message_type) }}]</span>
              <span class="msg-agent">@{{ msg.agent_id }}</span>
            </div>
            <div v-if="hasUsage(msg.extra)" class="token-row">🔴 【TOKEN】{{ usageText(msg.extra) }}</div>
            <div class="detail-body">{{ msg.content }}</div>
            <div v-if="msg.extra" class="extra-kv">
              <div v-for="(v, k) in cleanExtra(msg.extra)" :key="k" class="extra-item">
                {{ k }}: {{ typeof v === 'object' ? JSON.stringify(v) : v }}
              </div>
            </div>
          </div>

        </template>
      </div>
    </div>

    <!-- ============ Tab 2: 多agent上下文 ============ -->
    <div v-else class="tab-content">
      <div class="toolbar">
        <span class="count">{{ agents.length }} 个 Agent</span>
        <div class="toolbar-right">
          <el-button size="small" @click="onRefreshAgents">刷新</el-button>
        </div>
      </div>

      <div class="agent-tabs">
        <div v-for="a in agents" :key="a.agent_id" class="agent-tab" :class="{ active: activeAgentId === a.agent_id }" @click="switchAgent(a.agent_id)">{{ a.agent_name }}</div>
        <div v-if="agents.length === 0" class="empty-hint small">暂无已实例化 Agent（先发送一条对话）</div>
      </div>

      <div ref="ctxScrollRef" class="ctx-content" v-if="ctxData">
        <div class="ctx-title">Agent: {{ ctxData.agent_name }}（{{ ctxData.agent_id }}）</div>
        <div class="ctx-block">
          <div class="ctx-label">--- 1. 系统提示词 ---</div>
          <pre v-if="ctxData.system_prompt" class="ctx-pre">{{ ctxData.system_prompt }}</pre>
          <div v-else class="ctx-empty">（空）</div>
        </div>
        <div class="ctx-block">
          <div class="ctx-label">--- 2. 长期摘要 ---</div>
          <pre v-if="ctxData.summary" class="ctx-pre">{{ ctxData.summary }}</pre>
          <div v-else class="ctx-empty">（空）</div>
        </div>
        <div class="ctx-block">
          <div class="ctx-label">--- 3. 历史对话（{{ ctxData.history.length }} 条）---</div>
          <div v-if="ctxData.history.length > 0" class="ctx-pre">
            <CollapsibleJson :data="ctxData.history" />
          </div>
          <div v-else class="ctx-empty">[]</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import CollapsibleJson from '../components/CollapsibleJson.vue'

const activeTopTab = ref('stream')

// ========= Tab 1 =========
interface AgentMsg {
  timestamp: string
  agent_id: string
  message_type: string
  content: string
  extra: Record<string, any>
}
const messages = ref<AgentMsg[]>([])
const autoScroll = ref(true)
const scrollRef = ref<HTMLElement | null>(null)
let streamTimer: ReturnType<typeof setInterval> | null = null

// ========= Tab 2 =========
interface AgentInfo { agent_id: string; agent_name: string }
const agents = ref<AgentInfo[]>([])
const activeAgentId = ref('')
const ctxData = ref<any>(null)
const ctxScrollRef = ref<HTMLElement | null>(null)
let ctxTimer: ReturnType<typeof setInterval> | null = null

// ========= 消息类型映射 =========
const TYPE_LABEL: Record<string, string> = {
  user_input: '用户输入',
  router_decision: '路由器决策',
  context_build: '上下文传递',
  agent_receive: 'Agent接收',
  llm_call: 'LLM调用',
  tool_call: '工具调用',
  tool_result: '工具返回',
  agent_response: 'Agent回复',
  flow_progress: '执行进度',
  system: '系统',
  round_separator: '轮次分隔',
  summary_fallback: '摘要降级',
}
function msgTypeLabel(t: string) { return TYPE_LABEL[t] || t }

function msgTypeClass(t: string): string {
  const map: Record<string, string> = {
    user_input: 't-user', router_decision: 't-router', context_build: 't-context',
    agent_receive: 't-receive', llm_call: 't-llm', tool_call: 't-tool-call',
    tool_result: 't-tool-result', agent_response: 't-response', flow_progress: 't-flow-progress',
    system: 't-system', round_separator: 't-round', summary_fallback: 't-fallback',
  }
  return map[t] || 't-default'
}

// ========= Flet renderer 对齐的辅助函数 =========

// 安全 parse JSON string → object；已经是 object 则直接返回；无效时返回 null
function toJsonObj(raw: any): any {
  if (raw === null || raw === undefined) return null
  if (typeof raw === 'object') return raw
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return null }
  }
  return null
}

function hasUsage(extra: any): boolean {
  return extra && extra.usage && typeof extra.usage === 'object'
}

function usageText(extra: any): string {
  const u = extra?.usage || {}
  return `输入 ${u.input_tokens ?? '?'} | 输出 ${u.output_tokens ?? '?'} | 总计 ${u.total_tokens ?? '?'}`
}

function tokenPhaseLabel(extra: any): string {
  const phase = extra?.token_phase || ''
  const round = extra?.round_number
  const map: Record<string, string> = {
    phase1: '🔴 【Phase 1 工具目录选择】',
    phase2_round: `🔴 【Phase 2 工具调用${round ? ` 第 ${round} 轮` : ''}】`,
    main_agent: '🔴 【主Agent LLM 调用】',
  }
  return map[phase] || `🔴 【${phase}】`
}

function cleanExtra(extra: Record<string, any>): Record<string, any> {
  // 排除已经单独渲染过的字段
  const EXCLUDE = ['usage', 'token_phase', 'input_tokens', 'output_tokens', 'total_tokens', 'cumulative_total', 'round_number']
  const result: Record<string, any> = {}
  for (const k of Object.keys(extra)) {
    if (!EXCLUDE.includes(k)) result[k] = extra[k]
  }
  return result
}

// ========= Tab 1 轮询 =========
async function fetchMessages() {
  try {
    const resp = await fetch('/api/agent-messages')
    const data = await resp.json()
    if (data.ok && Array.isArray(data.messages)) {
      const newLen = data.messages.length
      const oldLen = messages.value.length
      messages.value = data.messages
      if (autoScroll.value && newLen > oldLen) {
        await nextTick()
        scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight })
      }
    }
  } catch { /* ignore */ }
}

async function onClearMessages() {
  try {
    await fetch('/api/agent-messages/clear', { method: 'POST' })
    messages.value = []
  } catch { /* ignore */ }
}

// ========= Tab 2 =========
async function fetchAgents() {
  try {
    const resp = await fetch('/api/agents')
    const data = await resp.json()
    if (data.ok && Array.isArray(data.agents)) {
      agents.value = data.agents
      if (!activeAgentId.value || !agents.value.some((a: AgentInfo) => a.agent_id === activeAgentId.value)) {
        if (agents.value.length > 0) {
          activeAgentId.value = agents.value[0].agent_id
          await fetchContext()
        } else {
          ctxData.value = null
        }
      }
    }
  } catch { /* ignore */ }
}

async function fetchContext() {
  if (!activeAgentId.value) return
  try {
    const resp = await fetch(`/api/agents/${activeAgentId.value}/context`)
    const data = await resp.json()
    if (data.ok) {
      ctxData.value = data
      await nextTick()
      ctxScrollRef.value?.scrollTo({ top: ctxScrollRef.value.scrollHeight })
    }
  } catch { /* ignore */ }
}

function switchAgent(id: string) {
  if (id !== activeAgentId.value) {
    activeAgentId.value = id
    fetchContext()
  }
}
function onRefreshAgents() { fetchAgents() }

function onTopTabChange(tab: string) { if (tab === 'context') fetchAgents() }

// ========= 生命周期 =========
onMounted(() => {
  fetchMessages()
  streamTimer = setInterval(fetchMessages, 500)
  fetchAgents()
  ctxTimer = setInterval(() => { if (activeTopTab.value === 'context') fetchAgents() }, 2000)
})
onBeforeUnmount(() => {
  if (streamTimer) clearInterval(streamTimer)
  if (ctxTimer) clearInterval(ctxTimer)
})
watch(autoScroll, (v) => { if (v) scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight }) })
</script>

<style scoped>
.agent-msg-page { display: flex; flex-direction: column; height: 100%; background: #fff; }
.tab-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; border-top: 1px solid #e4e7ed; }

.top-tabs { flex-shrink: 0; }
.top-tabs :deep(.el-tabs__header) { margin: 0; padding: 0 10px; }
.top-tabs :deep(.el-tabs__item) { font-size: 13px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 6px 12px; background: #fafbfc; border-bottom: 1px solid #e4e7ed; flex-shrink: 0; }
.count { font-size: 12px; color: #909399; }
.toolbar-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }

/* === Tab1: 消息列表 === */
.msg-list { flex: 1; overflow-y: auto; padding: 6px 10px; font-family: ui-monospace, Consolas, monospace; font-size: 12px; line-height: 1.6; }
.empty-hint { color: #c0c4cc; text-align: center; padding: 40px 0; font-size: 13px; }
.empty-hint.small { font-size: 12px; padding: 16px 0; }

/* round_separator */
.msg-round-sep { text-align: center; padding: 8px; color: #b91c1c; font-weight: 700; background: #fef2f2; border-radius: 4px; margin: 4px 0; }
.msg-round-sep .sep-text { font-size: 11px; margin: 2px 0; }

/* token 消息 */
.msg-token-card { padding: 8px; background: #fee2e2; border-radius: 4px; margin: 4px 0; border-left: 3px solid #dc2626; }
.msg-token-card .token-header { color: #991b1b; font-weight: 700; font-size: 13px; }
.msg-token-card .token-label { margin-right: 8px; }
.msg-token-card .token-cum { color: #b91c1c; font-weight: 600; font-style: italic; font-size: 12px; margin-top: 2px; }
.msg-token-card .token-extra { color: #6b7280; font-style: italic; margin-top: 4px; font-size: 11px; }

/* 通用 msg-detail */
.msg-detail { padding: 6px 10px; border-radius: 4px; margin: 3px 0; }
.msg-detail .detail-title { display: flex; flex-wrap: wrap; gap: 6px; font-weight: 600; align-items: baseline; }
.msg-detail .msg-ts { color: #9ca3af; font-weight: 400; }
.msg-detail .msg-type { font-weight: 700; }
.msg-detail .msg-agent { color: #9ca3af; font-size: 11px; }
.msg-detail .detail-meta { font-size: 10px; color: #6b7280; font-style: italic; margin-top: 2px; }
.msg-detail .detail-block { margin-top: 6px; }
.msg-detail .block-title { font-size: 10px; font-weight: 700; margin-bottom: 2px; }
.msg-detail .detail-pre { background: #fafbfc; border: 1px solid #e4e7ed; border-radius: 4px; padding: 6px 8px; font-size: 11px; font-family: ui-monospace, Consolas, monospace; line-height: 1.5; white-space: pre-wrap; word-break: break-all; color: #303133; margin: 0; max-height: 400px; overflow-y: auto; }
.msg-detail .detail-body { margin-top: 4px; white-space: pre-wrap; word-break: break-all; }
.msg-detail .detail-summary { margin-top: 4px; color: #6b7280; font-style: italic; }
.msg-detail .extra-kv { margin-top: 4px; }
.msg-detail .extra-item { font-size: 10px; color: #6b7280; font-style: italic; word-break: break-all; }

/* token 行 */
.token-row { padding: 4px 8px; margin-top: 4px; background: #fee2e2; color: #991b1b; font-weight: 700; border-radius: 4px; font-size: 13px; }

/* 11 种消息类型着色 */
.msg-router  { background: #f3e8ff; color: #4c1d95; }
.msg-router .block-title { color: #4c1d95; }
.msg-context { background: #fef3c7; color: #78350f; }
.msg-receive { background: #ffedd5; color: #9a3412; }
.msg-llm     { background: #eef2ff; color: #3730a3; }
.msg-llm .block-title { color: #3730a3; }
.msg-response { background: #dcfce7; color: #166534; }

.t-user        { background: #ecf5ff; color: #1a3a8a; }
.t-user .msg-type { color: #1a3a8a; }
.t-tool-call   { background: #ccfbf1; color: #115e59; }
.t-tool-call .msg-type { color: #115e59; }
.t-tool-result { background: #f0fdfa; color: #134e4a; }
.t-system      { background: #f3f4f6; color: #6b7280; }
.t-fallback    { background: #fed7aa; color: #7c2d12; font-weight: 600; }
.t-default     { background: #f9fafb; color: #374151; }

/* router_decision 特殊 */
.msg-router .mode-icon { font-weight: 400; }
.msg-router .mode-label { font-weight: 700; margin-right: 6px; }
.msg-router .warn-box { padding: 6px 10px; margin-top: 4px; background: #ffedd5; border-radius: 4px; color: #9a3412; font-weight: 700; font-size: 11px; border-left: 3px solid #ea580c; }

/* === Tab2 === */
.agent-tabs { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #e4e7ed; background: #fafbfc; flex-shrink: 0; }
.agent-tab { padding: 4px 12px; border: 1px solid #dcdfe6; border-radius: 14px; font-size: 12px; color: #606266; cursor: pointer; transition: all 0.15s; background: #fff; }
.agent-tab:hover { border-color: #409eff; color: #409eff; }
.agent-tab.active { border-color: #409eff; background: #ecf5ff; color: #409eff; font-weight: 600; }

.ctx-content { flex: 1; overflow-y: auto; padding: 10px 14px; }
.ctx-title { font-size: 13px; font-weight: 700; color: #1e40af; margin-bottom: 8px; }
.ctx-block { margin-bottom: 12px; }
.ctx-label { font-size: 11px; font-weight: 700; color: #78350f; margin-bottom: 4px; }
.ctx-pre { background: #fafbfc; border: 1px solid #e4e7ed; border-radius: 4px; padding: 8px 10px; font-size: 11px; font-family: ui-monospace, Consolas, monospace; line-height: 1.5; white-space: pre-wrap; word-break: break-all; color: #303133; margin: 0; max-height: 500px; overflow-y: auto; }
.ctx-empty { font-size: 11px; color: #9ca3af; font-style: italic; }
</style>
