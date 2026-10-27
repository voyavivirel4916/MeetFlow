<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,reactive,ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import type {ApiFailure} from '../api/client'
import StateNotice from '../components/StateNotice.vue'
import TaskPanel from '../components/TaskPanel.vue'
import {useSession} from '../auth/session'
import {groupsApi} from '../groups/api'
import {failure,useGroupLifetime} from '../groups/forms'
import {meetingsApi,validateContent,type Meeting,type MeetingContent} from '../meetings/api'
import {beijing} from '../polls/editor'

const id=String(useRoute().params.meetingId),session=useSession()
const saved=ref<Meeting>(),ownerId=ref<number>(),loading=ref(false),pending=ref(false),editing=ref(false),uncertain=ref(false)
const readError=ref<ApiFailure>(),writeError=ref<ApiFailure>(),notice=ref(''),checked=ref<Meeting>()
const fields=reactive<MeetingContent>({agenda:'',minutes:''}),errors=ref<Partial<Record<keyof MeetingContent,string>>>({})
const owner=computed(()=>ownerId.value===session.state.user?.id)
const dirty=computed(()=>!!saved.value&&(fields.agenda!==saved.value.agenda||fields.minutes!==saved.value.minutes))
const live=useGroupLifetime(()=>dirty.value||uncertain.value,()=>pending.value)
let reader:AbortController|undefined
watch(()=>fields.agenda,()=>{delete errors.value.agenda})
watch(()=>fields.minutes,()=>{delete errors.value.minutes})
function adopt(value:Meeting){saved.value=value;Object.assign(fields,{agenda:value.agenda,minutes:value.minutes});editing.value=false;uncertain.value=false;checked.value=undefined;writeError.value=undefined;errors.value={}}
async function load(){
  if(loading.value||pending.value||uncertain.value)return
  if(dirty.value&&!window.confirm('重新读取会清空尚未保存的修改，确定继续吗？'))return
  loading.value=true;readError.value=undefined;notice.value='';reader=new AbortController()
  try{
    const value=await meetingsApi.detail(id,reader.signal),group=await groupsApi.get(value.group_id,reader.signal)
    if(!live())return
    ownerId.value=group.owner_id;adopt(value)
  }catch(error){if(live()){readError.value=failure(error);if([403,404].includes(readError.value.status||0)){saved.value=undefined;fields.agenda='';fields.minutes='';editing.value=false;ownerId.value=undefined}}}
  finally{loading.value=false}
}
function cancel(){if(pending.value||uncertain.value)return;if(dirty.value&&!window.confirm('放弃尚未保存的修改吗？'))return;if(saved.value)adopt(saved.value)}
async function save(){
  if(!saved.value||!owner.value||loading.value||readError.value||pending.value||uncertain.value)return
  errors.value=validateContent(fields);if(Object.keys(errors.value).length)return
  pending.value=true;notice.value='';writeError.value=undefined
  try{const value=await meetingsApi.update(saved.value,{...fields});if(live()){adopt(value);notice.value='议程与纪要已保存。'}}
  catch(error){if(live()){writeError.value=failure(error);uncertain.value=writeError.value.uncertain||[403,409].includes(writeError.value.status||0);if(writeError.value.status===404){saved.value=undefined;fields.agenda='';fields.minutes='';editing.value=false;readError.value=writeError.value}}}
  finally{pending.value=false}
}
async function reconcile(){
  if(pending.value)return
  pending.value=true;checked.value=undefined
  try{
    const value=await meetingsApi.detail(id),group=await groupsApi.get(value.group_id)
    if(!live())return
    ownerId.value=group.owner_id
    if(!owner.value){adopt(value);notice.value='已读取最新内容，当前账号仅可查看。'}
    else if(value.agenda===fields.agenda&&value.minutes===fields.minutes){adopt(value);notice.value='已核对，议程与纪要已保存。'}
    else{checked.value=value;notice.value='服务端内容与当前输入不同。请先核对下方内容，再决定继续编辑或使用已保存内容。'}
  }catch(error){if(live()){writeError.value=failure(error);notice.value='暂未核对成功，你的输入仍保留。';if([403,404].includes(writeError.value.status||0)){saved.value=undefined;fields.agenda='';fields.minutes='';editing.value=false;uncertain.value=false;readError.value=writeError.value}}}
  finally{pending.value=false}
}
function keepEditing(){if(!checked.value||pending.value)return;saved.value=checked.value;checked.value=undefined;uncertain.value=false;writeError.value=undefined;notice.value='已保留输入，请核对后再保存。'}
onMounted(load)
onBeforeUnmount(()=>reader?.abort())
</script>
<template>
  <RouterLink class="back-link" :to="saved?`/groups/${saved.group_id}`:'/groups'">← 返回小组</RouterLink>
  <section class="group-heading"><div><h1>会议与行动</h1><p class="muted">记录要讨论的事，留下共同的决定。</p></div><button class="secondary" :disabled="loading||pending||uncertain" @click="load">{{loading?'正在读取…':'刷新'}}</button></section>
  <StateNotice v-if="loading&&!saved" kind="loading" title="正在读取会议" message="请稍候。"/>
  <StateNotice v-if="readError" kind="error" :title="[403,404].includes(readError.status||0)?'未找到可访问的会议':'会议暂时无法读取'" :message="readError.message" :request-id="readError.requestId"><button :disabled="loading||pending||uncertain" @click="load">重新读取会议</button></StateNotice>
  <p v-if="notice" class="success-note" role="status">{{notice}}</p>
  <template v-if="saved">
    <p v-if="loading||readError" class="matrix-stale">下方保留上次读取的内容，请刷新成功后再编辑。</p>
    <section class="meeting-overview"><div class="section-heading"><h2>{{saved.title}}</h2><span class="role-badge">已确认</span></div><p class="meeting-time">{{beijing(saved.start_at).replace('T',' ')}} — {{beijing(saved.end_at).slice(0,10)===beijing(saved.start_at).slice(0,10)?beijing(saved.end_at).slice(11):beijing(saved.end_at).replace('T',' ')}}</p><p class="muted">{{saved.location||'地点待定'}} · 北京时间</p><details v-if="saved.selection_reason"><summary>选择这个时间的理由</summary><p class="plain-text">{{saved.selection_reason}}</p></details><RouterLink class="button-link" :to="`/polls/${saved.poll_id}/results`">查看排期结果 →</RouterLink></section>
    <section class="meeting-content"><div class="section-heading"><h2>议程与纪要</h2><button v-if="owner&&!editing" class="secondary" :disabled="loading||!!readError||pending" @click="editing=true;notice=''">编辑议程与纪要</button><span v-else-if="!owner" class="form-help">负责人维护 · 成员可查看</span></div>
      <p class="form-help">上次保存：{{beijing(saved.updated_at).replace('T',' ')}}（北京时间）</p>
      <template v-if="!editing"><section class="meeting-text"><h3>会议议程</h3><p v-if="saved.agenda" class="plain-text">{{saved.agenda}}</p><p v-else class="muted">尚未填写议程。</p></section><section class="meeting-text"><h3>会议纪要</h3><p v-if="saved.minutes" class="plain-text">{{saved.minutes}}</p><p v-else class="muted">尚未填写纪要，讨论结束后在这里留下决定。</p></section></template>
      <form v-else novalidate @submit.prevent="save"><StateNotice v-if="writeError" :kind="uncertain?'uncertain':'error'" :title="uncertain?'保存结果需要核对':'保存未完成'" :message="writeError.message" :request-id="writeError.requestId"><button v-if="uncertain" type="button" class="secondary" :disabled="pending" @click="reconcile">核对保存结果</button></StateNotice>
        <fieldset :disabled="pending||uncertain||loading||!!readError"><div v-for="(label,key) in {agenda:'会议议程',minutes:'会议纪要'}" :key="key" class="form-field"><label :for="key">{{label}}</label><textarea :id="key" v-model="fields[key]" rows="7" maxlength="20000" :aria-invalid="!!errors[key]" :aria-describedby="`${key}-count ${key}-error`"/><small :id="`${key}-count`">{{Array.from(fields[key]).length}}/10000</small><p v-if="errors[key]" :id="`${key}-error`" class="field-error">{{errors[key]}}</p></div></fieldset>
        <section v-if="checked" class="meeting-reconcile"><h3>服务端已保存的内容</h3><h4>会议议程</h4><p class="plain-text">{{checked.agenda||'尚未填写议程。'}}</p><h4>会议纪要</h4><p class="plain-text">{{checked.minutes||'尚未填写纪要。'}}</p><div class="dialog-actions"><button type="button" class="secondary" :disabled="pending" @click="adopt(checked)">使用已保存内容</button><button type="button" :disabled="pending" @click="keepEditing">保留输入继续编辑</button></div></section>
        <div class="dialog-actions"><button type="button" class="secondary" :disabled="pending||uncertain" @click="cancel">取消编辑</button><button type="submit" :disabled="pending||uncertain||loading||!!readError||!dirty">{{pending?'正在处理…':'保存议程与纪要'}}</button></div></form>
    </section>
    <TaskPanel :group-id="saved.group_id" :meeting-id="saved.id"/>
  </template>
</template>
