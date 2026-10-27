import {afterEach,expect,it,vi} from 'vitest'
import {pollsApi,type Poll} from '../src/polls/api'
const id='c07e357967c148068a4f9aa539c759e2'
const time='2026-10-27T00:00:00.000Z'
const poll:Poll={id:1,group_id:2,title:'讨论',description:'',location:'',response_deadline:time,status:'DRAFT',effective_status:'DRAFT',participants:[],slots:[],updated_at:time,deleted_at:null,archived_at:null}
function mock(data:unknown){const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({data,request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}}));vi.stubGlobal('fetch',fetch);return fetch}
afterEach(()=>vi.unstubAllGlobals())
it('decodes deletion and sends only the explicit organization request',async()=>{
 const fetch=mock({...poll,deleted_at:time})
 expect((await pollsApi.organize(1,'delete')).deleted_at).toBe(time)
 expect(fetch).toHaveBeenCalledTimes(1)
 expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1/delete',expect.objectContaining({method:'POST',body:'{}'}))
})
it.each([
 {...poll,deleted_at:time,status:'CONFIRMED',effective_status:'CONFIRMED'},
 {...poll,deleted_at:'bad'}, {...poll,archived_at:time},
 {...poll,deleted_at:time,archived_at:time}, {...poll,id:3},
 poll
])('rejects malformed or unconfirmed deletion result without retry',async value=>{
 const fetch=mock(value)
 await expect(pollsApi.organize(1,'delete')).rejects.toMatchObject({kind:'protocol',uncertain:true})
 expect(fetch).toHaveBeenCalledTimes(1)
})
it('uses the history query and keeps pagination metadata',async()=>{
 const archived={...poll,status:'CONFIRMED',effective_status:'CONFIRMED',archived_at:time}
 const fetch=mock({items:[archived],page:1,page_size:20,total:1})
 expect((await pollsApi.list(2,1,undefined,'history')).items[0]?.archived_at).toBe(time)
 expect(fetch).toHaveBeenCalledWith('/api/v1/groups/2/polls?page=1&page_size=20&view=history',expect.anything())
})
it.each(['current','history','trash'] as const)('rejects records from the wrong view: %s',async view=>{
 const value=view==='current'?{...poll,deleted_at:time}:poll
 mock({items:[value],page:1,page_size:20,total:1})
 await expect(pollsApi.list(2,1,undefined,view)).rejects.toMatchObject({kind:'protocol'})
})
it('restore cannot silently report a still deleted record',async()=>{
 mock({...poll,deleted_at:time})
 await expect(pollsApi.organize(1,'restore')).rejects.toMatchObject({uncertain:true})
})
