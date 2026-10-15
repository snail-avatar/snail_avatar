// @Time    : 2026
// @Author  : 李涛
// @File    : useProcess.ts
// @Desc    : useProcess
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

/**
 * useProcess composable — 目标值定义流程的完整前端生命周期
 *
 * 职责：
 *   1. fetch vehicles（车型列表）+ steps（步骤拓扑）
 *   2. POST /api/process/run 启动流程
 *   3. EventSource 连接 /api/process/stream/{ik} 消费 SSE 进度事件
 *   4. 分发事件到 useProcessStore（更新步骤状态/整体进度/最终总结）
 *   5. 提供 stop / disconnect 方法
 *
 * 参考：useChat.ts 但有两个关键差异：
 *   - 超时 900s 空闲超时（每次 SSE 事件重置），不是绝对 5 分钟硬上限
 *   - 步骤拓扑预加载（/process/steps）驱动 UI 渲染
 */
import { ref, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useProcessStore, type ProcessEvent } from '../stores/useProcessStore'
import { api } from '../api/request'

// 绝对 URL 避开 Vite proxy SSE buffering（跟 useChat.ts 一致）
const SSE_BASE = 'http://localhost:8000/api'

/** SSE 空闲超时（秒）— 15 分钟无任何 SSE 事件才断开，避免绝对上限误杀长流程 */
const SSE_TIMEOUT_SECONDS = 900

