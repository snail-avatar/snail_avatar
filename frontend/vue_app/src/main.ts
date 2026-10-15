// @Time    : 2026
// @Author  : 李涛
// @File    : main.ts
// @Desc    : main
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
// 使用 markdown-it-katex 自带的 KaTeX CSS，因为它用自己 bundled 的 KaTeX 生成 HTML
// 顶层 katex 包是新版，类名从 .sizing 改成了 .katex-sizing，与生成的 HTML 不匹配
import 'markdown-it-katex/node_modules/katex/dist/katex.min.css'

import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
