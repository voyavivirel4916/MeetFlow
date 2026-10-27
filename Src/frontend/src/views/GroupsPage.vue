<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
import { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import { groupsApi, type GroupPage } from '../groups/api'
import { failure, useGroupLifetime, validateGroup, type GroupErrors } from '../groups/forms'

const router = useRouter(), session = useSession()
const saved = ref<GroupPage>(), loading = ref(false), readError = ref<ApiFailure>()
const mode = ref<'create' | 'join'>('create'), fields = reactive({ name: '', description: '', invite_code: '' })
const errors = ref<GroupErrors>({}), message = ref(''), writeError = ref<ApiFailure>(), pending = ref(false)
const uncertain = ref(false), checked = ref(false), acknowledged = ref(false), dirty = ref(false)
const summary = ref<HTMLElement>(), form = ref<HTMLFormElement>()
const live = useGroupLifetime(() => dirty.value, () => pending.value)
let reader: AbortController | undefined
const ready = computed(() => !!saved.value && !loading.value && !readError.value)
const pages = computed(() => Math.max(1, Math.ceil((saved.value?.total || 0) / 20)))
async function load(page = saved.value?.page || 1) {
  if (loading.value || pending.value) return
  reader = new AbortController(); const current = reader
  loading.value = true; readError.value = undefined
  try {
    const value = await groupsApi.list(page, current.signal)
    if (live()) { saved.value = value; if (uncertain.value) checked.value = true }
  } catch (error) { if (live()) readError.value = failure(error) }
  finally { if (reader === current) loading.value = false }
}
onMounted(() => load())
onBeforeUnmount(() => reader?.abort())
function changeMode(next: 'create' | 'join') {
  if (pending.value || next === mode.value) return
  if ((dirty.value || uncertain.value) && !window.confirm('切换后会清空当前输入，请先核对尚未确认的结果。确定切换吗？')) return
  mode.value = next; fields.name = ''; fields.description = ''; fields.invite_code = ''
  errors.value = {}; message.value = ''; writeError.value = undefined
  dirty.value = uncertain.value = checked.value = acknowledged.value = false
}
async function focusSummary() { await nextTick(); summary.value?.focus() }
function focusField(field: string) { form.value?.querySelector<HTMLElement>(`[name="${field}"]`)?.focus() }
function edited(event: Event) {
  dirty.value = true
  const field = (event.target as HTMLInputElement).name
  if ((field === 'name' || field === 'description' || field === 'invite_code') && errors.value[field] && !validateGroup(mode.value, fields)[field]) errors.value[field] = undefined
  if (!uncertain.value) { message.value = ''; writeError.value = undefined }
}
function blur(field: keyof GroupErrors) { errors.value = { ...errors.value, [field]: validateGroup(mode.value, fields)[field] } }
async function submit() {
  if (!ready.value || pending.value || (uncertain.value && !(checked.value && acknowledged.value))) return
  errors.value = validateGroup(mode.value, fields)
  if (Object.values(errors.value).some(Boolean)) { message.value = '请检查以下填写内容。'; await focusSummary(); return }
  pending.value = true; message.value = ''; writeError.value = undefined
  try {
    const value = mode.value === 'create' ? await groupsApi.create({ name: fields.name.trim(), description: fields.description })
      : await groupsApi.join(fields.invite_code.trim().toUpperCase())
    if (!live()) return
    dirty.value = false; pending.value = false
    await router.push({ path: `/groups/${value.id}`, state: { groupNotice: mode.value === 'create' ? '小组创建成功。' : '已加入小组；重复加入不会增加成员。' } })
  } catch (error) {
    if (!live()) return
    writeError.value = failure(error)
    uncertain.value = writeError.value.uncertain; checked.value = acknowledged.value = false
    message.value = uncertain.value ? '提交结果尚未确认，请先核对小组列表。' : writeError.value.message
    if (writeError.value.status === 422) {
      const details = writeError.value.details as { fields?: { location?: unknown[] }[] } | undefined
      for (const item of details?.fields || []) {
        const field = item.location?.[1]
        if (field === 'name' || field === 'description' || field === 'invite_code') errors.value[field] = '请检查此项的格式和长度。'
      }
    }
    await focusSummary()
  } finally { pending.value = false }
}
</script>

<template>
  <section class="group-heading"><div><h1>我的小组</h1><p class="muted">创建小组，或使用邀请码加入。</p></div><button class="secondary" :disabled="loading || pending" @click="load()">{{ loading ? '正在读取…' : '刷新列表' }}</button></section>
  <div class="groups-layout">
    <section class="groups-list" aria-label="我的小组列表" :aria-busy="loading">
      <StateNotice v-if="loading && !saved" kind="loading" title="正在读取小组" message="请稍候，你的小组马上呈现。" />
      <StateNotice v-if="readError" kind="error" title="小组列表暂时无法读取" :message="readError.message" :request-id="readError.requestId"><button :disabled="loading" @click="load()">重新读取</button></StateNotice>
      <p v-if="saved && (loading || readError)" class="muted">下方保留上次读取的内容，请重新读取后再提交。</p>
      <template v-if="saved">
        <p class="list-count">共 {{ saved.total }} 个小组 </p>
        <StateNotice v-if="!saved.items.length && !loading && !readError" kind="empty" :title="saved.total ? '这一页还没有小组' : '尚未加入小组'" message="创建一个课程小组，或用负责人分享的邀请码加入。" />
        <article v-for="(group, index) in saved.items" :key="group.id" class="group-card">
          <div class="group-card-top"><span class="puzzle-label" aria-hidden="true">{{ String((saved.page - 1) * 20 + index + 1).padStart(2, '0') }}</span><span class="role-badge">{{ group.owner_id === session.state.user?.id ? '负责人' : '成员' }}</span></div>
          <h2><RouterLink :to="`/groups/${group.id}`">{{ group.name }}</RouterLink></h2><p class="group-preview">{{ group.description || '暂无小组说明。' }}</p>
          <div class="group-card-bottom"><span>{{ group.member_count }} / 20 位成员</span><RouterLink :to="`/groups/${group.id}`">进入小组 <span aria-hidden="true">↗</span></RouterLink></div>
        </article>
        <nav v-if="pages > 1 || saved.page > 1" class="pagination" aria-label="小组分页"><button class="secondary" :disabled="loading || pending || saved.page <= 1" @click="load(saved.page - 1)">上一页</button><span>第 {{ saved.page }} / {{ pages }} 页</span><button class="secondary" :disabled="loading || pending || saved.page >= pages" @click="load(saved.page + 1)">下一页</button></nav>
      </template>
    </section>
    <section class="group-form-card" :aria-busy="pending">

      <div class="mode-switch" aria-label="选择小组操作"><button type="button" :aria-pressed="mode === 'create'" :disabled="pending" @click="changeMode('create')">创建小组</button><button type="button" :aria-pressed="mode === 'join'" :disabled="pending" @click="changeMode('join')">邀请码加入</button></div>
      <h2>{{ mode === 'create' ? '创建小组' : '加入小组' }}</h2><p class="muted">{{ mode === 'create' ? '你将成为负责人。创建后可复制邀请码给同学。' : '输入负责人分享的12位邀请码，加入后即可查看小组。' }}</p>
      <section v-if="message" ref="summary" class="form-summary" :class="{ uncertain }" role="alert" tabindex="-1"><p>{{ message }}</p><ul><template v-for="(error, field) in errors" :key="field"><li v-if="error"><button class="text-button" type="button" @click="focusField(field)">{{ error }}</button></li></template></ul><small v-if="writeError?.requestId">请求编号：{{ writeError.requestId }}</small>
        <template v-if="uncertain"><p>{{ mode === 'create' ? '请查看列表，找到后进入小组核对。名称可能重复，不能仅凭同名确定创建结果；再次提交可能产生重复小组。' : '请查看列表核对。再次加入同一小组不会产生重复成员。' }}</p><button class="secondary" :disabled="loading" @click="load(1)">核对小组列表</button><label v-if="checked" class="retry-check"><input v-model="acknowledged" type="checkbox">{{ mode === 'create' ? '我已核对，仍需重新提交创建（可能重复）' : '我已核对，仍需再次提交加入' }}</label></template>
      </section>
      <form ref="form" novalidate @submit.prevent="submit" @input="edited"><fieldset :disabled="pending || !ready">
        <template v-if="mode === 'create'"><div class="form-field"><label for="group-name">小组名称（必填）</label><input id="group-name" v-model="fields.name" name="name" required maxlength="200" placeholder="例如：软件工程课程小组" :aria-invalid="!!errors.name" aria-describedby="group-name-error" @blur="blur('name')"><p v-if="errors.name" id="group-name-error" class="field-error">{{ errors.name }}</p></div><div class="form-field"><label for="group-description">小组说明（选填）</label><textarea id="group-description" v-model="fields.description" name="description" rows="4" maxlength="20000" :aria-invalid="!!errors.description" aria-describedby="description-help description-error" @blur="blur('description')"/><small id="description-help">{{ Array.from(fields.description).length }} / 10000 字符</small><p v-if="errors.description" id="description-error" class="field-error">{{ errors.description }}</p></div></template>
        <div v-else class="form-field"><label for="invite-code">邀请码（必填）</label><input id="invite-code" v-model="fields.invite_code" name="invite_code" autocomplete="off" :spellcheck="false" maxlength="32" placeholder="12位字母或数字" required :aria-invalid="!!errors.invite_code" aria-describedby="invite-help invite-error" @blur="blur('invite_code')"><small id="invite-help">不区分大小写，每个小组最多20人。</small><p v-if="errors.invite_code" id="invite-error" class="field-error">{{ errors.invite_code }}</p></div>
        <button class="auth-submit" type="submit" :disabled="uncertain && !(checked && acknowledged)">{{ pending ? '正在提交…' : mode === 'create' ? '创建小组' : '加入小组' }}</button>
      </fieldset></form><p v-if="dirty" class="form-help">输入尚未提交，离开页面后会清空。</p>
    </section>
  </div>
</template>
