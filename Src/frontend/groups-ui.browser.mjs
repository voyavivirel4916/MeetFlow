import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

export async function verifyGroupsUI(browser, origin, { root, screenshots }) {
  const contexts = [], errors = [];
  const password = 'groups-ui-password';
  const account = async username => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    contexts.push(context);
    assert.equal((await context.request.post(origin + '/api/v1/auth/register', { data: { username, email: username + '@example.com', password } })).status(), 201);
    assert.equal((await context.request.post(origin + '/api/v1/auth/login', { data: { username, password } })).status(), 200);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    return { context, page };
  };
  const heading = (page, name) => page.getByRole('heading', { name, exact: true }).waitFor();
  const ready = page => page.waitForFunction(() => document.querySelector('fieldset') && !document.querySelector('fieldset').disabled);
  const submit = page => page.locator('button[type="submit"]');
  const shot = async (page, name) => {
    if (!screenshots) return;
    const directory = resolve(root, 'Docs/images/t13');
    await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, name + '.png'), fullPage: !name.includes('list') });
  };
  const reply = (route, status, code, message, details = {}) => route.fulfill({ status, contentType: 'application/json',
    headers: { 'X-Request-ID': 'c07e357967c148068a4f9aa539c759e2' }, body: JSON.stringify({ request_id: 'c07e357967c148068a4f9aa539c759e2', error: { code, message, details } }) });
  try {
    const owner = await account('ui_group_owner'), member = await account('ui_group_member'), stranger = await account('ui_group_outside');
    const page = owner.page;
    await page.goto(origin + '/groups');
    await ready(page);
    await heading(page, '你的第一块拼图，还在等你');
    await shot(page, '03-empty');
    await submit(page).click();
    await page.locator('.form-summary[role="alert"]').waitFor();
    assert.equal(await page.locator('.form-summary').evaluate(element => element === document.activeElement), true);
    await page.getByRole('button', { name: '小组名称需为1～100个字符。', exact: true }).click();
    assert.equal(await page.locator('#group-name').evaluate(element => element === document.activeElement), true);
    await page.locator('#group-name').fill('时间拼图 · 课程项目组');
    await page.locator('#group-description').fill('从一次课程讨论开始。\n把排期、会议决定和下一件事放在一起。');
    await page.route(/\/api\/v1\/groups$/, route => reply(route, 422, 'VALIDATION_ERROR', '请检查填写内容。', { fields: [{ location: ['body', 'name'] }] }));
    await submit(page).click();
    await page.getByText('请检查填写内容。', { exact: true }).waitFor();
    assert.equal(await page.locator('#group-name').inputValue(), '时间拼图 · 课程项目组');
    assert.equal(await page.locator('#group-name').getAttribute('aria-invalid'), 'true');
    await page.unroute(/\/api\/v1\/groups$/);
    await page.locator('#group-name').fill('时间拼图 · 课程项目组 ');
    let creates = 0;
    await page.route(/\/api\/v1\/groups$/, async route => {
      if (route.request().method() !== 'POST') return route.continue();
      creates++;
      await new Promise(done => setTimeout(done, 500));
      await route.continue();
    });
    await submit(page).click();
    await page.waitForFunction(() => document.querySelector('fieldset')?.disabled);
    await heading(page, '时间拼图 · 课程项目组');
    assert.equal(creates, 1);
    await page.unroute(/\/api\/v1\/groups$/);
    await page.getByText('小组创建成功。', { exact: true }).waitFor();
    const groupId = new URL(page.url()).pathname.split('/').at(-1);
    await page.waitForFunction(() => /^[A-Z0-9]{12}$/.test(document.querySelector('#current-invite')?.value || ''));
    const initialCode = await page.locator('#current-invite').inputValue();
    await page.reload();
    await heading(page, '时间拼图 · 课程项目组');
    assert.equal(await page.getByText('小组创建成功。', { exact: true }).count(), 0);
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async code => { window.__copiedCode = code; } } }));
    await page.getByRole('button', { name: '复制邀请码', exact: true }).click();
    await page.getByText('邀请码已复制，可分享给同学。', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.__copiedCode), initialCode);
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async () => { throw new Error('denied'); } } }));
    await page.getByRole('button', { name: '复制邀请码', exact: true }).click();
    await page.getByText('无法自动复制，已选中邀请码，请按 Ctrl+C 复制。', { exact: true }).waitFor();
    assert.equal(await page.locator('#current-invite').evaluate(element => element === document.activeElement && element.selectionEnd - element.selectionStart === 12), true);
    page.once('dialog', dialog => dialog.dismiss());
    await page.getByRole('button', { name: '重置邀请码', exact: true }).click();
    assert.equal(await page.locator('#current-invite').inputValue(), initialCode);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '重置邀请码', exact: true }).click();
    await page.getByText('邀请码已重置，旧码已失效。', { exact: true }).waitFor();
    const code = await page.locator('#current-invite').inputValue();
    assert.notEqual(code, initialCode);
    // A member-list read failure preserves the previous roster and disables invitation actions.
    await page.route(/\/api\/v1\/groups\/\d+\/members$/, route => route.abort());
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    await heading(page, '小组信息暂时无法读取');
    assert.equal(await page.locator('.member-list li').count(), 1);
    assert.equal(await page.getByRole('button', { name: '重置邀请码', exact: true }).isDisabled(), true);
    await page.unroute(/\/api\/v1\/groups\/\d+\/members$/);
    await page.getByRole('button', { name: '重新读取', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#current-invite')?.value?.length === 12);

    const memberPage = member.page;
    await memberPage.goto(origin + '/groups'); await ready(memberPage);
    await memberPage.getByRole('button', { name: '邀请码加入', exact: true }).click();
    await submit(memberPage).click();
    await memberPage.getByText('请输入12位字母或数字邀请码。', { exact: true }).first().waitFor();
    await memberPage.locator('#invite-code').fill(initialCode);
    await submit(memberPage).click();
    await memberPage.getByText('未找到可访问的小组。', { exact: true }).waitFor();
    assert.equal(await memberPage.locator('#invite-code').inputValue(), initialCode);
    // Real backend capacity has separate tests; verify the UI's 409 state without adding demo users.
    await memberPage.route('**/api/v1/groups/join', route => reply(route, 409, 'STATE_CONFLICT', '小组已满20人，暂时无法加入。'));
    await memberPage.locator('#invite-code').fill(code.toLowerCase());
    await submit(memberPage).click();
    await memberPage.getByText('小组已满20人，暂时无法加入。', { exact: true }).waitFor();
    assert.equal(await memberPage.locator('#invite-code').inputValue(), code.toLowerCase());
    await memberPage.unroute('**/api/v1/groups/join');
    await submit(memberPage).click();
    await heading(memberPage, '时间拼图 · 课程项目组');
    assert.equal(await memberPage.locator('.member-list li').count(), 2);
    await memberPage.route(/\/api\/v1\/groups\/\d+\/members$/, async route => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.data.items.reverse();
      await route.fulfill({ response, json: payload });
    });
    await memberPage.getByRole('button', { name: '刷新', exact: true }).click();
    await memberPage.waitForFunction(() => document.querySelector('.group-heading button')?.textContent === '刷新');
    assert.match(await memberPage.locator('.member-list li').first().textContent(), /ui_group_owner.*负责人/);
    assert.equal(await memberPage.locator('.member-list .current-member').count(), 1);
    assert.match(await memberPage.locator('.member-list .current-member').textContent(), /ui_group_member/);
    assert.equal(await memberPage.locator('.member-list .current-member').evaluate(element => getComputedStyle(element).backgroundColor), 'rgb(240, 234, 247)');
    assert.equal(await memberPage.getByText('这是你', { exact: true }).count(), 0);
    assert.equal(await memberPage.locator('.group-count').count(), 0);
    assert.equal(await memberPage.locator('.members-card .section-heading .member-capacity').textContent(), '02/20');
    assert.equal(await memberPage.locator('.member-capacity').evaluate(element => getComputedStyle(element).fontSize), '12px');
    assert.equal(await memberPage.locator('.group-about .plain-text').evaluate(element => getComputedStyle(element).fontSize), '13px');
    await memberPage.unroute(/\/api\/v1\/groups\/\d+\/members$/);
    assert.equal(await memberPage.getByRole('button', { name: '重置邀请码', exact: true }).count(), 0);
    assert.equal(await memberPage.locator('#current-invite').count(), 0);
    await shot(memberPage, '04-member');
    await page.getByRole('button', { name: '刷新', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.member-list li').length === 2);
    assert.match(await page.locator('.member-list .current-member').textContent(), /ui_group_owner/);
    await shot(page, '05-owner');
    for (const width of [1440, 1024, 800, 640, 400]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Detail overflow ${width}`);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    // A malformed reset response must hide the stale code until a successful GET.
    await page.route(/\/invite-code\/reset$/, async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '重置邀请码', exact: true }).click();
    await page.getByRole('button', { name: '核对当前邀请码', exact: true }).waitFor();
    assert.equal(await page.locator('#current-invite').inputValue(), '');
    assert.equal(await page.getByRole('button', { name: '复制邀请码', exact: true }).isDisabled(), true);
    await page.getByRole('button', { name: '核对当前邀请码', exact: true }).click();
    await page.getByText('已重新读取当前邀请码，请使用下方最新代码。', { exact: true }).waitFor();
    assert.notEqual(await page.locator('#current-invite').inputValue(), code);
    await page.unroute(/\/invite-code\/reset$/);
    const latestCode = await page.locator('#current-invite').inputValue();
    await memberPage.locator('.back-link').click(); await ready(memberPage);
    await memberPage.getByRole('button', { name: '邀请码加入', exact: true }).click();
    await memberPage.locator('#invite-code').fill(latestCode);
    let joins = 0;
    await memberPage.route('**/api/v1/groups/join', async route => {
      joins++;
      if (joins > 1) return route.continue();
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    await submit(memberPage).click();
    await memberPage.getByRole('button', { name: '核对小组列表', exact: true }).waitFor();
    assert.equal(joins, 1);
    assert.equal(await submit(memberPage).isDisabled(), true);
    await memberPage.getByRole('button', { name: '核对小组列表', exact: true }).click();
    await memberPage.getByRole('checkbox', { name: '我已核对，仍需再次提交加入', exact: true }).check();
    await submit(memberPage).click();
    await memberPage.waitForURL(origin + '/groups/' + groupId);
    await heading(memberPage, '小组成员');
    assert.equal(joins, 2);
    assert.equal(await memberPage.locator('.member-list li').count(), 2);
    await memberPage.unroute('**/api/v1/groups/join');

    // Create commits but its response is lost: exactly one POST, retained fields, manual list reconciliation.
    await page.locator('.back-link').click(); await ready(page);
    await page.locator('#group-name').fill('响应待核对的小组');
    await page.locator('#group-description').fill('<script>window.__unsafe=true</script>');
    let uncertainCreates = 0;
    await page.route(/\/api\/v1\/groups$/, async route => {
      uncertainCreates++;
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    await submit(page).click();
    await page.getByRole('button', { name: '核对小组列表', exact: true }).waitFor();
    assert.equal(await submit(page).isDisabled(), true);
    assert.equal(await page.locator('#group-name').inputValue(), '响应待核对的小组');
    await page.getByRole('button', { name: '核对小组列表', exact: true }).click();
    await page.getByRole('heading', { name: '响应待核对的小组', exact: true }).waitFor();
    assert.equal(uncertainCreates, 1);
    assert.equal(await submit(page).isDisabled(), true);
    await page.unroute(/\/api\/v1\/groups$/);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('heading', { name: '响应待核对的小组', exact: true }).getByRole('link').click();
    await heading(page, '关于这个小组');
    assert.equal(await page.evaluate(() => window.__unsafe), undefined);
    assert.equal(await page.locator('.plain-text').textContent(), '<script>window.__unsafe=true</script>');
    const secondGroupId = new URL(page.url()).pathname.split('/').at(-1);
    // A route change aborts old reads, so delayed data cannot overwrite the new group.
    await page.route(new RegExp(`/api/v1/groups/${groupId}$`), async route => {
      await new Promise(done => setTimeout(done, 400));
      try { await route.continue(); } catch { /* Expected cancellation on unmount. */ }
    });
    await page.goto(origin + '/groups/' + groupId);
    await page.locator('.back-link').click(); await ready(page);
    await page.getByRole('heading', { name: '响应待核对的小组', exact: true }).getByRole('link').click();
    await page.waitForURL(origin + '/groups/' + secondGroupId);
    await page.getByRole('heading', { name: '响应待核对的小组', exact: true, level: 1 }).waitFor();
    await page.unroute(new RegExp(`/api/v1/groups/${groupId}$`));
    assert.equal(new URL(page.url()).pathname, '/groups/' + secondGroupId);
    await stranger.page.goto(origin + '/groups/' + groupId);
    await heading(stranger.page, '未找到可访问的小组');
    assert.equal(await stranger.page.getByText('时间拼图 · 课程项目组', { exact: true }).count(), 0);

    // Pagination and failed reads preserve the last successful list, with no false empty screen.
    for (let index = 0; index < 20; index++) {
      assert.equal((await owner.context.request.post(origin + '/api/v1/groups', { data: { name: '课程协作 ' + (index + 1) } })).status(), 201);
    }
    await page.locator('.back-link').click(); await ready(page);
    assert.equal(await page.locator('.group-card').count(), 20);
    await shot(page, '06-list');
    await page.getByRole('button', { name: '下一页', exact: true }).click();
    await page.getByText('第 2 / 2 页', { exact: true }).waitFor();
    assert.equal(await page.locator('.group-card').count(), 2);
    await page.route(/\/api\/v1\/groups\?/, route => route.abort());
    await page.getByRole('button', { name: '刷新列表', exact: true }).click();
    await heading(page, '小组列表暂时无法读取');
    assert.equal(await page.locator('.group-card').count(), 2);
    assert.equal(await submit(page).isDisabled(), true);
    await page.unroute(/\/api\/v1\/groups\?/);
    await page.getByRole('button', { name: '重新读取', exact: true }).click(); await ready(page);
    for (const width of [1440, 1024, 800, 400]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `List overflow ${width}`);
    }
    // Dirty navigation can be cancelled, but a real 401 must still redirect and clear the draft.
    await page.locator('#group-name').fill('账号甲的未提交草稿');
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('aside a[href="/tasks/mine"]').click();
    assert.equal(await page.locator('#group-name').inputValue(), '账号甲的未提交草稿');
    await owner.context.request.post(origin + '/api/v1/auth/logout', { data: {} });
    await submit(page).click();
    await heading(page, '欢迎回来');
    assert.match(await page.locator('.auth-note').textContent(), /未提交的输入已清空/);
    await page.locator('#username').fill('ui_group_outside');
    await page.locator('#password').fill(password);
    await submit(page).click();
    await heading(page, '我的小组'); await ready(page);
    assert.equal(await page.locator('#group-name').inputValue(), '');
    assert.equal(await page.locator('.group-card').count(), 0);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    console.log('PASS T13 UI: empty/create/join, validation/focus, single POST, owner/member privacy, reset/copy/fallback, uncertain writes, stale reads, 404, pagination/read failure, dirty leave, expired session/new identity, plain text, widths.');
  } catch (error) {
    console.error('T13 failure', error, 'Page errors:', errors);
    for (const context of contexts) for (const page of context.pages()) if (await page.locator('main').count()) console.error('T13 diagnostic', page.url(), (await page.locator('main').innerText({ timeout: 1000 })).slice(0, 1600));
    throw error;
  } finally { for (const context of contexts) await context.close(); }
}
