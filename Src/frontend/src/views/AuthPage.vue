<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import { validateAuth, type AuthFields, type FieldErrors, type FieldName } from '../auth/validation'
import { safeReturnPath } from '../navigation'

const props = defineProps<{ registering: boolean }>()
const session = useSession(), router = useRouter(), route = useRoute()
const hint = props.registering ? null : session.consumeLoginHint()
const fields = reactive<AuthFields>({ username: hint?.username || '', email: '', password: '' })
const errors = ref<FieldErrors>({}), message = ref(''), requestId = ref<string>()
const pending = ref(false), uncertain = ref(false), dirty = ref(false), showPassword = ref(false)
const summary = ref<HTMLElement>(), usernameInput = ref<HTMLInputElement>(), emailInput = ref<HTMLInputElement>(), passwordInput = ref<HTMLInputElement>()
const title = computed(() => props.registering ? '创建你的账号' : '欢迎回来')
const notice = computed(() => route.query.expired === '1' ? '登录状态已过期，请重新登录后继续。' : hint?.message || '')
const returnPath = () => safeReturnPath(route.query.returnTo, router)
const links = computed(() => ({ returnTo: returnPath() }))
const labels = { username: '用户名', email: '邮箱', password: '密码' }
function focus(field: FieldName) { ({ username: usernameInput, email: emailInput, password: passwordInput })[field].value?.focus() }
async function focusSummary() { await nextTick(); summary.value?.focus() }
function blur(field: FieldName) {
  const error = validateAuth(props.registering, fields)[field]
  errors.value = { ...errors.value, [field]: error }
}
function edited() {
  dirty.value = true
  // Keep the recovery action available until an uncertain write is reconciled.
  if (!uncertain.value) { message.value = ''; requestId.value = undefined }
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value || pending.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => { fields.password = ''; window.removeEventListener('beforeunload', beforeUnload) })
onBeforeRouteLeave(() => pending.value ? false : !dirty.value || window.confirm('离开此页会清空尚未提交的输入，确定离开吗？'))

async function finishLogin() {
  dirty.value = false; fields.password = ''
  await router.replace(returnPath())
}
async function goLogin(registered = false) {
  session.setLoginHint(fields.username.trim().toLowerCase(), registered ? '注册成功，请使用新账号登录。' : '请先尝试登录，核对注册结果。')
  dirty.value = false; fields.password = ''
  await router.replace({ name: 'login', query: links.value })
}
async function reconcileLogin() {
  if (pending.value) return
  pending.value = true
  try {
    const phase = await session.check()
    if (phase === 'authenticated' && session.state.user?.username === fields.username.trim().toLowerCase()) {
      pending.value = false
      await finishLogin(); return
    }
    if (phase === 'anonymous') {
      uncertain.value = false
      message.value = '当前尚未登录。原请求结果未确认，你可以手动重新登录。'
    } else if (phase === 'authenticated') {
      message.value = '当前浏览器已登录其他账号，请先退出当前账号，再重新登录。'
      fields.password = ''
    } else {
      message.value = '暂时无法核对登录状态，请恢复连接后再次核对。'
    }
    await focusSummary()
  } finally { pending.value = false }
}
async function submit() {
  if (pending.value || session.state.pending || uncertain.value) return
  errors.value = validateAuth(props.registering, fields)
  if (Object.values(errors.value).some(Boolean)) {
    message.value = '请检查以下填写内容。'; await focusSummary(); return
  }
  pending.value = true; message.value = ''; requestId.value = undefined
  try {
    const credentials = { username: fields.username.trim().toLowerCase(), password: fields.password }
    if (props.registering) {
      await session.register({ ...credentials, email: fields.email.trim().toLowerCase() })
      pending.value = false
      await goLogin(true)
    } else {
      await session.login(credentials)
      pending.value = false
      await finishLogin()
    }
  } catch (error) {
    if (error instanceof ApiFailure) {
      requestId.value = error.requestId
      uncertain.value = error.uncertain
      message.value = error.uncertain ? (props.registering ? '注册结果尚未确认，请先去登录核对，避免重复提交。' : '登录结果尚未确认，正在核对当前会话。')
        : error.status === 401 ? '账号或密码错误，请重试。' : error.message
      if (error.status === 422) {
        const details = error.details as { fields?: { location?: unknown[] }[] } | undefined
        for (const item of details?.fields || []) {
          const field = item.location?.[1]
          if (field === 'username' || field === 'email' || field === 'password') errors.value[field] = `请检查${labels[field]}的格式和长度。`
        }
      }
    } else message.value = '操作暂时未完成，请稍后重试。'
    pending.value = false
    if (uncertain.value && !props.registering) await reconcileLogin()
    else await focusSummary()
  } finally { pending.value = false }
}
</script>

