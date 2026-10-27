// T15 API flow with real browser sessions; editing UI remains a separate T16 task.
import assert from 'node:assert/strict';

export async function verifyPolls(browser, origin) {
  const contexts = [];
  const api = (page, path, method = 'GET', body) => page.evaluate(async ({ path, method, body }) => {
    const response = await fetch('/api/v1' + path, { method, credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    return { status: response.status, body: await response.json(), cache: response.headers.get('cache-control'), id: response.headers.get('x-request-id') };
  }, { path, method, body });
  const ok = (response, status = 200) => {
    assert.equal(response.status, status);
    assert.equal(response.cache, 'no-store');
    assert.equal(response.body.request_id, response.id);
    return response.body.data;
  };
  try {
    const people = [];
    for (const role of ['owner', 'member', 'outside']) {
      const context = await browser.newContext(); contexts.push(context);
      const page = await context.newPage();
      const username = 'poll_browser_' + role, password = 'poll-browser-password';
      const account = await context.request.post(origin + '/api/v1/auth/register', { data: { username, password, email: username + '@example.com' } });
      assert.equal(account.status(), 201);
      const userId = (await account.json()).data.id;
      assert.equal((await context.request.post(origin + '/api/v1/auth/login', { data: { username, password } })).status(), 200);
      await page.goto(origin + '/connection');
      people.push({ page, userId });
    }
    const [owner, member, outside] = people;
    const group = ok(await api(owner.page, '/groups', 'POST', { name: '真实浏览器排期小组' }), 201);
    ok(await api(member.page, '/groups/join', 'POST', { invite_code: group.invite_code }));
    const now = Date.now();
    const draft = { title: '课程方案评审', description: 'T15临时接口验证', location: '2015A',
      response_deadline: new Date(now + 600_000).toISOString(), participants: [], slots: [] };
    const poll = ok(await api(owner.page, `/groups/${group.id}/polls`, 'POST', draft), 201);
    assert.equal(poll.status, 'DRAFT');
    assert.equal((await api(owner.page, `/polls/${poll.id}/open`, 'POST', {})).status, 422);
    const complete = { ...draft, participants: [{ user_id: owner.userId, importance: 'REQUIRED' }, { user_id: member.userId, importance: 'NORMAL' }],
      slots: [{ start_at: new Date(now+1_200_000).toISOString(), end_at: new Date(now+1_800_000).toISOString() }] };
    const saved = ok(await api(owner.page, `/polls/${poll.id}`, 'PUT', complete));
    assert.equal(saved.participants.length, 2);
    assert.ok(saved.participants.every(person => person.submitted_at === null && !('email' in person)));
    assert.deepEqual(ok(await api(member.page, `/polls/${poll.id}`)), saved);
    assert.equal((await api(outside.page, `/polls/${poll.id}`)).status, 404);
    assert.equal((await api(member.page, `/polls/${poll.id}`, 'PUT', complete)).status, 403);
    assert.equal((await api(member.page, `/polls/${poll.id}/open`, 'POST', {})).status, 403);
    assert.equal(ok(await api(owner.page, `/polls/${poll.id}/open`, 'POST', {})).effective_status, 'OPEN');
    assert.equal((await api(owner.page, `/polls/${poll.id}`, 'PUT', complete)).status, 409);
    await member.page.reload();
    assert.equal(ok(await api(member.page, `/groups/${group.id}/polls`)).items[0].status, 'OPEN');
    const closed = ok(await api(owner.page, `/polls/${poll.id}/close`, 'POST', {}));
    assert.equal(closed.status, 'CLOSED');
    assert.deepEqual(ok(await api(owner.page, `/polls/${poll.id}/close`, 'POST', {})), closed);
    const cancelled = ok(await api(owner.page, `/polls/${poll.id}/cancel`, 'POST', {}));
    assert.equal(cancelled.status, 'CANCELLED');
    assert.deepEqual(ok(await api(owner.page, `/polls/${poll.id}/cancel`, 'POST', {})), cancelled);
    assert.equal((await api(owner.page, `/polls/${poll.id}/open`, 'POST', {})).status, 409);
    ok(await api(member.page, '/auth/logout', 'POST', {}));
    assert.equal((await api(member.page, `/polls/${poll.id}`)).status, 401);
    console.log('PASS T15: real browser draft/create/replace/read/list, owner/member/outside permissions, publish freeze, close/cancel idempotence, terminal state, refresh and logout.');
  } finally { for (const context of contexts) await context.close(); }
}
