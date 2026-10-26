import { onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ApiFailure } from '../api/client'
import { useSession } from '../auth/session'
import type { GroupInput } from './api'

export type GroupErrors = Partial<Record<'name' | 'description' | 'invite_code', string>>
const length = (value: string) => Array.from(value).length
const invalidText = (value: string) => /\u0000|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)
export function validateGroup(mode: 'create' | 'join', fields: GroupInput & { invite_code: string }): GroupErrors {
  const errors: GroupErrors = {}
  if (mode === 'create') {
    if (!fields.name.trim() || length(fields.name.trim()) > 100 || invalidText(fields.name)) errors.name = '小组名称需为1～100个字符。'
    if (length(fields.description) > 10000 || invalidText(fields.description)) errors.description = '小组说明最多10000个字符，请检查文字。'
  } else if (!/^[a-zA-Z0-9]{12}$/.test(fields.invite_code.trim())) errors.invite_code = '请输入12位字母或数字邀请码。'
  return errors
}
export function failure(error: unknown) {
  return error instanceof ApiFailure ? error : new ApiFailure('network', '暂时无法连接，请稍后重试。')
}
// Do not block the authentication redirect or carry a draft into a different identity.
export function useGroupLifetime(dirty: () => boolean, pending: () => boolean) {
  const session = useSession(), identity = session.state.identityEpoch
  let mounted = true
  const live = () => mounted && session.state.identityEpoch === identity && session.state.phase === 'authenticated'
  const leave = () => !live() || (!pending() && (!dirty() || window.confirm('离开此页会清空尚未提交的输入，确定离开吗？')))
  onBeforeRouteLeave(leave)
  onBeforeRouteUpdate(leave)
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (live() && (dirty() || pending())) { event.preventDefault(); event.returnValue = '' }
  }
  window.addEventListener('beforeunload', beforeUnload)
  onBeforeUnmount(() => { mounted = false; window.removeEventListener('beforeunload', beforeUnload) })
  return live
}
