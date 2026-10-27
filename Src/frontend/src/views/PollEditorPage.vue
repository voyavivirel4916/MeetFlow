<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
import { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import { groupsApi, type Group, type Member } from '../groups/api'
import { failure, useGroupLifetime } from '../groups/forms'
import { pollsApi, statusLabel, type Draft, type Poll, type PollPage } from '../polls/api'
import { beijing, emptyFields, equivalent, fromPoll, payload, validate, type Errors } from '../polls/editor'

const route = useRoute(), router = useRouter(), session = useSession()
const pollId = route.params.pollId ? String(route.params.pollId) : undefined
const group = ref<Group>(), members = ref<Member[]>([]), poll = ref<Poll>()
const fields = reactive(emptyFields()), errors = ref<Errors>({}), summary = ref<HTMLElement>(), form = ref<HTMLFormElement>()
const loading = ref(false), pending = ref(false), dirty = ref(false), readError = ref<ApiFailure>(), writeError = ref<ApiFailure>()
const message = ref(''), success = ref(typeof history.state.pollNotice === 'string' ? history.state.pollNotice : '')
if (history.state.pollNotice) history.replaceState({ ...history.state, pollNotice: undefined }, '')
const uncertain = ref(false), needsAck = ref(false), acknowledged = ref(false), checks = ref<PollPage>()
let controller: AbortController | undefined, nextKey = 0, sent: Draft | undefined
const lastAction = ref<'save' | 'publish'>('save')
const live = useGroupLifetime(() => dirty.value, () => pending.value)
const isOwner = computed(() => group.value?.owner_id === session.state.user?.id)
const editable = computed(() => !!group.value && isOwner.value && (!poll.value || poll.value.effective_status === 'DRAFT'))
const ready = computed(() => !!group.value && !loading.value && !readError.value && !pending.value)
const heading = computed(() => poll.value && !editable.value ? '排期详情' : pollId ? '编辑排期' : '发起排期')
const readonlyMessage = computed(() => !isOwner.value ? '你可以查看排期，编辑与发布由小组负责人操作。'
  : poll.value?.effective_status === 'CANCELLED' ? '排期已取消，当前只能查看。'
  : poll.value?.effective_status === 'CLOSED' ? '排期已关闭，结构保持只读。'
  : poll.value?.effective_status === 'CONFIRMED' ? '排期已确认，当前只能查看。' : '排期已发布，结构已冻结，当前只能查看。')
const checkedRetry = computed(() => !uncertain.value && (!needsAck.value || acknowledged.value))
const selected = (id: number) => fields.participants.find(person => person.user_id === id)
function hydrate(value: Poll) { Object.assign(fields, fromPoll(value)); nextKey = fields.slots.length; dirty.value = false; errors.value = {} }
function clearRecovery() { uncertain.value = needsAck.value = acknowledged.value = false; checks.value = undefined }
async function load(preserve = false) {
  if (loading.value || pending.value) return
  controller = new AbortController(); const current = controller
  loading.value = true; readError.value = undefined
  try {
    const currentPoll = pollId ? await pollsApi.get(pollId, current.signal) : undefined
    const groupId = currentPoll?.group_id || String(route.params.groupId)
    const [currentGroup, roster] = await Promise.all([groupsApi.get(groupId, current.signal), groupsApi.members(groupId, current.signal)])
    if (!live()) return
    group.value = currentGroup; members.value = [...roster].sort((a,b) => Number(b.role === 'OWNER')-Number(a.role === 'OWNER')); poll.value = currentPoll
    if (!preserve && currentPoll) { hydrate(currentPoll); clearRecovery() }
    if (preserve && currentPoll) {
      uncertain.value = false; writeError.value = undefined
      if (lastAction.value === 'publish' && !dirty.value) {
        hydrate(currentPoll); clearRecovery()
        message.value = currentPoll.effective_status === 'DRAFT' ? '当前读取仍为草稿，请核对后再决定是否发布。' : `已读取最新状态：${statusLabel[currentPoll.effective_status]}。`
      } else if (sent && equivalent(sent, currentPoll)) {
        hydrate(currentPoll); clearRecovery(); success.value = '已核对服务端，当前草稿内容已保存。'; message.value = ''
      } else {
        needsAck.value = true; acknowledged.value = false
        message.value = editable.value ? '服务端内容与本页不同，已保留你的输入。可重新载入服务端版本，或确认后再次保存。' : '排期状态已变化，当前为只读；本页未保存的输入已保留供你查看。'
      }
    }
  } catch (error) {
    if (!live()) return
    readError.value = failure(error)
    if (readError.value.status === 403 || readError.value.status === 404) { group.value = undefined; poll.value = undefined; members.value = []; Object.assign(fields, emptyFields()); dirty.value = false }
  } finally { if (controller === current) loading.value = false }
}
onMounted(() => load())
onBeforeUnmount(() => controller?.abort())
async function reload() {
  if (dirty.value && !window.confirm('重新读取会替换本页未保存的输入，确定继续吗？')) return
  await load(false)
  if (!pollId && !readError.value) { Object.assign(fields, emptyFields()); dirty.value = false; clearRecovery() }
  if (!readError.value) { message.value = ''; writeError.value = undefined; success.value = '' }
}
function edited() {
  dirty.value = true; success.value = ''
  const current = validate(fields)
  for (const key of Object.keys(errors.value)) if (!current[key]) delete errors.value[key]
  if (!uncertain.value && !needsAck.value) { message.value = ''; writeError.value = undefined }
}
function selectMember(member: Member, enabled: boolean) {
  if (enabled && !selected(member.user_id)) fields.participants.push({ user_id: member.user_id, importance: 'NORMAL' })
  if (!enabled) fields.participants = fields.participants.filter(person => person.user_id !== member.user_id)
  edited()
}
function importance(id: number, required: boolean) { const person = selected(id); if (person) person.importance = required ? 'REQUIRED' : 'NORMAL'; edited() }
function addSlot() { fields.slots.push({ key: nextKey++, start: '', end: '' }); edited() }
function removeSlot(key: number) { fields.slots = fields.slots.filter(item => item.key !== key); edited() }
async function focusSummary() { await nextTick(); summary.value?.focus() }
function focusField(key: string) { form.value?.querySelector<HTMLElement>(`[data-field="${key}"]`)?.focus() }
function mapErrors(error: ApiFailure) {
  const details = error.details as { fields?: { location?: unknown[] }[] } | undefined
  for (const item of details?.fields || []) {
    const location = item.location || [], field = location[1]
    if (typeof field !== 'string') continue
    let key = field === 'response_deadline' ? 'deadline' : field
    if (field === 'slots' && typeof location[2] === 'number' && fields.slots[location[2]]) key = `${location[3] === 'end_at' ? 'end' : 'start'}-${fields.slots[location[2]].key}`
    if (['title','description','location','deadline','participants','slots'].includes(key) || /^(start|end)-\d+$/.test(key)) errors.value[key] = '请核对此项的内容、时间和长度。'
  }
}
async function checkResult(page = 1) {
  if (loading.value || pending.value || !group.value) return
  if (pollId) { await load(true); return }
  loading.value = true; readError.value = undefined
  controller = new AbortController()
  try {
    const result = await pollsApi.list(group.value.id, page, controller.signal)
    if (!live()) return
    checks.value = result; uncertain.value = false; needsAck.value = true; acknowledged.value = false
    message.value = '已读取小组排期，请找到刚才的草稿后进入核对。同名不能证明是本次创建，再次创建可能重复。'
  } catch (error) { if (live()) readError.value = failure(error) }
  finally { loading.value = false }
}
async function save() {
  if (!ready.value || !editable.value || !checkedRetry.value || !group.value) return
  errors.value = validate(fields)
  if (Object.keys(errors.value).length) { message.value = '请检查以下填写内容。'; await focusSummary(); return }
  sent = payload(fields); lastAction.value = 'save'; pending.value = true; message.value = ''; writeError.value = undefined; success.value = ''
  try {
    const value = pollId ? await pollsApi.save(pollId, sent) : await pollsApi.create(group.value.id, sent)
    if (!live()) return
    clearRecovery(); hydrate(value); poll.value = value; pending.value = false
    if (!pollId) await router.replace({ path: `/polls/${value.id}/edit`, state: { pollNotice: '草稿已保存，可以继续编辑或发布。' } })
    else success.value = `草稿已保存 · ${beijing(value.updated_at).replace('T', ' ')}（北京时间）`
  } catch (error) {
    if (!live()) return
    writeError.value = failure(error); mapErrors(writeError.value)
    uncertain.value = writeError.value.uncertain || writeError.value.status === 409 || writeError.value.status === 403
    needsAck.value = acknowledged.value = false; checks.value = undefined
    message.value = uncertain.value ? '提交结果或排期状态需要核对，输入仍保留。请先读取服务端结果，不要重复提交。' : writeError.value.message
    if (writeError.value.status === 404) { pending.value = false; await load(true) }
    await focusSummary()
  } finally { pending.value = false }
}
async function publish() {
  if (!ready.value || !editable.value || !pollId || dirty.value || !checkedRetry.value) return
  errors.value = validate(fields, true)
  if (Object.keys(errors.value).length) { message.value = '发布前请补全以下内容。'; await focusSummary(); return }
  if (!window.confirm('发布后，候选时间和参与者等排期内容将不能修改。确定开始收集吗？')) return
  lastAction.value = 'publish'; pending.value = true; message.value = ''; writeError.value = undefined; success.value = ''
  try {
    const value = await pollsApi.publish(pollId)
    if (!live()) return
    poll.value = value; hydrate(value); clearRecovery(); success.value = '排期已发布，候选时间和参与者已冻结。'
  } catch (error) {
    if (!live()) return
    writeError.value = failure(error); mapErrors(writeError.value)
    uncertain.value = writeError.value.uncertain || [403,409].includes(writeError.value.status || 0)
    message.value = uncertain.value ? '发布结果或排期状态尚需核对，请先读取最新结果。' : writeError.value.message
    await focusSummary()
  } finally { pending.value = false }
}
</script>

<template>
  <RouterLink class="back-link" :to="group ? `/groups/${group.id}` : '/groups'">← {{ group?.name || '我的小组' }}</RouterLink>
  <section class="group-heading"><div><p class="eyebrow">MEETFLOW / 拼出共同的时间</p><h1>{{ heading }}</h1><p class="muted">所有日期与时间均为北京时间（UTC+8），截止以服务端判断为准。</p></div><button class="secondary" :disabled="loading || pending" @click="reload">{{ loading ? '正在读取…' : '重新读取排期' }}</button></section>
  <p v-if="success" class="success-note" role="status">{{ success }}</p>
  <StateNotice v-if="loading && !group" kind="loading" title="正在读取排期信息" message="正在核对小组、成员和已保存内容。" />
  <StateNotice v-if="readError" kind="error" :title="readError.status === 404 ? '未找到可访问的排期或小组' : '排期信息暂时无法读取'" :message="readError.message" :request-id="readError.requestId"><button :disabled="loading || pending" @click="uncertain || needsAck ? checkResult() : reload()">重试读取排期</button></StateNotice>
  <StateNotice v-if="group && !pollId && !isOwner" kind="error" title="只有负责人可以发起排期" message="你可以返回小组，查看负责人已发起的排期。" />
  <section v-if="message" ref="summary" class="form-summary" :class="{ uncertain: uncertain || needsAck }" role="alert" tabindex="-1"><p>{{ message }}</p><ul><li v-for="(error, key) in errors" :key="key"><button type="button" class="text-button" @click="focusField(key)">{{ error }}</button></li></ul><small v-if="writeError?.requestId">请求编号：{{ writeError.requestId }}</small>
    <button v-if="uncertain" class="secondary" :disabled="!ready" @click="checkResult()">核对服务端结果</button>
    <template v-if="checks"><ul><li v-for="item in checks.items" :key="item.id"><RouterLink :to="`/polls/${item.id}/edit`">{{ item.title }} · {{ statusLabel[item.effective_status] }}</RouterLink></li></ul><p v-if="!checks.items.length">这一页暂无排期。</p><div class="recovery-pages"><button class="secondary" :disabled="loading || checks.page <= 1" @click="checkResult(checks.page-1)">上一页核对</button><span>第 {{ checks.page }} 页</span><button class="secondary" :disabled="loading || checks.page*20 >= checks.total" @click="checkResult(checks.page+1)">下一页核对</button></div></template>
    <label v-if="needsAck && editable" class="retry-check"><input v-model="acknowledged" type="checkbox">{{ pollId ? '我已核对，确认使用本页输入再次保存' : '我已核对，仍需再次创建（可能产生重复排期）' }}</label>
    <button v-if="needsAck && pollId" class="text-button" :disabled="!ready" @click="reload">载入服务端版本</button>
  </section>
  <template v-if="group && (pollId || isOwner)">
    <section v-if="poll && !editable" class="poll-readonly"><div class="section-heading"><h2>{{ poll.title }}</h2><span class="role-badge">{{ statusLabel[poll.effective_status] }}</span></div><p class="muted">{{ readonlyMessage }} 读取后显示最新状态，不自动刷新。</p><p class="plain-text">{{ poll.description || '暂无说明。' }}</p><p>地点：{{ poll.location || '未填写' }}</p><p>填写截止：{{ beijing(poll.response_deadline).replace('T',' ') }}（北京时间）</p><h3>参与者</h3><ul><li v-for="person in poll.participants" :key="person.user_id">{{ person.username }} · {{ person.importance === 'REQUIRED' ? '必到' : '普通' }}</li></ul><p v-if="!poll.participants.length" class="muted">暂无参与者。</p><h3>候选时间（北京时间）</h3><ol><li v-for="item in poll.slots" :key="item.id">{{ beijing(item.start_at).replace('T',' ') }} ～ {{ beijing(item.end_at).replace('T',' ') }}</li></ol><p v-if="!poll.slots.length" class="muted">暂无候选时间。</p></section>
    <form v-if="editable || dirty" ref="form" class="poll-editor" novalidate :aria-busy="pending" @submit.prevent="save" @input="edited"><p v-if="!editable" class="form-summary">下方为本页未保存输入，供你核对；上方才是服务端排期。</p>
      <fieldset :disabled="!ready || !editable || uncertain"><section class="editor-section"><p class="eyebrow">01 / 这次想讨论什么</p><h2>基本信息</h2><div class="form-field"><label for="poll-title">主题（必填）</label><input id="poll-title" v-model="fields.title" data-field="title" maxlength="200" required :aria-invalid="!!errors.title" aria-describedby="title-error" placeholder="例如：课程方案评审"><p v-if="errors.title" id="title-error" class="field-error">{{ errors.title }}</p></div><div class="form-field"><label for="poll-description">说明（选填）</label><textarea id="poll-description" v-model="fields.description" data-field="description" rows="3" maxlength="20000" :aria-invalid="!!errors.description" aria-describedby="poll-description-error"/><small>{{ Array.from(fields.description).length }}/10000 字符</small><p v-if="errors.description" id="poll-description-error" class="field-error">{{ errors.description }}</p></div><div class="form-field"><label for="poll-location">地点（选填）</label><input id="poll-location" v-model="fields.location" data-field="location" maxlength="400" :aria-invalid="!!errors.location" aria-describedby="poll-location-error"><p v-if="errors.location" id="poll-location-error" class="field-error">{{ errors.location }}</p></div></section>
      <section class="editor-section"><p class="eyebrow">02 / 谁来一起参与</p><h2>参与者与必到成员</h2><p class="form-help">草稿可暂不选择；发布时至少1人。必到成员的冲突会影响后续推荐。</p><div data-field="participants" tabindex="-1" class="participant-options" :aria-invalid="!!errors.participants" aria-describedby="participants-error"><div v-for="person in members" :key="person.user_id" class="participant-option"><label><input type="checkbox" :checked="!!selected(person.user_id)" :aria-label="`选择 ${person.username}`" @change="selectMember(person, ($event.target as HTMLInputElement).checked)">{{ person.username }}<small v-if="person.role === 'OWNER'">负责人</small></label><label class="required-choice"><input type="checkbox" :checked="selected(person.user_id)?.importance === 'REQUIRED'" :disabled="!selected(person.user_id)" :aria-label="`${person.username} 必到`" @change="importance(person.user_id, ($event.target as HTMLInputElement).checked)">必到</label></div></div><p v-if="errors.participants" id="participants-error" class="field-error">{{ errors.participants }}</p></section>
      <section class="editor-section"><p class="eyebrow">03 / 哪些时间可能合适</p><h2>候选时间</h2><p class="form-help">北京时间（UTC+8）。草稿可以为空，发布需1～15个；同一时段不能重复，开始须早于结束。</p><div data-field="slots" tabindex="-1" :aria-invalid="!!errors.slots" aria-describedby="slots-error"><section v-for="(item,index) in fields.slots" :key="item.key" class="candidate-row"><div class="section-heading"><h3>候选 {{ index+1 }}</h3><button class="text-button" type="button" :aria-label="`移除候选 ${index+1}`" @click="removeSlot(item.key)">移除</button></div><div class="candidate-times"><div class="form-field"><label :for="`start-${item.key}`">开始（北京时间）</label><input :id="`start-${item.key}`" v-model="item.start" type="datetime-local" step="0.001" :data-field="`start-${item.key}`" :aria-invalid="!!errors[`start-${item.key}`]" :aria-describedby="`start-error-${item.key}`"><p v-if="errors[`start-${item.key}`]" :id="`start-error-${item.key}`" class="field-error">{{ errors[`start-${item.key}`] }}</p></div><div class="form-field"><label :for="`end-${item.key}`">结束（北京时间）</label><input :id="`end-${item.key}`" v-model="item.end" type="datetime-local" step="0.001" :data-field="`end-${item.key}`" :aria-invalid="!!errors[`end-${item.key}`]" :aria-describedby="`end-error-${item.key}`"><p v-if="errors[`end-${item.key}`]" :id="`end-error-${item.key}`" class="field-error">{{ errors[`end-${item.key}`] }}</p></div></div></section></div><p v-if="!fields.slots.length" class="muted">还没有候选时间，可以先保存草稿。</p><p v-if="errors.slots" id="slots-error" class="field-error">{{ errors.slots }}</p><button type="button" class="secondary" @click="addSlot">＋ 添加候选时间</button><span class="form-help"> 已设置 {{ fields.slots.length }} 个</span></section>
      <section class="editor-section"><p class="eyebrow">04 / 何时结束填写</p><h2>填写截止</h2><div class="form-field"><label for="poll-deadline">填写截止（北京时间，必填）</label><input id="poll-deadline" v-model="fields.deadline" data-field="deadline" type="datetime-local" step="0.001" required :aria-invalid="!!errors.deadline" aria-describedby="deadline-help deadline-error"><small id="deadline-help">发布时须在未来，且早于每个候选开始时间；最终以服务端时间为准。</small><p v-if="errors.deadline" id="deadline-error" class="field-error">{{ errors.deadline }}</p></div></section>
      <div class="editor-actions"><button type="submit" :disabled="!checkedRetry">{{ pending && lastAction === 'save' ? '正在保存…' : '保存草稿' }}</button><button type="button" class="secondary" :disabled="!pollId || dirty || !checkedRetry" @click="publish">{{ pending && lastAction === 'publish' ? '正在发布…' : '发布收集' }}</button><p class="form-help">{{ dirty ? '输入尚未保存，离开页面后会清空。请先保存，再发布。' : '发布后，主题、时间、参与者等排期结构将不能修改。' }}</p></div>
      </fieldset></form>
  </template>
</template>
