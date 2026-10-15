// @Time    : 2026
// @Author  : 李涛
// @File    : AppHeader.vue
// @Desc    : AppHeader
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  AppHeader — 顶部标题栏（Logo + 工具栏 + 模式切换）

  新增：真正实现「打开」「保存」按钮：
    打开 → 隐藏的 <input type="file" accept=".xlsx,.xls"> → multipart 上传 → 后端重建 MemoryDatabase
    保存 → POST /api/files/save → memory_db.save_memorycore_to_excel() → 返回输出路径
    状态 → 显示当前加载的 Excel 文件名（没加载时显示「未加载」）

  数据源：GET /api/files/status（启动时 + 打开/保存操作后刷新）
-->
<template>
  <div class="app-header">
    <!-- Logo + 标题 -->
    <div class="header-left">
      <img src="/icons/brand/logo.png" alt="logo" class="header-logo" />
      <span class="header-title">Snail Avatar</span>
      <span class="header-subtitle">新能源汽车性能开发助手</span>
    </div>

    <!-- 右侧：工具栏 + 模式切换 -->
    <div class="header-right">
      <!-- 工具栏按钮（沿用 Flet 原版图标）-->
      <img
        src="/icons/toolbar/open.png"
        class="toolbar-btn"
        :title="status.loaded ? `重新打开 Excel（当前：${status.file_name}）` : '打开 Excel'"
        @click="triggerOpen"
      />
      <img
        src="/icons/toolbar/save.png"
        class="toolbar-btn"
        :title="status.loaded ? '保存 memorycore 回 Excel' : '保存（请先打开 Excel）'"
        :class="{ disabled: !status.loaded }"
        @click="onSave"
      />

      <!-- 分隔 -->
      <div class="header-sep"></div>

      <!-- 模式切换（dev ↔ admin）-->
      <span class="mode-label">{{ isAdminMode ? '管理模式' : '开发模式' }}</span>
      <img
        :src="modeToggleIcon"
        class="toolbar-btn"
        :title="modeToggleTitle"
        @click="onToggleMode"
      />
    </div>

    <!-- 隐藏的文件选择框 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="onFileChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, reactive } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { inject } from 'vue'
import type { Ref } from 'vue'

// ========== 模式控制（MainLayout 注入）==========
const isAdminMode = inject<Ref<boolean>>('isAdminMode')!
const toggleMode = inject<() => void>('toggleMode')!

const modeToggleIcon = computed(() => {
  return isAdminMode.value ? '/icons/toolbar/mode_dev.png' : '/icons/toolbar/mode_admin.png'
})
const modeToggleTitle = computed(() => {
  return isAdminMode.value ? '切换到开发模式' : '切换到管理模式'
})

// ========== Excel 加载状态 ==========
const status = reactive({
  ok: false,
  loaded: false,
  file_path: '',
  file_name: '',
  sheet_count: 0,
})

async function fetchStatus() {
  try {
    const r = await fetch('/api/files/status')
    const d = await r.json()
    Object.assign(status, d)
  } catch { /* 后端没启动时静默 */ }
}

// ========== 打开 Excel ==========
const fileInputRef = ref<HTMLInputElement | null>(null)

function triggerOpen() {
  fileInputRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const fd = new FormData()
  fd.append('file', file)

  try {
    ElMessage.info(`正在加载 ${file.name} ...`)
    const r = await fetch('/api/files/open', { method: 'POST', body: fd })
    const d = await r.json()
    if (d.ok) {
      Object.assign(status, {
        ok: true,
        loaded: true,
        file_path: d.file_path,
        file_name: d.file_name,
        sheet_count: d.sheet_count,
      })
      ElNotification({
        title: 'Excel 加载成功',
        message: `${d.file_name}（${d.sheet_count} 个 Sheet）`,
        type: 'success',
        duration: 2500,
      })
    } else {
      ElMessage.error(d.detail || '加载失败')
    }
  } catch (err: any) {
    ElMessage.error(`上传失败：${err.message}`)
  } finally {
    // 清空 input，方便下次选同一个文件也能触发 change
    input.value = ''
  }
}

// ========== 保存 Excel ==========
async function onSave() {
  if (!status.loaded) {
    ElMessage.warning('请先打开 Excel 文件')
    return
  }
  try {
    ElMessage.info('正在保存 memorycore ...')
    const r = await fetch('/api/files/save', { method: 'POST' })
    const d = await r.json()
    if (d.ok) {
      ElNotification({
        title: '保存成功',
        message: d.file_path,
        type: 'success',
        duration: 3000,
      })
    } else {
      ElMessage.error(d.error || '保存失败')
    }
  } catch (err: any) {
    ElMessage.error(`保存失败：${err.message}`)
  }
}

// ========== 模式切换 ==========
function onToggleMode() {
  toggleMode()
  ElMessage.success(`已切换到 ${isAdminMode.value ? '管理模式' : '开发模式'}`)
}

// ========== 启动时查询状态 ==========
onMounted(() => { fetchStatus() })
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  height: 100%;
}

/* 左侧 Logo + 标题 */
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
}
.header-title {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}
.header-subtitle {
  font-size: 12px;
  color: #909399;
}
/* 右侧工具栏 */
.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.toolbar-btn {
  width: 28px;
  height: 28px;
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  object-fit: contain;
}
.toolbar-btn:hover:not(.disabled) {
  background: #f0f2f5;
}
.toolbar-btn.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.header-sep {
  width: 1px;
  height: 20px;
  background: #e4e7ed;
  margin: 0 4px;
}
.mode-label {
  font-size: 12px;
  color: #606266;
  margin-right: 4px;
}
</style>
