<script setup lang="ts">
import {reactive,ref,watch} from 'vue'
import type {Member} from '../groups/api'
import {failure,useGroupLifetime} from '../groups/forms'
import type {ApiFailure} from '../api/client'
import StateNotice from './StateNotice.vue'
import {localMs} from '../polls/editor'
import {tasksApi,validateTask,type TaskFields,type TaskBody} from '../tasks/api'
const props=defineProps<{meetingId:number;groupId:number;members:Member[];disabled:boolean}>()
const emit=defineEmits<{created:[];reconcile:[]}>()
const fields=reactive<TaskFields>({title:'',description:'',assignee:'',due:''})
const errors=ref<Partial<Record<keyof TaskFields,string>>>({}),pending=ref(false),uncertain=ref(false),error=ref<ApiFailure>(),open=ref(false)
for(const key of ['title','description','assignee','due'] as const)watch(()=>fields[key],()=>{delete errors.value[key]})
let attempt:TaskBody|undefined
const live=useGroupLifetime(()=>open.value&&(!!fields.title||!!fields.description||!!fields.assignee||!!fields.due)||uncertain.value,()=>pending.value)
function cancel(){if(pending.value||uncertain.value)return;if((fields.title||fields.description||fields.assignee||fields.due)&&!window.confirm('放弃尚未创建的任务吗？'))return;clear()}
function clear(){Object.assign(fields,{title:'',description:'',assignee:'',due:''});open.value=false;errors.value={};error.value=undefined;attempt=undefined;uncertain.value=false}
async function submit(retry=false){
 if(pending.value||props.disabled||(!retry&&uncertain.value))return
 if(!retry){errors.value=validateTask(fields,props.members.map(person=>person.user_id));if(Object.keys(errors.value).length)return;attempt={title:fields.title.trim(),description:fields.description,assignee_id:Number(fields.assignee),due_at:new Date(localMs(fields.due)).toISOString(),client_request_id:crypto.randomUUID()}}
 if(!attempt)return
 pending.value=true;error.value=undefined
 try{await tasksApi.create(props.meetingId,props.groupId,attempt);if(live()){clear();emit('created')}}
 catch(value){if(live()){error.value=failure(value);uncertain.value=error.value.uncertain||error.value.status===409}}
 finally{pending.value=false}
}
</script>
<template>
 <button v-if="!open" class="secondary" :disabled="disabled" @click="open=true">＋ 添加任务</button>
 <form v-else class="task-create" novalidate @submit.prevent="submit()"><h3>把决定变成任务</h3>
  <StateNotice v-if="error" :kind="uncertain?'uncertain':'error'" :title="uncertain?'创建结果需要核对':'任务尚未创建'" :message="error.message" :request-id="error.requestId"><p v-if="uncertain" class="form-help">保留原输入重试，同一次创建不会产生重复任务。</p><button v-if="uncertain&&error.status!==409" type="button" :disabled="pending||disabled" @click="submit(true)">核对并重试原任务</button><button v-if="error.status===409" type="button" class="secondary" @click="clear();emit('reconcile')">返回列表核对</button></StateNotice>
  <fieldset :disabled="pending||uncertain||disabled"><div class="form-field"><label :for="`task-title-${meetingId}`">任务标题</label><input :id="`task-title-${meetingId}`" v-model="fields.title" maxlength="200" :aria-invalid="!!errors.title"><p v-if="errors.title" class="field-error">{{errors.title}}</p></div><div class="form-field"><label :for="`task-description-${meetingId}`">任务说明（选填）</label><textarea :id="`task-description-${meetingId}`" v-model="fields.description" rows="3" maxlength="20000" :aria-invalid="!!errors.description"/><p v-if="errors.description" class="field-error">{{errors.description}}</p></div>
  <div class="task-create-grid"><div class="form-field"><label :for="`task-assignee-${meetingId}`">执行人</label><select :id="`task-assignee-${meetingId}`" v-model="fields.assignee" :aria-invalid="!!errors.assignee"><option value="">选择小组成员</option><option v-for="person in members" :key="person.user_id" :value="String(person.user_id)">{{person.username}}</option></select><p v-if="errors.assignee" class="field-error">{{errors.assignee}}</p></div><div class="form-field"><label :for="`task-due-${meetingId}`">截止时间（北京时间）</label><input :id="`task-due-${meetingId}`" v-model="fields.due" type="datetime-local" step="60" :aria-invalid="!!errors.due"><p v-if="errors.due" class="field-error">{{errors.due}}</p></div></div></fieldset>
  <div class="dialog-actions"><button type="button" class="secondary" :disabled="pending||uncertain" @click="cancel">取消创建</button><button type="submit" :disabled="pending||uncertain||disabled">{{pending?'正在创建…':'创建任务'}}</button></div>
 </form>
</template>
