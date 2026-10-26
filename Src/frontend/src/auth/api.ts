import { ApiFailure, request } from '../api/client'

export type User = { id: number; username: string; email: string }
export type Credentials = { username: string; password: string }
export type Registration = Credentials & { email: string }

function user(value: unknown, requestId: string, writing: boolean): User {
  const data = value as Partial<User> | null
  if (!data || !Number.isSafeInteger(data.id) || Number(data.id) < 1 ||
      typeof data.username !== 'string' || !/^[a-z0-9_]{3,32}$/.test(data.username) ||
      typeof data.email !== 'string' || !data.email || data.email.length > 254) {
    throw new ApiFailure('protocol', '账号响应无法识别，请先核对登录状态。', undefined, undefined, requestId, undefined, writing)
  }
  return { id: data.id!, username: data.username, email: data.email }
}

export const authApi = {
  async me() {
    const result = await request<unknown>('/api/v1/users/me')
    return user(result.data, result.request_id, false)
  },
  async login(body: Credentials) {
    const result = await request<unknown>('/api/v1/auth/login', { method: 'POST', body })
    return user(result.data, result.request_id, true)
  },
  async register(body: Registration) {
    const result = await request<unknown>('/api/v1/auth/register', { method: 'POST', body })
    return user(result.data, result.request_id, true)
  },
  async logout() {
    const result = await request<{ logged_out: boolean }>('/api/v1/auth/logout', { method: 'POST', body: {} })
    if (result.data?.logged_out !== true) throw new ApiFailure('protocol', '退出结果暂时无法确认。', undefined, undefined, result.request_id, undefined, true)
  },
}
export type AuthApi = typeof authApi
