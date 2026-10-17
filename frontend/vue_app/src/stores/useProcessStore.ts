// @Time    : 2026
// @Author  : 李涛
// @File    : useProcessStore.ts
// @Desc    : useProcessStore
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// =========================================================================
// 类型定义
// =========================================================================

/** 车型下拉项 */
export interface Vehicle {
  name: string
  instance_key: string
  suffix?: string
}

/** Controller._serialize_states 输出的节点结构 */
export interface ControllerStateNode {
  step_id: string
  step_name: string
  step_type: string           // 'init' | 'llm' | 'agent' | 'process' | 'condition' | 'loop'
  status: 'pending' | 'running' | 'completed' | 'error' | 'skipped'
  current_loop_item?: string
  completed_loop_items?: string[]
  loop_items?: string[]
  sub_states?: ControllerStateNode[]
}

/** SSE 事件（来自后端 stream） */
export interface ProcessEvent {
  type: 'connected' | 'step_progress' | 'heartbeat' | 'done' | 'error' | 'status_change'
  step_id?: string
  step_name?: string
  loop_item?: string
  progress?: number
  timestamp?: string
  status?: string
  summary?: any
  message?: string
  new_status?: string           // status_change 事件专用: "paused" | "running"
  // ===== 新增：后端 states_tree =====
  states_tree?: ControllerStateNode[]
  completed_loop_items?: string[]
  remaining_loop_items?: string[]
  current_loop_item?: string
}

// =========================================================================
// Store
// =========================================================================

