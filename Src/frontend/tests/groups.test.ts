import { afterEach, expect, it, vi } from 'vitest'
import { groupsApi } from '../src/groups/api'
import { validateGroup } from '../src/groups/forms'

const id = 'c07e357967c148068a4f9aa539c759e2'
const owner = { id: 1, name: '项目组', description: '', owner_id: 2, member_count: 1, invite_code: 'ABCDEFGHIJKL', invite_enabled: true }
const basic = { id: 1, name: '项目组', description: '', owner_id: 2, member_count: 2 }
function mock(data: unknown) {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data, request_id: id }), {
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': id },
  })))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
afterEach(() => vi.unstubAllGlobals())

it('uses same-origin API paths and includes only known group fields', async () => {
  const fetch = mock({ ...owner, password_hash: 'extra-field' })
  expect(await groupsApi.create({ name: '项目组', description: '' })).toEqual(owner)
  expect(fetch).toHaveBeenCalledWith('/api/v1/groups', expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: '{"name":"项目组","description":""}' }))
})
it('accepts ordinary member DTO without invitation fields', async () => {
  mock(basic)
  expect(await groupsApi.join('ABCDEFGHIJKL')).toEqual(basic)
})
it.each([null, {}, { ...owner, member_count: 21 }, { ...owner, id: 1.5 }, { ...owner, invite_code: 'bad' },
  { ...basic, invite_enabled: true }, { ...basic, invite_code: 'ABCDEFGHIJKL' }, { ...owner, name: '' }])('rejects invalid group DTO %j with uncertain writes', async value => {
  mock(value)
  await expect(groupsApi.create({ name: '项目组', description: '' })).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
  await expect(groupsApi.get(1)).rejects.toMatchObject({ kind: 'protocol', uncertain: false })
})
it('checks group response belongs to requested path', async () => {
  mock(owner)
  await expect(groupsApi.get(3)).rejects.toMatchObject({ kind: 'protocol' })
})
it.each(['0', '-1', '../auth', '9223372036854775808'])('rejects invalid route IDs before fetching %s', async value => {
  const fetch = mock(owner)
  await expect(groupsApi.get(value)).rejects.toMatchObject({ status: 404 })
  expect(fetch).not.toHaveBeenCalled()
})
it('checks pagination, forwards read cancellation, and accepts an empty page', async () => {
  const fetch = mock({ items: [], page: 2, page_size: 20, total: 0 }), controller = new AbortController()
  expect(await groupsApi.list(2, controller.signal)).toEqual({ items: [], page: 2, page_size: 20, total: 0 })
  expect(fetch).toHaveBeenCalledWith('/api/v1/groups?page=2&page_size=20', expect.objectContaining({ signal: expect.any(AbortSignal) }))
})
it.each([
  { items: [owner], page: 2, page_size: 20, total: 1 },
  { items: [], page: 1, page_size: 20, total: 1 },
  { items: [owner, owner], page: 1, page_size: 20, total: 2 },
  { items: [], page: 1, page_size: 20, total: -1 },
])('rejects contradictory list response %j', async value => {
  mock(value)
  await expect(groupsApi.list()).rejects.toMatchObject({ kind: 'protocol' })
})
it('returns member summary without private fields', async () => {
  mock({ items: [{ user_id: 2, username: 'owner', role: 'OWNER', email: 'private@example.com' }] })
  expect(await groupsApi.members(1)).toEqual([{ user_id: 2, username: 'owner', role: 'OWNER' }])
})
it.each([[], [{ user_id: 1, username: 'owner', role: 'ADMIN' }],
  [{ user_id: 1, username: 'owner', role: 'OWNER' }, { user_id: 1, username: 'owner', role: 'MEMBER' }],
  [{ user_id: 1, username: 'member', role: 'MEMBER' }],
].map(items => ({ items })))('rejects invalid or duplicate roster %j', async ({ items }) => {
  mock({ items })
  await expect(groupsApi.members(1)).rejects.toMatchObject({ kind: 'protocol' })
})
it('validates reset result instead of reporting a false success', async () => {
  mock({ invite_code: 'ABCDEFGHIJKL', invite_enabled: false })
  await expect(groupsApi.reset(1)).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
})
const fields = { name: '  课程组  ', description: '', invite_code: ' abcdefgh1234 ' }
it('validates only the selected form and does not mutate input', () => {
  expect(validateGroup('create', fields)).toEqual({})
  expect(validateGroup('join', fields)).toEqual({})
  expect(fields.name).toBe('  课程组  ')
})
it.each([{ name: ' ' }, { name: '组'.repeat(101) }, { name: '\x00' }, { name: '\ud800' }, { description: '字'.repeat(10001) }])('rejects invalid group text', changes => {
  expect(Object.keys(validateGroup('create', { ...fields, ...changes }))).toHaveLength(1)
})
it('counts Unicode characters instead of UTF-16 code units', () => {
  expect(validateGroup('create', { ...fields, name: '😀'.repeat(100), description: '😀'.repeat(10000) })).toEqual({})
})
it.each(['ABCDEFGHIJK', 'ABCDEFGH123!', 'ABCDEFGH12ß', 'ＡBCDEFGH1234'])('rejects invalid invitation %s', invite_code => {
  expect(validateGroup('join', { ...fields, invite_code })).toHaveProperty('invite_code')
})
