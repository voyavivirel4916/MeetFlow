import {afterEach,expect,it,vi} from 'vitest'
import {readDashboard} from '../src/dashboard'
const time='2026-10-27T00:00:00.000Z'
const empty=()=>({generated_at:time,pending_polls:{total:0,items:[]},upcoming_meetings:{total:0,items:[]},tasks:{total:0,items:[]},groups:{total:0,items:[]}})
const poll={id:1,group_id:2,group_name:'课程组',title:'评审',response_deadline:'2026-10-28T00:00:00.000Z',candidate_count:3,participant_count:4,submitted_count:2}
function mock(value:unknown){const id='c07e357967c148068a4f9aa539c759e2';vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({data:value,request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}})))}
afterEach(()=>vi.unstubAllGlobals())
it('accepts an empty snapshot without inventing tasks',async()=>{mock(empty());expect(await readDashboard(5)).toEqual(empty())})
it('accepts a pending participant summary',async()=>{const value={...empty(),pending_polls:{total:1,items:[poll]}};mock(value);expect((await readDashboard(5)).pending_polls.total).toBe(1)})
it.each([{response_deadline:time},{candidate_count:0},{submitted_count:4},{participant_count:21}])('rejects inconsistent pending metadata %j',async change=>{
 mock({...empty(),pending_polls:{total:1,items:[{...poll,...change}]}});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})
})
it('requires complete capped lists instead of silently displaying partial data',async()=>{
 mock({...empty(),pending_polls:{total:7,items:[poll]}});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})
})
it('rejects duplicate ids even when counts match',async()=>{
 mock({...empty(),pending_polls:{total:2,items:[poll,poll]}});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})
})
it('rejects a finished meeting in an upcoming snapshot',async()=>{
 mock({...empty(),upcoming_meetings:{total:1,items:[{id:1,group_id:2,group_name:'组',title:'会议',location:'',start_at:'2026-10-26T00:00:00.000Z',end_at:time}]}});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})
})
it('rejects another assignee in my tasks',async()=>{
 mock({...empty(),tasks:{total:1,items:[{id:1,group_id:2,meeting_id:3,creator_id:4,assignee_id:6,title:'说明',description:'',status:'TODO',version:1,group_name:'组',due_at:'2026-10-28T00:00:00.000Z',created_at:time,updated_at:time,completed_at:null}]}});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})
})
it('does not accept a missing section as zero',async()=>{const value=empty();mock({...value,tasks:undefined});await expect(readDashboard(5)).rejects.toMatchObject({kind:'protocol'})})
