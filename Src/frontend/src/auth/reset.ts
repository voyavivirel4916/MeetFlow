import {ApiFailure, request} from '../api/client'
import {validateAuth} from './validation'

export function resetValidation(email:string,password:string,confirm:string,resetting:boolean){
 const errors=validateAuth(true,{username:'reset_user',email:resetting?'reset@example.com':email,password:resetting?password:'placeholder123'})
 return resetting?(errors.password|| (password!==confirm?'两次输入的密码不一致。':'')):(errors.email||'')
}
async function send(path:string,body:object){
 let result
 try{result=await request<{message:string}>(path,{method:'POST',body})}
 catch(error){if(error instanceof ApiFailure&&error.code==='MAIL_UNAVAILABLE')error.uncertain=false;throw error}
 if(!result.data||typeof result.data.message!=='string')throw new ApiFailure('protocol','服务响应无法识别，请重新核对。',undefined,undefined,result.request_id,undefined,true)
 return result.data.message
}
export const resetApi={
 request:(email:string)=>send('/api/v1/auth/password-reset/request',{email:email.trim().toLowerCase()}),
 confirm:(token:string,password:string)=>send('/api/v1/auth/password-reset/confirm',{token,password}),
}
