// T12 real same-origin API flow; the group UI is implemented separately in T13.
import assert from 'node:assert/strict';

export async function verifyGroups(browser, origin) {
  const contexts = [];
  const call = (page, path, body) => page.evaluate(async ({ path, body }) => {
    const response = await fetch('/api/v1' + path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const payload = await response.json();
    return { status: response.status, payload, requestId: response.headers.get('x-request-id'), cache: response.headers.get('cache-control') };
  }, { path, body });
  const ok = (response, status = 200) => {
    assert.equal(response.status, status);
    assert.equal(response.payload.request_id, response.requestId);
    assert.equal(response.cache, 'no-store');
    return response.payload.data;
  };
  try {
    const pages = [];
    for (let index = 0; index < 4; index++) {
      const context = await browser.newContext();
      contexts.push(context);
      const page = await context.newPage();
      await page.goto(origin + '/connection');
      const username = 'group_browser_' + index;
      const password = 'groups-browser-password';
      ok(await call(page, '/auth/register', { username, password, email: username + '@example.com' }), 201);
      ok(await call(page, '/auth/login', { username, password }));
      pages.push(page);
    }
    const group = ok(await call(pages[0], '/groups', { name: '浏览器四账号小组', description: 'T12临时验证' }), 201);
    assert.equal(group.member_count, 1);
    assert.equal((await call(pages[1], '/groups/' + group.id)).status, 404);
    for (let index = 1; index < 4; index++) {
      const joined = ok(await call(pages[index], '/groups/join', { invite_code: group.invite_code.toLowerCase() }));
      assert.equal(joined.member_count, index + 1);
      assert.equal('invite_code' in joined, false);
      assert.equal(ok(await call(pages[index], '/groups/join', { invite_code: group.invite_code })).member_count, index + 1);
    }
    const roster = ok(await call(pages[3], `/groups/${group.id}/members`)).items;
    assert.deepEqual(roster.map(member => member.role), ['OWNER', 'MEMBER', 'MEMBER', 'MEMBER']);
    assert.ok(roster.every(member => Object.keys(member).sort().join(',') === 'role,user_id,username'));
    const memberList = ok(await call(pages[1], '/groups')).items;
    assert.equal(memberList.length, 1);
    assert.equal('invite_code' in memberList[0], false);
    assert.equal((await call(pages[1], `/groups/${group.id}/invite-code/reset`, {})).status, 403);
    const reset = ok(await call(pages[0], `/groups/${group.id}/invite-code/reset`, {}));
    assert.notEqual(reset.invite_code, group.invite_code);
    assert.equal((await call(pages[2], '/groups/join', { invite_code: group.invite_code })).status, 404);
    assert.equal(ok(await call(pages[2], '/groups/join', { invite_code: reset.invite_code })).member_count, 4);
    await pages[0].reload();
    assert.equal(ok(await call(pages[0], '/groups/' + group.id)).invite_code, reset.invite_code);
    ok(await call(pages[3], '/auth/logout', {}));
    assert.equal((await call(pages[3], `/groups/${group.id}/members`)).status, 401);
    console.log('PASS T12: four real browser sessions, create/join/repeat, private group/members, owner-only invitation, reset/old-code invalidation, reload and logout.');
  } finally { for (const context of contexts) await context.close(); }
}
