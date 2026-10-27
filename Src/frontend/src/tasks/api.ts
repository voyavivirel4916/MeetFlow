import {ApiFailure,request} from '../api/client'
import {identifier,utc} from '../polls/api'
import {localMs} from '../polls/editor'
export const states={TODO:'待开始',IN_PROGRESS:'进行中',DONE:'已完成',CANCELLED:'已取消'} as const
export type Status=keyof typeof states
export type Task={id:number;group_id:number;meeting_id:number;creator_id:number;assignee_id:number;title:string;description:string;due_at:string;status:Status;completed_at:string|null;created_at:string;updated_at:string;version:number}
export type TaskUpdate={expected_version:number;title?:string;description?:string;assignee_id?:number;due_at?:string}
export type TaskPage={items:Task[];page:number;page_size:number;total:number}
export type TaskBody={title:string;description:string;assignee_id:number;due_at:string;client_request_id:string}
export type TaskFields={title:string;description:string;assignee:string;due:string}
export function validateTask(fields:TaskFields,members:number[],now=Date.now()){
 const errors:Partial<Record<keyof TaskFields,string>>={}
 const invalid=(s:string)=>/\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(s)
 if(!fields.title.trim()||Array.from(fields.title.trim()).length>100||invalid(fields.title))errors.title='标题需为1～100个字符。'
 if(Array.from(fields.description).length>10000||invalid(fields.description))errors.description='说明最多10000个有效字符。'
 if(!members.includes(Number(fields.assignee)))errors.assignee='请选择本小组执行人。'
 if(!Number.isFinite(localMs(fields.due))||localMs(fields.due)<=now)errors.due='截止时间须晚于当前时间。'
 return errors
}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
const positive=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>0
function invalid(id:string,writing=false):never{throw new ApiFailure('protocol','任务结果需要重新读取核对。',undefined,undefined,id,undefined,writing)}
export function decodeTask(value:unknown,id:string,writing=false):Task{
 if(!object(value)||!['id','group_id','meeting_id','creator_id','assignee_id','version'].every(key=>positive(value[key]))||
 typeof value.title!=='string'||!value.title.trim()||Array.from(value.title).length>100||typeof value.description!=='string'||Array.from(value.description).length>10000||
 typeof value.status!=='string'||!Object.hasOwn(states,value.status)||!utc(value.due_at)||!utc(value.created_at)||!utc(value.updated_at)||Date.parse(value.due_at)<=Date.parse(value.created_at)||
 (value.status==='DONE'?!utc(value.completed_at):value.completed_at!==null))return invalid(id,writing)
 return {id:Number(value.id),group_id:Number(value.group_id),meeting_id:Number(value.meeting_id),creator_id:Number(value.creator_id),assignee_id:Number(value.assignee_id),title:value.title,description:value.description,due_at:value.due_at,status:value.status as Status,completed_at:value.completed_at as string|null,created_at:value.created_at,updated_at:value.updated_at,version:Number(value.version)}
}
const decode=decodeTask
export const tasksApi={
 async list(scope:{groupId?:number;meetingId?:number;userId:number},page=1,status:''|Status='',signal?:AbortSignal,q=''):Promise<TaskPage>{
  const query=new URLSearchParams({page:String(page),page_size:'20'});if(status)query.set('status',status);if(scope.meetingId)query.set('meeting_id',String(scope.meetingId))
  if(q)query.set('q',q)
  const result=await request<unknown>(`/api/v1/${scope.groupId?`groups/${identifier(scope.groupId)}/tasks`:'tasks/mine'}?${query}`,{signal}),value=result.data
  if(!object(value)||!Array.isArray(value.items)||value.page!==page||value.page_size!==20||!Number.isSafeInteger(value.total)||Number(value.total)<0||value.items.length!==Math.min(20,Math.max(0,Number(value.total)-(page-1)*20)))return invalid(result.request_id)
  const items=value.items.map(row=>decode(row,result.request_id))
  if(new Set(items.map(row=>row.id)).size!==items.length||items.some(row=>(scope.groupId?row.group_id!==scope.groupId:row.assignee_id!==scope.userId)||
    (scope.meetingId&&row.meeting_id!==scope.meetingId)||(status?row.status!==status:!scope.groupId&&['DONE','CANCELLED'].includes(row.status)))||
    items.some((row,i)=>i>0&&(row.due_at<items[i-1]!.due_at||(row.due_at===items[i-1]!.due_at&&row.id<=items[i-1]!.id))))return invalid(result.request_id)
  return {items,page,page_size:20,total:Number(value.total)}
 },
 async create(meetingId:number,groupId:number,body:TaskBody){
  const result=await request<unknown>(`/api/v1/meetings/${identifier(meetingId)}/tasks`,{method:'POST',body}),value=decode(result.data,result.request_id,true)
  if(value.meeting_id!==meetingId||value.group_id!==groupId||(value.version===1&&(value.title!==body.title||value.description!==body.description||value.assignee_id!==body.assignee_id||value.due_at!==body.due_at)))return invalid(result.request_id,true)
  return value
 },
 async status(task:Task,status:Status){
  const result=await request<unknown>(`/api/v1/tasks/${identifier(task.id)}/status`,{method:'PATCH',body:{status,expected_version:task.version}}),value=decode(result.data,result.request_id,true)
  if(['id','meeting_id','group_id','creator_id','assignee_id','title','description','due_at','created_at'].some(key=>value[key as keyof Task]!==task[key as keyof Task])||value.status!==status||value.version!==(task.status===status?task.version:task.version+1))return invalid(result.request_id,true)
  return value
 },
 async edit(task:Task,body:TaskUpdate){
  const result=await request<unknown>(`/api/v1/tasks/${identifier(task.id)}`,{method:'PATCH',body}),value=decode(result.data,result.request_id,true)
  const fields=['title','description','assignee_id','due_at'] as const
  if(['id','meeting_id','group_id','creator_id','status','completed_at','created_at'].some(key=>value[key as keyof Task]!==task[key as keyof Task])||
    fields.some(key=>value[key]!== (body[key]??task[key]))||value.version!==task.version+(fields.some(key=>body[key]!==undefined&&body[key]!==task[key])?1:0))return invalid(result.request_id,true)
  return value
 },
}
