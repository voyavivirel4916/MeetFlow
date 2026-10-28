import { createMemoryHistory } from 'vue-router'
import { afterEach, expect, it, vi } from 'vitest'
import { createApplicationRouter, safeReturnPath } from '../src/router'
import { createSession } from '../src/auth/session'
import { ApiFailure, request } from '../src/api/client'
const user = { id: 1, username: 'student', email: 'student@example.com' }
const routers: ReturnType<typeof createApplicationRouter>[] = []
function setup(me = vi.fn().mockResolvedValue(user)) {
  const session = createSession({ me, login: vi.fn().mockResolvedValue(user), register: vi.fn().mockResolvedValue(user), logout: vi.fn().mockResolvedValue(undefined) })
  const router = createApplicationRouter(createMemoryHistory(), session)
  routers.push(router)
  return { router, session, me }
}
afterEach(() => { for (const router of routers.splice(0)) router.disposeSessionListener(); vi.unstubAllGlobals() })

it.each([
  ['/dashboard', '工作台'], ['/groups', '我的小组'], ['/groups/1', '小组空间'], ['/groups/1/polls/new', '发起排期'],
  ['/polls/2/edit', '编辑排期'], ['/polls/2/vote', '填写时间'], ['/polls/2/results', '排期结果'],
  ['/meetings/3', '会议与行动'], ['/tasks/mine', '我的任务'], ['/login', '登录'], ['/register', '注册'],
  ['/connection', '连接检查'], ['/groups/0', '找不到这个页面'], ['/groups/-1', '找不到这个页面'],
  ['/polls/abc/vote', '找不到这个页面'], ['/missing', '找不到这个页面'],
])('resolves %s', (path, title) => {
  const { router } = setup()
  expect(router.resolve(path).meta.title).toBe(title)
})

it('redirects the root into dashboard', async () => {
  const { router } = setup()
  await router.push('/')
  expect(router.currentRoute.value.path).toBe('/dashboard')
})

it.each([undefined, '//evil.com', 'https://evil.com', '/\\evil.com', '/login', '/missing',
  '/groups?password=secret', '/groups#answer', '/groups%3fsecret', '/groups\n'])('rejects unsafe return path %s', path => {
  expect(safeReturnPath(path, setup().router)).toBe('/dashboard')
})

it('preserves a known page path only', () => {
  expect(safeReturnPath('/polls/2/vote', setup().router)).toBe('/polls/2/vote')
})

it('redirects a guest with only a safe return path', async () => {
  const { router } = setup(vi.fn().mockRejectedValue(new ApiFailure('http', 'expired', 401)))
  await router.push('/polls/2/vote?password=private#answer')
  expect(router.currentRoute.value.path).toBe('/login')
  expect(router.currentRoute.value.query).toEqual({ returnTo: '/polls/2/vote' })
})

it('blocks protected content on network failure without assuming logout', async () => {
  const { router, me } = setup()
  await router.push('/groups')
  me.mockRejectedValue(new ApiFailure('network', 'offline'))
  await router.push('/tasks/mine')
  expect(router.currentRoute.value.path).toBe('/session-check')
  expect(router.currentRoute.value.query.returnTo).toBe('/tasks/mine')
})

it('lets guests use public connection and 404 pages without authentication calls', async () => {
  const { router, me } = setup()
  await router.push('/connection'); await router.push('/missing')
  expect(me).not.toHaveBeenCalled()
})

it('returns an authenticated user from login to a known page and rejects an external target', async () => {
  const { router } = setup()
  await router.push('/login?returnTo=/polls/3/results')
  expect(router.currentRoute.value.path).toBe('/polls/3/results')
  await router.push('/register?returnTo=https://evil.example')
  expect(router.currentRoute.value.path).toBe('/dashboard')
})

it('redirects protected API 401 to login and clears cached identity', async () => {
  const { router, session, me } = setup()
  await router.push('/polls/2/vote')
  me.mockRejectedValue(new ApiFailure('http', 'expired', 401))
  const id = 'c07e357967c148068a4f9aa539c759e2'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'UNAUTHENTICATED', message: 'expired' }, request_id: id }), { status: 401, headers: { 'Content-Type': 'application/json', 'X-Request-ID': id } })))
  await expect(request('/api/v1/groups')).rejects.toMatchObject({ status: 401 })
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/login'))
  expect(session.state.user).toBeNull()
  expect(router.currentRoute.value.query).toEqual({ returnTo: '/polls/2/vote', expired: '1' })
})