export function useProcess() {
  const store = useProcessStore()
  let eventSource: EventSource | null = null
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null

  const isLoading = ref(false)
  const loadingMessage = ref('')

  // ==================================================================
  // SSE 空闲超时计时器（可复用，每次收到事件时重置）
  // ==================================================================
  const startTimeoutTimer = () => {
    if (timeoutTimer) clearTimeout(timeoutTimer)
    timeoutTimer = setTimeout(() => {
      if (store.isStreaming && !store.isPaused) {
        store.addEvent({
          type: 'error',
          message: `流程执行超时（${SSE_TIMEOUT_SECONDS}s 无响应），请检查后端或网络`,
        })
        store.isStreaming = false
        disconnect()
      }
    }, SSE_TIMEOUT_SECONDS * 1000)
  }

  // ==================================================================
  // 数据预加载（组件 mounted 时调用）
  // ==================================================================

  async function loadVehicles() {
    try {
      const resp: any = await api.get('/process/vehicles')
      store.setVehicles(resp.vehicles || [])
    } catch (e: any) {
      console.warn('[Process] vehicles 加载失败:', e?.message)
      store.setVehicles([])
    }
  }

  async function loadSteps() {
    // 新方案：步骤拓扑不再需要预加载，由后端每次推完整 states_tree
    // 保留这个函数只是为了兼容调用方（空函数即可）
    return
  }

  /**
   * 刷新后恢复状态：GET /process/{ik}/status → 恢复 store
   * 后端返回 is_running + controller_state.states_tree + final_result
   */
  async function loadStatus(instanceKey: string) {
    if (!instanceKey) return
    try {
      const resp: any = await api.get(`/process/${instanceKey}/status`)
      store.statesTree = resp?.controller_state?.states_tree || []
      store.isStreaming = !!resp?.is_running
      store.finalStatus = resp?.is_finished ? 'success' : null
      store.finalSummary = resp?.final_result || ''
    } catch (e: any) {
      console.warn('[Process] status 加载失败:', e?.message)
    }
  }

  // ==================================================================
  // 启动流程（POST /run → EventSource /stream）
  // ==================================================================

  async function startProcess(instanceKey: string, mode: string = 'ALL') {
    if (!instanceKey) return
    if (store.isStreaming) return

    store.reset()
    store.setInstanceKey(instanceKey)
    isLoading.value = true
    loadingMessage.value = '启动流程...'

    // 1. POST 启动
    try {
      await api.post('/process/run', { instance_key: instanceKey, mode })
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '启动失败'
      store.addEvent({ type: 'error', message: msg })
      isLoading.value = false
      loadingMessage.value = ''
      return
    }

    // 2. 连接 SSE
    loadingMessage.value = '流程执行中，接收实时进度...'
    connectSSE(instanceKey)
  }

  function connectSSE(instanceKey: string) {
    // 关闭旧连接
    disconnect()

    const url = `${SSE_BASE}/process/stream/${encodeURIComponent(instanceKey)}`
    eventSource = new EventSource(url)

    // 启动空闲超时计时器（onmessage 里会不断重置）
    startTimeoutTimer()

    // --- SSE 事件处理 ---
    // 新方案：后端每次推完整 states_tree，前端直接渲染，不再手动跟踪 step 状态
    // stepResults 通过防抖轮询 /results 实时拉取（后端不单独推 step_result 事件）

    let resultsDebounceTimer: ReturnType<typeof setTimeout> | null = null

    eventSource.onmessage = (event) => {
      try {
        // 每次收到 SSE 事件都重置空闲超时计时器
        startTimeoutTimer()

        const payload = JSON.parse(event.data) as ProcessEvent

        // 直接交 store — states_tree 已带完整状态
        store.addEvent(payload)

        // step_progress 事件 → 防抖拉所有 tab 数据
        if (payload.type === 'step_progress') {
          if (resultsDebounceTimer) clearTimeout(resultsDebounceTimer)
          resultsDebounceTimer = setTimeout(() => {
            loadStepResults(instanceKey)
            loadProductDef(instanceKey)
            loadSandbox(instanceKey)
            loadVehicleSheets(instanceKey)
          }, 300)
        }

        // done / error → 关闭连接
        if (payload.type === 'done' || payload.type === 'error') {
          isLoading.value = false
          loadingMessage.value = ''
          disconnect()
        }
      } catch (e) {
        console.warn('[Process SSE] JSON parse failed:', e)
      }
    }

    eventSource.onerror = (e) => {
      console.error('[Process SSE] error:', e)
      if (eventSource?.readyState === EventSource.CLOSED) {
        store.isStreaming = false
        isLoading.value = false
        loadingMessage.value = ''
      }
    }

    eventSource.onopen = () => {
      isLoading.value = false
      loadingMessage.value = ''
    }
  }

  // ==================================================================
  // 停止 / 关闭
  // ==================================================================

  async function stopProcess() {
    if (!store.instanceKey) return
    if (!store.isStreaming) return

    try {
      await api.post(`/process/${store.instanceKey}/stop`)
    } catch (e: any) {
      console.warn('[Process] stop 失败:', e?.message)
    }
    // 等待 done/error 事件或 3s 后强制关闭
    setTimeout(() => {
      disconnect()
      store.isStreaming = false
      store.isPaused = false
      loadingMessage.value = ''
      isLoading.value = false
    }, 3000)
  }

  // ==================================================================
  // 暂停 / 继续
  // ==================================================================

  async function pauseProcess() {
    if (!store.instanceKey) return
    if (!store.isStreaming || store.isPaused) return
    try {
      const resp: any = await api.post(`/process/${store.instanceKey}/pause`)
      store.isPaused = true
      // 暂停时同时暂停 SSE 超时计时器——用户可能长时间 review 中间数据
      if (timeoutTimer) {
        clearTimeout(timeoutTimer)
        timeoutTimer = null
      }
      console.log('[Process] paused:', resp?.message)
    } catch (e: any) {
      console.warn('[Process] pause 失败:', e?.message)
    }
  }

  async function resumeProcess() {
    if (!store.instanceKey) return
    if (!store.isPaused) return
    try {
      const resp: any = await api.post(`/process/${store.instanceKey}/resume`)
      store.isPaused = false
      // 继续时重新启动 SSE 空闲超时计时器
      if (store.isStreaming) {
        startTimeoutTimer()
      }
      console.log('[Process] resumed:', resp?.message)
    } catch (e: any) {
      console.warn('[Process] resume 失败:', e?.message)
    }
  }

  // ==================================================================
  // 单步执行 / 重复本步
  // ==================================================================

  async function stepProcess() {
    if (!store.instanceKey) return
    try {
      const resp: any = await api.post(`/process/${store.instanceKey}/step`)
      // 如果当前还没有 isStreaming（场景 B：未启动/已结束），立即开始接收 SSE
      if (!store.isStreaming) {
        connectSSE(store.instanceKey)
      }
      console.log('[Process] step:', resp?.message)
    } catch (e: any) {
      ElMessage.warning(e?.response?.data?.detail || e?.message || '单步执行失败')
    }
  }

  async function repeatProcess() {
    if (!store.instanceKey) return
    try {
      const resp: any = await api.post(`/process/${store.instanceKey}/repeat`)
      if (!store.isStreaming) {
        connectSSE(store.instanceKey)
      }
      console.log('[Process] repeat:', resp?.message)
    } catch (e: any) {
      ElMessage.warning(e?.response?.data?.detail || e?.message || '重复执行失败')
    }
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }
  }

  // ==================================================================
  // 结果 / Sheet 数据加载（用于 5-tab 面板在流程完成后填充）
  // ==================================================================

  async function loadStepResults(ik: string) {
    try {
      const resp: any = await api.get(`/process/${ik}/results`)
      store.stepResults = resp.step_results || []
    } catch (e) {
      console.warn('[Process] step results 加载失败:', e?.message)
    }
  }

  async function loadProductDef(ik: string) {
    try {
      const resp: any = await api.get(`/process/${ik}/sheet`, { params: { sheet_key: 'base_产品定义' } })
      store.productDef = resp.data || []
    } catch (e) {
      console.warn('[Process] 产品定义加载失败:', e?.message)
    }
  }

  async function loadSandbox(ik: string) {
    try {
      const resp: any = await api.get(`/process/${ik}/sandbox`)
      store.sandboxData = resp.data
    } catch (e) {
      console.warn('[Process] sandbox 加载失败:', e?.message)
    }
  }

  /**
   * 把后端 /process/{ik}/sheet 返回的 dict-of-dict 展平成 SstsVtsPanel 组件期望的格式
   *
   * 完全对齐 flet VehicleDataCollector.flatten_items + _append_multi_value_item 逻辑：
   *   - 多值参数：参数值 list 合并到同一行，输出 8 列完整字段
   *   - 简单参数：原样输出（计算条件类，直接有 db_key + 值）
   *   - 每行附带 cat1/cat2 一级/二级分类
   *
   * 后端 data 结构:
   *   { "空气动力学": { "正投影": {"名称": "...", "参数值": [{"名称":"当前值", "db_key":"...", "值":...}, ...]}, ... } }
   *
   * 输出:
   *   { categories: [{ name: "空气动力学", params: [完整行, ...] }], total }
   *   每行字段: cat1, cat2, 名称, 单位, 达标判据, 当前值, 当前值_db_key, 目标值, 目标值_db_key, 达标标识, 达标标识_db_key, ...
   */
  function _adaptVtsSheet(rawData: any): { categories: any[]; flatItems: any[]; total: number } {
    const categories: any[] = []
    const flatItems: any[] = []
    let total = 0
    if (!rawData || typeof rawData !== 'object') return { categories, flatItems, total }

    // 子项"名称"到字段前缀的映射（对齐 flet name_to_field_prefix）
    const nameToFieldPrefix: Record<string, string> = {
      "当前值": "当前值", "实际值": "当前值", "现在值": "当前值",
      "目标值": "目标值", "标准值": "目标值", "基准值": "目标值",
      "达标标识": "达标标识", "是否达标": "达标标识", "状态": "达标标识",
    }

    for (const [cat1, cat1Data] of Object.entries(rawData)) {
      if (!cat1Data || typeof cat1Data !== 'object') continue
      const params: any[] = []

      // cat1Data 可能直接是 list（扁平 sheet），或 dict（分二级分类）
      const subEntries = Array.isArray(cat1Data)
        ? [["<未分类>", cat1Data]]
        : Object.entries(cat1Data as object)

      for (const [cat2, items] of subEntries) {
        if (!Array.isArray(items)) continue
        for (const item of items) {
          if (!item || typeof item !== 'object') continue
          const entry: any = { ...item, cat1, cat2 }

          const paramValues = (item as any)["参数值"]
          if (Array.isArray(paramValues) && paramValues.length > 0) {
            // 多值参数：合并到 entry 同一行
            for (const p of paramValues) {
              if (!p || typeof p !== 'object') continue
              const subName = String((p as any)["名称"] || "").trim()
              const prefix = nameToFieldPrefix[subName]
              if (!prefix) continue
              entry[prefix] = (p as any)["值"]
              entry[`${prefix}_db_key`] = (p as any).db_key
            }
            entry["_has_multi_values"] = true
          } else if ((item as any).db_key) {
            // 简单参数（计算条件类）：直接有 db_key + 值
            entry["当前值"] = (item as any)["值"] ?? null
            entry["当前值_db_key"] = (item as any).db_key
          }

          params.push(entry)
          flatItems.push(entry)
          total++
        }
      }
      categories.push({ name: cat1, params })
    }
    return { categories, flatItems, total }
  }

  async function loadVehicleSheets(ik: string) {
    if (!ik) return
    try {
      // VTS/SSTS 改用 /process/{ik}/sheet 端点（旧 /vehicles/{suffix}/vts 过滤逻辑有错）
      const [vts, ssts]: any[] = await Promise.allSettled([
        api.get(`/process/${ik}/sheet`, { params: { sheet_key: 'target_vts' } }),
        api.get(`/process/${ik}/sheet`, { params: { sheet_key: 'target_ssts' } }),
      ])
      if (vts.status === 'fulfilled') {
        const raw = vts.value?.data || {}
        store.vtsSheet = _adaptVtsSheet(raw)
      }
      if (ssts.status === 'fulfilled') {
        const raw = ssts.value?.data || {}
        store.sstsSheet = _adaptVtsSheet(raw)
      }
    } catch (e) {
      console.warn('[Process] VTS/SSTS 加载失败:', e?.message)
    }
  }

  /** 流程完成后的批量加载（done 事件触发）。ik 用于所有 sheet API */
  async function loadAllAfterDone(ik: string, _suffix?: string) {
    await Promise.all([
      loadStepResults(ik),
      loadProductDef(ik),
      loadSandbox(ik),
      loadVehicleSheets(ik),
    ])
  }

  // 组件销毁时自动清理
  onBeforeUnmount(disconnect)

  return {
    store,
    isLoading,
    loadingMessage,
    loadVehicles,
    loadSteps,
    loadStatus,
    startProcess,
    stopProcess,
    pauseProcess,
    resumeProcess,
    stepProcess,
    repeatProcess,
    disconnect,
    loadStepResults,
    loadProductDef,
    loadSandbox,
    loadVehicleSheets,
    loadAllAfterDone,
  }
}
