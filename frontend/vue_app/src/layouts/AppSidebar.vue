// @Time    : 2026
// @Author  : 李涛
// @File    : AppSidebar.vue
// @Desc    : AppSidebar
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <div class="app-sidebar">
    <el-menu
      :default-active="route.path"
      router
      class="sidebar-menu"
      background-color="transparent"
      text-color="#606266"
      active-text-color="#409eff"
    >
      <!-- ========== general 组：系统面板 ========== -->
      <el-menu-item index="/work-log">
        <img src="/icons/sidebar/work_log.png" class="menu-icon" />
        <span>工作日志</span>
      </el-menu-item>
      <el-menu-item index="/agent-messages">
        <img src="/icons/sidebar/agent_messages.png" class="menu-icon" />
        <span>Agent 消息</span>
      </el-menu-item>
      <el-menu-item index="/memory-dbs">
        <img src="/icons/sidebar/memory_dbs.png" class="menu-icon" />
        <span>内存记忆</span>
      </el-menu-item>

      <!-- 细横线分割 -->
      <el-divider class="menu-sep" />

      <!-- ========== agent 组：业务面板 ========== -->
      <el-menu-item index="/target-definition">
        <img src="/icons/sidebar/target_definition.png" class="menu-icon" />
        <span>目标值定义</span>
      </el-menu-item>
      <el-menu-item index="/vts-ssts">
        <img src="/icons/sidebar/VTS_SSTS.png" class="menu-icon" />
        <span>VTS/SSTS 参数</span>
      </el-menu-item>
      <el-menu-item index="/power">
        <img src="/icons/sidebar/power.png" class="menu-icon" />
        <span>动力性</span>
      </el-menu-item>
      <el-menu-item index="/economy">
        <img src="/icons/sidebar/eco.png" class="menu-icon" />
        <span>经济性</span>
      </el-menu-item>
      <el-menu-item index="/aero-expert">
        <img src="/icons/sidebar/aero.png" class="menu-icon" />
        <span>空气动力学专家</span>
      </el-menu-item>
      <el-menu-item index="/pe-expert">
        <img src="/icons/sidebar/pe_expert.png" class="menu-icon" />
        <span>PE专家</span>
      </el-menu-item>
      <el-menu-item index="/energy-regen">
        <img src="/icons/sidebar/energy_regeneration.png" class="menu-icon" />
        <span>能量回收</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<style scoped>
.app-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding-top: 8px;
}

.sidebar-menu {
  flex: 1;
  border-right: none !important;
}
.sidebar-menu .el-menu-item {
  height: 38px;
  line-height: 38px;
  font-size: 13px;
  border-radius: 4px;
  margin: 0 6px 2px;
}
.sidebar-menu .el-menu-item:first-child {
  margin-top: 19px;  /* 下移按钮高度的 50% (38px * 0.5) */
}
.menu-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  margin-right: 6px;
  vertical-align: middle;
}
.menu-sep {
  margin: 8px 12px;
}
</style>
