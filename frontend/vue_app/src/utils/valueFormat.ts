/**
 * 数值格式化工具
 *
 * 跨页面共享的 VTS/SSTS 数值显示逻辑。
 * 所有"当前值 / 目标值"等浮点数显示都走这里，
 * 保证 a301 VtsSstsPage、a101 TargetDefinitionPage、SstsVtsPanel 三处一致。
 *
 * 策略：round 到 3 位小数 + 去掉末尾多余的 0
 *   1096.6669 → "1096.667"
 *   0.32      → "0.32"
 *   7.5       → "7.5"
 *   2346.0    → "2346"
 */

/** 清理 float64 精度噪声，round 到 3 位小数，并去掉末尾多余的 0 */
export function formatDisplayValue(v: any): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'number') {
    if (!isFinite(v)) return '-'
    // 两步处理：先消 IEEE754 尾巴，再 round 到 3 位小数
    const cleaned = Math.round(v * 1e10) / 1e10
    const rounded = Math.round(cleaned * 1000) / 1000
    // 用 toFixed(3) 然后去末尾 0（和后端 round(3) 对齐）
    return parseFloat(rounded.toFixed(3)).toString()
  }
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}

/**
 * 达标状态行高亮判断
 *
 * 三态区分：
 *   flag === 0   → 真正不达标（计算了且判定不达标） → 返回 true 标红
 *   flag === 1   → 达标 → 返回 false 不高亮
 *   null/undefined/NaN/无判据 → 未计算/无数据 → 返回 false 不高亮
 *
 * 之前用 Number(passFlag) === 0 会把 null 误转成 0 标红。
 */
export function isNotPassed(passFlag: any): boolean {
  if (passFlag === undefined || passFlag === null) return false
  if (typeof passFlag === 'number' && !isFinite(passFlag)) return false
  return Number(passFlag) === 0
}
