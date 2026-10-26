<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
import { useSession } from '../auth/session'
import { safeReturnPath } from '../navigation'
const session = useSession(), router = useRouter(), route = useRoute(), checking = ref(false)
async function retry() {
  if (checking.value) return
  checking.value = true
  try {
    const phase = await session.check()
    const path = safeReturnPath(route.query.returnTo, router)
    if (phase === 'authenticated') await router.replace(path)
    else if (phase === 'anonymous') await router.replace({ name: 'login', query: { returnTo: path } })
  } finally { checking.value = false }
}
</script>
<template>
  <h1>确认登录状态</h1>
  <StateNotice :kind="checking ? 'loading' : 'error'" title="暂时无法确认登录状态" message="请检查本机服务和连接，再重试。确认之前，工作空间暂不开放。" :request-id="session.state.error?.requestId">
    <button :disabled="checking" @click="retry">{{ checking ? '正在核对…' : '重新检查' }}</button>
  </StateNotice>
</template>
