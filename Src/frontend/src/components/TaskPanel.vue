<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref} from 'vue'
import type {ApiFailure} from '../api/client'
import {useSession} from '../auth/session'
import {groupsApi,type Member} from '../groups/api'
import {failure,useGroupLifetime} from '../groups/forms'
import {beijing} from '../polls/editor'
import {tasksApi,states,type Status,type Task,type TaskPage} from '../tasks/api'
import StateNotice from './StateNotice.vue'
import TaskCreator from './TaskCreator.vue'
import TaskEditor from './TaskEditor.vue'
const progressStates={TODO:'待开始',IN_PROGRESS:'进行中',DONE:'已完成'} as const
const props=defineProps<{groupId?:number;meetingId?:number}>()
const session=useSession(),page=ref<TaskPage>(),filter=ref<''|Status>(''),loading=ref(false),error=ref<ApiFailure>(),writeError=ref<ApiFailure>(),pending=ref(false),uncertain=ref(false)
const ownerId=ref<number>(),members=ref<Member[]>([]),title=props.meetingId?'会议任务':props.groupId?'小组任务':'待办列表'
const owners=ref<Record<number,number>>({}),editing=ref<Task>(),editMembers=ref<Member[]>([])
const searchInput=ref(''),query=ref('')
const operation=ref<{task:Task;status:Status}>(),actionDialog=ref<HTMLDialogElement>()
const owner=computed(()=>ownerId.value===session.state.user?.id),pages=computed(()=>Math.max(1,Math.ceil((page.value?.total||0)/20)))
const live=useGroupLifetime(()=>uncertain.value,()=>pending.value)
const canChange=(task:Task)=>owner.value||task.assignee_id===session.state.user?.id
const canEdit=(task:Task)=>owners.value[task.group_id]===session.state.user?.id
const assignee=(task:Task)=>members.value.find(person=>person.user_id===task.assignee_id)?.username||(task.assignee_id===session.state.user?.id?session.state.user.username:'小组成员')
let reader:AbortController|undefined
async function refresh(number=page.value?.page||1,nextFilter:typeof filter.value=filter.value,nextQuery=query.value){
 if(loading.value||pending.value)return
 loading.value=true;error.value=undefined;reader=new AbortController()
 try{
  const [value,group,roster]=await Promise.all([tasksApi.list({...props,userId:session.state.user!.id},number,nextFilter,reader.signal,nextQuery),props.groupId?groupsApi.get(props.groupId,reader.signal):undefined,props.groupId?groupsApi.members(props.groupId,reader.signal):[]])
  if(!live())return
  const own:Record<number,number>={}
  if(group)own[group.id]=group.owner_id
  else {const groups=await Promise.all([...new Set(value.items.map(task=>task.group_id))].map(id=>groupsApi.get(id,reader!.signal)));for(const item of groups)own[item.id]=item.owner_id}
  if(!live())return
  owners.value=own;page.value=value;filter.value=nextFilter;query.value=nextQuery;ownerId.value=group?.owner_id;members.value=roster;uncertain.value=false;writeError.value=undefined
 }catch(value){if(live()){error.value=failure(value);if([403,404].includes(error.value.status||0)){page.value=undefined;members.value=[];ownerId.value=undefined;uncertain.value=false}}}
 finally{loading.value=false}
}
async function change(task:Task,event:Event){
 const select=event.target as HTMLSelectElement,status=select.value as Status;select.value=task.status
 await setStatus(task,status)
}
async function setStatus(task:Task,status:Status){
 if(!canChange(task)||pending.value||loading.value||error.value||uncertain.value||status===task.status)return
 pending.value=true;writeError.value=undefined
 try{await tasksApi.status(task,status);if(!live())return;pending.value=false;await refresh(1)}
 catch(value){if(live()){writeError.value=failure(value);uncertain.value=true}}
 finally{pending.value=false}
}
async function edit(task:Task){
 if(!canEdit(task)||pending.value||loading.value||uncertain.value||error.value)return
 loading.value=true
 try{const roster=await groupsApi.members(task.group_id);if(live()){editMembers.value=roster;editing.value=task}}
 catch(value){if(live())writeError.value=failure(value)}finally{loading.value=false}
}
async function organize(task:Task,status:Status){
 if(!canEdit(task)||loading.value||pending.value||uncertain.value||error.value)return
 operation.value={task,status};await nextTick();actionDialog.value?.showModal()
}
function dismissOperation(event?:Event){if(pending.value){event?.preventDefault();return}actionDialog.value?.close();operation.value=undefined}
async function confirmOperation(){const value=operation.value;if(!value)return;await setStatus(value.task,value.status);dismissOperation()}
function filterChanged(event:Event){const select=event.target as HTMLSelectElement;const value=select.value as typeof filter.value;select.value=filter.value;void refresh(1,value)}
function created(){void refresh(1)}
onMounted(()=>refresh())
onBeforeUnmount(()=>{reader?.abort();actionDialog.value?.close()})
</script>
<template>
 <section class="task-panel" :class="{'personal-task-panel':!groupId&&!meetingId}" :aria-label="title"><div class="section-heading"><h2>{{title}}</h2><button class="secondary" :disabled="loading||pending" @click="refresh()">{{loading?'正在读取…':'刷新任务'}}</button></div>
  <div class="task-controls"><nav v-if="!groupId&&!meetingId" class="personal-task-tabs" aria-label="任务分类"><button v-for="tab in [{value:'',label:'未完成'},{value:'DONE',label:'已完成'},{value:'CANCELLED',label:'已取消'}]" :key="tab.value" :aria-pressed="tab.value===''?['','TODO','IN_PROGRESS'].includes(filter):filter===tab.value" :disabled="loading||pending||uncertain" @click="refresh(1,tab.value as typeof filter)">{{tab.label}}</button></nav>
  <div class="task-toolbar"><label>任务状态 <select aria-label="任务状态" :value="filter" :disabled="loading||pending||uncertain" @change="filterChanged"><option value="">{{groupId?'全部状态':'未完成任务'}}</option><option v-for="(label,value) in states" :key="value" :value="value">{{label}}</option></select></label><span v-if="page" class="form-help">{{page.total}} 项任务</span></div>
  <form class="list-search task-search" role="search" aria-label="任务搜索" @submit.prevent="refresh(1,filter,searchInput.trim())"><input v-model="searchInput" type="search" aria-label="搜索任务" placeholder="搜索任务" maxlength="100" :disabled="loading||pending"><button class="secondary" :disabled="loading||pending">搜索</button><button v-if="query||searchInput" class="text-button" type="button" :disabled="loading||pending" @click="searchInput='';refresh(1,filter,'')">清除</button></form></div><p v-if="query" class="form-help">当前搜索：{{query}}</p>
  <StateNotice v-if="loading&&!page" kind="loading" title="正在读取任务" message="请稍候。"/>
  <StateNotice v-if="error" kind="error" title="任务列表暂时无法读取" :message="error.message" :request-id="error.requestId"><button :disabled="loading||pending" @click="refresh()">重新读取任务</button></StateNotice>
  <StateNotice v-if="writeError" kind="uncertain" title="任务状态需要核对" :message="writeError.message" :request-id="writeError.requestId"><button :disabled="loading||pending" @click="refresh()">核对最新任务</button></StateNotice>
  <p v-if="page&&(loading||error)" class="matrix-stale">保留上次读取的任务，请刷新成功后再操作。</p>
  <p v-if="page&&!page.items.length&&!error&&!loading" class="task-empty">{{filter?'当前状态下没有任务。':groupId?'暂无任务，负责人可在会议页添加。':'暂时没有未完成的任务。'}}</p>
  <ul v-if="page" class="task-list"><li v-for="task in page.items" :key="task.id" :data-task="task.id" :class="{completed:task.status==='DONE',cancelled:task.status==='CANCELLED'}"><button v-if="canChange(task)&&task.status!=='CANCELLED'" class="task-complete" role="checkbox" :aria-checked="task.status==='DONE'" :aria-label="`${task.status==='DONE'?'重新打开':'完成'}：${task.title}`" :disabled="loading||pending||uncertain||!!error" @click="setStatus(task,task.status==='DONE'?'TODO':'DONE')"><span aria-hidden="true">{{task.status==='DONE'?'✓':''}}</span></button><div class="task-main"><h3>{{task.title}}</h3><p class="task-meta">{{assignee(task)}} · 截止 {{beijing(task.due_at).replace('T',' ')}}（北京时间）<span v-if="!['DONE','CANCELLED'].includes(task.status)&&Date.parse(task.due_at)<Date.now()" class="task-overdue">已逾期</span></p><p v-if="task.description" class="plain-text">{{task.description}}</p><RouterLink v-if="!meetingId" :to="`/meetings/${task.meeting_id}`">查看会议 →</RouterLink><small v-if="task.completed_at" class="form-help">完成于 {{beijing(task.completed_at).replace('T',' ')}}</small></div><label v-if="canChange(task)&&task.status!=='CANCELLED'" class="task-status">状态<select :aria-label="`${task.title}的状态`" :value="task.status" :disabled="loading||pending||uncertain||!!error" @change="change(task,$event)"><option v-for="(label,value) in progressStates" :key="value" :value="value">{{label}}</option></select></label><span v-else class="role-badge">{{states[task.status]}}</span><div v-if="canEdit(task)" class="task-management"><button :disabled="loading||pending||uncertain||!!error" @click="edit(task)">编辑</button><button v-if="task.status==='CANCELLED'" :disabled="loading||pending||uncertain||!!error" @click="organize(task,'TODO')">恢复</button><button v-else-if="task.status!=='DONE'" class="cancel-action" :disabled="loading||pending||uncertain||!!error" @click="organize(task,'CANCELLED')">取消</button></div></li></ul>
  <nav v-if="page&&(pages>1||page.page>1)" class="pagination" aria-label="任务分页"><button class="secondary" :disabled="loading||pending||page.page<=1" @click="refresh(page.page-1)">上一页任务</button><span>第 {{page.page}}/{{pages}} 页</span><button class="secondary" :disabled="loading||pending||page.page>=pages" @click="refresh(page.page+1)">下一页任务</button></nav>
  <TaskCreator v-if="meetingId&&groupId&&owner" :meeting-id="meetingId" :group-id="groupId" :members="members" :disabled="loading||pending||uncertain||!!error" @created="created" @reconcile="refresh(1)"/>
  <TaskEditor v-if="editing" :task="editing" :members="editMembers" @saved="editing=undefined;refresh(1)" @closed="editing=undefined" @reconcile="refresh(1)"/>
  <dialog ref="actionDialog" class="task-action-dialog" aria-labelledby="task-operation-title" @cancel="dismissOperation($event)"><template v-if="operation"><h2 id="task-operation-title">{{operation.status==='CANCELLED'?'取消任务':'恢复任务'}}</h2><p>{{operation.task.title}}</p><p>{{operation.status==='CANCELLED'?'任务不再需要执行，保留记录；这不算完成。':'恢复为待开始，重新显示在未完成列表。'}}</p><div class="dialog-actions"><button class="secondary" :disabled="pending" autofocus @click="dismissOperation()">返回</button><button :disabled="pending" @click="confirmOperation()">{{pending?'正在保存…':'确认'}}</button></div></template></dialog>
 </section>
