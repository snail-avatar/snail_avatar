<!--
ParamEdit：可编辑单元格
点击显示输入框，失焦/回车保存，ESC 取消
-->
<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string
  dbKey?: string
  isWarn?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: string]
  save: [val: string]
}>()

const editing = ref(false)
const inputVal = ref(props.modelValue)

function startEdit() {
  if (props.disabled) return
  inputVal.value = props.modelValue
  editing.value = true
}

function commit() {
  editing.value = false
  emit('save', inputVal.value)
}

function cancel() {
  editing.value = false
}
</script>

<template>
  <span
    class="param-cell"
    :class="{ 'is-warn': isWarn, 'is-edit': editing, 'is-disabled': disabled }"
    @click="!editing && startEdit()"
  >
    <el-input
      v-if="editing"
      v-model="inputVal"
      size="small"
      style="width: 120px"
      @blur="commit"
      @keyup.enter="commit"
      @keyup.esc="cancel"
      @click.stop
    />
    <span v-else class="param-text">{{ modelValue || '-' }}</span>
  </span>
</template>

<style scoped>
.param-cell {
  display: inline-block;
  cursor: text;
  padding: 2px 6px;
  border-radius: 3px;
  min-height: 24px;
  line-height: 24px;
  user-select: text;
}
.param-cell:hover:not(.is-disabled) { background: #ecf5ff; }
.param-cell.is-edit { padding: 0; }
.param-cell.is-warn .param-text { color: #f56c6c; font-weight: 600; }
.param-cell.is-disabled { cursor: default; }
</style>
