export type ApiFailureKind = 'http' | 'network' | 'timeout' | 'aborted' | 'protocol'
export class ApiFailure extends Error {
  constructor(public kind: ApiFailureKind, message: string, public status?: number,
    public code?: string, public requestId?: string, public details?: unknown,
    public uncertain = false) { super(message); this.name = 'ApiFailure' }
}

type RequestOptions = { method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'; body?: unknown;
  signal?: AbortSignal; timeoutMs?: number }
type Envelope<T> = { data: T; request_id: string }
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)

export async function request<T>(path: string, options: RequestOptions = {}): Promise<Envelope<T>> {
  if (!/^\/api\/v1\/(?!.*(?:\.\.|[\\#]))[a-zA-Z0-9/_?=&%.-]+$/.test(path) || /%(?:2e|2f|5c)/i.test(path)) throw new TypeError('Expected a local /api/v1/ path')
  return send<T>(path, options)
}

export function checkLiveness() { return send<{ status: 'ok' }>('/livez', {}) }

async function send<T>(path: string, options: RequestOptions): Promise<Envelope<T>> {
  const method = options.method || 'GET'
  const writing = method !== 'GET'
  const serialized = options.body === undefined ? undefined : JSON.stringify(options.body)
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  else options.signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, options.timeoutMs ?? 10000)
  try {
    const response = await fetch(path, { method, credentials: 'same-origin', redirect: 'error', signal: controller.signal,
      headers: { Accept: 'application/json', ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(serialized === undefined ? {} : { body: serialized }) })
    const id = response.headers.get('X-Request-ID') || undefined
    const protocol = () => new ApiFailure('protocol', '服务响应无法识别，请稍后核对。', response.status, undefined, id, undefined, writing)
    if (response.headers.get('content-type')?.split(';')[0]?.trim() !== 'application/json') throw protocol()
    let body: unknown
    try { body = await response.json() } catch (error) {
      if (controller.signal.aborted) throw error
      throw protocol()
    }
    if (!object(body) || typeof body.request_id !== 'string' || !id || id !== body.request_id) throw protocol()
    if (!response.ok) {
      if (!object(body.error) || typeof body.error.code !== 'string' || typeof body.error.message !== 'string') throw protocol()
      // An unexpected server failure can happen after a write has committed.
      throw new ApiFailure('http', body.error.message, response.status, body.error.code, id, body.error.details, writing && response.status >= 500)
    }
    if (!('data' in body)) throw protocol()
    return body as Envelope<T>
  } catch (error) {
    if (error instanceof ApiFailure) throw error
    const kind = timedOut ? 'timeout' : controller.signal.aborted ? 'aborted' : 'network'
    throw new ApiFailure(kind, writing ? '提交结果暂时无法确认，请先刷新核对，再决定是否重试。' : '暂时无法连接服务，请稍后重试。', undefined, undefined, undefined, undefined, writing)
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}
