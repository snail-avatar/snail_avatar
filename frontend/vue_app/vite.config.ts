// @Time    : 2026
// @Author  : 李涛
// @File    : vite.config.ts
// @Desc    : vite.config
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0', // 监听所有网络接口，允许其他设备通过局域网 IP 访问
    proxy: {
      // 开发环境把 /api 转发到 FastAPI 后端
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
