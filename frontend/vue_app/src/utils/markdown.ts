// @Time    : 2026
// @Author  : 李涛
// @File    : markdown.ts
// @Desc    : markdown
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

/**
 * Markdown 渲染工具 — markdown-it + DOMPurify 安全消毒 + KaTeX 公式渲染
 *
 * KaTeX 渲染:
 *   - 行内公式: $...$
 *   - 块级公式: $$...$$
 *   - 需要 katex/dist/katex.min.css 在 main.ts 中引入
 */
import MarkdownIt from 'markdown-it'
import katexPlugin from 'markdown-it-katex'
import DOMPurify from 'dompurify'

const md = new MarkdownIt({
  html: false,         // 禁用原生 HTML（防 XSS）
  linkify: true,       // 自动链接
  breaks: true,        // 单行换行 → <br>
  typographer: true,
})

// 接入 KaTeX 数学公式渲染
// 注意: markdown-it-katex 会把 options 直接传给 katex.renderToString()，
// 所以 KaTeX 参数（throwOnError、output）必须放在顶层，不能嵌套
// output: 'html' — 只输出 HTML（不要 MathML），避免 DOMPurify 破坏 MathML 字号
md.use(katexPlugin, {
  throwOnError: false,
  output: 'html',
})

/** KaTeX 生成的 HTML 标签 + 属性白名单（供 DOMPurify 放行） */
const KATEX_ADD_TAGS = [
  'annotation', 'semantics',
  'mrow', 'mo', 'mi', 'mn', 'mtext', 'mspace',
  'mpadded', 'mphantom', 'mfenced',
  'mfrac', 'msqrt', 'mroot', 'none', 'mprescripts',
  'munder', 'munderover', 'mover', 'moverunder',
  'mstyle', 'menclose', 'merror', 'moperator',
  'msubsup', 'msub', 'msup', 'mmultiscripts',
  'mtable', 'mlabeledtr', 'mtr', 'mtd',
]
const KATEX_ADD_ATTR = [
  'encoding', 'mathcolor', 'mathbackground',
  'displaystyle', 'scriptlevel', 'accent', 'lspace', 'rspace',
  'width', 'height', 'depth', 'maxsize', 'minsize', 'stretch',
  'symmetric', 'largeop', 'movablelimits', 'prefix', 'standalone',
]

/** Markdown → 安全 HTML */
export function renderMarkdown(src: string): string {
  if (!src) return ''
  // 清理后端图片占位符（图片已在 bubble.images 独立渲染，占位符不显示）
  // 格式: [IMAGE:uuid]
  const cleanedSrc = src.replace(/\[IMAGE:[a-fA-F0-9-]+\]/g, '')
  const rawHtml = md.render(cleanedSrc)
  return DOMPurify.sanitize(rawHtml, {
    ADD_ATTR: ['target', ...KATEX_ADD_ATTR],
    ADD_TAGS: ['iframe', ...KATEX_ADD_TAGS],
  })
}
