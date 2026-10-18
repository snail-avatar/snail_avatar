// @Time    : 2026
// @Author  : 李涛
// @File    : SstsVtsPanel.vue
// @Desc    : SstsVtsPanel — VTS/SSTS 参数表（共享组件）
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <div class="ssts-vts-panel">
    <!-- 空状态 -->
    <el-empty
      v-if="!hasData"
      :description="emptyDesc"
    />

    <!-- 按一级分类 cat1 分组折叠展示 -->
    <el-collapse v-else v-model="activeCategories">
      <el-collapse-item
        v-for="cat in categories"
        :key="cat.name"
        :name="cat.name"
      >
        <template #title>
          <span class="cat-title">
            {{ cat.name }}
            <el-tag size="small" class="cat-count">{{ cat.params.length }} 项</el-tag>
          </span>
        </template>
        <!-- 每个分类内用扁平表格，每行带 cat2 二级分组 -->
        <el-table
          :data="cat.params"
          stripe
          size="small"
          border
          fit="false"
          :row-class-name="rowClassName"
          :span-method="makeCat2SpanMethod(cat.params)"
        >
          <el-table-column prop="cat2" label="分组" width="70" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="cat2-cell">{{ row.cat2 }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="名称" label="参数名" width="110" show-overflow-tooltip />
          <el-table-column prop="单位" label="单位" width="60" />
          <el-table-column prop="达标判据" label="达标判据" width="80" />
          <el-table-column label="当前值" width="90">
            <template #default="{ row }">
              <!-- 可编辑模式：用 ParamEdit -->
              <ParamEdit
                v-if="editable && (row['当前值_db_key'] || row.db_key)"
                :model-value="formatDisplayValue(row['当前值'] ?? row['值'])"
                :is-warn="isNotPassed(row['达标标识'])"
                @save="(v: string) => emitEditSave(row, '当前值', row['当前值_db_key'] || row.db_key, v)"
              />
              <!-- 只读模式 -->
              <span v-else :class="{ 'val-null': row['当前值'] == null && row['值'] == null }">
                {{ formatDisplayValue(row['当前值'] ?? row['值']) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="目标值" width="90">
            <template #default="{ row }">
              <!-- 可编辑模式：目标值也可编辑 -->
              <ParamEdit
                v-if="editable && row['目标值_db_key']"
                :model-value="formatDisplayValue(row['目标值'])"
                :is-warn="isNotPassed(row['达标标识'])"
                @save="(v: string) => emitEditSave(row, '目标值', row['目标值_db_key'], v)"
              />
              <!-- 只读模式 -->
              <span v-else :class="{ 'val-null': row['目标值'] == null }">
                {{ formatDisplayValue(row['目标值']) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="达标标识" width="80">
            <template #default="{ row }">
              <el-tag
                v-if="row['达标标识'] != null"
                size="small"
                :type="row['达标标识'] ? 'success' : 'danger'"
              >
                {{ row['达标标识'] ? '达标' : '未达标' }}
              </el-tag>
              <span v-else class="val-null">-</span>
            </template>
          </el-table-column>
          <el-table-column label="DB Key" width="90" show-overflow-tooltip>
            <template #default="{ row }">
              <code class="db-key">{{ row['当前值_db_key'] || row.db_key || '-' }}</code>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- 底部统计 -->
    <div v-if="hasData" class="panel-footer">
      共 {{ total }} 项 · {{ categories.length }} 个一级分类
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ParamEdit from './ParamEdit.vue'
import { formatDisplayValue, isNotPassed } from '../utils/valueFormat'

interface VtsRow {
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
  [key: string]: any
}

interface Category {
  name: string
  params: VtsRow[]
}

const props = defineProps<{
  data: {
    categories?: Category[]
    flatItems?: VtsRow[]
    total?: number
    note?: string
  } | null
  title?: string
  type?: 'vts' | 'ssts'
  /** 是否可编辑当前值/目标值列。a301 VtsSstsPage 传 true，a101 TargetDefinitionPage 不传（默认 false） */
  editable?: boolean
}>()

const emit = defineEmits<{
  /**
   * 编辑保存事件。
   * a301 VtsSstsPage 监听此事件，调 PUT /api/vts-ssts/param 写回 memory_db。
   */
  (e: 'edit-save', payload: {
    row: VtsRow
    field: '当前值' | '目标值'
    dbKey: string
    newValue: string
  }): void
}>()

const activeCategories = ref<string[]>([])

// 首次加载自动展开所有分类
watch(
  () => props.data?.categories?.length || 0,
  () => {
    if (props.data?.categories) {
      activeCategories.value = props.data.categories.map(c => c.name)
    }
  },
  { immediate: true },
)

const categories = computed<Category[]>(() => props.data?.categories || [])
const total = computed(() => props.data?.total ?? 0)
const hasData = computed(() => categories.value.length > 0)

const emptyDesc = computed(() => {
  if (props.data?.note) return props.data.note
  return `暂无 ${props.type === 'vts' ? 'VTS' : 'SSTS'} 数据`
})

function emitEditSave(row: VtsRow, field: '当前值' | '目标值', dbKey: string, newValue: string) {
  emit('edit-save', { row, field, dbKey, newValue })
}

// 达标标识=0 的行红色高亮
function rowClassName({ row }: { row: VtsRow }): string {
  if (isNotPassed(row['达标标识'])) return 'row-fail'
  return ''
}

/** 预计算 cat2 分组列的合并信息，返回 Element Plus span-method 函数
 *
 * 只合并第 0 列（cat2 分组列）。数据需按 cat2 连续排序，
 * 相同 cat2 的连续行合并为一个单元格。
 */
function makeCat2SpanMethod(params: VtsRow[]) {
  if (!params || params.length === 0) {
    return () => ({ rowspan: 1, colspan: 1 })
  }
  // 预计算：每个位置的 rowspan（0 表示被合并掉，1+ 表示首行并占 N 行）
  const spans: number[] = []
  for (let i = 0; i < params.length; i++) {
    if (i === 0 || params[i].cat2 !== params[i - 1].cat2) {
      // 当前 cat2 值首次出现 → 向后数连续相同的行数
      let count = 1
      while (i + count < params.length && params[i + count].cat2 === params[i].cat2) count++
      spans.push(count)
    } else {
      // 和上一行相同 → 被合并，不显示
      spans.push(0)
    }
  }
  // 返回 span-method 签名的函数
  return ({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) => {
    if (columnIndex !== 0) return { rowspan: 1, colspan: 1 }
    const r = spans[rowIndex] ?? 1
    if (r === 0) return { rowspan: 0, colspan: 0 }
    return { rowspan: r, colspan: 1 }
  }
}
</script>

<style scoped>
.ssts-vts-panel { padding: 8px 0; }

.cat-title {
  display: inline-flex; align-items: center; gap: 8px; font-weight: 500;
}
.cat-count { opacity: 0.8; }

.db-key {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
  color: #606266;
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 3px;
}

.val-null { color: #c0c4cc; font-style: italic; }

/* 表头文本强制不换行 */
:deep(.el-table th .cell) { white-space: nowrap; }
/* 分组列文本：字号同参数名，额外加粗 */
.cat2-cell { font-weight: 700; }

.panel-footer {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  text-align: right;
}

/* 达标标识=0 行红色高亮 */
:deep(.el-table .row-fail) {
  --el-table-tr-bg-color: #fef0f0;
}

/* 表格字号：表头 12px bold，内容 11px */
:deep(.el-table .el-table__header th .cell) {
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
:deep(.el-table .el-table__body td .cell) {
  font-size: 11px;
}
:deep(.el-table) {
  font-size: 11px;
}
/* 压缩单元格内边距，让列紧贴内容 */
:deep(.el-table th.el-table__cell),
:deep(.el-table td.el-table__cell) {
  padding: 0 4px !important;
}
:deep(.el-table .cell) {
  padding-left: 4px !important;
  padding-right: 4px !important;
}
</style>
