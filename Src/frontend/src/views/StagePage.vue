<script setup lang="ts">
import { useRoute } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
const route = useRoute()
</script>
<template>
  <p class="eyebrow">MEETFLOW / 一起把事情推进</p>
  <h1>{{ route.meta.title }}</h1>
  <StateNotice kind="empty" title="这一页正在准备中" :message="String(route.meta.description)">
    <p>当前为正式应用的工程起步版本，完整交互可在已确认的原型中查看。</p>
    <RouterLink to="/groups">返回我的小组 →</RouterLink>
  </StateNotice>
</template>
