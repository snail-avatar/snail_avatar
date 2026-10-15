// @Time    : 2026
// @Author  : 李涛
// @File    : EconomyPage.vue
// @Desc    : EconomyPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  EconomyPage — 经济性计算页面
  复用 WorkflowPage，panel_type = "economy"
  后端会根据车型后缀（evlto → EV_ECO_CALC，reevlto → REEV_ECO_CALC）
  自动匹配正确的 workflow YAML 和 DAG 布局。
-->
<template>
  <WorkflowPage panel-type="economy" page-title="经济性" />
</template>

<script setup lang="ts">
import WorkflowPage from '../components/WorkflowPage.vue'
</script>
