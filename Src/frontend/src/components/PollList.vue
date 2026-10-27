<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import StateNotice from './StateNotice.vue'
import { useSession } from '../auth/session'
import { pollsApi, statusLabel, type PollPage } from '../polls/api'
import { beijing } from '../polls/editor'
import { failure } from '../groups/forms'
import type { ApiFailure } from '../api/client'
const props = defineProps<{ groupId: number; canCreate: boolean }>()
const session = useSession()
const canVote = (poll: PollPage['items'][number]) => poll.effective_status !== 'DRAFT' && poll.participants.some(person => person.user_id === session.state.user?.id)
const saved = ref<PollPage>(), loading = ref(false), error = ref<ApiFailure>()
const pages = computed(() => Math.max(1, Math.ceil((saved.value?.total || 0) / 20)))
let controller: AbortController | undefined, alive = true
async function refresh(page = saved.value?.page || 1) {
  if (loading.value) return
  controller = new AbortController(); loading.value = true; error.value = undefined
  try { const result = await pollsApi.list(props.groupId, page, controller.signal); if (alive) saved.value = result }
  catch (value) { if (alive) { error.value = failure(value); if (error.value.status === 404) saved.value = undefined } }
  finally { loading.value = false }
}
onMounted(() => refresh())
onBeforeUnmount(() => { alive = false; controller?.abort() })
defineExpose({ refresh })
</script>
<template>
  <section class="poll-list-card" :aria-busy="loading"><div class="section-heading"><div class="poll-heading-title"><h2>小组排期</h2><button class="refresh-icon" :disabled="loading" :aria-label="loading ? '正在读取排期' : '刷新排期'" title="刷新排期" @click="refresh()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 1 1-2.35-5.65L20 7"/><path d="M20 3v4h-4"/></svg></button></div><RouterLink v-if="canCreate" class="button-link" :to="`/groups/${groupId}/polls/new`">＋ 发起排期</RouterLink></div>
    <StateNotice v-if="loading && !saved" kind="loading" title="正在读取排期" message="请稍候。" />
    <StateNotice v-if="error" kind="error" title="排期列表暂时无法读取" :message="error.message" :request-id="error.requestId"><button :disabled="loading" @click="refresh()">重新读取排期</button></StateNotice>
    <p v-if="saved && (loading || error)" class="form-help">下方保留上次读取的排期，请刷新核对最新状态。</p>
    <p v-if="saved && !saved.items.length && !error && !loading" class="muted">{{ canCreate ? '还没有排期，从一组候选时间开始吧。' : '还没有排期，等待负责人发起。' }}</p>
    <ul v-if="saved" class="poll-list"><li v-for="poll in saved.items" :key="poll.id"><div><RouterLink :to="`/polls/${poll.id}/edit`">{{ poll.title }}</RouterLink><small>填写截止：{{ beijing(poll.response_deadline).replace('T', ' ').slice(0,16) }}（北京时间）</small><RouterLink v-if="canVote(poll)" class="vote-entry" :to="`/polls/${poll.id}/vote`">{{ poll.effective_status === 'OPEN' ? '填写时间 →' : '查看我的填写 →' }}</RouterLink><RouterLink class="matrix-entry" :to="`/polls/${poll.id}/results`">查看矩阵 →</RouterLink></div><span class="role-badge">{{ statusLabel[poll.effective_status] }}</span></li></ul>
    <nav v-if="saved && (pages > 1 || saved.page > 1)" class="pagination" aria-label="排期分页"><button class="secondary" :disabled="loading || saved.page <= 1" @click="refresh(saved.page-1)">上一页排期</button><span>第 {{ saved.page }}/{{ pages }} 页</span><button class="secondary" :disabled="loading || saved.page >= pages" @click="refresh(saved.page+1)">下一页排期</button></nav>
  </section>
</template>
