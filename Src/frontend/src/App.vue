<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
<template>
  <a class="skip" href="#content">跳到主要内容</a>
  <div class="shell">
    <aside>
      <RouterLink class="brand" to="/groups"><span class="mark" aria-hidden="true">m</span><span>MeetFlow<small>凑时 · 小组协作</small></span></RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/groups">▦ 我的小组</RouterLink>
        <RouterLink to="/tasks/mine">✓ 我的待办</RouterLink>
        <RouterLink to="/connection">↗ 连接检查</RouterLink>
      </nav>
      <p class="aside-note">从找到共同时间，<br>到完成下一件事。</p>
    </aside>
    <div class="workspace">
      <header><span>工作空间 / {{ route.meta.title }}</span><span class="stage">工程起步版 · T08</span></header>
      <main id="content" tabindex="-1"><RouterView /></main>
    </div>
  </div>
</template>
