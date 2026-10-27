import { ApiFailure, request } from '../api/client'

export type PollStatus = 'DRAFT' | 'OPEN' | 'CLOSED' | 'CONFIRMED' | 'CANCELLED'
export type Participant = { user_id: number; username: string; importance: 'REQUIRED' | 'NORMAL'; submitted_at: string | null }
export type Slot = { id: number; start_at: string; end_at: string }
export type Poll = { id: number; group_id: number; title: string; description: string; location: string; response_deadline: string;
  status: PollStatus; effective_status: PollStatus; participants: Participant[]; slots: Slot[]; updated_at: string }
export type Draft = { title: string; description: string; location: string; response_deadline: string;
  participants: { user_id: number; importance: 'REQUIRED' | 'NORMAL' }[]; slots: { start_at: string; end_at: string }[] }
export type PollPage = { items: Poll[]; page: number; page_size: number; total: number }
export const statusLabel: Record<PollStatus, string> = { DRAFT: '草稿', OPEN: '收集中', CLOSED: '已关闭', CONFIRMED: '已确认', CANCELLED: '已取消' }
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0
const text = (value: unknown, limit: number): value is string => typeof value === 'string' && Array.from(value).length <= limit
export function utc(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value
}
function invalid(id: string, writing: boolean): never { throw new ApiFailure('protocol', '排期响应无法识别，请先重新读取核对。', undefined, undefined, id, undefined, writing) }
function decode(value: unknown, id: string, writing = false): Poll {
  if (!object(value) || !positive(value.id) || !positive(value.group_id) || !text(value.title, 100) || !value.title.trim() ||
      !text(value.description, 10000) || !text(value.location, 200) || !utc(value.response_deadline) || !utc(value.updated_at) ||
      typeof value.status !== 'string' || !Object.hasOwn(statusLabel, value.status) ||
      !(value.effective_status === value.status || (value.status === 'OPEN' && value.effective_status === 'CLOSED')) ||
      !Array.isArray(value.participants) || value.participants.length > 20 || !Array.isArray(value.slots)) invalid(id, writing)
  const participants = value.participants.map(person => {
    if (!object(person) || !positive(person.user_id) || typeof person.username !== 'string' || !/^[a-z0-9_]{3,32}$/.test(person.username) ||
        (person.importance !== 'REQUIRED' && person.importance !== 'NORMAL') || !(person.submitted_at === null || utc(person.submitted_at))) invalid(id, writing)
    return { user_id: person.user_id, username: person.username, importance: person.importance, submitted_at: person.submitted_at } as Participant
  })
  const slots = value.slots.map(slot => {
    if (!object(slot) || !positive(slot.id) || !utc(slot.start_at) || !utc(slot.end_at) || slot.start_at >= slot.end_at) invalid(id, writing)
    return { id: slot.id, start_at: slot.start_at, end_at: slot.end_at }
  })
  if (new Set(participants.map(item => item.user_id)).size !== participants.length || new Set(slots.map(item => item.id)).size !== slots.length ||
      new Set(slots.map(item => `${item.start_at}/${item.end_at}`)).size !== slots.length) invalid(id, writing)
  return { id: value.id, group_id: value.group_id, title: value.title, description: value.description, location: value.location,
    response_deadline: value.response_deadline, updated_at: value.updated_at, status: value.status as PollStatus,
    effective_status: value.effective_status as PollStatus, participants, slots }
}
function identifier(value: number | string) {
  const id = String(value)
  if (!/^[1-9]\d*$/.test(id) || BigInt(id) > 9223372036854775807n) throw new ApiFailure('http', '未找到可访问的排期。', 404, 'NOT_FOUND')
  return id
}
export const pollsApi = {
  async get(id: number | string, signal?: AbortSignal) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(id)}`, { signal })
    const poll = decode(result.data, result.request_id)
    if (String(poll.id) !== String(id)) invalid(result.request_id, false)
    return poll
  },
  async list(groupId: number | string, page = 1, signal?: AbortSignal): Promise<PollPage> {
    const result = await request<unknown>(`/api/v1/groups/${identifier(groupId)}/polls?page=${page}&page_size=20`, { signal })
    const value = result.data
    if (!object(value) || !Array.isArray(value.items) || value.page !== page || value.page_size !== 20 || !Number.isSafeInteger(value.total) || Number(value.total) < 0) invalid(result.request_id, false)
    const items = value.items.map(item => decode(item, result.request_id))
    if (items.some(item => String(item.group_id) !== String(groupId)) || new Set(items.map(item => item.id)).size !== items.length ||
        items.length !== Math.min(20, Math.max(Number(value.total) - (page - 1) * 20, 0))) invalid(result.request_id, false)
    return { items, page, page_size: 20, total: Number(value.total) }
  },
  async create(groupId: number | string, body: Draft) {
    const result = await request<unknown>(`/api/v1/groups/${identifier(groupId)}/polls`, { method: 'POST', body })
    const poll = decode(result.data, result.request_id, true)
    if (String(poll.group_id) !== String(groupId)) invalid(result.request_id, true)
    return poll
  },
  async save(id: number | string, body: Draft) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(id)}`, { method: 'PUT', body })
    const poll = decode(result.data, result.request_id, true)
    if (String(poll.id) !== String(id)) invalid(result.request_id, true)
    return poll
  },
  async publish(id: number | string) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(id)}/open`, { method: 'POST', body: {} })
    const poll = decode(result.data, result.request_id, true)
    if (String(poll.id) !== String(id)) invalid(result.request_id, true)
    return poll
  },
}
