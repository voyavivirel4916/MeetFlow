<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiFailure } from './api/client'
import { useSession } from './auth/session'
import { safeReturnPath } from './navigation'
import StateNotice from './components/StateNotice.vue'
const route = useRoute(), router = useRouter(), session = useSession()
const sampleLayout = computed(() => route.path === '/dashboard' || route.path === '/tasks/mine' || /^\/groups(?:\/\d+)?$/.test(route.path))
const loggingOut = ref(false), logoutMessage = ref('')
watch(() => session.state.identityEpoch, () => { logoutMessage.value = '' })
async function logout() {
  if (loggingOut.value || session.state.pending) return
  loggingOut.value = true; logoutMessage.value = ''
  const returnTo = safeReturnPath(route.path, router)
  try {
    await session.logout()
    await router.replace({ name: 'login', query: { returnTo } })
  } catch (error) {
    if (error instanceof ApiFailure && error.uncertain) {
      const phase = await session.check()
      if (phase === 'anonymous') { await router.replace({ name: 'login', query: { returnTo } }); return }
      logoutMessage.value = '退出结果尚未确认，请核对后手动重试。'
      if (phase === 'unavailable') await router.replace({ name: 'session-check', query: { returnTo } })
    } else logoutMessage.value = error instanceof ApiFailure ? error.message : '退出暂未完成，请重试。'
  } finally { loggingOut.value = false }
}
</script>
<template>
  <a class="skip" href="#content">跳到主要内容</a>
  <div class="shell" :class="{'sample-shell':sampleLayout}">
    <aside>
      <RouterLink class="brand" to="/dashboard"><span class="mark" aria-hidden="true">m</span><span>MeetFlow<small>凑时 · 小组协作</small></span></RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/dashboard">工作台</RouterLink>
        <RouterLink to="/groups">{{sampleLayout ? '我的小组' : '▦ 我的小组'}}</RouterLink>
        <RouterLink to="/tasks/mine">{{sampleLayout ? '我的任务' : '✓ 我的待办'}}</RouterLink>
        <RouterLink v-if="!sampleLayout" to="/connection">↗ 连接检查</RouterLink>
      </nav>
      <div v-if="sampleLayout" class="sample-account"><span class="sample-avatar">{{session.state.user?.username.slice(0,1).toUpperCase()}}</span><div>{{session.state.user?.username}}<small>个人空间</small></div><RouterLink to="/connection" aria-label="连接检查" title="连接检查">↗</RouterLink></div><p v-else class="aside-note">从找到共同时间，<br>到完成下一件事。</p>
    </aside>
    <div class="workspace">
      <header><span>{{ route.meta.requiresAuth ? '工作空间' : 'MeetFlow' }} / {{ route.meta.title || '正在读取' }}</span>
        <div class="user-actions" v-if="session.state.phase === 'authenticated' && session.state.user"><span class="user-label">{{ session.state.user.username }}</span><button class="secondary" :disabled="loggingOut || session.state.pending" @click="logout">{{ loggingOut ? '正在退出…' : '退出登录' }}</button></div>
        <div class="user-actions" v-else><RouterLink :to="{ name: 'login' }">登录</RouterLink><RouterLink :to="{ name: 'register' }">注册</RouterLink></div>
      </header>
      <main id="content" tabindex="-1">
        <p v-if="logoutMessage" role="alert" class="form-summary">{{ logoutMessage }}</p>
        <StateNotice v-if="!route.matched.length || (route.meta.requiresAuth && session.state.phase !== 'authenticated')" kind="loading" title="正在确认登录状态" message="请稍候，确认后将打开你的工作空间。" />
        <RouterView v-else v-slot="{ Component }"><component :is="Component" :key="route.path + (route.meta.requiresAuth ? ':' + session.state.identityEpoch : '')" /></RouterView>
      </main>
    </div>
  </div>
</template>
