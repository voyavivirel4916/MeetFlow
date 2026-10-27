import { ApiFailure, request } from '../api/client'
import { identifier, statusLabel, utc, type Participant, type PollStatus, type Slot } from '../polls/api'
import { options, type Availability } from './api'

export type Counts = { available_count: number; maybe_count: number; unavailable_count: number; unanswered_count: number }
export type Matrix = { poll_id: number; effective_status: PollStatus; participants: (Participant & Counts)[];
  slots: (Slot & Counts)[]; cells: { user_id: number; slot_id: number; availability: Availability | null }[];
  progress: { participant_count: number; submitted_count: number; unsubmitted_count: number } }
const object = (value: unknown): value is Record<string, any> => !!value && typeof value === 'object' && !Array.isArray(value)
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0
const count = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0
const countKeys = ['available_count','maybe_count','unavailable_count','unanswered_count'] as const
const counts = (value: Record<string, unknown>): Counts => Object.fromEntries(countKeys.map(key => [key,value[key]])) as Counts
export const availabilityLabel = (value: Availability | null) => options.find(option => option.value === value)?.label || '未填'
export const cellKey = (userId: number, slotId: number) => `${userId}:${slotId}`
export const cellIndex = (matrix: Matrix) => new Map(matrix.cells.map(cell => [cellKey(cell.user_id,cell.slot_id),cell.availability]))
function decode(value: unknown, id: number | string, requestId: string): Matrix {
  const invalid = (): never => { throw new ApiFailure('protocol', '矩阵数据不完整或统计不一致，请重新读取。', undefined, undefined, requestId) }
  if (!object(value) || String(value.poll_id) !== String(id) || !positive(value.poll_id) ||
    typeof value.effective_status !== 'string' || !Object.hasOwn(statusLabel,value.effective_status) ||
    !Array.isArray(value.participants) || value.participants.length > 20 || !Array.isArray(value.slots) || !Array.isArray(value.cells) || !object(value.progress)) return invalid()
  const participants: Matrix['participants'] = value.participants.map((person: unknown) => {
    if (!object(person) || !positive(person.user_id) || typeof person.username !== 'string' || !/^[a-z0-9_]{3,32}$/.test(person.username) ||
      !['REQUIRED','NORMAL'].includes(person.importance) || !(person.submitted_at === null || utc(person.submitted_at)) || !countKeys.every(key => count(person[key]))) return invalid()
    return { user_id:person.user_id,username:person.username,importance:person.importance,submitted_at:person.submitted_at,...counts(person) }
  })
  const slots: Matrix['slots'] = value.slots.map((slot: unknown) => {
    if (!object(slot) || !positive(slot.id) || !utc(slot.start_at) || !utc(slot.end_at) || slot.start_at >= slot.end_at || !countKeys.every(key => count(slot[key]))) return invalid()
    return { id:slot.id,start_at:slot.start_at,end_at:slot.end_at,...counts(slot) }
  })
  const peopleIds = new Set(participants.map(person => person.user_id)), slotIds = new Set(slots.map(slot => slot.id))
  if (peopleIds.size !== participants.length || slotIds.size !== slots.length || value.cells.length !== peopleIds.size*slotIds.size ||
    new Set(slots.map(slot => `${slot.start_at}/${slot.end_at}`)).size !== slots.length) return invalid()
  const cells: Matrix['cells'] = value.cells.map((cell: unknown) => {
    if (!object(cell) || !peopleIds.has(cell.user_id) || !slotIds.has(cell.slot_id) ||
      !(cell.availability === null || options.some(option => option.value === cell.availability))) return invalid()
    return { user_id:cell.user_id,slot_id:cell.slot_id,availability:cell.availability }
  })
  if (new Set(cells.map(cell => cellKey(cell.user_id,cell.slot_id))).size !== cells.length) return invalid()
  for (const person of participants) {
    const row = cells.filter(cell => cell.user_id === person.user_id)
    const expected = [row.filter(cell => cell.availability === 'AVAILABLE').length,row.filter(cell => cell.availability === 'MAYBE').length,
      row.filter(cell => cell.availability === 'UNAVAILABLE').length,row.filter(cell => cell.availability === null).length]
    if (!countKeys.every((key,index) => person[key] === expected[index])) return invalid()
  }
  for (const slot of slots) {
    const column = cells.filter(cell => cell.slot_id === slot.id)
    const expected = [column.filter(cell => cell.availability === 'AVAILABLE').length,column.filter(cell => cell.availability === 'MAYBE').length,
      column.filter(cell => cell.availability === 'UNAVAILABLE').length,column.filter(cell => cell.availability === null).length]
    if (!countKeys.every((key,index) => slot[key] === expected[index])) return invalid()
  }
  const progress = value.progress
  if (![progress.participant_count,progress.submitted_count,progress.unsubmitted_count].every(count) || progress.participant_count !== participants.length ||
    progress.submitted_count !== participants.filter(person => person.submitted_at !== null).length ||
    progress.unsubmitted_count !== participants.length-progress.submitted_count) return invalid()
  return { poll_id:value.poll_id,effective_status:value.effective_status as PollStatus,participants,slots,cells,
    progress:{participant_count:progress.participant_count,submitted_count:progress.submitted_count,unsubmitted_count:progress.unsubmitted_count} }
}
export const matrixApi = {
  async get(id: number | string, signal?: AbortSignal) {
    const result = await request<unknown>(`/api/v1/polls/${identifier(id)}/matrix`, { signal })
    return decode(result.data,id,result.request_id)
  },
}
