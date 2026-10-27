import { ApiFailure, request } from '../api/client'
import { identifier, utc, type Poll } from '../polls/api'
import type { Recommendation } from '../votes/recommendations'

export type Meeting={id:number;poll_id:number;group_id:number;selected_slot_id:number;title:string;location:string;start_at:string;end_at:string;selection_reason:string;agenda:string;minutes:string;updated_at:string}
export type ConfirmBody={slot_id:number;acknowledged:boolean;selection_reason:string}
export type MeetingContent={agenda:string;minutes:string}
export function validateContent(fields:MeetingContent){
  const errors:Partial<Record<keyof MeetingContent,string>>={}
  for(const key of ['agenda','minutes'] as const)if(Array.from(fields[key]).length>10000||/\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(fields[key]))errors[key]='请输入有效文字，最多10000个字符。'
  return errors
}
export const requiresAck=(item:Recommendation)=>item.rank!==1||item.required_unavailable_count>0||item.required_unsubmitted_count>0
export function validateConfirmation(item:Recommendation,acknowledged:boolean,reason:string){
  const errors:{acknowledged?:string;selection_reason?:string}={}
  if(requiresAck(item)&&!acknowledged)errors.acknowledged='请先确认已了解这些风险。'
  if((requiresAck(item)&&!reason.trim())||Array.from(reason.trim()).length>500||/\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(reason))errors.selection_reason='请填写有效理由，最多500个字符。'
  return errors
}
function decode(value:unknown,poll:Poll|undefined,id:string,writing:boolean):Meeting{
  const invalid=():never=>{throw new ApiFailure('protocol','会议结果无法识别，请先读取核对。',undefined,undefined,id,undefined,writing)}
  if(!value||typeof value!=='object'||Array.isArray(value))return invalid()
  const row=value as Record<string,unknown>,slot=poll?.slots.find(slot=>slot.id===row.selected_slot_id)
  const text=(value:unknown,max:number):value is string=>typeof value==='string'&&Array.from(value).length<=max
  const positive=(value:unknown):value is number=>Number.isSafeInteger(value)&&Number(value)>0
  if(!positive(row.id)||!positive(row.poll_id)||!positive(row.group_id)||!positive(row.selected_slot_id)||
    (poll&&(!slot||row.poll_id!==poll.id||row.group_id!==poll.group_id||row.start_at!==slot.start_at||row.end_at!==slot.end_at))||
    !utc(row.start_at)||!utc(row.end_at)||Date.parse(row.start_at)>=Date.parse(row.end_at)||!utc(row.updated_at)||
    !text(row.title,100)||!row.title.trim()||!text(row.location,200)||!text(row.selection_reason,500)||!text(row.agenda,10000)||!text(row.minutes,10000))return invalid()
  return {id:Number(row.id),poll_id:row.poll_id,group_id:row.group_id,selected_slot_id:row.selected_slot_id,title:row.title,location:row.location,start_at:row.start_at,end_at:row.end_at,selection_reason:row.selection_reason,agenda:row.agenda,minutes:row.minutes,updated_at:row.updated_at}
}
export const meetingsApi={
  async detail(id:string|number,signal?:AbortSignal){
    const result=await request<unknown>(`/api/v1/meetings/${identifier(id)}`,{signal})
    const value=decode(result.data,undefined,result.request_id,false)
    if(String(value.id)!==String(id))throw new ApiFailure('protocol','会议结果与当前页面不符，请重新读取。')
    return value
  },
  async update(saved:Meeting,body:MeetingContent){
    const result=await request<unknown>(`/api/v1/meetings/${identifier(saved.id)}`,{method:'PATCH',body})
    const value=decode(result.data,undefined,result.request_id,true)
    const fixed=['id','poll_id','group_id','selected_slot_id','title','location','start_at','end_at','selection_reason'] as const
    if(fixed.some(key=>value[key]!==saved[key])||value.agenda!==body.agenda||value.minutes!==body.minutes)throw new ApiFailure('protocol','保存结果需要核对，输入仍保留。',undefined,undefined,result.request_id,undefined,true)
    return value
  },
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
