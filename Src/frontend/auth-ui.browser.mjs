import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

export async function verifyAuthUI(browser, origin, { root, screenshots }) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const shot = async name => {
    if (!screenshots) return;
    const directory = resolve(root, 'Docs/images/t10');
    await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, name + '.png'), fullPage: true });
  };
  const submit = () => page.locator('button[type="submit"]');
  const password = 'ui-test-password';
  const fill = async (username, registering = false) => {
    await page.locator('#username').fill(username);
    if (registering) await page.locator('#email').fill(username + '@example.com');
    await page.locator('#password').fill(password);
  };
  const heading = name => page.getByRole('heading', { name, exact: true }).waitFor();
  try {
    await page.goto(origin + '/polls/2/vote?secret=discard');
    await heading('欢迎回来');
    assert.equal(new URL(page.url()).searchParams.get('returnTo'), '/polls/2/vote');
    assert.equal(await page.getByRole('heading', { name: '填写空闲状态', exact: true }).count(), 0);
    await shot('03-login');
    await submit().click();
    await page.getByRole('alert').waitFor();
    assert.equal(await page.getByRole('alert').evaluate(element => element === document.activeElement), true);
    assert.equal(await page.locator('#username').getAttribute('aria-invalid'), 'true');
    await shot('04-validation');
    await page.locator('.auth-switch a').click();
    await heading('创建你的账号');
    await fill('ui_student', true);
    let registrations = 0;
    await page.route('**/api/v1/auth/register', async route => {
      registrations++;
      await new Promise(done => setTimeout(done, 600));
      await route.continue();
    });
    await submit().click();
    await page.waitForFunction(() => document.querySelector('fieldset')?.disabled);
    await heading('欢迎回来');
    assert.equal(registrations, 1);
    assert.match(await page.locator('.auth-note').textContent(), /注册成功/);
    assert.equal(await page.locator('#username').inputValue(), 'ui_student');
    assert.equal(await page.locator('#password').inputValue(), '');
    assert.equal((await context.request.get(origin + '/api/v1/users/me')).status(), 401);
    await page.unroute('**/api/v1/auth/register');
    await page.locator('#password').fill('wrong-password');
    await submit().click();
    await page.getByText('账号或密码错误，请重试。', { exact: true }).waitFor();
    assert.equal(await page.locator('#password').inputValue(), 'wrong-password');
    await page.getByRole('button', { name: '显示密码', exact: true }).click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    const toggle = page.getByRole('button', { name: '隐藏密码', exact: true });
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
    assert.equal(await toggle.locator('svg[aria-hidden="true"]').count(), 1);
    assert.equal((await toggle.textContent()).trim(), '');
    await toggle.focus();
    await page.keyboard.press('Space');
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    assert.equal(await page.locator('#password').inputValue(), 'wrong-password');
    assert.equal(await page.getByRole('button', { name: '显示密码', exact: true }).getAttribute('aria-controls'), 'password');
    await page.locator('#password').fill(password);
    await submit().click();
    await page.waitForURL(origin + '/polls/2/vote');
    await page.reload();
    await page.getByRole('button', { name: '退出登录', exact: true }).waitFor();
    assert.match(await page.locator('header').textContent(), /ui_student/);
    await shot('05-authenticated');
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await heading('欢迎回来');
    assert.equal((await context.request.get(origin + '/api/v1/users/me')).status(), 401);
    await page.goto(origin + '/login?returnTo=https://evil.example/');
    await fill('ui_student');
    await submit().click();
    await page.waitForURL(origin + '/groups');
    // Revocation by another tab must be recognized before entering a protected page.
    await context.request.post(origin + '/api/v1/auth/logout', { data: {} });
    await page.locator('aside a[href="/tasks/mine"]').click();
    await heading('欢迎回来');
    assert.match(await page.locator('.auth-note').textContent(), /过期/);
    // A failed session read is a recovery page, not a successful anonymous check.
    await page.route('**/api/v1/users/me', route => route.abort());
    await page.goto(origin + '/groups');
    await page.getByRole('button', { name: '重新检查', exact: true }).waitFor();
    await shot('06-session-recovery');
    await page.unroute('**/api/v1/users/me');
    await page.getByRole('button', { name: '重新检查', exact: true }).click();
    await heading('欢迎回来');
    // The server commits login, but its response is damaged. Reconcile using GET; no POST retry.
    let logins = 0;
    await page.route('**/api/v1/auth/login', async route => {
      logins++;
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    await fill('ui_student');
    await submit().click();
    await page.waitForURL(origin + '/groups');
    assert.equal(logins, 1);
    await page.unroute('**/api/v1/auth/login');
    // An uncertain logout that did commit can be confirmed by a session read.
    await page.route('**/api/v1/auth/logout', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await heading('欢迎回来');
    await page.unroute('**/api/v1/auth/logout');
    await page.locator('.auth-switch a').click();
    await heading('创建你的账号');
    await page.route('**/api/v1/auth/register', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, body: '{damaged' });
    });
    await fill('ui_member', true);
    await submit().click();
    await page.getByRole('button', { name: '去登录核对', exact: true }).waitFor();
    assert.equal(await submit().isDisabled(), true);
    await page.locator('#email').fill('changed@example.com');
    assert.equal(await page.getByRole('button', { name: '去登录核对', exact: true }).isVisible(), true);
    await page.getByRole('button', { name: '去登录核对', exact: true }).click();
    await heading('欢迎回来');
    assert.equal(await page.locator('#password').inputValue(), '');
    await page.unroute('**/api/v1/auth/register');
    // Leave confirmation preserves input on cancel and clears it on acceptance.
    await page.locator('#password').fill(password);
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('.auth-switch a').click();
    assert.equal(await page.locator('#password').inputValue(), password);
    page.once('dialog', dialog => dialog.accept());
    await page.locator('.auth-switch a').click();
    await heading('创建你的账号');
    assert.equal(await page.locator('#password').inputValue(), '');
    for (const width of [1280, 800, 400]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Auth overflow ${width}`);
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await shot('07-register');
    await fill('ui_member', true);
    await submit().click();
    await page.getByText('用户名或邮箱已被使用。', { exact: true }).waitFor();
    assert.equal(await page.locator('#password').inputValue(), password);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.deepEqual(errors, []);
    console.log('PASS T10 UI: guards, registration/no auto-login, validation/focus, single submission, wrong login, reload, safe return, expiry, offline recovery, uncertain writes, leave confirmation, 3 widths, no browser storage.');
  } finally { await context.close(); }
}
