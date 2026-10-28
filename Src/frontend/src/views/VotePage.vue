<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
import type { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import { failure, useGroupLifetime } from '../groups/forms'
import { pollsApi, statusLabel, type Poll } from '../polls/api'
import { beijing } from '../polls/editor'
import { options, votesApi, sameAnswers, selections, toChoices, type Choices, type MyVotes, type Vote } from '../votes/api'

const id = String(useRoute().params.pollId), session = useSession()
const poll = ref<Poll>(), saved = ref<MyVotes>(), choices = ref<Choices>({})
const loading = ref(false), pending = ref(false), readError = ref<ApiFailure>(), writeError = ref<ApiFailure>()
const dirty = ref(false), recovery = ref(false), needsAck = ref(false), acknowledged = ref(false), blocked = ref(false)
const message = ref(''), success = ref(''), missing = ref<number[]>([]), summary = ref<HTMLElement>()
const live = useGroupLifetime(() => dirty.value, () => pending.value)
let controller: AbortController | undefined, sent: Vote[] | undefined
const participant = computed(() => poll.value?.participants.some(person => person.user_id === session.state.user?.id))
const writable = computed(() => participant.value && poll.value?.effective_status === 'OPEN' && !blocked.value)
const disabled = computed(() => loading.value || pending.value || !!readError.value || recovery.value || !writable.value)
const selected = computed(() => poll.value ? selections(poll.value, choices.value) : [])
const readonlyReason = computed(() => !participant.value ? '你未被列为本次排期的参与者，可以返回排期详情查看。' :
  poll.value?.effective_status === 'DRAFT' ? '排期尚未发布，暂时不能填写。' : dirty.value ? '本次收集已结束，本页选择尚未确认保存，请与服务端答案核对。' : '本次收集已结束，以下保留你最后保存的答案。')
function hydrate(value: MyVotes) { saved.value = value; choices.value = toChoices(value.votes); dirty.value = false; missing.value = [] }
async function load(preserve = false) {
  if (loading.value || pending.value) return
  loading.value = true; readError.value = undefined
  controller = new AbortController()
  try {
    const latest = await pollsApi.get(id, controller.signal)
    if (!live()) return
    const included = latest.participants.some(person => person.user_id === session.state.user?.id)
    const result = included ? await votesApi.get(latest, controller.signal) : undefined
    if (!live()) return
    poll.value = latest; saved.value = result; blocked.value = false
    if (!preserve) {
      if (result) hydrate(result)
      else { choices.value = {}; dirty.value = false }
      recovery.value = needsAck.value = acknowledged.value = false; message.value = ''; writeError.value = undefined
    } else if (result?.submitted_at && sent && sameAnswers(result.votes, sent)) {
      hydrate(result); recovery.value = needsAck.value = acknowledged.value = false
      message.value = ''; writeError.value = undefined; success.value = '已核对，你的选择已保存。'
    } else {
      recovery.value = false; needsAck.value = !!included && latest.effective_status === 'OPEN'; acknowledged.value = false
      message.value = needsAck.value ? '服务端结果与本页选择不同，已保留本页选择。请核对后决定载入或再次保存。' : '排期已不可填写，本页尚未确认保存的选择仍保留供你核对。'
    }
  } catch (error) {
    if (!live()) return
    readError.value = failure(error)
    if (readError.value.status === 404) { poll.value = undefined; saved.value = undefined; choices.value = {}; dirty.value = false }
  } finally { loading.value = false }
}
onMounted(() => load())
onBeforeUnmount(() => controller?.abort())
async function reload() {
  if (dirty.value && !window.confirm('重新读取会替换本页尚未保存的选择，确定继续吗？')) return
  success.value = ''; await load()
}
function choose(slotId: number, value: typeof options[number]['value']) {
  choices.value[slotId] = value
  dirty.value = !sameAnswers(selected.value, saved.value?.votes || [])
  missing.value = missing.value.filter(item => item !== slotId)
  success.value = ''
  if (!needsAck.value) { message.value = ''; writeError.value = undefined }
}
async function focusSummary() { await nextTick(); summary.value?.focus() }
function focusSlot(slotId: number) { document.getElementById(`vote-${slotId}-AVAILABLE`)?.focus() }
async function save() {
  if (disabled.value || !poll.value || (needsAck.value && !acknowledged.value)) return
  missing.value = poll.value.slots.filter(slot => !choices.value[slot.id]).map(slot => slot.id)
  if (missing.value.length || !poll.value.slots.length) { message.value = '请为每个候选时间选择一种状态。'; await focusSummary(); return }
  sent = selected.value.map(item => ({ ...item })); pending.value = true; message.value = ''; success.value = ''; writeError.value = undefined
  try {
    const result = await votesApi.save(poll.value, sent)
    if (!live()) return
    hydrate(result); needsAck.value = acknowledged.value = false
    success.value = '你的选择已保存。'
  } catch (error) {
    if (!live()) return
    writeError.value = failure(error)
    recovery.value = writeError.value.uncertain || [403,409].includes(writeError.value.status || 0)
    blocked.value = [403,409].includes(writeError.value.status || 0)
    acknowledged.value = false
    message.value = recovery.value ? '保存结果或排期状态需要核对，已保留你的选择。请先读取服务端结果。' : writeError.value.message
    if (writeError.value.status === 404) { pending.value = false; await load(true) }
    await focusSummary()
  } finally { pending.value = false }
}
const label = (value: string) => options.find(option => option.value === value)?.label || '未填写'
</script>

<template>
  <RouterLink class="back-link" :to="poll ? `/groups/${poll.group_id}` : '/groups'">← 返回小组</RouterLink>
  <section class="group-heading"><div><p class="eyebrow">MEETFLOW / 拼出共同的时间</p><h1>填写时间</h1><p class="muted">让大家知道，你在哪些时间可以一起参与。</p></div><button class="secondary" :disabled="loading || pending" @click="recovery || needsAck ? load(true) : reload()">{{ loading ? '正在读取…' : '重新读取填写' }}</button></section>
  <StateNotice v-if="loading && !poll" kind="loading" title="正在读取候选时间" message="正在读取排期和你已保存的选择。" />
  <StateNotice v-if="readError" kind="error" :title="readError.status === 404 ? '未找到可访问的排期' : '填写结果暂时无法读取'" :message="readError.message" :request-id="readError.requestId"><button :disabled="loading || pending" @click="load(recovery || needsAck || dirty)">重新读取结果</button></StateNotice>
  <p v-if="success" class="success-note" role="status">{{ success }}</p>
  <section v-if="message" ref="summary" class="form-summary" :class="{ uncertain: recovery || needsAck }" role="alert" tabindex="-1"><p>{{ message }}</p><ul v-if="missing.length"><li v-for="slotId in missing" :key="slotId"><button type="button" class="text-button" @click="focusSlot(slotId)">候选 {{ (poll?.slots.findIndex(slot => slot.id === slotId) || 0)+1 }} 尚未选择</button></li></ul><small v-if="writeError?.requestId">请求编号：{{ writeError.requestId }}</small>
    <button v-if="recovery" class="secondary" :disabled="loading || pending" @click="load(true)">核对服务端结果</button>
    <template v-if="needsAck || (dirty && !writable && !recovery)"><p class="form-help">服务端已保存：{{ saved?.submitted_at ? beijing(saved.submitted_at).replace('T',' ')+'（北京时间）' : '尚未提交' }}</p><ul class="server-votes"><li v-for="(slot,index) in poll?.slots" :key="slot.id">候选 {{ index+1 }}：{{ label(saved?.votes.find(item => item.slot_id === slot.id)?.availability || '') }}</li></ul><label v-if="needsAck" class="retry-check"><input v-model="acknowledged" type="checkbox">我已核对，确认用本页选择再次保存</label><button class="text-button" :disabled="loading || pending" @click="reload">载入服务端答案</button></template>
  </section>
  <template v-if="poll">
    <section class="vote-intro"><div class="section-heading"><h2>{{ poll.title }}</h2><span class="role-badge">{{ statusLabel[poll.effective_status] }}</span></div><p v-if="poll.description" class="plain-text">{{ poll.description }}</p><p class="muted">{{ poll.location || '地点待定' }} · 截止 {{ beijing(poll.response_deadline).replace('T',' ') }}（北京时间）</p><RouterLink :to="`/polls/${poll.id}/edit`">查看排期详情 →</RouterLink><RouterLink class="vote-matrix-link" :to="`/polls/${poll.id}/results`">查看时间矩阵 →</RouterLink></section>
    <StateNotice v-if="!participant || !writable" kind="empty" :title="blocked ? '请先核对最新排期状态' : '当前仅可查看'" :message="blocked ? '服务端已拒绝本次填写，请读取最新状态后再操作。' : readonlyReason" />
    <form v-if="participant" class="vote-form" novalidate :aria-busy="pending" @submit.prevent="save">
      <div class="vote-progress"><span>已选 {{ selected.length }}/{{ poll.slots.length }}</span><span>{{ saved?.submitted_at ? '上次保存 '+beijing(saved.submitted_at).replace('T',' ') : '尚未提交' }}</span></div>
      <p v-if="dirty" class="form-help">{{ !writable ? '下方包含本页未确认保存的选择。' : '选择尚未保存，请完成后统一保存。' }}</p>
      <fieldset :disabled="disabled" class="vote-fields"><fieldset v-for="(slot,index) in poll.slots" :key="slot.id" class="vote-card" :class="{ unanswered: missing.includes(slot.id) }" :aria-describedby="`vote-error-${slot.id}`"><legend>候选 {{ index+1 }}</legend><p class="vote-date">{{ beijing(slot.start_at).replace('T',' ') }} <span>— {{ beijing(slot.end_at).slice(0,10) === beijing(slot.start_at).slice(0,10) ? beijing(slot.end_at).slice(11) : beijing(slot.end_at).replace('T',' ') }}</span></p><p class="form-help">北京时间</p><div class="vote-options"><label v-for="option in options" :key="option.value" :class="['vote-choice', option.value.toLowerCase(), { chosen: choices[slot.id] === option.value }]"><input :id="`vote-${slot.id}-${option.value}`" type="radio" :name="`slot-${slot.id}`" :value="option.value" :checked="choices[slot.id] === option.value" :aria-invalid="missing.includes(slot.id)" @change="choose(slot.id, option.value)"><span class="choice-symbol" aria-hidden="true">{{ option.symbol }}</span><span>{{ option.label }}<small>{{ option.hint }}</small></span></label></div><p v-if="missing.includes(slot.id)" :id="`vote-error-${slot.id}`" class="field-error">请选择此候选时间的状态。</p><p v-else-if="!writable && !choices[slot.id]" class="muted">未填写</p></fieldset></fieldset>
      <p v-if="!poll.slots.length" class="muted">负责人尚未设置候选时间。</p>
      <div v-if="writable || recovery || blocked" class="editor-actions"><button type="submit" :disabled="disabled || (needsAck && !acknowledged)">{{ pending ? '正在保存…' : '保存我的选择' }}</button><p class="form-help">可以在收集截止前重新填写并保存；每次保存覆盖自己的全部答案。</p></div>
    </form>
  </template>
</template>
