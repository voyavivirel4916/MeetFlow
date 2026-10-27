import {ApiFailure,request} from './api/client'
import {utc} from './polls/api'
import {decodeTask,type Task} from './tasks/api'
export type PendingPoll={id:number;group_id:number;group_name:string;title:string;response_deadline:string;candidate_count:number;submitted_count:number;participant_count:number}
export type UpcomingMeeting={id:number;group_id:number;group_name:string;title:string;location:string;start_at:string;end_at:string}
export type DashboardGroup={id:number;name:string;owner_id:number;member_count:number}
type Section<T>={total:number;items:T[]}
export type Dashboard={generated_at:string;pending_polls:Section<PendingPoll>;upcoming_meetings:Section<UpcomingMeeting>;tasks:Section<Task&{group_name:string}>;groups:Section<DashboardGroup>}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)
const positive=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>0
const text=(v:unknown):v is string=>typeof v==='string'&&!!v.trim()&&Array.from(v).length<=100
export async function readDashboard(userId:number,signal?:AbortSignal):Promise<Dashboard>{
 const result=await request<unknown>('/api/v1/dashboard',{signal}),value=result.data
 const invalid=():never=>{throw new ApiFailure('protocol','工作台数据需要重新读取核对。',undefined,undefined,result.request_id)}
 if(!object(value)||!utc(value.generated_at))return invalid()
 const generated=value.generated_at
 function section<T>(input:unknown,parse:(row:Record<string,unknown>)=>T):Section<T>{
  if(!object(input)||!Number.isSafeInteger(input.total)||Number(input.total)<0||!Array.isArray(input.items)||input.items.length!==Math.min(5,Number(input.total)))return invalid()
  const ids=new Set<number>()
  const items=input.items.map(row=>{if(!object(row)||!positive(row.id)||ids.has(row.id))return invalid();ids.add(row.id);return parse(row)})
  return {total:Number(input.total),items}
 }
 const pending_polls=section(value.pending_polls,row=>{
  if(!positive(row.group_id)||!text(row.group_name)||!text(row.title)||!utc(row.response_deadline)||row.response_deadline<=generated||
   !positive(row.candidate_count)||row.candidate_count>15||!positive(row.participant_count)||row.participant_count>20||
   !Number.isSafeInteger(row.submitted_count)||Number(row.submitted_count)<0||Number(row.submitted_count)>=row.participant_count)return invalid()
  return row as unknown as PendingPoll
 })
 const upcoming_meetings=section(value.upcoming_meetings,row=>{
  if(!positive(row.group_id)||!text(row.group_name)||!text(row.title)||typeof row.location!=='string'||row.location.length>200||!utc(row.start_at)||!utc(row.end_at)||row.start_at>=row.end_at||row.end_at<=generated||Date.parse(row.start_at)>=Date.parse(generated)+7*86400000)return invalid()
  return row as unknown as UpcomingMeeting
 })
 const tasks=section(value.tasks,row=>{
  const task=decodeTask(row,result.request_id)
  if(task.assignee_id!==userId||!['TODO','IN_PROGRESS'].includes(task.status)||!text(row.group_name))return invalid()
  return {...task,group_name:row.group_name}
 })
 const groups=section(value.groups,row=>{
  if(!text(row.name)||!positive(row.owner_id)||!positive(row.member_count)||row.member_count>20)return invalid()
  return {id:Number(row.id),name:row.name,owner_id:row.owner_id,member_count:row.member_count}
 })
 for(const [items,key] of [[pending_polls.items,'response_deadline'],[upcoming_meetings.items,'start_at'],[tasks.items,'due_at']] as const){
  for(let i=1;i<items.length;i++){
   const previous=items[i-1] as unknown as Record<string,unknown>,current=items[i] as unknown as Record<string,unknown>
   if(String(previous[key])>String(current[key])||(previous[key]===current[key]&&Number(previous.id)>=Number(current.id)))return invalid()
  }
 }
 return {generated_at:generated,pending_polls,upcoming_meetings,tasks,groups}
}
