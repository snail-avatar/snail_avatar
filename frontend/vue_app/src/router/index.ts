// @Time    : 2026
// @Author  : 李涛
// @File    : index.ts
// @Desc    : index
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import { createRouter, createWebHistory } from 'vue-router'

/**
 * 图标路径统一映射 — 与左侧栏按钮用完全相同的 PNG 文件
 * 文件位置：vue_app/public/icons/sidebar/*.png
 */
const ICON = {
  work_log: '/icons/sidebar/work_log.png',
  agent_messages: '/icons/sidebar/agent_messages.png',
  memory_dbs: '/icons/sidebar/memory_dbs.png',
  target_definition: '/icons/sidebar/target_definition.png',
  vts_ssts: '/icons/sidebar/VTS_SSTS.png',
  power: '/icons/sidebar/power.png',
  eco: '/icons/sidebar/eco.png',
  aero: '/icons/sidebar/aero.png',
  pe_expert: '/icons/sidebar/pe_expert.png',
  energy_regen: '/icons/sidebar/energy_regeneration.png',
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/work-log' },

        // ========== general 系统面板 ==========
        { path: 'work-log', name: 'WorkLog', component: () => import('../views/WorkLogPage.vue'),
          meta: { title: '工作日志', icon: ICON.work_log } },
        { path: 'agent-messages', name: 'AgentMessages', component: () => import('../views/AgentMessagesPage.vue'),
          meta: { title: 'Agent 消息', icon: ICON.agent_messages } },
        { path: 'memory-dbs', name: 'MemoryDbs', component: () => import('../views/MemoryDbsPage.vue'),
          meta: { title: '内存记忆', icon: ICON.memory_dbs } },

        // ========== agent 业务面板 ==========
        { path: 'target-definition', name: 'TargetDefinition', component: () => import('../views/TargetDefinitionPage.vue'),
          meta: { title: '目标值定义', icon: ICON.target_definition } },
        { path: 'vts-ssts', name: 'VtsSsts', component: () => import('../views/VtsSstsPage.vue'),
          meta: { title: 'VTS/SSTS 参数', icon: ICON.vts_ssts } },
        { path: 'power', name: 'Power', component: () => import('../views/PowerPage.vue'),
          meta: { title: '动力性', icon: ICON.power } },
        { path: 'economy', name: 'Economy', component: () => import('../views/EconomyPage.vue'),
          meta: { title: '经济性', icon: ICON.eco } },
        { path: 'aero-expert', name: 'AeroExpert', component: () => import('../views/AeroExpertPage.vue'),
          meta: { title: '空气动力学专家', icon: ICON.aero } },
        { path: 'pe-expert', name: 'PeExpert', component: () => import('../views/PeExpertPage.vue'),
          meta: { title: 'PE专家', icon: ICON.pe_expert } },
        { path: 'energy-regen', name: 'EnergyRegen', component: () => import('../views/EnergyRegenPage.vue'),
          meta: { title: '能量回收', icon: ICON.energy_regen } },
      ],
    },
  ],
})

export default router
