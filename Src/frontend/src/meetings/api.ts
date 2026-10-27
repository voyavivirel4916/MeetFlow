import { ApiFailure, request } from '../api/client'
import { identifier, utc, type Poll } from '../polls/api'
import type { Recommendation } from '../votes/recommendations'

export type Meeting={id:number;poll_id:number;group_id:number;selected_slot_id:number;title:string;location:string;start_at:string;end_at:string;selection_reason:string;agenda:string;minutes:string;updated_at:string}
export type ConfirmBody={slot_id:number;acknowledged:boolean;selection_reason:string}
export const requiresAck=(item:Recommendation)=>item.rank!==1||item.required_unavailable_count>0||item.required_unsubmitted_count>0
export function validateConfirmation(item:Recommendation,acknowledged:boolean,reason:string){
  const errors:{acknowledged?:string;selection_reason?:string}={}
  if(requiresAck(item)&&!acknowledged)errors.acknowledged='请先确认已了解这些风险。'
  if((requiresAck(item)&&!reason.trim())||Array.from(reason.trim()).length>500||/\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(reason))errors.selection_reason='请填写有效理由，最多500个字符。'
  return errors
}
function decode(value:unknown,poll:Poll,id:string,writing:boolean):Meeting{
  const invalid=():never=>{throw new ApiFailure('protocol','会议结果无法识别，请先读取核对。',undefined,undefined,id,undefined,writing)}
  if(!value||typeof value!=='object'||Array.isArray(value))return invalid()
  const row=value as Record<string,unknown>,slot=poll.slots.find(slot=>slot.id===row.selected_slot_id)
  const text=(value:unknown,max:number):value is string=>typeof value==='string'&&Array.from(value).length<=max
  if(!Number.isSafeInteger(row.id)||Number(row.id)<=0||row.poll_id!==poll.id||row.group_id!==poll.group_id||!slot||
    !utc(row.start_at)||!utc(row.end_at)||row.start_at!==slot.start_at||row.end_at!==slot.end_at||!utc(row.updated_at)||
    !text(row.title,100)||!row.title.trim()||!text(row.location,200)||!text(row.selection_reason,500)||!text(row.agenda,10000)||!text(row.minutes,10000))return invalid()
  return {id:Number(row.id),poll_id:poll.id,group_id:poll.group_id,selected_slot_id:slot.id,title:row.title,location:row.location,start_at:row.start_at,end_at:row.end_at,selection_reason:row.selection_reason,agenda:row.agenda,minutes:row.minutes,updated_at:row.updated_at}
}
export const meetingsApi={
  async get(poll:Poll,signal?:AbortSignal){
    const result=await request<unknown>(`/api/v1/polls/${identifier(poll.id)}/meeting`,{signal})
    return result.data===null?null:decode(result.data,poll,result.request_id,false)
  },
  async confirm(poll:Poll,body:ConfirmBody){
    const result=await request<unknown>(`/api/v1/polls/${identifier(poll.id)}/confirm`,{method:'POST',body})
    const meeting=decode(result.data,poll,result.request_id,true)
    if(meeting.selected_slot_id!==body.slot_id)throw new ApiFailure('protocol','确认结果与所选时间不同，请先读取核对。',undefined,undefined,result.request_id,undefined,true)
    return meeting
  },
}
