import { ApiFailure, request } from '../api/client'

export type Group = { id: number; name: string; description: string; owner_id: number; member_count: number; invite_code?: string; invite_enabled?: boolean }
export type GroupPage = { items: Group[]; page: number; page_size: number; total: number }
export type Member = { user_id: number; username: string; role: 'OWNER' | 'MEMBER' }
export type GroupInput = { name: string; description: string }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0
const text = (value: unknown, max: number): value is string => typeof value === 'string' && Array.from(value).length <= max
function invalid(id: string, writing = false): never {
  throw new ApiFailure('protocol', '小组响应无法识别，请重新读取核对。', undefined, undefined, id, undefined, writing)
}
function group(value: unknown, id: string, writing = false): Group {
  if (!object(value) || !positive(value.id) || !positive(value.owner_id) || !text(value.name, 100) || !value.name.trim() ||
      !text(value.description, 10000) || !positive(value.member_count) || value.member_count > 20 ||
      (value.invite_code !== undefined && (typeof value.invite_code !== 'string' || !/^[A-Z0-9]{12}$/.test(value.invite_code))) ||
      (value.invite_enabled !== undefined && typeof value.invite_enabled !== 'boolean') ||
      (('invite_code' in value) !== ('invite_enabled' in value))) invalid(id, writing)
  return { id: value.id, name: value.name, description: value.description, owner_id: value.owner_id, member_count: value.member_count,
    ...(value.invite_code === undefined ? {} : { invite_code: value.invite_code as string, invite_enabled: value.invite_enabled as boolean }) }
}
function groupId(id: string | number) {
  const value = String(id)
  if (!/^[1-9]\d*$/.test(value) || BigInt(value) > 9223372036854775807n) throw new ApiFailure('http', '未找到可访问的小组。', 404, 'NOT_FOUND')
  return value
}
export const groupsApi = {
  async list(page = 1, signal?: AbortSignal): Promise<GroupPage> {
    const result = await request<unknown>(`/api/v1/groups?page=${page}&page_size=20`, { signal })
    const value = result.data
    if (!object(value) || !Array.isArray(value.items) || value.items.length > 20 || value.page !== page || value.page_size !== 20 ||
        !Number.isSafeInteger(value.total) || Number(value.total) < 0) invalid(result.request_id)
    const items = value.items.map(item => group(item, result.request_id))
    if (new Set(items.map(item => item.id)).size !== items.length || items.length !== Math.min(20, Math.max(Number(value.total) - (page - 1) * 20, 0))) invalid(result.request_id)
    return { items, page, page_size: 20, total: Number(value.total) }
  },
  async get(id: string | number, signal?: AbortSignal) {
    const result = await request<unknown>(`/api/v1/groups/${groupId(id)}`, { signal })
    const value = group(result.data, result.request_id)
    if (String(value.id) !== String(id)) invalid(result.request_id)
    return value
  },
  async members(id: string | number, signal?: AbortSignal): Promise<Member[]> {
    const result = await request<unknown>(`/api/v1/groups/${groupId(id)}/members`, { signal })
    const value = result.data
    if (!object(value) || !Array.isArray(value.items) || value.items.length < 1 || value.items.length > 20) invalid(result.request_id)
    const items = value.items.map(item => {
      if (!object(item) || !positive(item.user_id) || typeof item.username !== 'string' || !/^[a-z0-9_]{3,32}$/.test(item.username) ||
          (item.role !== 'OWNER' && item.role !== 'MEMBER')) invalid(result.request_id)
      return { user_id: item.user_id, username: item.username, role: item.role } as Member
    })
    if (new Set(items.map(item => item.user_id)).size !== items.length || items.filter(item => item.role === 'OWNER').length !== 1) invalid(result.request_id)
    return items
  },
  async create(body: GroupInput) {
    const result = await request<unknown>('/api/v1/groups', { method: 'POST', body })
    return group(result.data, result.request_id, true)
  },
  async join(invite_code: string) {
    const result = await request<unknown>('/api/v1/groups/join', { method: 'POST', body: { invite_code } })
    return group(result.data, result.request_id, true)
  },
  async reset(id: string | number) {
    const result = await request<unknown>(`/api/v1/groups/${groupId(id)}/invite-code/reset`, { method: 'POST', body: {} })
    const value = result.data
    if (!object(value) || typeof value.invite_code !== 'string' || !/^[A-Z0-9]{12}$/.test(value.invite_code) || value.invite_enabled !== true) invalid(result.request_id, true)
    return { invite_code: value.invite_code, invite_enabled: true }
  },
}
