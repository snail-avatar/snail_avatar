// @Time    : 2026
// @Author  : 李涛
// @File    : App.vue
// @Desc    : App
// Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
// 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

<template>
  <router-view />
</template>

<script setup lang="ts">
// App.vue 保持极简 — 布局在 MainLayout.vue 中通过路由嵌套渲染
</script>

<style>
/* 全局样式重置 */
* {
  box-sizing: border-box;
}
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}
</style>