export const useProcessStore = defineStore('process', () => {
  /** 当前选中的 instance_key */
  const instanceKey = ref<string>('')
  /** 车型列表 */
  const vehicles = ref<Vehicle[]>([])
  /** 所有 SSE 事件（时间顺序，用于调试） */
  const events = ref<ProcessEvent[]>([])

  // ===== 核心：直接来自 SSE 的完整状态树 =====
  /** Controller._states 的序列化版本，每次 step_progress 推送新快照 */
  const statesTree = ref<ControllerStateNode[]>([])

  /** 是否正在流式接收 */
  const isStreaming = ref(false)
  /** 流程最终状态 */
  const finalStatus = ref<string | null>(null)
  /** 最终总结文本（FINAL_SUMMARY） */
  const finalSummary = ref<string>('')
  /** 整体进度 0-1 */
  const overallProgress = ref(0)
  /** 错误信息 */
  const errorMessage = ref<string>('')
  /** 是否处于暂停状态（status_change 事件驱动） */
  const isPaused = ref(false)

  // ---------- Sheet / 结果数据（5-tab 面板用） ----------
  const stepResults = ref<any[]>([])
  const productDef = ref<any[]>([])
  const sandboxData = ref<any>(null)
  const vtsSheet = ref<any>(null)
  const sstsSheet = ref<any>(null)

  // ---------- 计算属性（全部从 statesTree 取，不再自行推导） ----------

  /** 过滤掉 ProcessParser bug 产生的空 loop 节点 + 保留真正有 sub_states 的顶层节点 */
  const outerStepList = computed(() => {
    if (!statesTree.value.length) return []
    // 只保留真正有意义的顶层节点：
    //  - 普通 step（没有 sub_states 或 loop_items）
    //  - loop step（有 sub_states 或 loop_items）
    return statesTree.value.filter((node, idx, arr) => {
      // 跳过纯 synthetic loop 空壳（ProcessParser bug 产生的重复节点）
      if (node.step_type === 'loop') {
        // 如果下一个也是 loop 且当前没有 sub_states，说明是空壳
        if (idx + 1 < arr.length && arr[idx + 1].step_type === 'loop' && !node.sub_states?.length) {
          return false
        }
      }
      return true
    }).map(node => ({
      step_id: node.step_id,
      step_name: node.step_name,
      step_type: node.step_type,
      status: node.status,
    }))
  })

  /** 找到当前活跃的 loop 节点（step_type === 'loop' 的节点） */
  const currentLoopNode = computed(() => {
    if (!statesTree.value.length) return null
    // 先找 status 为 running 的
    let loopNode = statesTree.value.find(n =>
      n.step_type === 'loop' && n.status === 'running'
    )
    // 没有 running 的 → 找最后一个有 sub_states 的 loop（已完成或 pending）
    if (!loopNode) {
      const allLoops = statesTree.value.filter(n => n.step_type === 'loop' && n.sub_states?.length)
      loopNode = allLoops[allLoops.length - 1] || null
    }
    return loopNode
  })

  /** 所有 loop item 名称（从 currentLoopNode.loop_items 取） */
  const allLoopItems = computed(() => {
    return currentLoopNode.value?.loop_items || []
  })

  /** 已完成的 loop item 列表 */
  const completedLoopItems = computed(() => {
    return currentLoopNode.value?.completed_loop_items || []
  })

  /** 当前活跃的 loop item */
  const currentLoopItem = computed(() => {
    return currentLoopNode.value?.current_loop_item || ''
  })

  /** 当前 loop item 下的内层步骤列表（过滤掉 condition 节点） */
  const innerStepList = computed(() => {
    const subs = currentLoopNode.value?.sub_states
    if (!subs?.length) return []
    // 过滤掉 condition 节点（不直接显示，通过 pass/fail 分支动态体现）
    return subs
      .filter(s => s.step_type !== 'condition')
      .map(s => ({
        step_id: s.step_id,
        step_name: s.step_name,
        status: s.status,
      }))
  })

  // ---------- actions ----------

  function setVehicles(v: Vehicle[]) {
    vehicles.value = v
  }

  function setInstanceKey(ik: string) {
    instanceKey.value = ik
  }

  function reset() {
    // 只清执行痕迹，保留 Excel 静态参数数据（productDef / vtsSheet / sstsSheet）
    events.value = []
    statesTree.value = []
    finalStatus.value = null
    finalSummary.value = ''
    overallProgress.value = 0
    errorMessage.value = ''
    isStreaming.value = false
    isPaused.value = false
    stepResults.value = []
    sandboxData.value = null
  }

  function addEvent(ev: ProcessEvent) {
    events.value.push(ev)

    switch (ev.type) {
      case 'connected':
        isStreaming.value = true
        errorMessage.value = ''
        break

      case 'step_progress': {
        // ===== 核心改动：直接替换 statesTree，不再自行推导状态 =====
        if (ev.states_tree?.length) {
          statesTree.value = ev.states_tree
        }
        if (typeof ev.progress === 'number') {
          overallProgress.value = ev.progress
        }
        // ===== DEBUG: 前端 store 收到的 statesTree 摘要 =====
        const st = ev.states_tree || []
        const stTop = st.map((n: any) => `${n.step_id}[${n.status}]`)
        const loopNode = st.find((n: any) => n.step_type === 'loop')
        const subs = loopNode?.sub_states?.slice(0, 4).map((s: any) => `${s.step_id}[${s.status}]`) || []
        const loopItems = loopNode?.loop_items || []
        const done = ev.completed_loop_items || []
        const cur = ev.current_loop_item || ''
        // eslint-disable-next-line no-console
        console.log(`[DEBUG][Vue store] step_progress: top=${stTop} loop_subs=${subs} loop_items=${loopItems} done=${done} current=${cur}`)
        break
      }

      case 'heartbeat':
        break

      case 'done': {
        isStreaming.value = false
        finalStatus.value = ev.status || 'unknown'
        if (ev.summary?.summary) {
          finalSummary.value = String(ev.summary.summary)
        }
        overallProgress.value = 1.0
        break
      }

      case 'error': {
        isStreaming.value = false
        errorMessage.value = ev.message || '未知错误'
        finalStatus.value = 'error'
        break
      }

      case 'status_change': {
        const ns = ev.new_status
        if (ns === 'paused') {
          isPaused.value = true
        } else if (ns === 'running') {
          isPaused.value = false
        }
        break
      }
    }
  }

  return {
    instanceKey,
    vehicles,
    events,
    statesTree,
    isStreaming,
    isPaused,
    finalStatus,
    finalSummary,
    overallProgress,
    errorMessage,
    stepResults,
    productDef,
    sandboxData,
    vtsSheet,
    sstsSheet,
    // computed
    outerStepList,
    currentLoopNode,
    allLoopItems,
    completedLoopItems,
    currentLoopItem,
    innerStepList,
    // actions
    setVehicles,
    setInstanceKey,
    reset,
    addEvent,
  }
})
