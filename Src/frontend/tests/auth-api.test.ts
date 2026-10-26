import { afterEach, expect, it, vi } from 'vitest'
import { authApi } from '../src/auth/api'
import { advanceAuthEpoch, onUnauthorized, request } from '../src/api/client'

const id = 'c07e357967c148068a4f9aa539c759e2'
const response = (data: unknown, status = 200) => new Response(JSON.stringify({ data, request_id: id }), {
  status, headers: { 'Content-Type': 'application/json', 'X-Request-ID': id },
})
const denied = () => new Response(JSON.stringify({ error: { code: 'UNAUTHENTICATED', message: '请登录' }, request_id: id }), {
  status: 401, headers: { 'Content-Type': 'application/json', 'X-Request-ID': id },
})
afterEach(() => vi.unstubAllGlobals())

it('keeps only public user fields and sends credentials in the body', async () => {
  const fetch = vi.fn().mockResolvedValue(response({ id: 1, username: 'student', email: 'student@example.com', token: 'untrusted-extra' }))
  vi.stubGlobal('fetch', fetch)
  expect(await authApi.login({ username: 'student', password: 'private-password' }))
    .toEqual({ id: 1, username: 'student', email: 'student@example.com' })
  expect(fetch).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ body: '{"username":"student","password":"private-password"}' }))
})

it.each([null, {}, { id: 0, username: 'student', email: 'a@b.com' }, { id: 1, username: '<script>', email: 'a@b.com' }])('rejects invalid user DTO %j; a write result is uncertain', async data => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(response(data))))
  await expect(authApi.me()).rejects.toMatchObject({ kind: 'protocol', uncertain: false })
  await expect(authApi.login({ username: 'student', password: 'password' })).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
})

it('requires an explicit logout acknowledgement', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ logged_out: false })))
  await expect(authApi.logout()).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
})

it('notifies once for a current protected 401 and disposes listeners', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(denied())))
  const listener = vi.fn(), dispose = onUnauthorized(listener)
  try {
    await expect(request('/api/v1/groups')).rejects.toMatchObject({ status: 401 })
    expect(listener).toHaveBeenCalledTimes(1)
    for (const path of ['/api/v1/auth/login', '/api/v1/users/me', '/api/v1/health']) {
      await expect(request(path)).rejects.toMatchObject({ status: 401 })
    }
    expect(listener).toHaveBeenCalledTimes(1)
  } finally { dispose() }
  await expect(request('/api/v1/groups')).rejects.toMatchObject({ status: 401 })
  expect(listener).toHaveBeenCalledTimes(1)
})

it('ignores a stale 401 that arrives after an identity transition', async () => {
  let resolve!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise<Response>(done => { resolve = done })))
  const listener = vi.fn(), dispose = onUnauthorized(listener)
  try {
    const pending = request('/api/v1/groups').catch(error => error)
    advanceAuthEpoch()
    resolve(denied())
    expect(await pending).toMatchObject({ status: 401 })
    expect(listener).not.toHaveBeenCalled()
  } finally { dispose() }
})
