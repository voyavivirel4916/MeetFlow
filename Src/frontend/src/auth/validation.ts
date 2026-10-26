export type AuthFields = { username: string; email: string; password: string }
export type FieldName = keyof AuthFields
export type FieldErrors = Partial<Record<FieldName, string>>
export function validateAuth(registering: boolean, fields: AuthFields): FieldErrors {
  const errors: FieldErrors = {}
  const username = fields.username.trim().toLowerCase()
  if (!username) errors.username = '请填写用户名。'
  else if (registering && !/^[a-z0-9_]{3,32}$/.test(username)) errors.username = '用户名需为3～32位字母、数字或下划线。'
  else if (Array.from(username).length > 32) errors.username = '用户名不能超过32个字符。'
  const length = Array.from(fields.password).length
  if (!length) errors.password = '请填写密码。'
  else if (length > 128 || (registering && (length < 8 || !fields.password.trim()))) errors.password = '密码需为8～128个字符，且不能全为空白。'
  if (registering) {
    const email = fields.email.trim()
    if (Array.from(email).length > 254 || !/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/u.test(email)) errors.email = '请填写有效邮箱，最多254个字符。'
  }
  return errors
}
