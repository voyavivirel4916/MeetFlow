import { afterEach, expect, it, vi } from 'vitest'
import { availabilityLabel, cellIndex, cellKey, matrixApi, type Matrix } from '../src/votes/matrix'

const zero = { available_count:0,maybe_count:0,unavailable_count:0,unanswered_count:0 }
const base: Matrix = { poll_id:1,effective_status:'OPEN',
  participants:[{user_id:1,username:'owner',importance:'REQUIRED',submitted_at:'2026-10-27T00:00:00.000Z',...zero,available_count:1,maybe_count:1},
    {user_id:2,username:'member',importance:'NORMAL',submitted_at:null,...zero,unanswered_count:2}],
  slots:[{id:3,start_at:'2026-10-28T00:00:00.000Z',end_at:'2026-10-28T01:00:00.000Z',...zero,available_count:1,unanswered_count:1},
    {id:4,start_at:'2026-10-29T00:00:00.000Z',end_at:'2026-10-29T01:00:00.000Z',...zero,maybe_count:1,unanswered_count:1}],
  cells:[{user_id:1,slot_id:3,availability:'AVAILABLE'},{user_id:1,slot_id:4,availability:'MAYBE'},
    {user_id:2,slot_id:3,availability:null},{user_id:2,slot_id:4,availability:null}],
  progress:{participant_count:2,submitted_count:1,unsubmitted_count:1} }
function mock(value: unknown) {
  const id = 'c07e357967c148068a4f9aa539c759e2'
  const fetch = vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify({data:value,request_id:id}),{
    headers:{'Content-Type':'application/json','X-Request-ID':id},
  })))
  vi.stubGlobal('fetch',fetch)
  return fetch
}
afterEach(()=>vi.unstubAllGlobals())
it('keeps unknown distinct from all three states and indexes by both identifiers',()=>{
  expect(availabilityLabel(null)).toBe('未填')
  expect(['AVAILABLE','MAYBE','UNAVAILABLE'].map(value=>availabilityLabel(value as 'AVAILABLE'))).toEqual(['有空','勉强','没空'])
  const index = cellIndex(base)
  expect(index.get(cellKey(1,3))).toBe('AVAILABLE')
  expect(index.get(cellKey(2,3))).toBeNull()
})
it('reads once, strips private extras and preserves the server snapshot',async()=>{
  const fetch = mock({...base,token:'private',participants:base.participants.map(person=>({...person,email:'private@example.com'}))})
  expect(await matrixApi.get(1)).toEqual(base)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1/matrix',expect.objectContaining({method:'GET',credentials:'same-origin'}))
})
it('accepts empty draft and zero-denominator progress without inventing cells',async()=>{
  const empty = {...base,effective_status:'DRAFT',participants:[],slots:[],cells:[],progress:{participant_count:0,submitted_count:0,unsubmitted_count:0}}
  mock(empty)
  expect(await matrixApi.get('1')).toEqual(empty)
})
it.each(['DRAFT','OPEN','CLOSED','CONFIRMED','CANCELLED'])('accepts readable state %s',async status=>{
  mock({...base,effective_status:status})
  expect((await matrixApi.get(1)).effective_status).toBe(status)
})
const malformed: [string,(value: Matrix)=>unknown][] = [
  ['foreign poll',v=>({...v,poll_id:2})],['unknown state',v=>({...v,effective_status:'DONE'})],
  ['missing cell',v=>({...v,cells:v.cells.slice(1)})],['duplicate cell',v=>({...v,cells:[v.cells[0],v.cells[0],...v.cells.slice(2)]})],
  ['foreign participant',v=>({...v,cells:[{...v.cells[0],user_id:99},...v.cells.slice(1)]})],
  ['foreign slot',v=>({...v,cells:[{...v.cells[0],slot_id:99},...v.cells.slice(1)]})],
  ['invalid state value',v=>({...v,cells:[{...v.cells[0],availability:'UNKNOWN'},...v.cells.slice(1)]})],
  ['unanswered counted available',v=>({...v,slots:[{...v.slots[0],available_count:2,unanswered_count:0},v.slots[1]]})],
  ['incorrect person count',v=>({...v,participants:[{...v.participants[0],maybe_count:0},v.participants[1]]})],
  ['negative count',v=>({...v,slots:[{...v.slots[0],maybe_count:-1},v.slots[1]]})],
  ['fractional count',v=>({...v,participants:[{...v.participants[0],available_count:0.5},v.participants[1]]})],
  ['wrong submitted total',v=>({...v,progress:{participant_count:2,submitted_count:2,unsubmitted_count:0}})],
  ['wrong participant total',v=>({...v,progress:{participant_count:3,submitted_count:1,unsubmitted_count:2}})],
  ['wrong remaining total',v=>({...v,progress:{participant_count:2,submitted_count:1,unsubmitted_count:2}})],
  ['duplicate person',v=>({...v,participants:[v.participants[0],v.participants[0]]})],
  ['duplicate slot',v=>({...v,slots:[v.slots[0],v.slots[0]]})],
  ['bad timestamp',v=>({...v,participants:[{...v.participants[0],submitted_at:'2026-10-27T00:00:00'},v.participants[1]]})],
  ['inverted times',v=>({...v,slots:[{...v.slots[0],end_at:v.slots[0]!.start_at},v.slots[1]]})],
  ['invalid role',v=>({...v,participants:[{...v.participants[0],importance:'ADMIN'},v.participants[1]]})],
]
it.each(malformed)('rejects %s without presenting it as empty or a successful refresh',async(_name,change)=>{
  mock(change(structuredClone(base)))
  await expect(matrixApi.get(1)).rejects.toMatchObject({kind:'protocol',uncertain:false})
})
it.each([null,{},[]])('rejects missing response structure %s',async value=>{
  mock(value)
  await expect(matrixApi.get(1)).rejects.toMatchObject({kind:'protocol'})
})
it('rejects invalid IDs without issuing requests',async()=>{
  const fetch = mock(base)
  await expect(matrixApi.get('../groups')).rejects.toMatchObject({status:404})
  expect(fetch).not.toHaveBeenCalled()
})
