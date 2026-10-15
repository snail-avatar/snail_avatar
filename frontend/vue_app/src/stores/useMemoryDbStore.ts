// @Time    : 2026
// @Author  : 李涛
// @File    : useMemoryDbStore.ts
// @Desc    : useMemoryDbStore
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

/**
 * 全局 MemoryDatabase 状态 Store
 *
 * 职责：
 *   1. 轮询 /api/files/status → 检测 Excel 文件是否变化（file_name 变了 = 换了文件）
 *   2. 轮询 /api/memory-dbs → 缓存完整的 vehsuffix / memorycore / sheets 等
 *   3. 所有页面（WorkflowPage / VtsSstsPage / MemoryDbsPage）统一 watch 此 store
 *      的 fileChangeVersion，一旦变化就刷新各自的本地数据
 *
 * 为什么用轮询而不是 WebSocket/SSE：
 *   - Excel 打开频率低（用户一天可能只换 1-2 次文件）
 *   - 后端没有 WebSocket 基础设施
 *   - 2 秒轮询 /api/files/status 非常轻量（< 100B 响应）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useMemoryDbStore = defineStore('memoryDb', () => {
  // ============ 状态 ============
  const loaded = ref(false)
  const fileName = ref('')
  const filePath = ref('')
  const fileChangeVersion = ref(0)  // 每次换文件 +1，所有页面 watch 这个刷新

  // memory-dbs 完整数据（轮询缓存）
  const vehsuffix = ref<any[]>([])
  const memorycore = ref<Record<string, any>>({})
  const sheets = ref<Record<string, any>>({})
  const memoryCoreKey = ref('')
  const ecoCycle = ref<any>(null)
  const interData = ref<any>(null)

  let _statusTimer: ReturnType<typeof setInterval> | null = null
  let _dbsTimer: ReturnType<typeof setInterval> | null = null

  // ============ 轮询 ============
  async function pollStatus() {
    try {
      const r = await fetch('/api/files/status')
      const d = await r.json()
      if (d?.ok) {
        const wasLoaded = loaded.value
        const oldName = fileName.value
        loaded.value = !!d.loaded
        fileName.value = d.file_name || ''
        filePath.value = d.file_path || ''

        // 检测文件变化：loaded 从 false→true，或 file_name 变了
        if ((!wasLoaded && loaded.value) || (loaded.value && fileName.value !== oldName && oldName !== '')) {
          fileChangeVersion.value++
        } else if (loaded.value && oldName === '' && fileName.value !== '') {
          // 首次加载
          fileChangeVersion.value++
        }
      }
    } catch (e) {
      // 后端挂了没关系，下次轮询再说
    }
  }

  async function pollMemoryDbs() {
    if (!loaded.value) return
    try {
      const r = await fetch('/api/memory-dbs')
      const d = await r.json()
      if (d?.ok) {
        vehsuffix.value = d.vehsuffix || []
        memorycore.value = d.memorycore || {}
        sheets.value = d.sheets || {}
        ecoCycle.value = d.ecocycle || null
        interData.value = d.inter_data || null
      }
    } catch (e) {
      // 静默失败
    }
  }

  function startPolling() {
    if (_statusTimer) return
    pollStatus()      // 立即跑一次
    // 文件状态检测：5 秒足够（Excel 文件一天换不了几次）
    _statusTimer = setInterval(pollStatus, 5000)
    // memory-dbs 全量数据缓存：30 秒
    _dbsTimer = setInterval(pollMemoryDbs, 30000)
  }

  function stopPolling() {
    if (_statusTimer) { clearInterval(_statusTimer); _statusTimer = null }
    if (_dbsTimer) { clearInterval(_dbsTimer); _dbsTimer = null }
  }

  // ============ computed ============
  const vehicleNames = computed(() =>
    vehsuffix.value.map((v: any) => ({
      name: v['车型'] || v['车型名称'] || '',
      suffix: v['车型后缀'] || '',
      label: v['车型'] && v['车型后缀']
        ? `${v['车型']}__${v['车型后缀']}`
        : (v['车型后缀'] || v['车型'] || ''),
    })).filter((v: any) => v.suffix || v.name)
  )

  return {
    // 状态
    loaded, fileName, filePath, fileChangeVersion,
    vehsuffix, memorycore, sheets, ecoCycle, interData,
    // 方法
    startPolling, stopPolling,
    pollStatus, pollMemoryDbs,
    // computed
    vehicleNames,
  }
})