</template>

<style scoped>
.task-panel{border-radius:8px}.task-list>li{align-items:center;gap:16px}.task-complete{padding:0;min-height:22px;width:22px;height:22px;flex:0 0 22px;background:#fff;border:1.5px solid #bdb2ce;border-radius:50%;display:grid;place-items:center;position:relative}.task-complete::after{content:'';position:absolute;inset:-9px}.task-complete[aria-checked=true]{background:#7250a1;border-color:#7250a1;color:#fff}.task-complete span{font-size:12px}.completed .task-main h3{text-decoration:line-through;color:#7c7485}.cancelled .task-main h3{color:#7c7485}.task-management{display:flex;gap:12px;align-items:center}.task-management button{min-height:40px;background:none;border:0;color:#7250a1;font-size:13px;padding:4px}.task-management .cancel-action{color:#a5514e}.task-action-dialog{width:min(440px,calc(100vw - 32px));border:1px solid #dfd8e8;border-radius:8px;padding:26px;color:#292d50}.task-action-dialog::backdrop{background:#20273750}.task-action-dialog button:not(.secondary){background:#7250a1}.task-status select{min-height:40px}
@media(max-width:760px){.task-list>li{display:grid;grid-template-columns:22px minmax(0,1fr);gap:12px;align-items:start}.task-main{grid-column:2;min-width:0}.task-complete{grid-column:1;grid-row:1;margin-top:4px}.task-status,.task-list>li>.role-badge{grid-column:2;justify-self:start}.task-management{grid-column:2;justify-self:end}.task-main h3{overflow-wrap:anywhere}}
</style>
