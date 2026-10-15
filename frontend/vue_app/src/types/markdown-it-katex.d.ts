// @Time    : 2026
// @Author  : 李涛
// @File    : markdown-it-katex.d.ts
// @Desc    : markdown-it-katex.d
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

// markdown-it-katex 没有自带 TypeScript 声明，补一个最小类型
declare module 'markdown-it-katex' {
  import type MarkdownIt from 'markdown-it'
  const plugin: (md: MarkdownIt, options?: any) => void
  export default plugin
}
