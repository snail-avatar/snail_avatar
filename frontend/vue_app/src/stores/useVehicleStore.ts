// @Time    : 2026
// @Author  : 李涛
// @File    : useVehicleStore.ts
// @Desc    : useVehicleStore
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/request'

export interface VehicleInfo {
  vehicle_suffix: string
  vehicle_name?: string
  energy_type?: string
}

export const useVehicleStore = defineStore('vehicle', () => {
  const vehicles = ref<VehicleInfo[]>([])
  const currentVehicle = ref<VehicleInfo | null>(null)
  const vtsParams = ref<any[]>([])
  const sstsParams = ref<any[]>([])

  async function fetchVehicles() {
    try {
      const res: any = await api.get('/vehicles')
      vehicles.value = res.vehicles || []
      if (vehicles.value.length > 0 && !currentVehicle.value) {
        currentVehicle.value = vehicles.value[0]
      }
    } catch (e) {
      console.error('fetchVehicles failed', e)
    }
  }

  async function fetchParams(suffix: string, paramType: 'vts' | 'ssts') {
    try {
      const res: any = await api.get(`/vehicles/${suffix}/${paramType}`)
      if (paramType === 'vts') vtsParams.value = res.categories || []
      else sstsParams.value = res.categories || []
    } catch (e) {
      console.error(`fetch${paramType.toUpperCase()} failed`, e)
    }
  }

  return { vehicles, currentVehicle, vtsParams, sstsParams, fetchVehicles, fetchParams }
})
