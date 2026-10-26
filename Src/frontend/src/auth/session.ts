import { inject, reactive, readonly, type InjectionKey } from 'vue'
import { advanceAuthEpoch, ApiFailure } from '../api/client'
import { authApi, type AuthApi, type Credentials, type Registration, type User } from './api'

export function createSession(api: AuthApi = authApi) {
  const state = reactive({ user: null as User | null,
    phase: 'unknown' as 'unknown' | 'authenticated' | 'anonymous' | 'unavailable',
    error: null as ApiFailure | null, pending: false, identityEpoch: 0, expired: false,
    loginHint: null as { username: string; message: string } | null })
  let revision = 0
  let checking: Promise<typeof state.phase> | undefined

  function apply(account: User | null) {
    if (state.user?.id !== account?.id) state.identityEpoch++
    state.user = account
    state.phase = account ? 'authenticated' : 'anonymous'
    state.error = null
  }

  function expire() {
    revision++; checking = undefined; advanceAuthEpoch()
    state.expired = state.user !== null || state.expired
    apply(null)
  }

  function check(): Promise<typeof state.phase> {
    if (checking) return checking
    const ticket = revision
    advanceAuthEpoch()
    const operation = (async () => {
      try {
        const account = await api.me()
        if (ticket === revision) apply(account)
      } catch (error) {
        if (ticket === revision) {
          if (error instanceof ApiFailure && error.status === 401) {
            state.expired = state.user !== null || state.expired
            apply(null)
          } else {
            state.phase = 'unavailable'
            state.error = error instanceof ApiFailure ? error : new ApiFailure('network', '暂时无法确认登录状态，请重试。')
          }
        }
      }
      return state.phase
    })()
    checking = operation
    void operation.finally(() => { if (checking === operation) checking = undefined })
    return operation
  }

  async function login(credentials: Credentials) {
    if (state.pending) throw new Error('An account operation is already pending.')
    state.pending = true
    const ticket = ++revision
    checking = undefined; advanceAuthEpoch()
    try {
      const account = await api.login(credentials)
      if (ticket === revision) { apply(account); state.expired = false }
      return account
    } finally { state.pending = false }
  }

  async function register(data: Registration) {
    if (state.pending) throw new Error('An account operation is already pending.')
    state.pending = true
    try { return await api.register(data) } finally { state.pending = false }
  }

  async function logout() {
    if (state.pending) throw new Error('An account operation is already pending.')
    state.pending = true
    const ticket = ++revision
    checking = undefined; advanceAuthEpoch()
    try {
      try { await api.logout() }
      catch (error) { if (!(error instanceof ApiFailure && error.status === 401)) throw error }
      if (ticket === revision) { apply(null); state.expired = false }
    } finally { state.pending = false }
  }

  function setLoginHint(username: string, message: string) { state.loginHint = { username, message } }
  function consumeLoginHint() { const hint = state.loginHint; state.loginHint = null; return hint }
  return { state: readonly(state), check, login, register, logout, expire, setLoginHint, consumeLoginHint }
}

export type Session = ReturnType<typeof createSession>
export const sessionKey: InjectionKey<Session> = Symbol('session')
export function useSession() {
  const session = inject(sessionKey)
  if (!session) throw new Error('Session provider is required.')
  return session
}
