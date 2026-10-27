<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,reactive,ref,watch} from 'vue'
import type {Member} from '../groups/api'
import {failure,useGroupLifetime} from '../groups/forms'
import type {ApiFailure} from '../api/client'
import {beijing,localMs} from '../polls/editor'
import {tasksApi,validateTask,type Task,type TaskFields,type TaskUpdate} from '../tasks/api'
import StateNotice from './StateNotice.vue'
const props=defineProps<{task:Task;members:Member[]}>()
const emit=defineEmits<{saved:[];closed:[];reconcile:[]}>()
const dialog=ref<HTMLDialogElement>(),pending=ref(false),error=ref<ApiFailure>(),uncertain=ref(false)
const original={title:props.task.title,description:props.task.description,assignee:String(props.task.assignee_id),due:beijing(props.task.due_at)}
const fields=reactive<TaskFields>({...original}),errors=ref<Partial<Record<keyof TaskFields,string>>>({})
const dirty=computed(()=>Object.keys(original).some(key=>fields[key as keyof TaskFields]!==original[key as keyof TaskFields]))
const live=useGroupLifetime(()=>dirty.value||uncertain.value,()=>pending.value)
for(const key of ['title','description','assignee','due'] as const)watch(()=>fields[key],()=>{delete errors.value[key]})
function close(event?:Event){
 if(pending.value){event?.preventDefault();return}
 event?.preventDefault()
 if(dirty.value&&!window.confirm('关闭后将放弃尚未保存的修改，是否继续？'))return
 dialog.value?.close();if(uncertain.value)emit('reconcile');emit('closed')
}
async function save(){
 if(pending.value||uncertain.value)return
 errors.value=validateTask(fields,props.members.map(p=>p.user_id))
 if(fields.due===original.due)delete errors.value.due
 if(Object.keys(errors.value).length)return
 const body:TaskUpdate={expected_version:props.task.version}
 if(fields.title.trim()!==original.title)body.title=fields.title.trim()
 if(fields.description!==original.description)body.description=fields.description
 if(fields.assignee!==original.assignee)body.assignee_id=Number(fields.assignee)
 if(fields.due!==original.due)body.due_at=new Date(localMs(fields.due)).toISOString()
 if(Object.keys(body).length===1){dialog.value?.close();emit('closed');return}
 pending.value=true;error.value=undefined
 try{await tasksApi.edit(props.task,body);if(!live())return;dialog.value?.close();emit('saved')}
 catch(value){if(live()){error.value=failure(value);uncertain.value=error.value.uncertain||error.value.status===409}}
 finally{pending.value=false}
}
onMounted(()=>dialog.value?.showModal())
onBeforeUnmount(()=>dialog.value?.close())
</script>
<template>
 <dialog ref="dialog" class="task-edit-dialog" aria-labelledby="task-edit-title" @cancel="close($event)"><form novalidate @submit.prevent="save"><h2 id="task-edit-title">编辑任务</h2>
  <StateNotice v-if="error" :kind="uncertain?'uncertain':'error'" :title="uncertain?'修改结果需要核对':'修改尚未保存'" :message="error.message" :request-id="error.requestId"><p v-if="uncertain">保留了本次输入。请先核对内容；关闭后刷新列表，再基于最新任务编辑。</p></StateNotice>
  <fieldset :disabled="pending||uncertain"><div class="form-field"><label for="edit-task-title">任务标题</label><input id="edit-task-title" v-model="fields.title" autofocus :aria-invalid="!!errors.title" :aria-describedby="errors.title?'edit-title-error':undefined"><p v-if="errors.title" id="edit-title-error" class="field-error">{{errors.title}}</p></div>
  <div class="form-field"><label for="edit-task-description">任务说明（选填）</label><textarea id="edit-task-description" v-model="fields.description" rows="3" :aria-invalid="!!errors.description" :aria-describedby="errors.description?'edit-description-error':undefined"/><p v-if="errors.description" id="edit-description-error" class="field-error">{{errors.description}}</p></div>
  <div class="task-create-grid"><div class="form-field"><label for="edit-task-assignee">执行人</label><select id="edit-task-assignee" v-model="fields.assignee" :aria-invalid="!!errors.assignee" :aria-describedby="errors.assignee?'edit-assignee-error':undefined"><option v-for="person in members" :key="person.user_id" :value="String(person.user_id)">{{person.username}}</option></select><p v-if="errors.assignee" id="edit-assignee-error" class="field-error">{{errors.assignee}}</p></div><div class="form-field"><label for="edit-task-due">截止时间（北京时间）</label><input id="edit-task-due" v-model="fields.due" type="datetime-local" step="60" :aria-invalid="!!errors.due" :aria-describedby="errors.due?'edit-due-error':undefined"><p v-if="errors.due" id="edit-due-error" class="field-error">{{errors.due}}</p></div></div></fieldset>
  <div class="dialog-actions"><button type="button" class="secondary" :disabled="pending" @click="close()">{{uncertain?'关闭并刷新列表':'取消编辑'}}</button><button type="submit" :disabled="pending||uncertain">{{pending?'正在保存…':'保存修改'}}</button></div>
 </form></dialog>
</template>
<style scoped>
.task-edit-dialog{width:min(620px,calc(100vw - 32px));max-height:calc(100dvh - 32px);overflow:auto;border:1px solid #dfd8e8;border-radius:8px;padding:26px;color:#292d50}.task-edit-dialog::backdrop{background:#20273750}.task-edit-dialog h2{margin-top:0}.task-edit-dialog button:not(.secondary){background:#7250a1}.task-edit-dialog .form-field{margin-top:18px}
</style>
