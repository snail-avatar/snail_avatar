// @Time    : 2026
// @Author  : 李涛
// @File    : WorkLogPage.vue
// @Desc    : WorkLogPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  WorkLogPage — 工作日志面板（对齐 Flet 原版 WorkLogPanel）
  - 定时 0.5s 轮询 GET /api/work-logs 获取最新日志
  - ERROR 红色加粗 / WARN 橙色加粗 / INFO 灰色
  - 自动滚动到底部（auto_scroll）
  - 清空按钮（POST /api/work-logs/clear）
-->
<template>
  <div class="work-log-page">
    <!-- 顶部工具栏：清空/自动滚动按钮（标题已由 MainLayout 统一渲染） -->
    <div class="log-toolbar">
      <span class="log-count" v-if="logs.length > 0">共 {{ logs.length }} 条</span>
      <div class="toolbar-right">
        <el-switch
          v-model="autoScroll"
          active-text="自动滚动"
          inactive-text=""
          size="small"
        />
        <el-button
          type="danger"
          size="small"
          :disabled="logs.length === 0"
          @click="onClear"
        >清空日志</el-button>
      </div>
    </div>

    <!-- 日志列表 -->
    <div ref="scrollRef" class="log-list">
      <div v-if="logs.length === 0" class="empty-hint">暂无日志</div>
      <div
        v-for="(line, idx) in logs"
        :key="idx"
        class="log-line"
        :class="levelClass(line.level)"
      >
        <span v-if="line.timestamp" class="log-ts">{{ line.timestamp }}</span>
        <span class="log-level">[{{ line.level }}]</span>
        <span class="log-msg">{{ line.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'

interface LogLine {
  timestamp: string
  level: string
  message: string
}

const logs = ref<LogLine[]>([])
const autoScroll = ref(true)
const scrollRef = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let lastFetchLen = 0  // 记录上次拉取的条数，用于判断是否需要滚动

function levelClass(level: string) {
  const lv = (level || 'INFO').toUpperCase()
  if (lv === 'ERROR') return 'level-error'
  if (lv === 'WARN' || lv === 'WARNING') return 'level-warn'
  return 'level-info'
}

async function fetchLogs() {
  try {
    const resp = await fetch('/api/work-logs')
    const data = await resp.json()
    if (data.ok && Array.isArray(data.logs)) {
      logs.value = data.logs
      // 有新日志且开启自动滚动 → 滚到底
      if (autoScroll.value && logs.value.length > lastFetchLen) {
        await nextTick()
        scrollToBottom()
      }
      lastFetchLen = logs.value.length
    }
  } catch {
    // 后端没启动时静默忽略
  }
}

function scrollToBottom() {
  if (scrollRef.value) {
    scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  }
}

async function onClear() {
  try {
    await fetch('/api/work-logs/clear', { method: 'POST' })
    logs.value = []
    lastFetchLen = 0
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchLogs()
  pollTimer = setInterval(fetchLogs, 500)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// 用户手动滚动后关闭自动滚动，滚到底部时重新开启
watch(autoScroll, (v) => {
  if (v) scrollToBottom()
})
</script>

<style scoped>
.work-log-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
}

/* 工具栏 */
.log-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: #fafbfc;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}
.log-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.log-count {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 日志列表 */
.log-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 12px;
  font-family: ui-monospace, Consolas, "Courier New", monospace;
  font-size: 11px;
  line-height: 1.5;
}

.empty-hint {
  color: #c0c4cc;
  text-align: center;
  padding: 40px 0;
  font-size: 13px;
}

.log-line {
  padding: 1px 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-ts {
  color: #a0a0a0;
  margin-right: 6px;
}
.log-level {
  display: inline-block;
  min-width: 56px;
  font-weight: 600;
}
.log-msg {
  color: inherit;
}

/* 三种级别颜色（对齐 Flet 原版） */
.level-info { color: #606266; }
.level-info .log-level { color: #909399; }

.level-warn { color: #b88230; font-weight: 600; }
.level-warn .log-level { color: #cf6e00; }

.level-error { color: #c0392b; font-weight: 700; }
.level-error .log-level { color: #e74c3c; }
</style>
