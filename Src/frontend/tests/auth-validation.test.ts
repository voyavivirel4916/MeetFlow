import { expect, it } from 'vitest'
import { validateAuth } from '../src/auth/validation'
const valid = { username: ' STUDENT ', email: 'student@example.com', password: ' password123 ' }
it('accepts normalization without trimming passwords or changing inputs', () => {
  expect(validateAuth(true, valid)).toEqual({})
  expect(valid.password).toBe(' password123 ')
})
it.each([
  [{ username: 'ab' }, 'username'], [{ username: 'a-b' }, 'username'], [{ username: '中' }, 'username'],
  [{ email: 'not-email' }, 'email'], [{ email: 'name <a@example.com>' }, 'email'],
  [{ password: 'short' }, 'password'], [{ password: ' '.repeat(8) }, 'password'], [{ password: 'a'.repeat(129) }, 'password'],
])('rejects invalid registration %j', (changes, field) => {
  expect(validateAuth(true, { ...valid, ...changes })).toHaveProperty(field)
})
it('counts Unicode characters rather than UTF-16 code units', () => {
  expect(validateAuth(true, { ...valid, password: '😊'.repeat(128) })).toEqual({})
  expect(validateAuth(true, { ...valid, password: '😊'.repeat(129) })).toHaveProperty('password')
})
it('lets short wrong login passwords reach the uniform server error', () => {
  expect(validateAuth(false, { ...valid, password: 'x' })).toEqual({})
  expect(validateAuth(false, { ...valid, password: '' })).toHaveProperty('password')
})
