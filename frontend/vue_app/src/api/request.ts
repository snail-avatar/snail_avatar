// @Time    : 2026
// @Author  : 李涛
// @File    : request.ts
// @Desc    : request
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import axios from 'axios'

// 创建 axios 实例 — baseURL 用相对路径让开发环境经 Vite proxy 转发
export const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// 请求拦截器
api.interceptors.request.use((config) => {
  // 可在此添加 token 等认证信息
  return config
})

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('[API Error]', error?.config?.url, error?.message)
    return Promise.reject(error)
  }
)
