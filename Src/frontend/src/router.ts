import { createRouter, type RouterHistory, type RouteRecordRaw } from 'vue-router'
import StagePage from './views/StagePage.vue'
import ConnectionPage from './views/ConnectionPage.vue'
import AuthPage from './views/AuthPage.vue'
import SessionCheckPage from './views/SessionCheckPage.vue'
import GroupsPage from './views/GroupsPage.vue'
import GroupDetailPage from './views/GroupDetailPage.vue'
import PollEditorPage from './views/PollEditorPage.vue'
import VotePage from './views/VotePage.vue'
import MatrixPage from './views/MatrixPage.vue'
import MeetingPage from './views/MeetingPage.vue'
import TasksPage from './views/TasksPage.vue'
import { onUnauthorized } from './api/client'
import type { Session } from './auth/session'
import { safeReturnPath } from './navigation'
export { safeReturnPath } from './navigation'

const page = (path: string, title: string, description: string): RouteRecordRaw => ({
  path, component: StagePage, meta: { title, description, requiresAuth: !path.includes('pathMatch') },
})

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/groups' },
  { path: '/groups', component: GroupsPage, meta: { title: '我的小组', requiresAuth: true } },
  { path: '/groups/:groupId([1-9]\\d*)', component: GroupDetailPage, meta: { title: '小组空间', requiresAuth: true } },
  { path: '/groups/:groupId([1-9]\\d*)/polls/new', component: PollEditorPage, meta: { title: '发起排期', requiresAuth: true } },
  { path: '/polls/:pollId([1-9]\\d*)/edit', component: PollEditorPage, meta: { title: '编辑排期', requiresAuth: true } },
  { path: '/polls/:pollId([1-9]\\d*)/vote', component: VotePage, meta: { title: '填写时间', requiresAuth: true } },
  { path: '/polls/:pollId([1-9]\\d*)/results', component: MatrixPage, meta: { title: '排期结果', requiresAuth: true } },
  {path:'/meetings/:meetingId([1-9]\\d*)',component:MeetingPage,meta:{title:'会议与行动',requiresAuth:true}},
  {path:'/tasks/mine',component:TasksPage,meta:{title:'我的待办',requiresAuth:true}},
  { path: '/login', name: 'login', component: AuthPage, props: { registering: false }, meta: { title: '登录', authPage: true } },
  { path: '/register', name: 'register', component: AuthPage, props: { registering: true }, meta: { title: '注册', authPage: true } },
  { path: '/session-check', name: 'session-check', component: SessionCheckPage, meta: { title: '确认登录状态' } },
  { path: '/connection', component: ConnectionPage, meta: { title: '连接检查' } },
  page('/:pathMatch(.*)*', '找不到这个页面', '请检查地址，或返回我的小组。'),
]

export function createApplicationRouter(history: RouterHistory, session: Session) {
  const router = createRouter({ history, routes })
  router.beforeEach(async to => {
    if (!to.meta.requiresAuth && !to.meta.authPage) return true
    const phase = await session.check()
    if (to.meta.authPage) {
      return phase === 'authenticated' ? safeReturnPath(to.query.returnTo, router) : true
    }
    if (phase === 'authenticated') return true
    return { name: phase === 'anonymous' ? 'login' : 'session-check',
      query: { returnTo: safeReturnPath(to.path, router), ...(session.state.expired ? { expired: '1' } : {}) }, replace: true }
  })
  const dispose = onUnauthorized(() => {
    session.expire()
    const to = router.currentRoute.value
    if (to.meta.requiresAuth) void router.replace({ name: 'login', query: { returnTo: safeReturnPath(to.path, router), expired: '1' } })
  })
  router.afterEach(to => {
    if (typeof document !== 'undefined') document.title = `${String(to.meta.title || 'MeetFlow')} · MeetFlow`
  })
  return Object.assign(router, { disposeSessionListener: dispose })
}
