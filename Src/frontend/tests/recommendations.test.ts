import { afterEach, expect, it, vi } from 'vitest'
import type { Matrix } from '../src/votes/matrix'
import { recommendationsApi } from '../src/votes/recommendations'

const zero = {available_count:0,maybe_count:0,unavailable_count:0,unanswered_count:0}
const matrix:Matrix = {poll_id:1,effective_status:'OPEN',
  participants:[{user_id:1,username:'owner',importance:'REQUIRED',submitted_at:'2026-10-27T00:00:00.000Z',...zero,available_count:2},
    {user_id:2,username:'member',importance:'NORMAL',submitted_at:'2026-10-27T00:00:00.000Z',...zero,unavailable_count:2},
    {user_id:3,username:'waiting',importance:'REQUIRED',submitted_at:null,...zero,unanswered_count:2}],
  slots:[3,4].map((id,index)=>({id,start_at:`2026-10-${28+index}T00:00:00.000Z`,end_at:`2026-10-${28+index}T01:00:00.000Z`,...zero,available_count:1,unavailable_count:1,unanswered_count:1})),
  cells:[3,4].flatMap(slot_id=>[{user_id:1,slot_id,availability:'AVAILABLE' as const},{user_id:2,slot_id,availability:'UNAVAILABLE' as const},{user_id:3,slot_id,availability:null}]),
  progress:{participant_count:3,submitted_count:2,unsubmitted_count:1}}
const item = {slot_id:3,rank:1,base_score:4,score:2,required_unavailable_count:0,required_unsubmitted_count:1,required_maybe_count:0,
  available_count:1,maybe_count:0,unavailable_count:1,unsubmitted_count:1,conflict_user_ids:[2],reason:'基础分4，未填扣分2，最终分2。必到成员有1人未填，出席情况尚未确定。'}
const response = {poll_id:1,items:[item,{...item,slot_id:4,rank:2}]}
function mock(value:unknown){
  const id='c07e357967c148068a4f9aa539c759e2'
  const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify({data:value,request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}})))
  vi.stubGlobal('fetch',fetch);return fetch
}
afterEach(()=>vi.unstubAllGlobals())
it('reads server ranking once, strips extras and does not change scores or explanations',async()=>{
  const fetch=mock({...response,extra:'private',items:response.items.map(row=>({...row,secret:'private'}))})
  expect(await recommendationsApi.get(matrix)).toEqual(response.items)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1/recommendations',expect.objectContaining({method:'GET',credentials:'same-origin'}))
})
it.each([
  ['foreign poll',{...response,poll_id:2}],['missing candidate',{...response,items:[item]}],
  ['duplicate candidate',{...response,items:[item,{...item,rank:2}]}],
  ['invalid rank',{...response,items:[{...item,rank:0},response.items[1]]}],
  ['foreign slot',{...response,items:[{...item,slot_id:999},response.items[1]]}],
  ['noninteger score',{...response,items:[{...item,score:'2'},response.items[1]]}],
  ['noninteger base',{...response,items:[{...item,base_score:4.5},response.items[1]]}],
  ['empty reason',{...response,items:[{...item,reason:' '},response.items[1]]}],
  ['wrong available',{...response,items:[{...item,available_count:2},response.items[1]]}],
  ['wrong unknown',{...response,items:[{...item,unsubmitted_count:0},response.items[1]]}],
  ['wrong required conflict',{...response,items:[{...item,required_unavailable_count:1},response.items[1]]}],
  ['hidden required unknown',{...response,items:[{...item,required_unsubmitted_count:0},response.items[1]]}],
  ['wrong required maybe',{...response,items:[{...item,required_maybe_count:1},response.items[1]]}],
  ['foreign conflict user',{...response,items:[{...item,conflict_user_ids:[1]},response.items[1]]}],
  ['duplicate conflict user',{...response,items:[{...item,conflict_user_ids:[2,2]},response.items[1]]}],
])('rejects %s instead of mixing it with another matrix snapshot',async(_name,value)=>{
  mock(value)
  await expect(recommendationsApi.get(matrix)).rejects.toMatchObject({kind:'protocol',uncertain:false})
})
it('keeps a server explanation as plain text data',async()=>{
  mock({...response,items:[{...item,reason:'<img src=x onerror=alert(1)>'},response.items[1]]})
  expect((await recommendationsApi.get(matrix))[0]!.reason).toBe('<img src=x onerror=alert(1)>')
})
