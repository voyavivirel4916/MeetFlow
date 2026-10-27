import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

export async function verifyVotesUI(browser, origin, { root, screenshots }) {
  const contexts = [], errors = [], password = 'votes-ui-password';
  const account = async username => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/Los_Angeles' });
    contexts.push(context);
    const response = await context.request.post(origin+'/api/v1/auth/register', { data: { username, password, email: username+'@example.com' } });
    assert.equal(response.status(), 201);
    const id = (await response.json()).data.id;
    assert.equal((await context.request.post(origin+'/api/v1/auth/login', { data: { username, password } })).status(), 200);
    const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message));
    return { context, page, id };
  };
  const ready = page => page.waitForFunction(() => document.querySelector('.vote-fields') && !document.querySelector('.vote-fields').disabled);
  const save = page => page.getByRole('button', { name: '保存我的选择', exact: true });
  const radio = (page, slot, value) => page.locator(`#vote-${slot.id}-${value}`);
  const get = async (actor, poll) => (await (await actor.context.request.get(origin+`/api/v1/polls/${poll.id}/votes/me`)).json()).data;
  const shot = async (page, name) => {
    if (!screenshots) return;
    const directory = resolve(root, 'Docs/images/t18'); await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory,name+'.png'), fullPage: true });
  };
  const reply = (route, status, code, message) => route.fulfill({ status, contentType: 'application/json', headers: { 'X-Request-ID': 'c07e357967c148068a4f9aa539c759e2' },
    body: JSON.stringify({ error: { code, message }, request_id: 'c07e357967c148068a4f9aa539c759e2' }) });
  try {
    const owner = await account('vote_owner'), member = await account('vote_member'), observer = await account('vote_observer'), outside = await account('vote_outside');
    const group = (await (await owner.context.request.post(origin+'/api/v1/groups', { data: { name: '拼出我们的共同时间', description: '一起确定方案评审时间' } })).json()).data;
    for (const actor of [member,observer]) assert.equal((await actor.context.request.post(origin+'/api/v1/groups/join', { data: { invite_code: group.invite_code } })).status(), 200);
    const now = Math.floor(Date.now()/60000)*60000;
    const created = await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`, { data: { title: '课程方案评审', description: '讨论功能边界，确认下一轮分工。', location: '计算机大楼2015A',
      response_deadline: new Date(now+3600_000).toISOString(), participants: [{ user_id: owner.id, importance: 'REQUIRED' }, { user_id: member.id, importance: 'NORMAL' }],
      slots: [0,1,2].map(day => ({ start_at: new Date(now+7200_000+day*86400_000).toISOString(), end_at: new Date(now+10800_000+day*86400_000).toISOString() })) } });
    assert.equal(created.status(), 201);
    const poll = (await created.json()).data, groupUrl = origin+`/groups/${group.id}`, voteUrl = origin+`/polls/${poll.id}/vote`, path = `**/api/v1/polls/${poll.id}/votes/me`;
    // Draft is read-only and has no misleading save operation.
    await member.page.goto(voteUrl); await member.page.getByText('排期尚未发布，暂时不能填写。', { exact: true }).waitFor();
    assert.equal(await radio(member.page,poll.slots[0],'AVAILABLE').isDisabled(), true);
    assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/open`, { data: {} })).status(), 200);
    const page = member.page;
    await page.goto(groupUrl);
    const refresh = page.getByRole('button', { name: '刷新排期', exact: true });
    await refresh.waitFor();
    assert.equal((await refresh.innerText()).trim(), '');
    assert.equal(await page.locator('.poll-heading-title button svg').count(), 1);
    let release;
    const delay = new Promise(done => { release = done; });
    await page.route(`**/api/v1/groups/${group.id}/polls?*`, async route => { await delay; await route.continue(); });
    await refresh.click();
    await page.waitForFunction(() => document.querySelector('.refresh-icon')?.disabled);
    assert.equal(await page.getByRole('button', { name: '正在读取排期', exact: true }).isDisabled(), true);
    release();
    await page.waitForFunction(() => document.querySelector('.refresh-icon') && !document.querySelector('.refresh-icon').disabled);
    await page.unroute(`**/api/v1/groups/${group.id}/polls?*`);
    await page.getByRole('link', { name: '填写时间 →', exact: true }).click(); await ready(page);
    assert.equal(await page.locator('.vote-card').count(), 3);
    assert.equal(await page.locator('.vote-card input:checked').count(), 0);
    await page.getByText('已选 0/3', { exact: true }).waitFor();
    assert.match(await page.locator('.vote-date').first().innerText(), /\d{4}-\d{2}-\d{2} \d{2}:\d{2} — \d{2}:\d{2}/);
    await save(page).click();
    assert.equal(await page.locator('.form-summary').evaluate(element => element === document.activeElement), true);
    assert.equal(await page.locator('.vote-card .field-error').count(), 3);
    await page.getByRole('button', { name: '候选 1 尚未选择', exact: true }).click();
    assert.equal(await radio(page,poll.slots[0],'AVAILABLE').evaluate(element => element === document.activeElement), true);
    await page.keyboard.press('Space');
    await page.keyboard.press('ArrowRight');
    assert.equal(await radio(page,poll.slots[0],'MAYBE').isChecked(), true);
    await radio(page,poll.slots[0],'AVAILABLE').check();
    await radio(page,poll.slots[1],'MAYBE').check();
    await radio(page,poll.slots[2],'UNAVAILABLE').check();
    await page.getByText('已选 3/3', { exact: true }).waitFor();
    const expected = ['AVAILABLE','MAYBE','UNAVAILABLE'];
    let writes = 0;
    await page.route(path, async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      writes++; await new Promise(done => setTimeout(done, 300)); await route.continue();
    });
    await save(page).click();
    await page.waitForFunction(() => document.querySelector('.vote-fields')?.disabled);
    await page.getByText('你的选择已保存。', { exact: true }).waitFor();
    assert.equal(writes,1); await page.unroute(path);
    assert.deepEqual((await get(member,poll)).votes.map(item => item.availability), expected);
    assert.deepEqual((await get(owner,poll)).votes, []);
    await page.reload(); await ready(page);
    for (const [index,slot] of poll.slots.entries()) assert.equal(await radio(page,slot,expected[index]).isChecked(), true);
    await shot(page,'03-filled');
    for (const width of [1440,1024,800,400]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Vote overflow ${width}`);
    }
    await page.setViewportSize({ width:1440,height:1000 });
    await radio(page,poll.slots[0],'UNAVAILABLE').check();
    page.once('dialog', dialog => dialog.dismiss()); await page.locator('.back-link').click();
    assert.equal(page.url(),voteUrl);
    page.once('dialog', dialog => dialog.dismiss()); await page.getByRole('button',{name:'重新读取填写',exact:true}).click();
    assert.equal(await radio(page,poll.slots[0],'UNAVAILABLE').isChecked(),true);
    // 422 preserves current selection and allows correction/retry.
    await page.route(path, route => route.request().method() === 'PUT' ? reply(route,422,'VALIDATION_ERROR','请重新核对全部时段。') : route.continue());
    await save(page).click(); await page.getByText('请重新核对全部时段。',{exact:true}).waitFor();
    assert.equal(await radio(page,poll.slots[0],'UNAVAILABLE').isChecked(),true);
    await page.unroute(path);
    // Lost save response: reconcile, do not automatically PUT again.
    writes = 0;
    await page.route(path, async route => {
      if (route.request().method() !== 'PUT') return route.continue();
      writes++; const response = await route.fetch(); await route.fulfill({ response, body:'{damaged' });
    });
    await save(page).click(); await page.getByRole('button',{name:'核对服务端结果',exact:true}).waitFor();
    assert.equal(await save(page).isDisabled(),true);
    await page.route(path, route => route.request().method() === 'GET' ? route.abort() : route.fallback());
    await page.getByRole('button',{name:'核对服务端结果',exact:true}).click();
    await page.getByRole('heading',{name:'填写结果暂时无法读取',exact:true}).waitFor();
    assert.equal(await radio(page,poll.slots[0],'UNAVAILABLE').isChecked(),true);
    await page.unroute(path);
    await page.getByRole('button',{name:'重新读取结果',exact:true}).click();
    await page.getByText('已核对，你的选择已保存。',{exact:true}).waitFor();
    assert.equal(writes,1);
    // Aborted write with different server answers requires explicit acknowledgement.
    await radio(page,poll.slots[0],'MAYBE').check();
    await page.route(path, route => route.request().method() === 'PUT' ? route.abort() : route.continue());
    await save(page).click(); await page.getByRole('button',{name:'核对服务端结果',exact:true}).click();
    await page.getByRole('checkbox',{name:'我已核对，确认用本页选择再次保存',exact:true}).waitFor();
    assert.equal(await save(page).isDisabled(),true);
    assert.equal(await radio(page,poll.slots[0],'MAYBE').isChecked(),true);
    await shot(page,'04-reconcile');
    await page.unroute(path);
    await page.getByRole('checkbox',{name:'我已核对，确认用本页选择再次保存',exact:true}).check();
    await save(page).click(); await page.getByText('你的选择已保存。',{exact:true}).waitFor();
    assert.equal((await get(member,poll)).votes[0].availability,'MAYBE');
    // Initial read failure is not an empty result and can be retried.
    await page.route(path,route=>route.abort()); await page.reload();
    await page.getByRole('heading',{name:'填写结果暂时无法读取',exact:true}).waitFor();
    assert.equal(await page.locator('.vote-card').count(),0);
    await page.unroute(path); await page.getByRole('button',{name:'重新读取结果',exact:true}).click(); await ready(page);
    // Participant permissions and entry links.
    await observer.page.goto(groupUrl);
    assert.equal(await observer.page.getByRole('link',{name:'填写时间 →',exact:true}).count(),0);
    await observer.page.goto(voteUrl); await observer.page.getByText('你未被列为本次排期的参与者，可以返回排期详情查看。',{exact:true}).waitFor();
    assert.equal(await observer.page.locator('.vote-form').count(),0);
    await outside.page.goto(voteUrl); await outside.page.getByRole('heading',{name:'未找到可访问的排期',exact:true}).waitFor();
    assert.equal(await outside.page.getByText(poll.title,{exact:true}).count(),0);
    // Closing during edits rejects save, preserves inputs and allows readback.
    await radio(page,poll.slots[0],'AVAILABLE').check();
    assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/close`,{data:{}})).status(),200);
    await save(page).click(); await page.getByRole('button',{name:'核对服务端结果',exact:true}).click();
    await page.getByText('排期已不可填写，本页尚未确认保存的选择仍保留供你核对。',{exact:true}).waitFor();
    assert.equal(await radio(page,poll.slots[0],'AVAILABLE').isChecked(),true);
    assert.equal(await radio(page,poll.slots[0],'AVAILABLE').isDisabled(),true);
    page.once('dialog',dialog=>dialog.accept()); await page.getByRole('button',{name:'重新读取填写',exact:true}).click();
    await page.getByText('本次收集已结束，以下保留你最后保存的答案。',{exact:true}).waitFor();
    await page.waitForFunction(() => document.querySelector('.vote-progress')?.textContent && !document.querySelector('.group-heading button')?.disabled);
    assert.equal(await radio(page,poll.slots[0],'MAYBE').isChecked(),true);
    assert.equal(await save(page).count(),0);
    await shot(page,'05-closed');
    // Real session expiry must bypass dirty leave guard and discard previous actor's input.
    await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/cancel`,{data:{}});
    const fresh = await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`,{data:{ title:'会话失效测试', response_deadline:new Date(now+3600_000).toISOString(), participants:[{user_id:member.id,importance:'NORMAL'}], slots:[{start_at:new Date(now+7200_000).toISOString(),end_at:new Date(now+10800_000).toISOString()}] }});
    const nextPoll = (await fresh.json()).data;
    await owner.context.request.post(origin+`/api/v1/polls/${nextPoll.id}/open`,{data:{}});
    await page.goto(origin+`/polls/${nextPoll.id}/vote`); await ready(page);
    await radio(page,nextPoll.slots[0],'AVAILABLE').check();
    await member.context.request.post(origin+'/api/v1/auth/logout',{data:{}});
    await save(page).click(); await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
    await page.locator('#username').fill('vote_outside'); await page.locator('#password').fill(password); await page.locator('button[type=submit]').click();
    await page.getByRole('heading',{name:'未找到可访问的排期',exact:true}).waitFor();
    assert.equal(await page.locator('.vote-card').count(),0);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert.deepEqual(errors,[]);
    console.log('PASS T18 UI: entry/refresh icon, three states/keyboard, completeness, one PUT, save/reload, dirty leave, 422, lost response/reconcile/retry, initial read failure, own/nonparticipant/outside rights, concurrent close, expiry/new account, minute Beijing dates and 4 widths.');
  } catch(error) {
    console.error('T18 failure',error,'Page errors:',errors);
    for(const context of contexts) for(const page of context.pages()) if (await page.locator('main').count()) console.error('T18 diagnostic',page.url(),(await page.locator('main').innerText({timeout:1000})).slice(0,2500));
    throw error;
  } finally { for(const context of contexts) await context.close(); }
}
