<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import StateNotice from '../components/StateNotice.vue'
import { groupsApi, type Group, type Member } from '../groups/api'
import { failure, useGroupLifetime } from '../groups/forms'

const route = useRoute(), session = useSession(), id = String(route.params.groupId)
const group = ref<Group>(), members = ref<Member[]>([]), loading = ref(false), readError = ref<ApiFailure>()
const pending = ref(false), copying = ref(false), uncertain = ref(false), message = ref(''), writeError = ref<ApiFailure>()
const selectedCode = ref<HTMLInputElement>(), manualCopy = ref(false)
const success = ref(typeof history.state.groupNotice === 'string' ? history.state.groupNotice : '')
// Consume navigation feedback once; a reload is a fresh read, not a repeated save.
if (history.state.groupNotice) history.replaceState({ ...history.state, groupNotice: undefined }, '')
const live = useGroupLifetime(() => false, () => pending.value)
const owner = computed(() => group.value?.owner_id === session.state.user?.id)
const orderedMembers = computed(() => [...members.value].sort((a, b) => Number(b.role === 'OWNER') - Number(a.role === 'OWNER')))
const ready = computed(() => !!group.value && !loading.value && !readError.value && !pending.value)
let reader: AbortController | undefined
async function load() {
  if (loading.value || pending.value) return
  reader = new AbortController(); const current = reader
  loading.value = true; readError.value = undefined; manualCopy.value = false
  try {
    const [value, roster] = await Promise.all([groupsApi.get(id, current.signal), groupsApi.members(id, current.signal)])
    if (!live()) return
    if (roster.find(member => member.role === 'OWNER')?.user_id !== value.owner_id) throw new ApiFailure('protocol', '成员信息需要重新核对，请刷新。')
    group.value = value; members.value = roster
    if (uncertain.value) { uncertain.value = false; message.value = '已重新读取当前邀请码，请使用下方最新代码。'; writeError.value = undefined }
  } catch (error) {
    if (!live()) return
    readError.value = failure(error)
    if (readError.value.status === 404 || readError.value.status === 403) { group.value = undefined; members.value = [] }
  } finally { if (reader === current) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => reader?.abort())
async function reset() {
  if (!ready.value || !owner.value || uncertain.value || !window.confirm('重置后，旧邀请码会立即失效，已加入成员不受影响。确定重置吗？')) return
  pending.value = true; message.value = ''; writeError.value = undefined; success.value = ''; manualCopy.value = false
  try {
    await groupsApi.reset(id)
    if (!live()) return
    pending.value = false
    await load()
    if (!live()) return
    success.value = '邀请码已重置，旧码已失效。'
  } catch (error) {
    if (!live()) return
    writeError.value = failure(error); uncertain.value = writeError.value.uncertain
    message.value = uncertain.value ? '重置结果尚未确认，请先重新读取当前邀请码，不要连续重置。' : writeError.value.message
    if (writeError.value.status === 403 || writeError.value.status === 404) { pending.value = false; await load() }
  } finally { pending.value = false }
}
async function copy() {
  if (!ready.value || uncertain.value || !group.value?.invite_code || copying.value) return
  copying.value = true
  const code = group.value.invite_code
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
    await navigator.clipboard.writeText(code)
    if (live() && code === group.value?.invite_code) { message.value = '邀请码已复制，可分享给同学。'; writeError.value = undefined }
  } catch {
    if (live()) { manualCopy.value = true; selectedCode.value?.focus(); selectedCode.value?.select(); message.value = '无法自动复制，已选中邀请码，请按 Ctrl+C 复制。' }
  } finally { copying.value = false }
}
</script>

