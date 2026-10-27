<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,ref} from 'vue'
import {useSession} from '../auth/session'
import {readDashboard,type Dashboard} from '../dashboard'
import {failure,useGroupLifetime} from '../groups/forms'
import type {ApiFailure} from '../api/client'
import {tasksApi,states,type Task} from '../tasks/api'
import {beijing} from '../polls/editor'
import StateNotice from '../components/StateNotice.vue'
const session=useSession(),saved=ref<Dashboard>(),loading=ref(false),pending=ref(false),uncertain=ref(false),error=ref<ApiFailure>(),writeError=ref<ApiFailure>()
const live=useGroupLifetime(()=>uncertain.value,()=>pending.value)
const date=computed(()=>saved.value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(new Date(saved.value.generated_at)):'')
const minute=(value:string)=>beijing(value).replace('T',' ')
let reader:AbortController|undefined
async function refresh(){
 if(loading.value||pending.value)return
 loading.value=true;error.value=undefined;reader=new AbortController()
 try{const value=await readDashboard(session.state.user!.id,reader.signal);if(live()){saved.value=value;uncertain.value=false;writeError.value=undefined}}
 catch(value){if(live())error.value=failure(value)}finally{loading.value=false}
}
async function complete(task:Task){
 if(loading.value||pending.value||uncertain.value||error.value)return
 pending.value=true;writeError.value=undefined
 try{await tasksApi.status(task,'DONE');if(!live())return;pending.value=false;await refresh()}
 catch(value){if(live()){writeError.value=failure(value);uncertain.value=true}}finally{pending.value=false}
}
onMounted(refresh);onBeforeUnmount(()=>reader?.abort())
</script>
<template>
 <section class="dashboard-page" :aria-busy="loading||pending">
  <div class="dashboard-heading"><div><h1>工作台</h1><p v-if="saved" class="dashboard-meta">{{date}}</p></div><button class="secondary" :disabled="loading||pending" @click="refresh">{{loading?'正在读取…':'刷新'}}</button></div>
  <StateNotice v-if="loading&&!saved" kind="loading" title="正在读取工作台" message="请稍候。"/>
  <StateNotice v-if="error" kind="error" title="工作台暂时无法读取" :message="error.message" :request-id="error.requestId"><button :disabled="loading||pending" @click="refresh">重新读取工作台</button></StateNotice>
  <StateNotice v-if="writeError" kind="uncertain" title="任务结果需要核对" :message="writeError.message" :request-id="writeError.requestId"><button :disabled="loading||pending" @click="refresh">核对最新工作台</button></StateNotice>
  <p v-if="saved&&(loading||error)" class="dashboard-meta">保留上次读取的数据，请刷新成功后再操作。</p>
  <template v-if="saved">
   <div class="dashboard-summary"><RouterLink to="/groups"><small>待填写排期</small><strong data-count="polls">{{saved.pending_polls.total}}</strong></RouterLink><a href="#dashboard-meetings"><small>近期会议</small><strong data-count="meetings">{{saved.upcoming_meetings.total}}</strong></a><RouterLink to="/tasks/mine"><small>未完成任务</small><strong data-count="tasks">{{saved.tasks.total}}</strong></RouterLink></div>
   <div class="dashboard-columns"><div><section class="dashboard-section"><div class="dashboard-section-heading"><h2>待填写</h2><RouterLink to="/groups">进入小组 →</RouterLink></div><p v-if="!saved.pending_polls.items.length" class="dashboard-empty">暂无待填写排期。</p><article v-for="poll in saved.pending_polls.items" :key="poll.id" class="dashboard-row" :data-pending-poll="poll.id"><div class="dashboard-row-main"><h3>{{poll.title}}</h3><p class="dashboard-meta">{{poll.group_name}} · {{poll.candidate_count}}个候选时段 · {{poll.submitted_count}}/{{poll.participant_count}}人已填写</p><p class="dashboard-meta">{{minute(poll.response_deadline)}} 截止</p></div><RouterLink class="button-link" :to="`/polls/${poll.id}/vote`">填写时间</RouterLink></article></section>
   <section class="dashboard-section"><div class="dashboard-section-heading"><h2>我的任务</h2><RouterLink to="/tasks/mine">查看全部 →</RouterLink></div><p v-if="!saved.tasks.items.length" class="dashboard-empty">暂无未完成任务。</p><article v-for="task in saved.tasks.items" :key="task.id" class="dashboard-row" :data-dashboard-task="task.id"><button class="dashboard-complete" role="checkbox" aria-checked="false" :aria-label="`完成：${task.title}`" :disabled="loading||pending||uncertain||!!error" @click="complete(task)"></button><div class="dashboard-row-main"><RouterLink :to="`/meetings/${task.meeting_id}`"><h3>{{task.title}}</h3></RouterLink><p class="dashboard-meta">{{task.group_name}} · {{minute(task.due_at)}} 截止 <span v-if="task.due_at<saved.generated_at" class="dashboard-overdue">已逾期</span></p></div><span class="dashboard-tag">{{states[task.status]}}</span></article></section></div>
   <div><section id="dashboard-meetings" class="dashboard-section"><div class="dashboard-section-heading"><h2>近期会议</h2><small>进行中及未来7天</small></div><p v-if="!saved.upcoming_meetings.items.length" class="dashboard-empty">近期没有会议安排。</p><RouterLink v-for="meeting in saved.upcoming_meetings.items" :key="meeting.id" :to="`/meetings/${meeting.id}`" class="dashboard-row" :data-upcoming-meeting="meeting.id"><div class="dashboard-row-main"><h3>{{meeting.title}}</h3><p class="dashboard-meta">{{minute(meeting.start_at)}} — {{minute(meeting.end_at)}}</p><p class="dashboard-meta">{{meeting.location||'地点待定'}} · {{meeting.group_name}}</p></div></RouterLink></section>
   <section class="dashboard-section"><div class="dashboard-section-heading"><h2>我的小组</h2><RouterLink to="/groups">查看全部 →</RouterLink></div><p v-if="!saved.groups.items.length" class="dashboard-empty">尚未加入小组，可先创建或使用邀请码加入。</p><RouterLink v-for="group in saved.groups.items" :key="group.id" :to="`/groups/${group.id}`" class="dashboard-group"><h3>{{group.name}}</h3><p class="dashboard-meta">{{group.member_count}}位成员 · {{group.owner_id===session.state.user?.id?'负责人':'成员'}}</p></RouterLink></section></div></div>
   <p class="dashboard-footnote">各列表最多显示5项 · 北京时间 · 更新于 {{minute(saved.generated_at)}}</p>
  </template>
 </section>
