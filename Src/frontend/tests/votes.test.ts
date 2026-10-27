import { afterEach, expect, it, vi } from 'vitest'
import type { Poll } from '../src/polls/api'
import { votesApi, sameAnswers, selections, toChoices } from '../src/votes/api'

const poll: Poll = { id: 1, group_id: 1, title: '测试', description: '', location: '', status: 'OPEN', effective_status: 'OPEN',
  response_deadline: '2026-10-28T00:00:00.000Z', updated_at: '2026-10-27T00:00:00.000Z', participants: [],
  slots: [{ id: 3, start_at: '2026-10-28T01:00:00.000Z', end_at: '2026-10-28T02:00:00.000Z' },
    { id: 4, start_at: '2026-10-28T03:00:00.000Z', end_at: '2026-10-28T04:00:00.000Z' }] }
const votes = [{ slot_id: 3, availability: 'AVAILABLE' as const }, { slot_id: 4, availability: 'MAYBE' as const }]
const result = { poll_id: 1, submitted_at: '2026-10-27T00:00:00.000Z', votes }
function mock(value: unknown) {
  const id = 'c07e357967c148068a4f9aa539c759e2'
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data: value, request_id: id }), {
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': id },
  })))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
afterEach(() => vi.unstubAllGlobals())
it('keeps unchosen slots unknown and submits only current candidate IDs in poll order', () => {
  const choices = toChoices(votes)
  expect(selections(poll, choices)).toEqual(votes)
  delete choices[4]
  choices[999] = 'UNAVAILABLE'
  expect(selections(poll, choices)).toEqual([votes[0]])
  expect(votes).toHaveLength(2)
})
it('compares answers independently of order and rejects duplicates or missing answers', () => {
  expect(sameAnswers(votes, [...votes].reverse())).toBe(true)
  expect(sameAnswers(votes, [votes[0]!, votes[0]!])).toBe(false)
  expect(sameAnswers([votes[0]!, votes[0]!], votes)).toBe(false)
  expect(sameAnswers(votes, [votes[0]!])).toBe(false)
  expect(sameAnswers(votes, [{ ...votes[0]!, availability: 'UNAVAILABLE' }, votes[1]!])).toBe(false)
})
it('distinguishes no submission from a saved full answer', async () => {
  mock({ poll_id: 1, submitted_at: null, votes: [] })
  expect((await votesApi.get(poll)).submitted_at).toBeNull()
  mock({ ...result, secret: 'ignored', votes: votes.map(item => ({ ...item, user_id: 999 })) })
  expect(await votesApi.get(poll)).toEqual(result)
})
it('sends only the current actor complete answer once and returns matching saved contents', async () => {
  const fetch = mock(result)
  expect(await votesApi.save(poll, votes)).toEqual(result)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledWith('/api/v1/polls/1/votes/me', expect.objectContaining({ method: 'PUT', credentials: 'same-origin', body: JSON.stringify({ votes }) }))
})
it.each([null, {}, { ...result, poll_id: 2 }, { ...result, submitted_at: null }, { ...result, votes: [] },
  { ...result, submitted_at: '2026-10-27T00:00:00' }, { ...result, votes: [votes[0], votes[0]] },
  { ...result, votes: [votes[0]] }, { ...result, votes: [{ slot_id: 999, availability: 'AVAILABLE' }, votes[1]] },
  { ...result, votes: [{ slot_id: 3, availability: 'UNKNOWN' }, votes[1]] },
  { ...result, votes: [{ slot_id: '3', availability: 'AVAILABLE' }, votes[1]] },
])('rejects damaged or foreign results and marks write results uncertain', async value => {
  mock(value)
  await expect(votesApi.get(poll)).rejects.toMatchObject({ kind: 'protocol', uncertain: false })
  await expect(votesApi.save(poll, votes)).rejects.toMatchObject({ kind: 'protocol', uncertain: true })
})
it('does not treat an empty or different successful PUT response as saved', async () => {
  mock({ poll_id: 1, submitted_at: null, votes: [] })
  await expect(votesApi.save(poll, votes)).rejects.toMatchObject({ uncertain: true })
  mock({ ...result, votes: [{ slot_id: 3, availability: 'UNAVAILABLE' }, votes[1]] })
  await expect(votesApi.save(poll, votes)).rejects.toMatchObject({ uncertain: true })
})
it('rejects invalid IDs without sending a request', async () => {
  const fetch = mock(result)
  await expect(votesApi.get({ ...poll, id: 0 })).rejects.toMatchObject({ status: 404 })
  expect(fetch).not.toHaveBeenCalled()
})
