// @Time    : 2026
// @Author  : 李涛
// @File    : MainLayout.vue
// @Desc    : MainLayout
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <el-container class="main-layout">
    <!-- ========== 顶部工具栏 ========== -->
    <el-header class="layout-header" height="56px">
      <AppHeader />
    </el-header>

    <!-- ========== 三栏水平主区 ========== -->
    <div ref="rowRef" class="main-row">
      <!-- 左栏：导航（宽度可拖拽） -->
      <div
        v-show="!isAdminMode"
        class="layout-aside"
        :style="{ width: sidebarWidth + 'px' }"
      >
        <AppSidebar />
      </div>

      <!-- 左-中 拖拽分割条 -->
      <div
        v-show="!isAdminMode"
        class="resizer"
        @mousedown="(e) => startDrag(e, 'left')"
      ></div>

      <!-- 中栏：AI 聊天（flex:1 自动伸缩） -->
      <div class="layout-chat">
        <ChatPanel />
      </div>

      <!-- 中-右 拖拽分割条 -->
      <div
        v-show="!isAdminMode"
        class="resizer"
        @mousedown="(e) => startDrag(e, 'right')"
      ></div>

      <!-- 右栏：业务面板（宽度可拖拽） -->
      <div
        v-show="!isAdminMode"
        class="layout-right-panel"
        :style="{ width: rightPanelWidth + 'px' }"
      >
        <!-- 统一页面标题栏（图标与左侧按钮一致） -->
        <div class="right-panel-header">
          <img v-if="route.meta.icon" :src="route.meta.icon" class="page-icon" alt="" />
          <span class="page-title">{{ route.meta.title }}</span>
          <div class="header-right-extra">
            <ExtraControls />
          </div>
        </div>
        <div class="right-panel-body">
          <router-view />
        </div>
      </div>
    </div>
  </el-container>
</template>

<script setup lang="ts">
import { ref, provide, onMounted, onBeforeUnmount, reactive, defineComponent, h } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import ChatPanel from './ChatPanel.vue'

const route = useRoute()

// ========= 持久化宽度（localStorage） =========
const LS_SIDEBAR = 'snail_sidebar_w'
const LS_RIGHT = 'snail_right_w'
const DEFAULT_SIDEBAR = 180
const DEFAULT_RIGHT = 480
const MIN_SIDEBAR = 120
const MIN_RIGHT = 280
const MIN_CHAT = 320

const rowRef = ref<HTMLElement | null>(null)
const sidebarWidth = ref<number>(
  Number(localStorage.getItem(LS_SIDEBAR)) || DEFAULT_SIDEBAR
)
const rightPanelWidth = ref<number>(
  Number(localStorage.getItem(LS_RIGHT)) || DEFAULT_RIGHT
)

// ========= dev/admin 模式 =========
const isAdminMode = ref(false)
provide('isAdminMode', isAdminMode)
function toggleMode() {
  isAdminMode.value = !isAdminMode.value
}
provide('toggleMode', toggleMode)

// ========= 右栏页面标题栏右侧动态控件 =========
// 子页面（如 WorkflowPage）mounted 时注册一个渲染函数，
// 返回 VNode 数组，卸载时清空
const headerExtra = reactive({
  factory: null as null | (() => any)
})
provide('rightPanelHeaderExtra', headerExtra)

// 动态组件：渲染子页面注册的控件（无注册则渲染 null）
const ExtraControls = defineComponent({
  name: 'ExtraControls',
  setup() {
    return () => headerExtra.factory ? headerExtra.factory() : null
  }
})

// ========= 拖拽分割条 =========
let dragSide: 'left' | 'right' | null = null
let startX = 0
let startWidth = 0

function startDrag(e: MouseEvent, side: 'left' | 'right') {
  e.preventDefault()
  dragSide = side
  startX = e.clientX
  startWidth = side === 'left' ? sidebarWidth.value : rightPanelWidth.value

  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onDrag(e: MouseEvent) {
  if (!dragSide || !rowRef.value) return
  const rowRect = rowRef.value.getBoundingClientRect()
  const dx = e.clientX - startX

  if (dragSide === 'left') {
    // 左栏：鼠标右移 → 左栏变宽 → 中栏被挤
    let w = startWidth + dx
    // 限制：最小左栏 120，最大不能让中栏 < MIN_CHAT
    const maxW = rowRect.width - rightPanelWidth.value - MIN_CHAT - 8
    w = Math.max(MIN_SIDEBAR, Math.min(w, maxW))
    sidebarWidth.value = w
  } else {
    // 右栏：鼠标左移 → 右栏变宽
    let w = startWidth - dx
    const maxW = rowRect.width - sidebarWidth.value - MIN_CHAT - 8
    w = Math.max(MIN_RIGHT, Math.min(w, maxW))
    rightPanelWidth.value = w
  }
}

function stopDrag() {
  dragSide = null
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  // 持久化
  localStorage.setItem(LS_SIDEBAR, String(sidebarWidth.value))
  localStorage.setItem(LS_RIGHT, String(rightPanelWidth.value))
}

onMounted(() => {
  window.addEventListener('mouseup', stopDrag)
})
onBeforeUnmount(() => {
  window.removeEventListener('mouseup', stopDrag)
})
</script>

<style scoped>
.main-layout {
  height: 100vh;
  overflow: hidden;
}
.layout-header {
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
  display: flex;
  align-items: center;
  padding: 0 16px;
}

/* 三栏水平主区 */
.main-row {
  display: flex;
  height: calc(100vh - 56px);
  overflow: hidden;
}

/* 左栏导航 */
.layout-aside {
  flex-shrink: 0;
  background: #f5f7fa;
  overflow-y: auto;
}

/* 可拖拽分割条 */
.resizer {
  flex-shrink: 0;
  width: 5px;
  height: 100%;
  background: transparent;
  cursor: col-resize;
  position: relative;
  z-index: 10;
  transition: background 0.15s;
}
.resizer:hover,
.resizer:active {
  background: #409eff;
}
.resizer::after {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 1px;
  height: 100%;
  background: #e4e7ed;
  pointer-events: none;
}
.resizer:hover::after {
  background: #409eff;
  width: 2px;
}

/* 中栏聊天 — flex:1 自动伸缩 */
.layout-chat {
  flex: 1;
  min-width: 320px;
  height: 100%;
  padding: 0;
  overflow: hidden;
  background: #fff;
}

/* 右栏业务面板 — flex column：header（固定）+ body（滚动） */
.layout-right-panel {
  flex-shrink: 0;
  min-width: 280px;
  height: 100%;
  background: #fff;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* 统一页面标题栏 */
.right-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fafbfc;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}
.page-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}
.page-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* 页面标题栏右侧动态控件容器 */
.header-right-extra {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
}

/* 页面内容区 */
.right-panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
}
</style>