</template>
<style scoped>
.dashboard-page{padding:28px;background:#fff;border:1px solid #e8e5ed;border-radius:8px;min-width:0}.dashboard-heading,.dashboard-section-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.dashboard-heading{margin-bottom:24px}.dashboard-heading h1{font-size:26px;margin:0}.dashboard-meta{font-size:12px;color:#77717e;margin:6px 0 0;line-height:1.7}.dashboard-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;border-bottom:1px solid #ebe6f0;padding-bottom:24px;margin-bottom:30px}.dashboard-summary>a{border-left:2px solid #e8dff1;padding-left:14px;color:#292d50;text-decoration:none}.dashboard-summary small{display:block;font-size:12px;color:#77717e}.dashboard-summary strong{font-size:26px;font-weight:600;line-height:1.7}.dashboard-columns{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:32px}.dashboard-section{margin-bottom:32px;min-width:0}.dashboard-section-heading h2{font-size:16px;margin:0}.dashboard-section-heading>a,.dashboard-section-heading small{font-size:12px;white-space:nowrap}.dashboard-section-heading>a{color:#7250a1}.dashboard-section-heading small{color:#77717e}.dashboard-row{display:flex;align-items:center;gap:12px;padding:18px 0;border-bottom:1px solid #ebe6f0;text-decoration:none;color:#292d50}.dashboard-row-main{flex:1;min-width:0}.dashboard-row h3,.dashboard-group h3{font-size:14px;line-height:1.6;margin:0;font-weight:550;overflow-wrap:anywhere}.dashboard-row .button-link{background:#7250a1;font-size:12px;min-height:40px;white-space:nowrap;border-radius:5px;padding:10px 12px}.dashboard-row-main>a{color:inherit;text-decoration:none}.dashboard-row-main>a:hover{color:#7250a1}.dashboard-empty{font-size:13px;color:#77717e;padding:18px 0}.dashboard-complete{background:white;border:1.5px solid #c5b6d7;border-radius:50%;width:20px;height:20px;min-height:20px;flex:0 0 20px;padding:0;position:relative}.dashboard-complete::after{content:'';position:absolute;inset:-10px}.dashboard-tag{font-size:11px;padding:3px 7px;white-space:nowrap;border-radius:4px;background:#f0eaf7;color:#60418b}.dashboard-overdue{color:#a55242}.dashboard-group{display:block;text-decoration:none;color:#292d50;border:1px solid #ebe6f0;border-radius:5px;padding:15px;margin-top:12px}.dashboard-footnote{color:#8b8493;font-size:11px;margin-top:20px}
@media(max-width:1000px){.dashboard-columns{grid-template-columns:1fr;gap:0}}
@media(max-width:600px){.dashboard-page{padding:20px 16px}.dashboard-heading h1{font-size:23px}.dashboard-summary{gap:8px}.dashboard-summary>a{padding-left:9px}.dashboard-row{flex-wrap:wrap}.dashboard-row>.button-link{margin-left:auto}.dashboard-row-main{flex-basis:65%}.dashboard-tag{margin-left:auto}.dashboard-complete{align-self:flex-start;margin-top:3px}.dashboard-section-heading{flex-wrap:wrap}}
</style>
