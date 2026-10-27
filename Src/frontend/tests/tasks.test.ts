import {afterEach,expect,it,vi} from 'vitest'
import {tasksApi,validateTask,type Task} from '../src/tasks/api'
const now=Date.parse('2026-10-27T00:00:00.000Z')
const task:Task={version:1,id:1,group_id:2,meeting_id:3,creator_id:4,assignee_id:5,title:'整理方案',description:'讨论\n结果',due_at:'2026-10-28T00:00:00.000Z',status:'TODO',completed_at:null,created_at:'2026-10-27T00:00:00.000Z',updated_at:'2026-10-27T00:00:00.000Z'}
function mock(data:unknown){const id='c07e357967c148068a4f9aa539c759e2';const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({data,request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}}));vi.stubGlobal('fetch',fetch);return fetch}
afterEach(()=>vi.unstubAllGlobals())
const fields={title:'  整理方案  ',description:'',assignee:'5',due:'2026-10-28T08:00'}
it('validates member, minute precision and Unicode text',()=>expect(validateTask(fields,[5],now)).toEqual({}))
it.each([{title:' '},{title:'😀'.repeat(101)},{description:'x'.repeat(10001)},{title:'\u0000'},{assignee:'6'},{due:'2026-02-30T12:00'},{due:'2026-10-27T08:00'}])('rejects invalid field %j',change=>expect(Object.keys(validateTask({...fields,...change},[5],now))).not.toHaveLength(0))
it('validates a scoped task page and does not expose request id',async()=>{mock({items:[{...task,client_request_id:'private'}],page:1,page_size:20,total:1});expect((await tasksApi.list({groupId:2,userId:4})).items).toEqual([task])})
it.each([{group_id:9},{status:'OTHER'},{completed_at:task.created_at},{due_at:task.created_at},{assignee_id:0},{description:5}])('rejects mismatched task data %j',async change=>{mock({items:[{...task,...change}],page:1,page_size:20,total:1});await expect(tasksApi.list({groupId:2,userId:4})).rejects.toMatchObject({kind:'protocol'})})
it('does not show another assignee or completed task in default mine',async()=>{mock({items:[task],page:1,page_size:20,total:1});await expect(tasksApi.list({userId:4})).rejects.toMatchObject({kind:'protocol'});mock({items:[{...task,status:'DONE',completed_at:task.updated_at}],page:1,page_size:20,total:1});await expect(tasksApi.list({userId:5})).rejects.toMatchObject({kind:'protocol'})})
it('rejects another meeting in the current meeting task list',async()=>{mock({items:[task],page:1,page_size:20,total:1});await expect(tasksApi.list({groupId:2,meetingId:99,userId:4})).rejects.toMatchObject({kind:'protocol'})})
it('retains the caller creation id in the submitted body',async()=>{const fetch=mock(task),body={title:task.title,description:task.description,assignee_id:5,due_at:task.due_at,client_request_id:'621ff63b-2850-4c3c-a324-7201af5eb970'};expect(await tasksApi.create(3,2,body)).toEqual(task);expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual(body)})
it('rejects wrong mutation result as uncertain',async()=>{mock({...task,assignee_id:6,status:'DONE',completed_at:task.updated_at});await expect(tasksApi.status(task,'DONE')).rejects.toMatchObject({uncertain:true})})
it('accepts actual completion and reopening snapshots',async()=>{mock({...task,version:2,status:'DONE',completed_at:task.updated_at});expect((await tasksApi.status(task,'DONE')).status).toBe('DONE');mock({...task,version:3});expect((await tasksApi.status({...task,version:2,status:'DONE',completed_at:task.updated_at},'TODO')).completed_at).toBeNull()})
it('includes the expected version in a status request',async()=>{
 const fetch=mock({...task,version:2,status:'IN_PROGRESS'})
 await tasksApi.status(task,'IN_PROGRESS')
 expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual({status:'IN_PROGRESS',expected_version:1})
})
it.each([undefined,0,true,1.5])('rejects invalid task version %s',async version=>{
 mock({items:[{...task,version}],page:1,page_size:20,total:1})
 await expect(tasksApi.list({groupId:2,userId:4})).rejects.toMatchObject({kind:'protocol'})
})
it('does not include cancelled tasks in default mine',async()=>{
 mock({items:[{...task,status:'CANCELLED'}],page:1,page_size:20,total:1})
 await expect(tasksApi.list({userId:5})).rejects.toMatchObject({kind:'protocol'})
})
it('edits only changed fields and checks the new snapshot',async()=>{
 const fetch=mock({...task,version:2,title:'新标题'})
 const body={expected_version:1,title:'新标题'}
 expect((await tasksApi.edit(task,body)).title).toBe('新标题')
 expect(JSON.parse(fetch.mock.calls[0]![1].body)).toEqual(body)
})
it('rejects a stale snapshot reported as successful edit',async()=>{
 mock({...task,title:'新标题'})
 await expect(tasksApi.edit(task,{expected_version:1,title:'新标题'})).rejects.toMatchObject({uncertain:true})
})
it('accepts the current edited task when retrying its original creation',async()=>{
 mock({...task,version:2,title:'编辑后的标题'})
 expect((await tasksApi.create(3,2,{title:task.title,description:task.description,assignee_id:5,due_at:task.due_at,client_request_id:'621ff63b-2850-4c3c-a324-7201af5eb970'})).title).toBe('编辑后的标题')
})
