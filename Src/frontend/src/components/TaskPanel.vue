<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import type {ApiFailure} from '../api/client'
import {useSession} from '../auth/session'
import {groupsApi,type Member} from '../groups/api'
import {failure,useGroupLifetime} from '../groups/forms'
import {beijing} from '../polls/editor'
import {tasksApi,states,type Status,type Task,type TaskPage} from '../tasks/api'
import StateNotice from './StateNotice.vue'
import TaskCreator from './TaskCreator.vue'
const props=defineProps<{groupId?:number;meetingId?:number}>()
const session=useSession(),page=ref<TaskPage>(),filter=ref<''|Status>(''),loading=ref(false),error=ref<ApiFailure>(),writeError=ref<ApiFailure>(),pending=ref(false),uncertain=ref(false),notice=ref('')
const ownerId=ref<number>(),members=ref<Member[]>([]),title=props.meetingId?'会议任务':props.groupId?'小组任务':'待办列表'
const owner=computed(()=>ownerId.value===session.state.user?.id),pages=computed(()=>Math.max(1,Math.ceil((page.value?.total||0)/20)))
const live=useGroupLifetime(()=>uncertain.value,()=>pending.value)
const canChange=(task:Task)=>owner.value||task.assignee_id===session.state.user?.id
const assignee=(task:Task)=>members.value.find(person=>person.user_id===task.assignee_id)?.username||(task.assignee_id===session.state.user?.id?session.state.user.username:'小组成员')
let reader:AbortController|undefined
async function refresh(number=page.value?.page||1,nextFilter:typeof filter.value=filter.value){
 if(loading.value||pending.value)return
 loading.value=true;error.value=undefined;reader=new AbortController()
 try{
  const [value,group,roster]=await Promise.all([tasksApi.list({...props,userId:session.state.user!.id},number,nextFilter,reader.signal),props.groupId?groupsApi.get(props.groupId,reader.signal):undefined,props.groupId?groupsApi.members(props.groupId,reader.signal):[]])
  if(!live())return
  page.value=value;filter.value=nextFilter;ownerId.value=group?.owner_id;members.value=roster;uncertain.value=false;writeError.value=undefined
 }catch(value){if(live()){error.value=failure(value);if([403,404].includes(error.value.status||0)){page.value=undefined;members.value=[];ownerId.value=undefined;uncertain.value=false}}}
 finally{loading.value=false}
}
async function change(task:Task,event:Event){
 const select=event.target as HTMLSelectElement,status=select.value as Status;select.value=task.status
 if(!canChange(task)||pending.value||loading.value||error.value||uncertain.value||status===task.status)return
 pending.value=true;notice.value='';writeError.value=undefined
 try{await tasksApi.status(task,status);if(!live())return;pending.value=false;notice.value='任务状态已保存。';await refresh(1)}
 catch(value){if(live()){writeError.value=failure(value);uncertain.value=true}}
 finally{pending.value=false}
}
function filterChanged(event:Event){const select=event.target as HTMLSelectElement;const value=select.value as typeof filter.value;select.value=filter.value;void refresh(1,value)}
function created(){notice.value='任务已创建。';void refresh(1)}
onMounted(()=>refresh())
onBeforeUnmount(()=>reader?.abort())
</script>
<template>
 <section class="task-panel" :aria-label="title"><div class="section-heading"><h2>{{title}}</h2><button class="secondary" :disabled="loading||pending" @click="refresh()">{{loading?'正在读取…':'刷新任务'}}</button></div>
  <div class="task-toolbar"><label>任务状态 <select aria-label="任务状态" :value="filter" :disabled="loading||pending||uncertain" @change="filterChanged"><option value="">{{groupId?'全部状态':'未完成任务'}}</option><option v-for="(label,value) in states" :key="value" :value="value">{{label}}</option></select></label><span v-if="page" class="form-help">{{page.total}} 项任务</span></div>
  <p v-if="notice" class="success-note" role="status">{{notice}}</p>
  <StateNotice v-if="loading&&!page" kind="loading" title="正在读取任务" message="请稍候。"/>
  <StateNotice v-if="error" kind="error" title="任务列表暂时无法读取" :message="error.message" :request-id="error.requestId"><button :disabled="loading||pending" @click="refresh()">重新读取任务</button></StateNotice>
  <StateNotice v-if="writeError" kind="uncertain" title="任务状态需要核对" :message="writeError.message" :request-id="writeError.requestId"><button :disabled="loading||pending" @click="refresh()">核对最新任务</button></StateNotice>
  <p v-if="page&&(loading||error)" class="matrix-stale">保留上次读取的任务，请刷新成功后再操作。</p>
  <p v-if="page&&!page.items.length&&!error&&!loading" class="task-empty">{{filter?'当前状态下没有任务。':groupId?'还没有任务，把会议决定拆成下一步行动吧。':'暂时没有未完成的任务。'}}</p>
  <ul v-if="page" class="task-list"><li v-for="task in page.items" :key="task.id" :data-task="task.id"><div class="task-main"><h3>{{task.title}}</h3><p class="task-meta">{{assignee(task)}} · 截止 {{beijing(task.due_at).replace('T',' ')}}（北京时间）<span v-if="task.status!=='DONE'&&Date.parse(task.due_at)<Date.now()" class="task-overdue">已逾期</span></p><p v-if="task.description" class="plain-text">{{task.description}}</p><RouterLink v-if="!meetingId" :to="`/meetings/${task.meeting_id}`">查看会议 →</RouterLink><small v-if="task.completed_at" class="form-help">完成于 {{beijing(task.completed_at).replace('T',' ')}}</small></div><label v-if="canChange(task)" class="task-status">状态<select :aria-label="`${task.title}的状态`" :value="task.status" :disabled="loading||pending||uncertain||!!error" @change="change(task,$event)"><option v-for="(label,value) in states" :key="value" :value="value">{{label}}</option></select></label><span v-else class="role-badge">{{states[task.status]}}</span></li></ul>
  <nav v-if="page&&(pages>1||page.page>1)" class="pagination" aria-label="任务分页"><button class="secondary" :disabled="loading||pending||page.page<=1" @click="refresh(page.page-1)">上一页任务</button><span>第 {{page.page}}/{{pages}} 页</span><button class="secondary" :disabled="loading||pending||page.page>=pages" @click="refresh(page.page+1)">下一页任务</button></nav>
  <TaskCreator v-if="meetingId&&groupId&&owner" :meeting-id="meetingId" :group-id="groupId" :members="members" :disabled="loading||pending||uncertain||!!error" @created="created" @reconcile="notice='';refresh(1)"/>
 </section>
</template>
