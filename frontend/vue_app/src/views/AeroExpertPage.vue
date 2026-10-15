// @Time    : 2026
// @Author  : 李涛
// @File    : AeroExpertPage.vue
// @Desc    : AeroExpertPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  AeroExpertPage — 空气动力学专家页面
  复用 ExpertPanel，agent_id = aero_expert_agent
-->
<template>
  <ExpertPanel agent-id="aero_expert_agent" />
</template>

<script setup lang="ts">
import ExpertPanel from '../components/ExpertPanel.vue'
</script>
