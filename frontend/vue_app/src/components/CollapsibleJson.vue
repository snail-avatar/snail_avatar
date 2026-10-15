// @Time    : 2026
// @Author  : 李涛
// @File    : CollapsibleJson.vue
// @Desc    : CollapsibleJson
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  CollapsibleJson — 可折叠 JSON 树形展示组件

  功能：递归渲染任意 JSON 结构，每个 dict/list 在最左侧有折叠/展开按钮。
  用法：<CollapsibleJson :data="someJson" />

  组件特点：
  - 默认全部展开
  - 父节点展开时，所有子级同时展开（通过 forceExpand prop 向下传递）
  - 每一行最左侧显示 ▶/▼ 折叠按钮
  - 原始值（string/number/boolean/null）直接显示
  - 长字符串 hover 看完整值
-->
<template>
  <div class="cj-root">
    <template v-if="isContainer">
      <!-- 容器（dict/array） -->
      <div class="cj-line" :class="{ 'cj-expanded': expanded }">
        <span class="cj-toggle" @click.self="toggle">{{ expanded ? '▼' : '▶' }}</span>
        <span class="cj-brace">{{ isArray ? '[' : '{' }}</span>
        <span v-if="!expanded" class="cj-summary">
          {{ isArray ? `Array(${size})` : `Object(${size})` }}
        </span>
      </div>
      <div v-if="expanded" class="cj-children">
        <template v-if="isArray">
          <div v-for="(item, idx) in data" :key="idx" class="cj-child">
            <div v-if="isContainerValue(item)" class="cj-line">
              <span class="cj-key cj-idx">[{{ idx }}]</span>
              <CollapsibleJson :data="item" :depth="depth + 1" :force-expand="forceExpand || expanded" />
            </div>
            <div v-else class="cj-line cj-leaf">
              <span class="cj-key cj-idx">[{{ idx }}]</span>
              <span class="cj-val" :class="valueClass(item)" :title="strTruncate(item)">{{ formatLeaf(item) }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="(item, k) in data" :key="String(k)" class="cj-child">
            <div v-if="isContainerValue(item)">
              <div class="cj-line cj-key-line">
                <span class="cj-toggle" @click="toggleObjChild(String(k))">
                  {{ childOpen[String(k)] ? '▼' : '▶' }}
                </span>
                <span class="cj-key">"{{ k }}"</span>
                <span class="cj-sep">:</span>
                <span class="cj-brace">{{ Array.isArray(item) ? '[' : '{' }}</span>
                <span v-if="!childOpen[String(k)]" class="cj-summary">
                  {{ Array.isArray(item) ? `Array(${item.length})` : `Object(${Object.keys(item).length})` }}
                </span>
              </div>
              <div v-if="childOpen[String(k)]" class="cj-children">
                <CollapsibleJson :data="item" :depth="depth + 1" :force-expand="forceExpand || expanded" />
              </div>
            </div>
            <div v-else class="cj-line cj-leaf">
              <span class="cj-key">"{{ k }}"</span>
              <span class="cj-sep">:</span>
              <span class="cj-val" :class="valueClass(item)" :title="strTruncate(item)">{{ formatLeaf(item) }}</span>
            </div>
          </div>
        </template>
      </div>
      <div class="cj-line"><span class="cj-brace">{{ isArray ? ']' : '}' }}</span></div>
    </template>
    <template v-else>
      <div class="cj-line cj-leaf">
        <span class="cj-val" :class="valueClass(data)" :title="strTruncate(data)">{{ formatLeaf(data) }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'

const props = defineProps<{
  data: any
  depth?: number
  forceExpand?: boolean  // 父级展开时传递，强制当前节点展开并传递给所有后代
}>()

const depth = computed(() => props.depth ?? 0)

const isArray = computed(() => Array.isArray(props.data))
const isObject = computed(() => props.data !== null && typeof props.data === 'object' && !Array.isArray(props.data))
const isContainer = computed(() => isArray.value || isObject.value)

const isContainerValue = (v: any): boolean => v !== null && typeof v === 'object'
const size = computed(() => isArray.value ? props.data.length : Object.keys(props.data ?? {}).length)

// ===== 自身展开状态 =====
// 默认全展开；forceExpand 为 true 时强制展开
const expanded = ref(true)
function toggle() { expanded.value = !expanded.value }

// ===== dict 子节点展开状态 =====
// forceExpand 为 true 时子节点也全部展开
const childOpen = reactive<Record<string, boolean>>({})
function toggleObjChild(key: string) {
  childOpen[key] = !childOpen[key]
}

// 初始化所有子节点为展开
if (isObject.value) {
  for (const k of Object.keys(props.data)) {
    if (isContainerValue(props.data[k])) {
      childOpen[k] = true
    }
  }
}

// forceExpand 变化时，强制所有子节点展开
watch(() => props.forceExpand, (v) => {
  if (v) {
    expanded.value = true
    for (const k of Object.keys(childOpen)) childOpen[k] = true
  }
})

function formatLeaf(v: any): string {
  if (v === null) return 'null'
  if (v === undefined) return 'undefined'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'string') {
    const escaped = v.replace(/"/g, '\\"').replace(/\n/g, '\\n')
    return `"${escaped}"`
  }
  return String(v)
}

function valueClass(v: any): string {
  if (v === null || v === undefined) return 'cj-null'
  if (typeof v === 'boolean') return 'cj-bool'
  if (typeof v === 'number') return 'cj-num'
  if (typeof v === 'string') return 'cj-str'
  return ''
}

function strTruncate(v: any): string {
  if (typeof v === 'string' && v.length > 80) return v
  return ''
}
</script>

<style scoped>
.cj-root { font-family: ui-monospace, Consolas, monospace; font-size: 11px; line-height: 1.5; color: #303133; }
.cj-line { display: flex; align-items: flex-start; gap: 4px; white-space: nowrap; }
.cj-toggle { cursor: pointer; color: #409eff; user-select: none; width: 14px; text-align: center; flex-shrink: 0; }
.cj-toggle:hover { color: #f56c6c; }
.cj-brace { color: #606266; font-weight: 700; }
.cj-children { padding-left: 14px; border-left: 1px dashed #dcdfe6; margin-left: 2px; }
.cj-child { display: block; }
.cj-key { color: #7c3aed; }
.cj-key.cj-idx { color: #606266; font-style: italic; }
.cj-sep { color: #606266; }
.cj-val { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.cj-null { color: #909399; font-style: italic; }
.cj-bool { color: #1a3a8a; font-weight: 700; }
.cj-num { color: #b45309; }
.cj-str { color: #166534; }
.cj-summary { color: #909399; font-style: italic; font-size: 10px; }
.cj-leaf { padding-left: 0; }
</style>
