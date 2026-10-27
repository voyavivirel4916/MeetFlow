import { ApiFailure, request } from '../api/client'
import { identifier, utc, type Poll } from '../polls/api'

export const options = [
  { value: 'AVAILABLE', label: '有空', hint: '可以参加', symbol: '✓' },
  { value: 'MAYBE', label: '勉强', hint: '需要协调', symbol: '~' },
  { value: 'UNAVAILABLE', label: '没空', hint: '无法参加', symbol: '×' },
] as const
export type Availability = typeof options[number]['value']
export type Vote = { slot_id: number; availability: Availability }
export type MyVotes = { poll_id: number; submitted_at: string | null; votes: Vote[] }
export type Choices = Record<number, Availability>
export const sameAnswers = (a: Vote[], b: Vote[]) => a.length === b.length &&
  new Set(a.map(item => item.slot_id)).size === a.length && new Set(b.map(item => item.slot_id)).size === b.length &&
  a.every(item => b.some(other => item.slot_id === other.slot_id && item.availability === other.availability))
export const toChoices = (votes: Vote[]): Choices => Object.fromEntries(votes.map(item => [item.slot_id, item.availability]))
export function selections(poll: Poll, choices: Choices): Vote[] {
  return poll.slots.filter(slot => choices[slot.id]).map(slot => ({ slot_id: slot.id, availability: choices[slot.id]! }))
}
function decode(value: unknown, poll: Poll, requestId: string, writing: boolean): MyVotes {
  const invalid = (): never => { throw new ApiFailure('protocol', '填写结果无法识别，请重新读取核对。', undefined, undefined, requestId, undefined, writing) }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid()
  const row = value as Record<string, unknown>
  if (row.poll_id !== poll.id || !(row.submitted_at === null || utc(row.submitted_at)) || !Array.isArray(row.votes)) return invalid()
  const votes: Vote[] = row.votes.map(item => {
    if (!item || typeof item !== 'object' || !Number.isSafeInteger(item.slot_id) ||
      !poll.slots.some(slot => slot.id === item.slot_id) || !options.some(option => option.value === item.availability)) return invalid()
    return { slot_id: item.slot_id, availability: item.availability }
  })
  if (new Set(votes.map(item => item.slot_id)).size !== votes.length ||
    (row.submitted_at === null ? votes.length !== 0 || writing : votes.length !== poll.slots.length || !votes.length)) return invalid()
  return { poll_id: poll.id, submitted_at: row.submitted_at as string | null, votes }
}
export const votesApi = {
  async get(poll: Poll, signal?: AbortSignal) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(poll.id)}/votes/me`, { signal })
    return decode(result.data, poll, result.request_id, false)
  },
  async save(poll: Poll, votes: Vote[]) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(poll.id)}/votes/me`, { method: 'PUT', body: { votes } })
    const saved = decode(result.data, poll, result.request_id, true)
    if (!sameAnswers(saved.votes, votes)) throw new ApiFailure('protocol', '返回的填写结果与本次选择不同，请先核对。', undefined, undefined, result.request_id, undefined, true)
    return saved
  },
}
