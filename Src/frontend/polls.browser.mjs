// T15/T17 API flows with real browser sessions and an isolated database.
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
    const votePath = `/polls/${poll.id}/votes/me`;
    assert.deepEqual(ok(await api(member.page, votePath)), { poll_id: poll.id, submitted_at: null, votes: [] });
    const choice = availability => ({ votes: [{ slot_id: saved.slots[0].id, availability }] });
    let myVote;
    for (const value of ['AVAILABLE', 'MAYBE', 'UNAVAILABLE']) {
      myVote = ok(await api(member.page, votePath, 'PUT', choice(value)));
      assert.deepEqual(myVote.votes, choice(value).votes);
      assert.match(myVote.submitted_at, /^\d{4}-\d{2}-\d{2}T.*\.\d{3}Z$/);
    }
    assert.deepEqual(ok(await api(owner.page, votePath)).votes, []);
    assert.equal((await api(member.page, votePath, 'PUT', { ...choice('MAYBE'), user_id: owner.userId })).status, 422);
    assert.equal((await api(member.page, votePath, 'PUT', { votes: [] })).status, 422);
    assert.equal((await api(member.page, votePath, 'PUT', { votes: [...choice('MAYBE').votes, ...choice('MAYBE').votes] })).status, 422);
    assert.equal((await api(outside.page, votePath)).status, 404);
    await member.page.reload();
    assert.deepEqual(ok(await api(member.page, votePath)), myVote);
    const matrixPath = `/polls/${poll.id}/matrix`;
    const matrix = ok(await api(owner.page, matrixPath));
    assert.deepEqual(matrix.progress, { participant_count: 2, submitted_count: 1, unsubmitted_count: 1 });
    assert.equal(matrix.cells.length, 2);
    assert.equal(matrix.cells.find(cell => cell.user_id === owner.userId).availability, null);
    assert.equal(matrix.cells.find(cell => cell.user_id === member.userId).availability, 'UNAVAILABLE');
    assert.deepEqual([matrix.slots[0].available_count,matrix.slots[0].maybe_count,matrix.slots[0].unavailable_count,matrix.slots[0].unanswered_count], [0,0,1,1]);
    assert.equal((await api(outside.page, matrixPath)).status, 404);
    const closed = ok(await api(owner.page, `/polls/${poll.id}/close`, 'POST', {}));
    assert.equal(closed.status, 'CLOSED');
    assert.deepEqual(ok(await api(owner.page, `/polls/${poll.id}/close`, 'POST', {})), closed);
    assert.equal((await api(member.page, votePath, 'PUT', choice('MAYBE'))).body.error.code, 'POLL_CLOSED');
    assert.deepEqual(ok(await api(member.page, votePath)), myVote);
    assert.equal(ok(await api(member.page, matrixPath)).effective_status, 'CLOSED');
    const cancelled = ok(await api(owner.page, `/polls/${poll.id}/cancel`, 'POST', {}));
    assert.equal(cancelled.status, 'CANCELLED');
    assert.deepEqual(ok(await api(owner.page, `/polls/${poll.id}/cancel`, 'POST', {})), cancelled);
    assert.equal((await api(owner.page, `/polls/${poll.id}/open`, 'POST', {})).status, 409);
    ok(await api(member.page, '/auth/logout', 'POST', {}));
    assert.equal((await api(member.page, `/polls/${poll.id}`)).status, 401);
    assert.equal((await api(member.page, votePath)).status, 401);
    assert.equal((await api(member.page, matrixPath)).status, 401);
    console.log('PASS T15: real browser draft/create/replace/read/list, owner/member/outside permissions, publish freeze, close/cancel idempotence, terminal state, refresh and logout.');
    console.log('PASS T17: own answers, all three values, replace/reload, actor isolation, forged actor/empty/duplicate rejection, outside rights, closed read/write and expired session.');
    console.log('PASS T19: matrix/progress, explicit unknowns, three-state counts, owner/member access, outsider/anonymous rejection and closed readback.');
  } finally { for (const context of contexts) await context.close(); }
}
