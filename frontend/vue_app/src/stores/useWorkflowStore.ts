// @Time    : 2026
// @Author  : 李涛
// @File    : useWorkflowStore.ts
// @Desc    : useWorkflowStore
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useWorkflowStore = defineStore('workflow', () => {
  const vizData = ref<any[]>([])
  const isRunning = ref(false)

  return { vizData, isRunning }
})
