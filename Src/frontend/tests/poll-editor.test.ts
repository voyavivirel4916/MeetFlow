import { afterEach, expect, it, vi } from 'vitest'
import { pollsApi, type Poll } from '../src/polls/api'
import { beijing, emptyFields, equivalent, fromPoll, localMs, payload, validate, timeFeedback } from '../src/polls/editor'

const id = 'c07e357967c148068a4f9aa539c759e2'
const poll: Poll = { id: 1, group_id: 2, title: '课程评审', description: '', location: '', response_deadline: '2026-10-28T00:00:00.000Z', status: 'DRAFT', effective_status: 'DRAFT', updated_at: '2026-10-27T00:00:00.000Z',
  participants: [{ user_id: 1, username: 'owner', importance: 'REQUIRED', submitted_at: null }],
  slots: [{ id: 3, start_at: '2026-10-28T01:00:00.000Z', end_at: '2026-10-28T02:00:00.000Z' }] }
function mock(data: unknown) {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data, request_id: id }), {
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': id },
  })))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
afterEach(() => vi.unstubAllGlobals())

it('displays Beijing minutes across days while parsing legacy precise timestamps strictly', () => {
  expect(beijing('2026-10-27T20:30:59.123Z')).toBe('2026-10-28T04:30')
  expect(localMs('2026-10-28T04:30:00.123')).toBe(Date.parse('2026-10-27T20:30:00.123Z'))
  expect(localMs('2026-10-28T08:00')).toBe(Date.parse(poll.response_deadline))
  expect(localMs('2026-10-28T08:00:00.1')).toBe(Date.parse('2026-10-28T00:00:00.100Z'))
})
it('hydrates legacy seconds to minute inputs without mutating the saved poll or weakening reconciliation', () => {
  const legacy = { ...poll, response_deadline: '2026-10-28T00:00:59.600Z' }
  const fields = fromPoll(legacy)
  expect(fields.deadline).toBe('2026-10-28T08:00')
  expect(payload(fields).response_deadline).toBe('2026-10-28T00:00:00.000Z')
  expect(legacy.response_deadline).toBe('2026-10-28T00:00:59.600Z')
  expect(equivalent(payload(fields), legacy)).toBe(false)
})
it('keeps untouched empty times quiet and validates a cleared field after interaction', () => {
  expect(timeFeedback(emptyFields(), new Set(), 0)).toEqual({})
  expect(timeFeedback(emptyFields(), new Set(['deadline']), 0)).toHaveProperty('deadline')
  const fields = fromPoll(poll)
  fields.slots.push({ key: 4, start: '', end: '' })
  expect(timeFeedback(fields, new Set(), 0)).toEqual({})
  expect(timeFeedback(fields, new Set(['end-4']), 0)).toHaveProperty('end-4')
})
it('automatically checks past cutoff, dependency changes, inverted times and duplicates without requiring publication', () => {
  const fields = fromPoll(poll)
  expect(timeFeedback(fields, new Set(), Date.parse(poll.response_deadline))).toHaveProperty('deadline')
  fields.deadline = fields.slots[0]!.start
  expect(timeFeedback(fields, new Set(), 0)).toHaveProperty('deadline', '填写截止须早于每个候选开始时间。')
  expect(timeFeedback(fields, new Set(), 0)).toHaveProperty('start-0')
  fields.deadline = '2026-10-28T08:00'
  fields.slots[0]!.end = fields.slots[0]!.start
  expect(timeFeedback(fields, new Set(), 0)).toHaveProperty('end-0')
  fields.slots[0]!.end = '2026-10-28T10:00'
  fields.slots.push({ ...fields.slots[0]!, key: 7 })
  expect(timeFeedback(fields, new Set(), 0)).toHaveProperty('start-7', '候选时段不能重复。')
  fields.slots.pop()
  expect(timeFeedback(fields, new Set(), 0)).toEqual({})
})
it.each(['', '2026-02-30T08:00', '2026-13-01T08:00', '2026-10-28T24:00', '2026-10-28T08:00Z', '2026-10-28 08:00', '2026-10-28T08:00:00.1234'])('rejects invalid local date %s', value => {
  expect(Number.isNaN(localMs(value))).toBe(true)
})
it('builds only editable input fields without IDs, names, status or submission times', () => {
  const fields = fromPoll(poll), body = payload(fields)
  expect(body.participants).toEqual([{ user_id: 1, importance: 'REQUIRED' }])
  expect(body.slots).toEqual([{ start_at: poll.slots[0].start_at, end_at: poll.slots[0].end_at }])
  expect(Object.keys(body).sort()).toEqual(['title','description','location','participants','response_deadline','slots'].sort())
  fields.participants[0]!.importance = 'NORMAL'
  expect(poll.participants[0]!.importance).toBe('REQUIRED')
})
it('allows an empty-child draft and past deadline but rejects publishing it', () => {
  const fields = { ...emptyFields(), title: '暂存', deadline: '2020-01-01T08:00' }
  expect(validate(fields)).toEqual({})
  expect(validate(fields, true)).toHaveProperty('deadline')
  expect(validate(fields, true)).toHaveProperty('participants')
  expect(validate(fields, true)).toHaveProperty('slots')
})
it('accepts a complete publish before deadline and rejects the exact deadline', () => {
  const fields = fromPoll(poll), deadline = Date.parse(poll.response_deadline)
  expect(validate(fields, true, deadline-1)).toEqual({})
  expect(validate(fields, true, deadline)).toHaveProperty('deadline')
})
it.each([{ title: ' ' }, { title: '字'.repeat(101) }, { description: '字'.repeat(10001) }, { location: '字'.repeat(201) }, { title: '\x00' }, { description: '\ud800' }])('rejects invalid text fields', changes => {
  expect(Object.keys(validate({ ...fromPoll(poll), ...changes }))).toHaveLength(1)
})
it('counts emoji as Unicode characters', () => {
  expect(validate({ ...fromPoll(poll), title: '😀'.repeat(100), description: '😀'.repeat(10000), location: '😀'.repeat(200) })).toEqual({})
})
it('rejects inverted and duplicate candidates with stable UI keys', () => {
  const fields = fromPoll(poll)
  fields.slots.push({ ...fields.slots[0]!, key: 9 })
  expect(validate(fields)).toHaveProperty('start-9')
  fields.slots[1]!.end = fields.slots[1]!.start
  expect(validate(fields)).toHaveProperty('end-9')
})
it('defers candidate count to publish and checks cutoff before every candidate', () => {
  const fields = fromPoll(poll)
  fields.slots = Array.from({ length: 16 }, (_, key) => ({ key, start: `2026-10-29T${String(key).padStart(2,'0')}:00`, end: `2026-10-29T${String(key).padStart(2,'0')}:30` }))
  expect(validate(fields)).toEqual({})
  expect(validate(fields, true, 0)).toHaveProperty('slots')
  fields.slots = [{ key: 4, start: fields.deadline, end: '2026-10-28T10:00' }]
  expect(validate(fields, true, 0)).toHaveProperty('start-4')
})
it('compares normalized save contents independently of property order, child IDs and ordering', () => {
  const body = payload(fromPoll(poll))
  body.participants = [{ importance: 'REQUIRED', user_id: 1 }]
  expect(equivalent(body, { ...poll, slots: [{ ...poll.slots[0]!, id: 99 }] })).toBe(true)
  body.title = '另一个主题'
  expect(equivalent(body, poll)).toBe(false)
})
it('decodes only public fields and sends a complete PUT body once', async () => {
  const fetch = mock({ ...poll, token: 'private-extra' }), body = payload(fromPoll(poll))
  expect(await pollsApi.save(1, body)).toEqual(poll)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1', expect.objectContaining({ method: 'PUT', credentials: 'same-origin', body: JSON.stringify(body) }))
})
it.each([null, {}, { ...poll, status: 'ADMIN' }, { ...poll, effective_status: 'OPEN' }, { ...poll, response_deadline: '2026-10-28T00:00:00' },
  { ...poll, participants: [...poll.participants, ...poll.participants] }, { ...poll, slots: [...poll.slots, ...poll.slots] },
  { ...poll, slots: [{ ...poll.slots[0], end_at: poll.slots[0]!.start_at }] },
])('rejects malformed poll response and treats write results as uncertain', async value => {
  mock(value)
  await expect(pollsApi.get(1)).rejects.toMatchObject({ kind: 'protocol', uncertain: false })
  await expect(pollsApi.publish(1)).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
})
it('allows server-derived effective close while retaining stored OPEN', async () => {
  mock({ ...poll, status: 'OPEN', effective_status: 'CLOSED' })
  expect((await pollsApi.get(1)).effective_status).toBe('CLOSED')
})
it('checks response ownership of a list and path', async () => {
  mock(poll)
  await expect(pollsApi.get(2)).rejects.toMatchObject({ kind: 'protocol' })
  await expect(pollsApi.create(3, payload(fromPoll(poll)))).rejects.toMatchObject({ uncertain: true })
  mock({ items: [poll], page: 1, page_size: 20, total: 1 })
  await expect(pollsApi.list(3)).rejects.toMatchObject({ kind: 'protocol' })
})
it('validates list count and returns an empty page without assuming write success', async () => {
  mock({ items: [], page: 1, page_size: 20, total: 1 })
  await expect(pollsApi.list(2)).rejects.toMatchObject({ kind: 'protocol' })
  mock({ items: [], page: 2, page_size: 20, total: 0 })
  expect((await pollsApi.list(2, 2)).items).toEqual([])
})
it.each(['0', '../groups', '9223372036854775808'])('rejects invalid identifiers %s without issuing a request', async value => {
  const fetch = mock(poll)
  await expect(pollsApi.get(value)).rejects.toMatchObject({ status: 404 })
  expect(fetch).not.toHaveBeenCalled()
})
