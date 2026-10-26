import { createMemoryHistory } from 'vue-router'
import { expect, it } from 'vitest'
import { createApplicationRouter, safeReturnPath } from '../src/router'

it.each([
  ['/groups', '我的小组'], ['/groups/1', '小组空间'], ['/groups/1/polls/new', '发起排期'],
  ['/polls/2/edit', '编辑排期'], ['/polls/2/vote', '填写时间'], ['/polls/2/results', '排期结果'],
  ['/meetings/3', '会议与行动'], ['/tasks/mine', '我的待办'], ['/login', '登录'], ['/register', '注册'],
  ['/connection', '连接检查'], ['/groups/0', '找不到这个页面'], ['/groups/-1', '找不到这个页面'],
  ['/polls/abc/vote', '找不到这个页面'], ['/missing', '找不到这个页面'],
])('resolves %s', (path, title) => {
  const router = createApplicationRouter(createMemoryHistory())
  expect(router.resolve(path).meta.title).toBe(title)
})

it('redirects the root into groups', async () => {
  const router = createApplicationRouter(createMemoryHistory())
  await router.push('/')
  expect(router.currentRoute.value.path).toBe('/groups')
})

it.each([undefined, '//evil.com', 'https://evil.com', '/\\evil.com', '/login', '/missing',
  '/groups?password=secret', '/groups#answer', '/groups%3fsecret', '/groups\n'])('rejects unsafe return path %s', path => {
  expect(safeReturnPath(path, createApplicationRouter(createMemoryHistory()))).toBe('/groups')
})

it('preserves a known page path only', () => {
  expect(safeReturnPath('/polls/2/vote', createApplicationRouter(createMemoryHistory()))).toBe('/polls/2/vote')
})
