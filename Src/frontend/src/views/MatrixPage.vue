<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import StateNotice from '../components/StateNotice.vue'
import { ApiFailure } from '../api/client'
import ConfirmMeeting from '../components/ConfirmMeeting.vue'
import { groupsApi } from '../groups/api'
import { meetingsApi, type Meeting } from '../meetings/api'
import { useSession } from '../auth/session'
import { failure, useGroupLifetime } from '../groups/forms'
import { pollsApi, statusLabel, type Poll } from '../polls/api'
import { beijing } from '../polls/editor'
import { options } from '../votes/api'
import { matrixApi, availabilityLabel, cellIndex, cellKey, type Matrix } from '../votes/matrix'
import { recommendationsApi, type Recommendation } from '../votes/recommendations'

const id = String(useRoute().params.pollId), session = useSession()
const poll = ref<Poll>(), matrix = ref<Matrix>(), loading = ref(false), error = ref<ApiFailure>(), checkedAt = ref('')
const recommendations = ref<Recommendation[]>([]), showAll = ref(false)
const ownerId = ref<number>(), meeting = ref<Meeting|null>(null)
const confirmation = ref<{open:(slotId:number)=>void;canChoose:boolean}>()
const isOwner = computed(()=>ownerId.value===session.state.user?.id)
const visibleRecommendations = computed(() => showAll.value ? recommendations.value : recommendations.value.slice(0,3))
const allConflicted = computed(() => recommendations.value.length > 0 && recommendations.value.every(item=>item.unavailable_count>0))
const requiredUnknown = computed(() => recommendations.value.some(item=>item.required_unsubmitted_count>0))
const slotFor = (id:number) => matrix.value!.slots.find(slot=>slot.id===id)!
const candidateNumber = (id:number) => matrix.value!.slots.findIndex(slot=>slot.id===id)+1
const conflictNames = (ids:number[]) => ids.map(id=>matrix.value?.participants.find(person=>person.user_id===id)?.username).join('、')
const live = useGroupLifetime(() => false, () => false)
let controller: AbortController | undefined
const index = computed(() => matrix.value ? cellIndex(matrix.value) : new Map())
const valueAt = (userId: number, slotId: number) => index.value.get(cellKey(userId,slotId)) ?? null
const canFill = computed(() => matrix.value?.effective_status === 'OPEN' && matrix.value.participants.some(person => person.user_id === session.state.user?.id))
const unsubmitted = computed(() => matrix.value?.participants.filter(person => person.submitted_at === null) || [])
const proportion = computed(() => matrix.value?.progress.participant_count ? matrix.value.progress.submitted_count/matrix.value.progress.participant_count*100 : 0)
async function refresh() {
  if (loading.value) return
  loading.value = true; error.value = undefined; controller = new AbortController()
  try {
    const [detail,result] = await Promise.all([pollsApi.get(id,controller.signal),matrixApi.get(id,controller.signal)])
    if (!live()) return
    const ranking = ['OPEN','CLOSED','CONFIRMED'].includes(result.effective_status) ? await recommendationsApi.get(result,controller.signal) : []
    const [group,saved] = await Promise.all([groupsApi.get(detail.group_id,controller.signal),meetingsApi.get(detail,controller.signal)])
    if (!live()) return
    if ((result.effective_status==='CONFIRMED') !== (saved!==null)) throw new ApiFailure('protocol','会议状态刚刚发生变化，请刷新核对。')
    ownerId.value=group.owner_id; meeting.value=saved
    poll.value = detail; matrix.value = result; recommendations.value = ranking; checkedAt.value = beijing(new Date().toISOString()).replace('T',' ')
  } catch (value) {
    if (!live()) return
    error.value = failure(value)
    if ([403,404].includes(error.value.status || 0)) { poll.value = undefined; matrix.value = undefined; recommendations.value = []; checkedAt.value = ''; meeting.value=null;ownerId.value=undefined }
  } finally { loading.value = false }
}
onMounted(() => refresh())
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <RouterLink class="back-link" :to="poll ? `/groups/${poll.group_id}` : '/groups'">← 返回小组</RouterLink>
  <section class="group-heading"><div><p class="eyebrow">MEETFLOW / 拼出共同的时间</p><h1>排期结果</h1><p class="muted">看看大家的时间，找到可以一起讨论的可能。</p></div><button class="secondary" :disabled="loading" @click="refresh">{{ loading ? '正在刷新…' : '刷新' }}</button></section>
  <StateNotice v-if="loading && !matrix" kind="loading" title="正在读取时间矩阵" message="正在核对大家已保存的填写结果。" />
  <StateNotice v-if="error" kind="error" :title="[403,404].includes(error.status || 0) ? '未找到可访问的排期' : '排期结果暂时无法读取'" :message="error.message" :request-id="error.requestId"><button :disabled="loading" @click="refresh">重新读取矩阵</button></StateNotice>
  <p v-if="matrix && (loading || error)" class="matrix-stale" role="status">下方保留上次读取的结果，请刷新成功后再核对。</p>
  <template v-if="matrix && poll">
    <section class="vote-intro"><div class="section-heading"><h2>{{ poll.title }}</h2><span class="role-badge">{{ statusLabel[matrix.effective_status] }}</span></div><p class="muted">{{ poll.location || '地点待定' }} · 填写截止 {{ beijing(poll.response_deadline).replace('T',' ') }}（北京时间）</p><div class="matrix-links"><RouterLink class="button-link" :to="`/polls/${poll.id}/edit`">排期详情 →</RouterLink><RouterLink v-if="canFill" class="button-link" :to="`/polls/${poll.id}/vote`">填写我的时间</RouterLink></div></section>
    <section class="matrix-progress" aria-labelledby="progress-heading"><div class="section-heading"><h2 id="progress-heading">提交进度</h2><span class="progress-count">{{ matrix.progress.submitted_count }}/{{ matrix.progress.participant_count }} 人已提交</span></div><div class="progress-track" role="progressbar" aria-label="提交进度" :aria-valuenow="matrix.progress.submitted_count" aria-valuemin="0" :aria-valuemax="Math.max(1,matrix.progress.participant_count)" :aria-valuetext="`${matrix.progress.submitted_count}/${matrix.progress.participant_count} 人已提交`"><span :style="{ width: `${proportion}%` }"/></div><p v-if="!matrix.participants.length" class="muted">负责人尚未选择参与者。</p><p v-else-if="unsubmitted.length" class="muted">未提交：{{ unsubmitted.map(person => person.username).join('、') }}</p><p v-else class="muted">所有参与者均已提交。</p><p class="form-help">仅统计已保存的答案。上次读取：{{ checkedAt }}（北京时间）</p></section>
    <section class="recommendations-section" aria-labelledby="recommendations-heading"><div class="section-heading"><h2 id="recommendations-heading">推荐时间</h2></div>
      <ConfirmMeeting ref="confirmation" :poll="poll" :matrix="matrix" :recommendations="recommendations" :is-owner="isOwner" :meeting="meeting" :disabled="loading||!!error" :refresh="refresh" />
      <p v-if="matrix.effective_status === 'DRAFT'" class="muted">发布排期后可以查看推荐时间。</p><p v-else-if="matrix.effective_status === 'CANCELLED'" class="muted">排期已取消，不再生成推荐。</p>
      <template v-else><p v-if="requiredUnknown" class="ranking-warning" role="status">还有必到成员未填写，出席情况尚未确定。</p><p v-if="allConflicted" class="ranking-warning" role="status">每个候选时间都有成员没空，请先查看冲突；排名不代表全员可参加。</p>
        <ol class="recommendation-list"><li v-for="item in visibleRecommendations" :key="item.slot_id" :data-recommendation="item.slot_id" class="recommendation-item" :class="{ 'first-ranked': item.rank===1 }"><div class="recommendation-top"><span class="ranking-number">{{ String(item.rank).padStart(2,'0') }}</span><div class="recommendation-time"><span class="form-help">候选 {{ candidateNumber(item.slot_id) }}{{ item.rank===1 ? ' · 优先比较' : '' }}</span><h3>{{ beijing(slotFor(item.slot_id).start_at).replace('T',' ') }} — {{ beijing(slotFor(item.slot_id).end_at).slice(0,10) === beijing(slotFor(item.slot_id).start_at).slice(0,10) ? beijing(slotFor(item.slot_id).end_at).slice(11) : beijing(slotFor(item.slot_id).end_at).replace('T',' ') }}</h3></div><div class="recommendation-score"><strong>{{ item.score }}</strong><span>最终分</span></div></div>
          <div class="recommendation-counts"><span>有空 <strong>{{ item.available_count }}</strong></span><span>勉强 <strong>{{ item.maybe_count }}</strong></span><span>没空 <strong>{{ item.unavailable_count }}</strong></span><span>未填 <strong>{{ item.unsubmitted_count }}</strong></span></div><div class="recommendation-risks"><span v-if="item.required_unavailable_count" class="risk-conflict">必到没空 {{ item.required_unavailable_count }} 人</span><span v-if="item.required_unsubmitted_count" class="risk-unknown">必到未填 {{ item.required_unsubmitted_count }} 人</span><span v-if="item.required_maybe_count" class="risk-maybe">必到勉强 {{ item.required_maybe_count }} 人</span></div>
          <details class="recommendation-reason"><summary>分数组成与推荐理由</summary><p>{{ item.reason }}</p><p v-if="item.conflict_user_ids.length">没空成员：{{ conflictNames(item.conflict_user_ids) }}</p></details><button v-if="isOwner&&matrix.effective_status==='CLOSED'&&!meeting" class="choose-time" :disabled="!confirmation?.canChoose" @click="confirmation?.open(item.slot_id)">选择这个时间</button></li></ol>
        <button v-if="recommendations.length>3" type="button" class="text-button" :aria-expanded="showAll" @click="showAll=!showAll">{{ showAll ? '收起其余候选' : `展开其余 ${recommendations.length-3} 个候选` }}</button>
        <details class="ranking-rule"><summary>排序依据</summary><p>先比较必到成员没空人数，越少越优先；再比较最终分和有空人数。仍相同时，按开始、结束时间先后排列，并保持固定顺序。推荐仅供比较，会议时间由负责人确认。</p></details></template>
    </section>
    <section class="matrix-card"><div class="section-heading"><h2>时间矩阵</h2><span class="form-help">北京时间</span></div><ul class="matrix-legend" aria-label="状态图例"><li v-for="option in options" :key="option.value"><span :class="['matrix-state',option.value.toLowerCase()]"><span aria-hidden="true">{{ option.symbol }}</span> {{ option.label }}</span></li><li><span class="matrix-state unknown">— 未填</span></li></ul>
      <p v-if="!matrix.slots.length" class="muted">尚未设置候选时间，负责人设置后可在这里查看。</p><p v-else-if="!matrix.participants.length" class="muted">尚无参与者，选择参与者后会显示时间矩阵。</p>
      <div v-else class="matrix-scroll" role="region" aria-label="时间矩阵，可横向滚动" tabindex="0"><table class="time-matrix"><caption>参与者与候选时间；未填表示未知，不计作有空或没空。</caption><thead><tr><th scope="col" class="matrix-person">参与者</th><th v-for="(slot,column) in matrix.slots" :key="slot.id" scope="col"><span class="candidate-label">候选 {{ column+1 }}</span><strong>{{ beijing(slot.start_at).slice(0,10) }}</strong><span>{{ beijing(slot.start_at).slice(11) }} — {{ beijing(slot.end_at).slice(0,10) === beijing(slot.start_at).slice(0,10) ? beijing(slot.end_at).slice(11) : beijing(slot.end_at).replace('T',' ') }}</span></th></tr></thead>
        <tbody><tr v-for="person in matrix.participants" :key="person.user_id" :class="{ 'matrix-me': person.user_id === session.state.user?.id }"><th scope="row" class="matrix-person"><div class="matrix-person-name"><strong :title="person.username">{{ person.username }}</strong><span v-if="person.importance === 'REQUIRED'" class="role-badge">必到</span></div><small :title="person.submitted_at ? beijing(person.submitted_at).replace('T',' ')+'（北京时间）' : ''">{{ person.submitted_at ? '已提交' : '未提交' }}</small></th><td v-for="slot in matrix.slots" :key="slot.id" :data-user="person.user_id" :data-slot="slot.id"><span :class="['matrix-state',valueAt(person.user_id,slot.id)?.toLowerCase() || 'unknown']"><span aria-hidden="true">{{ options.find(option => option.value === valueAt(person.user_id,slot.id))?.symbol || '—' }}</span> {{ availabilityLabel(valueAt(person.user_id,slot.id)) }}</span></td></tr></tbody>
        <tfoot><tr><th scope="row" class="matrix-person">时段统计<small>按已保存答案</small></th><td v-for="slot in matrix.slots" :key="slot.id"><div class="slot-counts"><span>有空 <strong>{{ slot.available_count }}</strong></span><span>勉强 <strong>{{ slot.maybe_count }}</strong></span><span>没空 <strong>{{ slot.unavailable_count }}</strong></span><span>未填 <strong>{{ slot.unanswered_count }}</strong></span></div></td></tr></tfoot></table></div>
    </section>
  </template>
</template>
