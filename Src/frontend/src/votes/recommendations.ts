import { ApiFailure, request } from '../api/client'
import { identifier } from '../polls/api'
import { cellIndex, cellKey, type Matrix } from './matrix'

export type Recommendation = { slot_id:number; rank:number; base_score:number; score:number;
  required_unavailable_count:number; required_unsubmitted_count:number; required_maybe_count:number;
  available_count:number; maybe_count:number; unavailable_count:number; unsubmitted_count:number;
  conflict_user_ids:number[]; reason:string }
const object = (value:unknown):value is Record<string,any> => !!value && typeof value==='object' && !Array.isArray(value)
function decode(value:unknown,matrix:Matrix,requestId:string):Recommendation[] {
  const invalid = ():never => { throw new ApiFailure('protocol','填写结果已更新或推荐数据不一致，请刷新。',undefined,undefined,requestId) }
  if (!object(value) || value.poll_id!==matrix.poll_id || !Array.isArray(value.items) || value.items.length!==matrix.slots.length) return invalid()
  const index = cellIndex(matrix), seen = new Set<number>()
  return value.items.map((item:unknown,position:number)=>{
    if (!object(item)) return invalid()
    const slot = matrix.slots.find(slot=>slot.id===item.slot_id)
    if (!slot || seen.has(slot.id) || item.rank!==position+1 || !Number.isSafeInteger(item.base_score) || !Number.isSafeInteger(item.score) ||
      typeof item.reason!=='string' || !item.reason.trim() || item.reason.length>2000 || !Array.isArray(item.conflict_user_ids)) return invalid()
    seen.add(slot.id)
    if (item.available_count!==slot.available_count || item.maybe_count!==slot.maybe_count || item.unavailable_count!==slot.unavailable_count || item.unsubmitted_count!==slot.unanswered_count) return invalid()
    const required = matrix.participants.filter(person=>person.importance==='REQUIRED')
    const requiredCount = (value:string|null)=>required.filter(person=>index.get(cellKey(person.user_id,slot.id))===value).length
    const conflictIds = matrix.participants.filter(person=>index.get(cellKey(person.user_id,slot.id))==='UNAVAILABLE').map(person=>person.user_id).sort((a,b)=>a-b)
    if (item.required_unavailable_count!==requiredCount('UNAVAILABLE') || item.required_unsubmitted_count!==requiredCount(null) ||
      item.required_maybe_count!==requiredCount('MAYBE') || item.conflict_user_ids.length!==conflictIds.length ||
      !item.conflict_user_ids.every((id:unknown,i:number)=>id===conflictIds[i])) return invalid()
    return {slot_id:slot.id,rank:item.rank,base_score:item.base_score,score:item.score,
      required_unavailable_count:item.required_unavailable_count,required_unsubmitted_count:item.required_unsubmitted_count,required_maybe_count:item.required_maybe_count,
      available_count:item.available_count,maybe_count:item.maybe_count,unavailable_count:item.unavailable_count,unsubmitted_count:item.unsubmitted_count,
      conflict_user_ids:[...conflictIds],reason:item.reason}
  })
}
export const recommendationsApi = {
  async get(matrix:Matrix,signal?:AbortSignal) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(matrix.poll_id)}/recommendations`,{signal})
    return decode(result.data,matrix,result.request_id)
  },
}
