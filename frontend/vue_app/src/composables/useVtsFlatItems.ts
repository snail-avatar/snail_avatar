/**
 * VTS/SSTS sheet 拍平工具
 *
 * 一份拍平逻辑，服务两处调用方：
 *   - a301 VtsSstsPage：从 /api/memory-dbs 拿到嵌套 dict 后拍平
 *   - a101 useProcess._adaptVtsSheet：从 /process/{ik}/sheet 拿到嵌套 dict 后拍平
 *
 * 对齐后端 data_formatter.iter_flat_items 的语义：
 *   嵌套 dict { cat1: { cat2: [items] } } → 扁平行列表
 *   "参数值"多值结构 → 同行合并
 *   NAME_TO_FIELD_PREFIX 映射 → 统一字段名
 */

/** 子项"名称"到字段前缀的映射（对齐后端 data_formatter._NAME_TO_FIELD_PREFIX） */
const NAME_TO_FIELD_PREFIX: Record<string, string> = {
  '当前值': '当前值', '实际值': '当前值', '现在值': '当前值',
  '目标值': '目标值', '标准值': '目标值', '基准值': '目标值',
  '达标标识': '达标标识', '是否达标': '达标标识', '状态': '达标标识',
}

export interface VtsRow {
  cat1: string
  cat2: string
  名称?: string
  单位?: string
  达标判据?: string
  '当前值'?: any
  '当前值_db_key'?: string
  '目标值'?: any
  '目标值_db_key'?: string
  '达标标识'?: any
  '达标标识_db_key'?: string
  db_key?: string
  值?: any
  _has_multi_values?: boolean
  [key: string]: any
}

export interface CategoryGroup {
  name: string
  params: VtsRow[]
}

export interface FlattenResult {
  categories: CategoryGroup[]
  flatItems: VtsRow[]
  total: number
}

/**
 * 将 memorycore 的 VTS/SSTS 嵌套 sheet 数据拍平
 *
 * 输入（嵌套 dict）：
 *   { "空气动力学": { "正投影": [{ "名称": "...", "参数值": [...] }, ...] } }
 *   或 { "空气动力学": [{ "名称": "...", "参数值": [...] }, ...] }（扁平 sheet）
 *
 * 输出：
 *   { categories: [{ name, params }], flatItems: [...], total }
 */
export function flattenSheetData(rawData: any): FlattenResult {
  const categories: CategoryGroup[] = []
  const flatItems: VtsRow[] = []
  let total = 0

  if (!rawData || typeof rawData !== 'object') {
    return { categories, flatItems, total }
  }

  for (const [cat1, cat1Data] of Object.entries(rawData)) {
    if (!cat1Data || typeof cat1Data !== 'object') continue
    const params: VtsRow[] = []

    // cat1Data 可能直接是 list（扁平 sheet），或 dict（分二级分类）
    const subEntries = Array.isArray(cat1Data)
      ? [['<未分类>', cat1Data]]
      : Object.entries(cat1Data as object)

    for (const [cat2, items] of subEntries) {
      if (!Array.isArray(items)) continue
      for (const item of items) {
        if (!item || typeof item !== 'object') continue
        const entry: VtsRow = { ...item, cat1, cat2 }

        const paramValues = (item as any)['参数值']
        if (Array.isArray(paramValues) && paramValues.length > 0) {
          // 多值参数：合并到 entry 同一行
          for (const p of paramValues) {
            if (!p || typeof p !== 'object') continue
            const subName = String((p as any)['名称'] || '').trim()
            const prefix = NAME_TO_FIELD_PREFIX[subName]
            if (!prefix) continue
            entry[prefix] = (p as any)['值']
            entry[`${prefix}_db_key`] = (p as any).db_key
          }
          entry._has_multi_values = true
        } else if ((item as any).db_key) {
          // 简单参数（计算条件类）：直接有 db_key + 值
          entry['当前值'] = (item as any)['值'] ?? null
          entry['当前值_db_key'] = (item as any).db_key
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