<template>
  <RouterLink class="back-link" to="/groups">← 我的小组</RouterLink>
  <section class="group-heading"><div><p class="eyebrow">MEETFLOW / 把想法拼成行动</p><h1>{{ group?.name || '小组空间' }}</h1><p class="muted">{{ group ? `${members.length} 位伙伴 · ${owner ? '你是小组负责人' : '你是小组成员'}` : '一起找到时间，继续把事情推进。' }}</p></div><button class="secondary" :disabled="loading || pending" @click="load">{{ loading ? '正在读取…' : '刷新小组' }}</button></section>
  <p v-if="success" class="success-note" role="status">{{ success }}</p>
  <StateNotice v-if="loading && !group" kind="loading" title="正在读取小组" message="正在核对小组和成员信息。" />
  <StateNotice v-if="readError" kind="error" :title="readError.status === 404 ? '未找到可访问的小组' : '小组信息暂时无法读取'" :message="readError.status === 404 ? '请确认你已加入这个小组，或返回我的小组。' : readError.message" :request-id="readError.requestId"><button :disabled="loading" @click="load">重新读取</button></StateNotice>
  <p v-if="group && (loading || readError)" class="muted">下方是上次读取的内容；邀请码操作需重新读取成功后使用。</p>
  <p v-if="message" :role="writeError ? 'alert' : 'status'" class="form-summary" :class="{ uncertain }">{{ message }}<small v-if="writeError?.requestId">请求编号：{{ writeError.requestId }}</small><button v-if="uncertain" class="secondary" :disabled="loading || pending" @click="load">核对当前邀请码</button></p>
  <div v-if="group" class="group-detail-layout">
    <div><section class="group-about"><p class="eyebrow">OUR SHARED SPACE</p><h2>关于这个小组</h2><p class="plain-text">{{ group.description || '还没有填写说明，从一次共同讨论开始吧。' }}</p></section>
      <section class="members-card"><div class="section-heading"><h2>小组成员</h2><span class="member-capacity" :aria-label="`小组成员${members.length}人，上限20人`">{{ members.length.toString().padStart(2, '0') }}/20</span></div><ul class="member-list"><li v-for="member in orderedMembers" :key="member.user_id" :class="{ 'current-member': member.user_id === session.state.user?.id }" :aria-label="member.user_id === session.state.user?.id ? `${member.username}，当前登录成员` : undefined"><span class="member-avatar" aria-hidden="true">{{ member.username.slice(0, 1).toUpperCase() }}</span><div><strong>{{ member.username }}</strong></div><span class="role-badge">{{ member.role === 'OWNER' ? '负责人' : '成员' }}</span></li></ul></section>
    </div>
    <div><section v-if="owner" class="invite-card"><p class="eyebrow">邀请伙伴，补齐拼图</p><h2>小组邀请码</h2><p class="muted">分享给同学，登录后即可加入。{{ group.member_count >= 20 ? '目前已满20人。' : `还可加入${20 - group.member_count}人。` }}</p>
      <label for="current-invite" class="form-help">{{ uncertain || readError || loading ? '上次读取的邀请码（待核对）' : '当前邀请码' }}</label><input id="current-invite" ref="selectedCode" class="invite-display" readonly :value="uncertain || readError || loading ? '' : group.invite_code" :placeholder="uncertain || readError || loading ? '请先重新读取' : ''" :aria-label="uncertain ? '邀请码待核对' : '当前邀请码'">
      <p v-if="group.invite_enabled === false" class="field-error">当前邀请已停用，负责人可重置后重新邀请。</p><div class="invite-actions"><button :disabled="!ready || uncertain || copying || !group.invite_enabled" @click="copy">{{ copying ? '正在复制…' : '复制邀请码' }}</button><button class="text-button" :disabled="!ready || uncertain || copying" @click="reset">{{ pending ? '正在重置…' : '重置邀请码' }}</button></div><small v-if="manualCopy" class="muted">选中代码后按 Ctrl+C 复制。</small><p class="form-help">重置会立即使旧码失效，已加入的成员保留。</p>
    </section><section v-else class="member-guide"><p class="eyebrow">一起参与</p><h2>你已在小组中</h2><p class="muted">想邀请新的伙伴？请联系小组负责人分享邀请码。</p></section>
    <section class="next-step-card"><span class="puzzle-label" aria-hidden="true">↗</span><h2>接下来，找到共同时间</h2><p class="muted">排期、会议和任务功能正在准备中。这里会成为小组持续协作的空间。</p></section></div>
  </div>
</template>
