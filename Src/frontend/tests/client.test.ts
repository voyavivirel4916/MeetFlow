import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiFailure, checkLiveness, request } from '../src/api/client'

const id = 'c07e357967c148068a4f9aa539c759e2'
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify({ ...body as object, request_id: id }), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-Request-ID': id },
  })
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('API transport', () => {
  it('uses same-origin cookies, JSON and server request id', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ data: { id: 3 } }, 201))
    vi.stubGlobal('fetch', fetch)
    expect(await request('/api/v1/groups', { method: 'POST', body: { name: '项目组' } }))
      .toEqual({ data: { id: 3 }, request_id: id })
    expect(fetch).toHaveBeenCalledWith('/api/v1/groups', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', redirect: 'error', body: '{"name":"项目组"}',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    }))
  })

  it.each([401, 403, 409, 422, 503])('preserves structured HTTP %i errors without retry', async status => {
    const fetch = vi.fn().mockResolvedValue(json({ error: { code: 'TEST_ERROR', message: '请核对输入。', details: { field: 'name' } } }, status))
    vi.stubGlobal('fetch', fetch)
    await expect(request('/api/v1/groups', { method: 'POST', body: {} })).rejects.toMatchObject({
      kind: 'http', status, code: 'TEST_ERROR', message: '请核对输入。', requestId: id,
      details: { field: 'name' }, uncertain: status >= 500,
    })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('marks a disconnected write as uncertain, but not a read', async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError('private network detail'))
    vi.stubGlobal('fetch', fetch)
    await expect(request('/api/v1/groups', { method: 'POST' })).rejects.toMatchObject({ kind: 'network', uncertain: true })
    await expect(request('/api/v1/groups')).rejects.toMatchObject({ kind: 'network', uncertain: false })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('times out once and does not resend a write', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn((_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    vi.stubGlobal('fetch', fetch)
    const result = request('/api/v1/groups', { method: 'POST', timeoutMs: 20 }).catch(error => error)
    await vi.advanceTimersByTimeAsync(21)
    expect(await result).toMatchObject({ kind: 'timeout', uncertain: true })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('supports caller cancellation and removes its listener', async () => {
    const controller = new AbortController()
    const remove = vi.spyOn(controller.signal, 'removeEventListener')
    vi.stubGlobal('fetch', (_url: string, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const result = request('/api/v1/groups', { signal: controller.signal }).catch(error => error)
    controller.abort()
    expect(await result).toMatchObject({ kind: 'aborted', uncertain: false })
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
  })

  it.each([
    () => new Response('<html>fallback</html>', { headers: { 'Content-Type': 'text/html' } }),
    () => json({ error: {} }),
    () => new Response('{broken', { headers: { 'Content-Type': 'application/json', 'X-Request-ID': id } }),
    () => new Response(JSON.stringify({ data: {}, request_id: 'different' }), { headers: { 'Content-Type': 'application/json', 'X-Request-ID': id } }),
  ])('rejects malformed envelopes or SPA fallback', async factory => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(factory()))
    await expect(request('/api/v1/groups')).rejects.toBeInstanceOf(ApiFailure)
    await expect(request('/api/v1/groups')).rejects.toMatchObject({ kind: 'protocol' })
  })

  it.each(['https://example.com/api/v1/groups', '//example.com', '/api/v1/../livez', '/api/v1/%2e%2e/livez', '/groups'])('rejects non-API targets %s', async path => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    await expect(request(path)).rejects.toBeInstanceOf(TypeError)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('checks liveness through a relative URL', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ data: { status: 'ok' } }))
    vi.stubGlobal('fetch', fetch)
    expect((await checkLiveness()).data.status).toBe('ok')
    expect(fetch).toHaveBeenCalledWith('/livez', expect.any(Object))
  })
})
