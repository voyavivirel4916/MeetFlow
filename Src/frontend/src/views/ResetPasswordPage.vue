<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue'
import {onBeforeRouteLeave,onBeforeRouteUpdate,useRoute,useRouter} from 'vue-router'
import {resetApi,resetValidation} from '../auth/reset'
import {useSession} from '../auth/session'
import {ApiFailure} from '../api/client'
const props=defineProps<{resetting?:boolean}>(),session=useSession()
const route=useRoute(),router=useRouter()
const email=ref(''),password=ref(''),confirmation=ref(''),pending=ref(false),message=ref(''),error=ref(''),done=ref(false),visible=ref(false),uncertain=ref(false)
let token=''
const hasToken=ref(false)
watch(()=>route.hash,hash=>{
 if(!props.resetting||!hash)return
 token=new URLSearchParams(hash.slice(1)).get('token')||''
 hasToken.value=/^[A-Za-z0-9_-]{43}$/.test(token)
 done.value=false;message.value='';error.value='';password.value='';confirmation.value=''
 void router.replace({path:route.path,query:route.query,hash:''})
},{immediate:true})
async function submit(){
 if(pending.value||done.value)return
 error.value=resetValidation(email.value,password.value,confirmation.value,!!props.resetting)
 if(error.value)return
 if(props.resetting&&!hasToken.value){error.value='重置链接无效，请重新申请。';return}
 pending.value=true;uncertain.value=false
 try{
  message.value=props.resetting?await resetApi.confirm(token,password.value):await resetApi.request(email.value)
  done.value=true;password.value='';confirmation.value='';token=''
  if(props.resetting){session.expire();session.setLoginHint('',message.value)}
 }catch(value){error.value=value instanceof Error?value.message:'暂时无法完成，请稍后再试。';uncertain.value=value instanceof ApiFailure&&value.uncertain}
 finally{pending.value=false}
}
onBeforeRouteLeave(()=>pending.value?false:(!password.value&&!confirmation.value)||window.confirm('新密码尚未提交，离开后会清空，是否继续？'))
onBeforeRouteUpdate(()=>!pending.value)
onBeforeUnmount(()=>{token='';password.value='';confirmation.value=''})
</script>
<template>
 <section class="auth-card reset-card" :aria-busy="pending">
  <h1>{{resetting?'设置新密码':'找回密码'}}</h1>
  <p class="form-help">{{resetting?'重置后所有设备需要重新登录。':'填写注册邮箱，通过邮件中的链接设置新密码。'}}</p>
  <p v-if="resetting&&!hasToken&&!done" class="field-error">重置链接无效，请从邮件打开完整链接，或重新申请。</p>
  <p v-if="message" role="status" class="auth-note">{{message}}</p>
  <p v-if="error" role="alert" class="field-error">{{error}}</p>
  <p v-if="uncertain" class="form-help">{{resetting?'结果未确认，可先用新密码登录核对；仍失败时重新申请链接。':'结果未确认，请先检查邮件，稍后再申请。'}}</p>
  <form v-if="!done&&(!resetting||hasToken)" novalidate @submit.prevent="submit">
   <fieldset :disabled="pending">
    <div v-if="!resetting" class="form-field"><label for="reset-email">注册邮箱</label><input id="reset-email" v-model="email" type="email" autocomplete="email" maxlength="254" required></div>
    <template v-else>
     <div class="form-field"><label for="new-password">新密码</label><div class="password-row"><input id="new-password" v-model="password" :type="visible?'text':'password'" autocomplete="new-password" maxlength="256" required><button type="button" class="password-toggle" :aria-label="visible?'隐藏密码':'显示密码'" :aria-pressed="visible" @click="visible=!visible"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path v-if="!visible" d="m3 3 18 18"/></svg></button></div><small>8～128个字符，不能全为空白。</small></div>
     <div class="form-field"><label for="confirm-password">确认新密码</label><input id="confirm-password" v-model="confirmation" :type="visible?'text':'password'" autocomplete="new-password" maxlength="256" required></div>
    </template>
    <button class="auth-submit" :disabled="pending">{{pending?'正在提交…':resetting?'保存新密码':'发送重置邮件'}}</button>
   </fieldset>
  </form>
  <p class="auth-switch"><RouterLink to="/login">返回登录</RouterLink><RouterLink v-if="resetting&&!done" to="/forgot-password">重新申请链接</RouterLink></p>
 </section>
</template>
<style scoped>
.reset-card{max-width:480px;margin:20px auto}.reset-card fieldset{border:0;padding:0;margin:0;min-width:0}.auth-switch{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
</style>
