import {afterEach,expect,it,vi} from 'vitest'
import {meetingsApi,validateConfirmation,validateContent} from '../src/meetings/api'
import type {Poll} from '../src/polls/api'
import type {Recommendation} from '../src/votes/recommendations'
const item={rank:1,required_unavailable_count:0,required_unsubmitted_count:0,required_maybe_count:0} as Recommendation
const poll={id:1,group_id:2,slots:[{id:3,start_at:'2026-10-28T01:00:00.000Z',end_at:'2026-10-28T02:00:00.000Z'}]} as Poll
const meeting={id:4,poll_id:1,group_id:2,selected_slot_id:3,title:'评审',location:'',start_at:poll.slots[0]!.start_at,end_at:poll.slots[0]!.end_at,selection_reason:'',agenda:'',minutes:'',updated_at:'2026-10-27T00:00:00.000Z'}
function mock(data:unknown){const id='c07e357967c148068a4f9aa539c759e2';const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({data,request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}}));vi.stubGlobal('fetch',fetch);return fetch}
afterEach(()=>vi.unstubAllGlobals())
it('allows the first safe choice and required maybe without forcing a reason',()=>{
 expect(validateConfirmation(item,false,'')).toEqual({})
 expect(validateConfirmation({...item,required_maybe_count:1},false,'')).toEqual({})
})
it.each([{rank:2},{required_unavailable_count:1},{required_unsubmitted_count:1}])('requires both acknowledgement and reason for %j',risk=>{
 const value={...item,...risk};expect(Object.keys(validateConfirmation(value,false,'')).length).toBe(2)
 expect(validateConfirmation(value,true,' 已协调 ')).toEqual({})
 expect(validateConfirmation(value,false,'已协调')).toHaveProperty('acknowledged')
 expect(validateConfirmation(value,true,' ')).toHaveProperty('selection_reason')
})
it.each(['x'.repeat(501),'\u0000','\ud800','\udc00'])('rejects invalid or excessive reason',reason=>expect(validateConfirmation(item,true,reason)).toHaveProperty('selection_reason'))
it('counts Unicode characters and accepts exactly 500 emoji',()=>expect(validateConfirmation(item,false,'😀'.repeat(500))).toEqual({}))
it('reads a missing meeting without writing or inventing a result',async()=>{const fetch=mock(null);expect(await meetingsApi.get(poll)).toBeNull();expect(fetch).toHaveBeenCalledTimes(1);expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1/meeting',expect.objectContaining({method:'GET'}))})
it('confirms once and strips nonpublic properties',async()=>{const fetch=mock({...meeting,private:'secret'});expect(await meetingsApi.confirm(poll,{slot_id:3,acknowledged:false,selection_reason:''})).toEqual(meeting);expect(fetch).toHaveBeenCalledTimes(1)})
it.each([{poll_id:9},{group_id:9},{selected_slot_id:99},{start_at:'2026-10-29T01:00:00.000Z'},{end_at:'bad'},{id:0},{title:''},{selection_reason:'x'.repeat(501)}])('rejects mismatched confirmation response %j as uncertain',async change=>{mock({...meeting,...change});await expect(meetingsApi.confirm(poll,{slot_id:3,acknowledged:false,selection_reason:''})).rejects.toMatchObject({kind:'protocol',uncertain:true})})
it('rejects a different selected slot even if it belongs to the poll',async()=>{mock(meeting);await expect(meetingsApi.confirm({...poll,slots:[...poll.slots,{...poll.slots[0]!,id:5}]},{slot_id:5,acknowledged:true,selection_reason:'协调'})).rejects.toMatchObject({uncertain:true})})
it('accepts empty and exactly 10000 Unicode characters of plain meeting content',()=>{
 expect(validateContent({agenda:'',minutes:'😀'.repeat(10000)})).toEqual({})
 expect(validateContent({agenda:'<script>not HTML</script>',minutes:'  \n  '})).toEqual({})
})
it.each(['x'.repeat(10001),'\u0000','\ud800','\udc00'])('rejects invalid agenda and minutes',value=>expect(Object.keys(validateContent({agenda:value,minutes:value}))).toEqual(['agenda','minutes']))
it('reads meeting detail by its own identity',async()=>{mock(meeting);expect(await meetingsApi.detail(4)).toEqual(meeting)})
it('rejects a detail for a different identity',async()=>{mock(meeting);await expect(meetingsApi.detail(99)).rejects.toMatchObject({kind:'protocol',uncertain:false})})
it('preserves whitespace and Unicode when saving plain content',async()=>{
 const content={agenda:'  讨论🧩\n',minutes:'<p>结论</p>'};const fetch=mock({...meeting,...content});expect(await meetingsApi.update(meeting,content)).toEqual({...meeting,...content});expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([{title:'changed'},{poll_id:99},{agenda:'not sent'},{minutes:'not sent'},{start_at:meeting.end_at}])('requires reconciliation for inconsistent save %j',async change=>{mock({...meeting,...change});await expect(meetingsApi.update(meeting,{agenda:'',minutes:''})).rejects.toMatchObject({uncertain:true})})