<template>
  <div class="auth-layout">
    <section class="auth-story" aria-label="MeetFlow介绍">
      <p class="eyebrow">MEETFLOW / 时间拼图</p>
      <h1>把大家的时间，<br>拼成下一步。</h1>
      <p>从找到共同时间，到记下会议决定，再一起完成每一件事。</p>
      <div class="time-pieces" aria-hidden="true"><span>找到时间</span><span>形成决定</span><span>继续行动</span></div>
      <p class="story-foot">为课程小组准备的协作空间</p>
    </section>
    <section class="auth-card" :aria-busy="pending">
      <p class="eyebrow">{{ registering ? '开始一起协作' : '继续你的小组协作' }}</p>
      <h2>{{ title }}</h2>
      <p v-if="notice" class="auth-note" role="status">{{ notice }}</p>
      <p class="form-help">以下均为必填项。{{ registering ? '注册后需要登录。' : '使用用户名和密码登录。' }}</p>
      <section v-if="message" ref="summary" class="form-summary" :class="{ uncertain }" role="alert" tabindex="-1" aria-label="表单提示">
        <p>{{ message }}</p>
        <ul v-if="Object.values(errors).some(Boolean)"><template v-for="(error, field) in errors" :key="field"><li v-if="error"><button class="text-button" type="button" @click="focus(field)">{{ error }}</button></li></template></ul>
        <small v-if="requestId">请求编号：{{ requestId }}</small>
        <button v-if="uncertain && !registering" class="secondary" type="button" :disabled="pending" @click="reconcileLogin">核对登录状态</button>
        <button v-if="uncertain && registering" class="secondary" type="button" @click="goLogin()">去登录核对</button>
      </section>
      <form novalidate @submit.prevent="submit" @input="edited">
        <fieldset :disabled="pending || session.state.pending">
          <div class="form-field"><label for="username">用户名</label>
            <input id="username" ref="usernameInput" v-model="fields.username" name="username" autocomplete="username" autocapitalize="none" :spellcheck="false" maxlength="64" required :aria-invalid="!!errors.username" aria-describedby="username-help username-error" @blur="blur('username')">
            <small id="username-help">{{ registering ? '3～32位字母、数字或下划线，不区分大小写。' : '用户名不区分大小写。' }}</small><p v-if="errors.username" id="username-error" class="field-error">{{ errors.username }}</p>
          </div>
          <div v-if="registering" class="form-field"><label for="email">邮箱</label>
            <input id="email" ref="emailInput" v-model="fields.email" name="email" type="email" autocomplete="email" maxlength="508" required :aria-invalid="!!errors.email" aria-describedby="email-error" @blur="blur('email')">
            <p v-if="errors.email" id="email-error" class="field-error">{{ errors.email }}</p>
          </div>
          <div class="form-field"><label for="password">密码</label>
            <div class="password-row"><input id="password" ref="passwordInput" v-model="fields.password" name="password" :type="showPassword ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" maxlength="256" required :aria-invalid="!!errors.password" aria-describedby="password-help password-error" @blur="blur('password')"><button class="secondary" type="button" :aria-pressed="showPassword" @click="showPassword = !showPassword">{{ showPassword ? '隐藏密码' : '显示密码' }}</button></div>
            <small id="password-help">{{ registering ? '8～128个字符，不能全为空白；首尾空格会保留。' : '密码首尾空格会保留。' }}</small><p v-if="errors.password" id="password-error" class="field-error">{{ errors.password }}</p>
          </div>
          <button class="auth-submit" type="submit" :disabled="uncertain">{{ pending ? '正在提交…' : registering ? '注册账号' : '登录' }}</button>
        </fieldset>
      </form>
      <p class="auth-switch">{{ registering ? '已经有账号？' : '还没有账号？' }} <RouterLink :to="{ name: registering ? 'login' : 'register', query: links }">{{ registering ? '去登录' : '创建账号' }}</RouterLink></p>
      <p v-if="dirty" class="form-help">输入尚未提交，离开页面后会清空。</p>
    </section>
  </div>
</template>
