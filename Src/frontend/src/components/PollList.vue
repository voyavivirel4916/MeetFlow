<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import StateNotice from './StateNotice.vue'
import { useSession } from '../auth/session'
import { pollsApi, statusLabel, type PollPage, type PollView, type OrganizationAction, type Poll } from '../polls/api'
import { beijing } from '../polls/editor'
import { failure, useGroupLifetime } from '../groups/forms'
import type { ApiFailure } from '../api/client'
const props = defineProps<{ groupId: number; canCreate: boolean }>()
const session = useSession()
const canVote = (poll: PollPage['items'][number]) => poll.effective_status !== 'DRAFT' && poll.participants.some(person => person.user_id === session.state.user?.id)
const saved = ref<PollPage>(), loading = ref(false), error = ref<ApiFailure>()
const view=ref<PollView>('current'),pending=ref(false),uncertain=ref(false),writeError=ref<ApiFailure>()
const dialog=ref<HTMLDialogElement>(),selected=ref<{poll:Poll;action:OrganizationAction}>()
useGroupLifetime(()=>uncertain.value,()=>pending.value)
const views=computed(()=>props.canCreate?['current','history','trash'] as const:['current','history'] as const)
const viewLabels={current:'当前',history:'历史',trash:'回收站'}
const actions:Record<OrganizationAction,{title:string;message:string}>={
 delete:{title:'删除',message:'移入回收站，可由负责人恢复。已有填写记录会保留。'},
 restore:{title:'恢复',message:'恢复原有状态，不会重新开启时间收集。'},
 archive:{title:'归档',message:'移入历史，会议记录和未完成任务仍可查看。'},
 unarchive:{title:'取消归档',message:'将排期放回当前列表，会议和任务不受影响。'},
 cancel:{title:'取消排期',message:'停止收集时间。取消后可移入回收站。'}
}
function actionFor(poll:Poll):OrganizationAction{
 if(view.value==='trash')return 'restore'
 if(poll.effective_status==='CONFIRMED')return view.value==='history'?'unarchive':'archive'
 return poll.effective_status==='OPEN'?'cancel':'delete'
}
async function open(poll:Poll,action:OrganizationAction){
 if(!props.canCreate||loading.value||pending.value||uncertain.value||error.value)return
 selected.value={poll,action};await nextTick();dialog.value?.showModal()
}
function dismiss(event?:Event){if(pending.value){event?.preventDefault();return}dialog.value?.close();selected.value=undefined}
async function confirm(){
 const choice=selected.value;if(!choice||pending.value)return
 pending.value=true;writeError.value=undefined
 try{await pollsApi.organize(choice.poll.id,choice.action);if(!alive)return;pending.value=false;dismiss();await refresh(1)}
 catch(value){if(alive){writeError.value=failure(value);uncertain.value=true;pending.value=false;dismiss()}}
 finally{pending.value=false}
}
const pages = computed(() => Math.max(1, Math.ceil((saved.value?.total || 0) / 20)))
let controller: AbortController | undefined, alive = true
async function refresh(page = saved.value?.page || 1, nextView:PollView=view.value) {
  if (loading.value||pending.value) return
  controller = new AbortController(); loading.value = true; error.value = undefined
  try { const result = await pollsApi.list(props.groupId, page, controller.signal,nextView); if (alive) {saved.value = result;view.value=nextView;uncertain.value=false;writeError.value=undefined} }
  catch (value) { if (alive) { error.value = failure(value); if ([403,404].includes(error.value.status||0)) saved.value = undefined } }
  finally { loading.value = false }
}
onMounted(() => refresh())
onBeforeUnmount(() => { alive = false; controller?.abort();dialog.value?.close() })
defineExpose({ refresh })
</script>
<template>
  <section class="poll-list-card" :aria-busy="loading"><div class="section-heading"><div class="poll-heading-title"><h2>小组排期</h2><button class="refresh-icon" :disabled="loading||pending" :aria-label="loading ? '正在读取排期' : '刷新排期'" title="刷新排期" @click="refresh()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 1 1-2.35-5.65L20 7"/><path d="M20 3v4h-4"/></svg></button></div><RouterLink v-if="canCreate" class="button-link" :to="`/groups/${groupId}/polls/new`">＋ 发起排期</RouterLink></div>
    <StateNotice v-if="loading && !saved" kind="loading" title="正在读取排期" message="请稍候。" />
    <nav class="poll-view-tabs" aria-label="排期分类"><button v-for="item in views" :key="item" :aria-pressed="view===item" :disabled="loading||pending" @click="refresh(1,item)">{{viewLabels[item]}}</button></nav>
    <StateNotice v-if="writeError" kind="uncertain" title="请核对排期状态" :message="writeError.message" :request-id="writeError.requestId"><button :disabled="loading||pending" @click="refresh(1)">核对最新排期</button></StateNotice>
    <StateNotice v-if="error" kind="error" title="排期列表暂时无法读取" :message="error.message" :request-id="error.requestId"><button :disabled="loading||pending" @click="refresh()">重新读取排期</button></StateNotice>
    <p v-if="saved && (loading || error)" class="form-help">下方保留上次读取的排期，请刷新核对最新状态。</p>
    <p v-if="saved && !saved.items.length && !error && !loading" class="muted">{{view==='trash'?'回收站为空。':view==='history'?'还没有归档排期。':'暂无当前排期。'}}</p>
    <ul v-if="saved" class="poll-list"><li v-for="poll in saved.items" :key="poll.id" :data-poll="poll.id"><div><strong v-if="view==='trash'">{{poll.title}}</strong><RouterLink v-else :to="`/polls/${poll.id}/edit`">{{ poll.title }}</RouterLink><small>填写截止：{{ beijing(poll.response_deadline).replace('T', ' ').slice(0,16) }}（北京时间）</small><RouterLink v-if="view!=='trash'&&canVote(poll)" class="vote-entry" :to="`/polls/${poll.id}/vote`">{{ poll.effective_status === 'OPEN' ? '填写时间 →' : '查看我的填写 →' }}</RouterLink><RouterLink v-if="view!=='trash'" class="matrix-entry" :to="`/polls/${poll.id}/results`">查看矩阵 →</RouterLink></div><span class="role-badge">{{ statusLabel[poll.effective_status] }}</span><div v-if="canCreate" class="poll-row-actions"><button :class="{danger:actionFor(poll)==='delete'}" :disabled="loading||pending||uncertain||!!error" @click="open(poll,actionFor(poll))">{{actions[actionFor(poll)].title}}</button></div></li></ul>
    <nav v-if="saved && (pages > 1 || saved.page > 1)" class="pagination" aria-label="排期分页"><button class="secondary" :disabled="loading || pending || saved.page <= 1" @click="refresh(saved.page-1)">上一页排期</button><span>第 {{ saved.page }}/{{ pages }} 页</span><button class="secondary" :disabled="loading || pending || saved.page >= pages" @click="refresh(saved.page+1)">下一页排期</button></nav>
    <dialog ref="dialog" class="poll-organize-dialog" aria-labelledby="poll-organize-title" @cancel="dismiss($event)"><template v-if="selected"><h2 id="poll-organize-title">{{actions[selected.action].title}}{{selected.action==='cancel'?'':'排期'}}</h2><p>{{selected.poll.title}}</p><p>{{actions[selected.action].message}}</p><div class="form-actions"><button class="secondary" :disabled="pending" autofocus @click="dismiss()">返回</button><button :disabled="pending" @click="confirm()">{{pending?'正在保存…':'确认'}}</button></div></template></dialog>
  </section>
