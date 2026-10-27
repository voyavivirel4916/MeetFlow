<script setup lang="ts">
import {computed,nextTick,ref,watch} from 'vue'
import {useGroupLifetime,failure} from '../groups/forms'
import {pollsApi,type Poll} from '../polls/api'
import {beijing} from '../polls/editor'
import type {Matrix} from '../votes/matrix'
import type {Recommendation} from '../votes/recommendations'
import {meetingsApi,requiresAck,validateConfirmation,type Meeting} from '../meetings/api'

const props=defineProps<{poll:Poll;matrix:Matrix;recommendations:Recommendation[];isOwner:boolean;meeting:Meeting|null;disabled:boolean;refresh:()=>Promise<void>}>()
const dialog=ref<HTMLDialogElement>(),selected=ref<number>(),reason=ref(''),acknowledged=ref(false),pending=ref(false),uncertain=ref(false),message=ref(''),success=ref('')
const errors=ref<{acknowledged?:string;selection_reason?:string}>({}),sent=ref<number>(),requestId=ref<string>()
const live=useGroupLifetime(()=>selected.value!==undefined||uncertain.value,()=>pending.value)
const item=computed(()=>props.recommendations.find(item=>item.slot_id===selected.value))
const slot=computed(()=>props.matrix.slots.find(slot=>slot.id===selected.value))
const canChoose=computed(()=>props.isOwner&&props.matrix.effective_status==='CLOSED'&&!props.meeting&&!props.disabled&&!pending.value&&!uncertain.value)
const risky=computed(()=>!!item.value&&requiresAck(item.value))
watch(acknowledged,()=>{delete errors.value.acknowledged})
watch(reason,()=>{delete errors.value.selection_reason})
async function open(slotId:number){
  if(!canChoose.value)return
  selected.value=slotId;reason.value='';acknowledged.value=false;errors.value={};message.value='';success.value=''
  await nextTick();dialog.value?.showModal()
}
function dismiss(event?:Event){
  if(pending.value){event?.preventDefault();return}
  dialog.value?.close();selected.value=undefined;errors.value={}
  if(!uncertain.value){reason.value='';acknowledged.value=false}
}
async function closeCollection(){
  if(!props.isOwner||props.disabled||pending.value||uncertain.value||!window.confirm('结束收集后，成员将不能再修改空闲状态。确定结束收集吗？'))return
  pending.value=true;message.value='';success.value='';sent.value=undefined
  try{await pollsApi.close(props.poll.id);if(!live())return;success.value='已结束收集，可以选择会议时间。';await props.refresh()}
  catch(error){if(!live())return;const value=failure(error);requestId.value=value.requestId;uncertain.value=value.uncertain||[403,409].includes(value.status||0);message.value=uncertain.value?'结束收集结果需要核对，请先刷新最新状态。':value.message}
  finally{pending.value=false}
}
async function submit(){
  if(!canChoose.value||!item.value||!slot.value)return
  errors.value=validateConfirmation(item.value,acknowledged.value,reason.value)
  if(Object.keys(errors.value).length){await nextTick();dialog.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();return}
  pending.value=true;message.value='';success.value='';sent.value=slot.value.id
  try{
    await meetingsApi.confirm(props.poll,{slot_id:slot.value.id,acknowledged:acknowledged.value,selection_reason:reason.value.trim()})
    if(!live())return
    dialog.value?.close();selected.value=undefined;reason.value='';acknowledged.value=false;uncertain.value=false;success.value='会议时间已确认。'
    await props.refresh()
  }catch(error){
    if(!live())return
    const value=failure(error);requestId.value=value.requestId
    uncertain.value=value.uncertain||[400,403,409].includes(value.status||0)
    message.value=uncertain.value?'确认结果或排期状态需要核对，已保留你的选择和理由。请先读取服务端结果。':value.message
    if(value.status===404){dialog.value?.close();selected.value=undefined;await props.refresh()}
  }finally{pending.value=false}
}
async function reconcile(){
  if(pending.value)return
  pending.value=true
  try{
    const meeting=await meetingsApi.get(props.poll)
    if(!live())return
    await props.refresh();if(!live())return;await nextTick()
    if(props.disabled){message.value='最新结果尚未读取成功，输入仍保留，请重试核对。';return}
    if(meeting){
      dialog.value?.close();selected.value=undefined;reason.value='';acknowledged.value=false
      success.value=sent.value===meeting.selected_slot_id?'已核对，所选会议时间已确认。':'已读取最新会议结果，请以已确认时间为准。'
      uncertain.value=false;message.value=''
    }else{uncertain.value=false;message.value='已核对，当前尚未生成会议。请确认最新状态后再提交。'}
  }catch(error){if(live()){const value=failure(error);requestId.value=value.requestId;message.value='核对暂未成功，选择和理由仍保留，请稍后重试。'}}
  finally{pending.value=false}
}
defineExpose({open,canChoose})
</script>
<template>
  <section v-if="meeting" class="meeting-confirmed" aria-label="已确认会议"><h3>会议时间已确认</h3><p class="confirmed-time">{{ beijing(meeting.start_at).replace('T',' ') }} — {{ beijing(meeting.end_at).replace('T',' ') }}</p><p class="muted">{{ meeting.title }} · {{ meeting.location||'地点待定' }}</p><details v-if="meeting.selection_reason"><summary>查看选择理由</summary><p class="plain-text">{{ meeting.selection_reason }}</p></details><RouterLink class="button-link" :to="`/meetings/${meeting.id}`">查看会议 →</RouterLink></section>
  <div v-else-if="isOwner&&matrix.effective_status==='OPEN'" class="confirmation-entry"><p class="form-help">结束收集后，就可以确认会议时间。</p><button class="secondary" :disabled="disabled||pending||uncertain" @click="closeCollection">{{pending?'正在处理…':'结束收集'}}</button></div>
  <p v-if="success" class="success-note" role="status">{{success}}</p>
  <div v-if="message&&!dialog?.open" class="form-summary" :class="{uncertain}" role="alert"><p>{{message}}</p><small v-if="requestId">请求编号：{{requestId}}</small><button v-if="uncertain" class="secondary" :disabled="pending" @click="reconcile">核对服务端结果</button></div>
  <dialog ref="dialog" class="confirm-dialog" aria-labelledby="confirm-meeting-title" @cancel="dismiss"><form novalidate @submit.prevent="submit"><h2 id="confirm-meeting-title">确认会议时间</h2><p v-if="slot" class="confirmed-time">{{ beijing(slot.start_at).replace('T',' ') }} — {{ beijing(slot.end_at).replace('T',' ') }}</p><p class="muted">{{poll.title}} · {{poll.location||'地点待定'}}</p>
    <template v-if="item"><ul class="confirmation-warnings"><li v-if="item.required_unavailable_count">{{item.required_unavailable_count}} 位必到成员没空。</li><li v-if="item.required_unsubmitted_count">{{item.required_unsubmitted_count}} 位必到成员尚未填写，不能确定能否参加。</li><li v-if="item.required_maybe_count">{{item.required_maybe_count}} 位必到成员勉强有空，仍需协调。</li><li v-if="item.rank!==1">当前选择的候选排名第 {{item.rank}}，不是推荐首位。</li></ul><p class="form-help">确认后将生成唯一会议，不能改为其他候选时间。</p></template>
    <div v-if="message" class="form-summary" :class="{uncertain}" role="alert"><p>{{message}}</p><small v-if="requestId">请求编号：{{requestId}}</small><button v-if="uncertain" type="button" class="secondary" :disabled="pending" @click="reconcile">核对服务端结果</button></div>
    <fieldset :disabled="pending||uncertain||disabled"><label v-if="risky" class="retry-check"><input v-model="acknowledged" type="checkbox" :aria-invalid="!!errors.acknowledged" aria-describedby="confirmation-ack-error">我已了解上述风险，仍选择这个时间</label><p v-if="errors.acknowledged" id="confirmation-ack-error" class="field-error">{{errors.acknowledged}}</p><div class="form-field"><label for="selection-reason">选择理由{{risky?'（必填）':'（选填）'}}</label><textarea id="selection-reason" v-model="reason" rows="3" maxlength="1000" :aria-invalid="!!errors.selection_reason" aria-describedby="selection-reason-error" placeholder="说明为什么选择这个时间"/><small>{{Array.from(reason.trim()).length}}/500</small><p v-if="errors.selection_reason" id="selection-reason-error" class="field-error">{{errors.selection_reason}}</p></div></fieldset>
    <div class="dialog-actions"><button type="button" class="secondary" :disabled="pending" @click="dismiss">返回结果</button><button type="submit" :disabled="pending||uncertain||disabled||!canChoose">{{pending?'正在确认…':'确认生成会议'}}</button></div></form></dialog>
</template>
