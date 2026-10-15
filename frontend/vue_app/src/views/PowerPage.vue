// @Time    : 2026
// @Author  : 李涛
// @File    : PowerPage.vue
// @Desc    : PowerPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  PowerPage — 动力性计算页面
  复用 WorkflowPage，panel_type = "power"
  后端会根据车型后缀自动匹配正确的 workflow YAML
-->
<template>
  <WorkflowPage panel-type="power" page-title="动力性" />
</template>

<script setup lang="ts">
import WorkflowPage from '../components/WorkflowPage.vue'
</script>