</template>

<style scoped>
.poll-list-card{border-radius:8px}.poll-view-tabs{display:flex;gap:22px;border-bottom:1px solid #e8e4ed;padding:0;margin:12px 0 2px}.poll-view-tabs button{border:0;border-radius:0;background:none;color:#75707d;padding:10px 0;border-bottom:2px solid transparent;min-height:40px}.poll-view-tabs button[aria-pressed=true]{color:#7250a1;border-color:#7250a1}.poll-list>li{display:grid;grid-template-columns:minmax(0,1fr) 72px 88px;gap:16px;align-items:center}.poll-list>li>div:first-child{min-width:0}.poll-list .role-badge{width:72px;text-align:center;justify-self:center;font-size:12px;background:#f0eaf7;color:#60418b}.poll-row-actions{width:88px;text-align:center}.poll-row-actions button{width:100%;min-height:40px;padding:6px 0;border:0;background:none;color:#7250a1;font-size:13px;white-space:nowrap}.poll-row-actions .danger{color:#a5514e}.poll-organize-dialog{width:min(450px,calc(100vw - 32px));border:1px solid #ddd6e6;border-radius:8px;padding:26px;color:#292d50}.poll-organize-dialog::backdrop{background:#20273750}.poll-organize-dialog p{font-size:14px;line-height:1.7}.poll-organize-dialog .form-actions{justify-content:flex-end}.poll-organize-dialog button:not(.secondary){background:#7250a1}
@media(max-width:760px){.poll-list>li{grid-template-columns:minmax(0,1fr) 72px 88px;gap:8px 12px}.poll-list>li>div:first-child{grid-column:1/-1}.poll-list .role-badge{grid-column:2}.poll-row-actions{grid-column:3}}
</style>
