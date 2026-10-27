import type { Router } from 'vue-router'

// Return targets carry only known protected paths, never form fields or queries.
export function safeReturnPath(value: unknown, router: Router): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\?#\s\u0000-\u001f%]/u.test(value)) return '/dashboard'
  const target = router.resolve(value)
  return target.meta.requiresAuth === true ? target.path : '/dashboard'
}
