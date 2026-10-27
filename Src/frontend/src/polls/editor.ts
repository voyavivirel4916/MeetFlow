import type { Draft, Poll } from './api'

export type Candidate = { key: number; start: string; end: string }
export type Fields = { title: string; description: string; location: string; deadline: string;
  participants: Draft['participants']; slots: Candidate[] }
export type Errors = Record<string, string>
export const emptyFields = (): Fields => ({ title: '', description: '', location: '', deadline: '', participants: [], slots: [] })
export function beijing(value: string) { return new Date(Date.parse(value) + 8 * 3600_000).toISOString().slice(0, 23) }
export function localMs(value: string) {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::(\d{2})(?:\.(\d{1,3}))?)?$/.exec(value)
  if (!match) return NaN
  const canonical = `${match[1]}:${match[2] || '00'}.${(match[3] || '').padEnd(3, '0')}`
  const milliseconds = Date.parse(canonical + '+08:00')
  return Number.isFinite(milliseconds) && beijing(new Date(milliseconds).toISOString()) === canonical ? milliseconds : NaN
}
export function fromPoll(poll: Poll): Fields {
  return { title: poll.title, description: poll.description, location: poll.location, deadline: beijing(poll.response_deadline),
    participants: poll.participants.map(({ user_id, importance }) => ({ user_id, importance })),
    slots: poll.slots.map((item, key) => ({ key, start: beijing(item.start_at), end: beijing(item.end_at) })) }
}
export function payload(fields: Fields): Draft {
  return { title: fields.title.trim(), description: fields.description, location: fields.location,
    response_deadline: new Date(localMs(fields.deadline)).toISOString(), participants: fields.participants.map(item => ({ ...item })),
    slots: fields.slots.map(item => ({ start_at: new Date(localMs(item.start)).toISOString(), end_at: new Date(localMs(item.end)).toISOString() })) }
}
const invalidText = (value: string) => /\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)
export function validate(fields: Fields, publishing = false, now = Date.now()): Errors {
  const errors: Errors = {}
  if (!fields.title.trim() || Array.from(fields.title.trim()).length > 100 || invalidText(fields.title)) errors.title = '主题需为1～100个字符。'
  if (Array.from(fields.description).length > 10000 || invalidText(fields.description)) errors.description = '说明最多10000个字符，请检查文字。'
  if (Array.from(fields.location).length > 200 || invalidText(fields.location)) errors.location = '地点最多200个字符，请检查文字。'
  const deadline = localMs(fields.deadline)
  if (!Number.isFinite(deadline)) errors.deadline = '请填写有效的填写截止时间（北京时间）。'
  if (publishing && (!fields.participants.length || fields.participants.length > 20)) errors.participants = '发布前请至少选择一位组内参与者。'
  if (publishing && (!fields.slots.length || fields.slots.length > 15)) errors.slots = '发布前请设置1～15个候选时段。'
  if (publishing && deadline <= now) errors.deadline = '填写截止须在未来；最终以服务端时间为准。'
  const seen = new Set<string>()
  for (const item of fields.slots) {
    const start = localMs(item.start), end = localMs(item.end)
    if (!Number.isFinite(start)) errors[`start-${item.key}`] = '请填写有效的候选开始时间。'
    if (!Number.isFinite(end) || end <= start) errors[`end-${item.key}`] = '候选结束时间须晚于开始时间。'
    if (publishing && start <= deadline) errors[`start-${item.key}`] = '候选开始须晚于填写截止。'
    const pair = `${start}/${end}`
    if (Number.isFinite(start) && Number.isFinite(end) && seen.has(pair)) errors[`start-${item.key}`] = '候选时段不能重复。'
    seen.add(pair)
  }
  return errors
}
export function equivalent(draft: Draft, poll: Poll) {
  const normalized = (value: Draft) => JSON.stringify({ title: value.title.trim(), description: value.description, location: value.location,
    response_deadline: Date.parse(value.response_deadline), participants: [...value.participants].sort((a, b) => a.user_id-b.user_id).map(item => [item.user_id,item.importance]),
    slots: value.slots.map(item => [Date.parse(item.start_at), Date.parse(item.end_at)]).sort((a, b) => a[0]-b[0] || a[1]-b[1]) })
  return normalized(draft) === normalized({ ...poll, participants: poll.participants.map(({ user_id, importance }) => ({ user_id, importance })) })
}
