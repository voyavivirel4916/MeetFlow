import { createRouter, type Router, type RouterHistory, type RouteRecordRaw } from 'vue-router'
import StagePage from './views/StagePage.vue'
import ConnectionPage from './views/ConnectionPage.vue'

const page = (path: string, title: string, description: string): RouteRecordRaw => ({
  path, component: StagePage, meta: { title, description },
})

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/groups' },
  page('/groups', '我的小组', '小组列表与创建、加入功能将在账户和小组接口完成后接入。'),
  page('/groups/:groupId([1-9]\\d*)', '小组空间', '这里将展示成员、排期和小组任务。'),
  page('/groups/:groupId([1-9]\\d*)/polls/new', '发起排期', '这里将设置候选时间和必到成员。'),
  page('/polls/:pollId([1-9]\\d*)/edit', '编辑排期', '草稿编辑将在排期接口完成后接入。'),
  page('/polls/:pollId([1-9]\\d*)/vote', '填写时间', '这里将填写本人在各候选时间的空闲状态。'),
  page('/polls/:pollId([1-9]\\d*)/results', '排期结果', '这里将展示时间矩阵、推荐理由和会议确认。'),
  page('/meetings/:meetingId([1-9]\\d*)', '会议与行动', '这里将维护议程、纪要和后续任务。'),
  page('/tasks/mine', '我的待办', '这里将汇总分配给你的会议任务。'),
  page('/login', '登录', '注册登录将在认证接口完成后接入。'),
  page('/register', '注册', '注册登录将在认证接口完成后接入。'),
  { path: '/connection', component: ConnectionPage, meta: { title: '连接检查' } },
  page('/:pathMatch(.*)*', '找不到这个页面', '请检查地址，或返回我的小组。'),
]

export function createApplicationRouter(history: RouterHistory) {
  const router = createRouter({ history, routes })
  router.afterEach(to => {
    if (typeof document !== 'undefined') document.title = `${String(to.meta.title || 'MeetFlow')} · MeetFlow`
  })
  return router
}

// Login return targets carry only a known page path, never queries or form values.
export function safeReturnPath(value: unknown, router: Router): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\?#\s\u0000-\u001f%]/u.test(value)) return '/groups'
  const target = router.resolve(value)
  if (target.matched.length === 0 || target.matched[0]?.path.includes('pathMatch') || ['/login', '/register', '/connection'].includes(target.path)) return '/groups'
  return target.path
}
