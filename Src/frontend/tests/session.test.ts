import { expect, it, vi } from 'vitest'
import { createSession } from '../src/auth/session'
import { ApiFailure } from '../src/api/client'
const alice = { id: 1, username: 'alice', email: 'alice@example.com' }
const bob = { id: 2, username: 'bob', email: 'bob@example.com' }
function setup() {
  const api = { me: vi.fn().mockResolvedValue(alice), login: vi.fn().mockResolvedValue(alice),
    register: vi.fn().mockResolvedValue(alice), logout: vi.fn().mockResolvedValue(undefined) }
  return { api, session: createSession(api) }
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { resolve, promise } }

it('loads a user and deduplicates simultaneous identity checks', async () => {
  const { session, api } = setup()
  const [first, second] = await Promise.all([session.check(), session.check()])
  expect([first, second]).toEqual(['authenticated', 'authenticated'])
  expect(api.me).toHaveBeenCalledTimes(1)
  expect(session.state.user).toEqual(alice)
})
it('distinguishes no session from a network failure and preserves the last identity for recovery', async () => {
  const { session, api } = setup()
  await session.check()
  api.me.mockRejectedValueOnce(new ApiFailure('network', 'offline'))
  expect(await session.check()).toBe('unavailable')
  expect(session.state.user).toEqual(alice)
  api.me.mockRejectedValueOnce(new ApiFailure('http', 'expired', 401))
  expect(await session.check()).toBe('anonymous')
  expect(session.state.user).toBeNull()
  expect(session.state.expired).toBe(true)
})
it('changes the protected-view identity key when accounts change or expire', async () => {
  const { session, api } = setup()
  await session.check(); const first = session.state.identityEpoch
  await session.check(); expect(session.state.identityEpoch).toBe(first)
  api.me.mockResolvedValue(bob); await session.check()
  expect(session.state.identityEpoch).toBeGreaterThan(first)
  const second = session.state.identityEpoch
  session.expire(); expect(session.state.identityEpoch).toBeGreaterThan(second)
})
it('does not let an old identity read overwrite a newly logged-in user', async () => {
  const { session, api } = setup(), old = deferred<typeof alice>()
  api.me.mockReturnValue(old.promise); const check = session.check()
  api.login.mockResolvedValue(bob)
  await session.login({ username: 'bob', password: 'password' })
  old.resolve(alice); await check
  expect(session.state.user).toEqual(bob)
})
it('registration does not establish a session and keeps no password in state', async () => {
  const { session } = setup()
  await session.register({ username: 'alice', email: 'alice@example.com', password: 'private-password' })
  expect(session.state.user).toBeNull()
  expect(JSON.stringify(session.state)).not.toContain('private-password')
})
it('keeps the current user after failed login and clears it only after confirmed logout', async () => {
  const { session, api } = setup()
  await session.check()
  api.login.mockRejectedValue(new ApiFailure('http', 'wrong', 401))
  await expect(session.login({ username: 'bob', password: 'wrong' })).rejects.toMatchObject({ status: 401 })
  expect(session.state.user).toEqual(alice)
  api.logout.mockRejectedValueOnce(new ApiFailure('network', 'uncertain', undefined, undefined, undefined, undefined, true))
  await expect(session.logout()).rejects.toMatchObject({ uncertain: true })
  expect(session.state.user).toEqual(alice)
  api.logout.mockRejectedValueOnce(new ApiFailure('http', 'expired', 401))
  await session.logout(); expect(session.state.user).toBeNull()
})
it('prevents duplicate account writes while one is pending', async () => {
  const { session, api } = setup(), pending = deferred<typeof alice>()
  api.login.mockReturnValue(pending.promise)
  const first = session.login({ username: 'alice', password: 'password' })
  await expect(session.login({ username: 'alice', password: 'password' })).rejects.toThrow('already pending')
  expect(api.login).toHaveBeenCalledTimes(1)
  pending.resolve(alice); await first
  expect(session.state.pending).toBe(false)
})
it('consumes registration login hints once, without URL or storage state', () => {
  const { session } = setup()
  session.setLoginHint('alice', 'registered')
  expect(session.consumeLoginHint()).toEqual({ username: 'alice', message: 'registered' })
  expect(session.consumeLoginHint()).toBeNull()
})
