// @Time    : 2026
// @Author  : 李涛
// @File    : EnergyRegenPage.vue
// @Desc    : EnergyRegenPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  EnergyRegenPage — 能量回收计算页面
  复用 WorkflowPage，panel_type = "energy_regen"
  后端会根据车型后缀自动匹配 workflow_energy_regen.yaml
-->
<template>
  <WorkflowPage panel-type="energy_regen" page-title="能量回收" />
</template>

<script setup lang="ts">
import WorkflowPage from '../components/WorkflowPage.vue'
</script>
