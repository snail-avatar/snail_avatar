// @Time    : 2026
// @Author  : 李涛
// @File    : PeExpertPage.vue
// @Desc    : PeExpertPage
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<!--
  PeExpertPage — PE专家（动力经济性）页面
  复用 ExpertPanel，agent_id = pe_expert_agent
-->
<template>
  <ExpertPanel agent-id="pe_expert_agent" />
</template>

<script setup lang="ts">
import ExpertPanel from '../components/ExpertPanel.vue'
</script>
