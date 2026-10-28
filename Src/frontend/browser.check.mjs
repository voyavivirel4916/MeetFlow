// Isolated development proxy or built same-origin delivery; never uses developer data.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, rename, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createNetServer } from 'node:net';
import { createServer, loadConfigFromFile } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const acceptanceFlags=['--auth-ui','--groups-ui','--poll-editor','--votes-ui','--matrix-ui','--recommendations-ui','--confirmation-ui','--meeting-ui','--tasks-ui'];
if(process.argv.includes('--acceptance'))process.argv.push(...acceptanceFlags);
const startedAt=new Date().toISOString(),startedClock=performance.now();
const built = process.argv.includes('--built');
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const temp = await mkdtemp(resolve(tmpdir(), 'meetflow-t06-'));
const portProbe = createNetServer();
await new Promise(done => portProbe.listen(0, '127.0.0.1', done));
const port = portProbe.address().port;
await new Promise(done => portProbe.close(done));
const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('MEETFLOW_')));
Object.assign(env, { MEETFLOW_APP_ENV: 'test', MEETFLOW_PORT: String(port), MEETFLOW_DATA_DIR: temp,
  MEETFLOW_FRONTEND_DIR: resolve(here, 'dist') });
const python = process.env.MEETFLOW_TEST_PYTHON || resolve(root, 'Src/backend/.venv/Scripts/python.exe');
const backendOptions = { cwd: resolve(root, 'Src/backend'), env, windowsHide: true };
let logs = '', spawnError;
let backend, server, browser;
try {
  const migration = spawnSync(python, ['-m', 'app.db.migrate'], { ...backendOptions, encoding: 'utf8', timeout: 15000 });
  assert.equal(migration.status, 0, migration.stderr || String(migration.error));
  backend = spawn(python, ['-m', 'app'], { ...backendOptions, stdio: 'pipe' });
  backend.stdout.on('data', chunk => logs += chunk);
  backend.stderr.on('data', chunk => logs += chunk);
  backend.on('error', error => spawnError = error);
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (spawnError) throw spawnError;
    if (backend.exitCode !== null) throw new Error(`Backend exited: ${logs}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/livez`, { signal: AbortSignal.timeout(500) });
      if (response.ok) { ready = true; break; }
    } catch { /* Await startup, bounded below. */ }
    await new Promise(done => setTimeout(done, 100));
  }
  assert.ok(ready, `Backend startup timed out: ${logs}`);
  const target = `http://127.0.0.1:${port}`;
  let origin = target;
  if (!built) {
    const frontendProbe = createNetServer();
    await new Promise(done => frontendProbe.listen(0, '127.0.0.1', done));
    const frontendPort = frontendProbe.address().port;
    await new Promise(done => frontendProbe.close(done));
    const loaded = await loadConfigFromFile({ command: 'serve', mode: 'development' }, resolve(here, 'vite.config.ts'));
    const proxyFor = key => {
      const rule = loaded.config.server.proxy[key];
      return typeof rule === 'string' ? target : { ...rule, target };
    };
    server = await createServer({ configFile: resolve(here, 'vite.config.ts'), root: here,
      server: { host: '127.0.0.1', port: frontendPort, proxy: {
        '/api': proxyFor('/api'), '/livez': proxyFor('/livez'),
      } } });
    await server.listen();
    origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  }
  browser = await chromium.launch({ channel: process.env.PROTOTYPE_BROWSER || 'chrome', headless: true });
  console.log(`Browser: ${process.env.PROTOTYPE_BROWSER||'chrome'} ${browser.version()}; platform ${process.platform}/${process.arch}`);
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const bootstrap = { username: 'bootstrap_user', password: 'bootstrap-only-password' };
  assert.equal((await context.request.post(origin + '/api/v1/auth/register', { data: { ...bootstrap, email: 'bootstrap@example.com' } })).status(), 201);
  assert.equal((await context.request.post(origin + '/api/v1/auth/login', { data: bootstrap })).status(), 200);
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await page.goto(origin + '/');
  await page.getByRole('heading', { name: '工作台', exact: true, level:1 }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/dashboard');
  await page.locator('[data-count="tasks"]').waitFor();
  assert.equal(await page.locator('[data-count="tasks"]').innerText(),'0');
  for (const [path, title] of [
    ['/groups/1', '小组空间'], ['/groups/1/polls/new', '发起排期'], ['/polls/1/edit', '编辑排期'],
    ['/polls/1/vote', '填写时间'], ['/polls/1/results', '排期结果'], ['/meetings/1', '会议与行动'],
    ['/tasks/mine', '我的任务'],
    ['/groups/0', '找不到这个页面'], ['/missing', '找不到这个页面'],
  ]) {
    await page.goto(origin + path);
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(await page.title(), `${title} · MeetFlow`);
  }
  assert.ok(requests.filter(url => new URL(url).pathname.startsWith('/api/')).every(url =>
    /^\/api\/v1\/(users\/me|dashboard|groups(?:\/1(?:\/members|\/polls|\/tasks)?)?|polls\/1(?:\/matrix)?|meetings\/1|tasks\/mine)$/.test(new URL(url).pathname)));
  await page.goto(origin + '/polls/1/results');
  await page.reload();
  await page.getByRole('heading', { name: '排期结果', exact: true }).waitFor();
  await page.goto(origin + '/connection');
  await page.getByRole('button', { name: '检查连接' }).click();
  await page.getByRole('heading', { name: '连接成功' }).waitFor();
  assert.match(await page.getByRole('status').textContent(), /请求编号：[0-9a-f]{32}/);
  const api = await page.request.get(origin + '/api/v1/not-implemented');
  assert.equal(api.status(), 404);
  assert.equal((await api.json()).error.code, 'NOT_FOUND');
  if (built) {
    const missingAsset = await page.request.get(origin + '/assets/no-such-file.js');
    assert.equal(missingAsset.status(), 404);
    assert.ok(!(missingAsset.headers()['content-type'] || '').includes('text/html'));
  }
  const screenshot = async name => {
    if (!process.argv.includes('--screenshots')) return;
    const dir = resolve(root, process.argv.includes('--tasks-ui') ? 'Docs/images/t29' : process.argv.includes('--meeting-ui') ? 'Docs/images/t27' : process.argv.includes('--confirmation-ui') ? 'Docs/images/t25' : process.argv.includes('--recommendations-ui') ? 'Docs/images/t23' : process.argv.includes('--matrix-ui') ? 'Docs/images/t20' : process.argv.includes('--votes-ui') ? 'Docs/images/t18' : process.argv.includes('--poll-editor') ? 'Docs/images/t16' : process.argv.includes('--groups-ui') ? 'Docs/images/t13' : process.argv.includes('--auth-ui') ? 'Docs/images/t10' : built ? 'Docs/images/t08' : 'Docs/images/t06');
    await mkdir(dir, { recursive: true });
    await page.screenshot({ path: resolve(dir, name + '.png'), fullPage: true });
  };
  await screenshot('01-connection');
  // A delayed response must disable the button and suppress duplicate submissions.
  let calls = 0;
  await page.route('**/api/v1/health', async route => {
    calls++;
    await new Promise(done => setTimeout(done, 350));
    await route.continue();
  });
  await page.getByRole('button', { name: '检查连接' }).click();
  assert.equal(await page.getByRole('button', { name: '正在检查…' }).isDisabled(), true);
  await page.getByRole('heading', { name: '连接成功' }).waitFor();
  assert.equal(calls, 1);
  await page.unroute('**/api/v1/health');
  // Move only this test's own database, verify live 503, then restore it.
  const database = resolve(temp, 'meetflow.sqlite3');
  const saved = resolve(temp, 'preserved.sqlite3');
  await rename(database, saved);
  try {
    const health = await page.request.get(origin + '/api/v1/health');
    assert.equal(health.status(), 503);
    assert.equal((await health.json()).error.code, 'STORAGE_UNAVAILABLE');
    assert.equal((await page.request.get(origin + '/livez')).status(), 200);
    await page.getByRole('button', { name: '检查连接' }).click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').textContent(), /本机存储暂时不可用/);
    await screenshot('02-storage-unavailable');
  } finally { await rename(saved, database); }
  await page.getByRole('button', { name: '检查连接' }).click();
  await page.getByRole('heading', { name: '连接成功' }).waitFor();
  await page.route('**/api/v1/health', route => route.abort('connectionrefused'));
  await page.getByRole('button', { name: '检查连接' }).click();
  await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').textContent(), /暂时无法连接服务/);
  assert.equal(await page.getByRole('button', { name: '检查连接' }).isEnabled(), true);
  for (const width of [1440, 1024, 900, 800, 640, 400]) {
    await page.setViewportSize({ width, height: 900 });
    const box = await page.evaluate(() => {
      const aside = document.querySelector('aside').getBoundingClientRect();
      const content = document.querySelector('main').getBoundingClientRect();
      return { noScroll: document.documentElement.scrollWidth <= innerWidth,
        noOverlap: content.left >= aside.right - 1 || content.top >= aside.bottom - 1 };
    });
    assert.ok(box.noScroll && box.noOverlap, `Overlap/overflow at ${width}px`);
    if (width === 800) await screenshot('02-error-800');
  }
  await page.goto(origin + '/groups');
  await page.getByRole('heading', { name: '我的小组', exact: true }).waitFor();
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.textContent), '跳到主要内容');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'content');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.ok(requests.every(url => new URL(url).hostname === '127.0.0.1'));
  if (built) assert.ok(requests.every(url => new URL(url).origin === origin), 'Built UI must use one origin');
  assert.deepEqual(errors, []);
  if (process.argv.includes('--auth')) {
    await context.request.post(origin + '/api/v1/auth/logout', { data: {} });
    await page.goto(origin + '/connection');
    const { verifyAuth } = await import('./auth.browser.mjs');
    await verifyAuth(browser, page, origin);
  }
  if (process.argv.includes('--auth-ui')) {
    const { verifyAuthUI } = await import('./auth-ui.browser.mjs');
    await verifyAuthUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--groups')) {
    const { verifyGroups } = await import('./groups.browser.mjs');
    await verifyGroups(browser, origin);
  }
  if (process.argv.includes('--groups-ui')) {
    const { verifyGroupsUI } = await import('./groups-ui.browser.mjs');
    await verifyGroupsUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--polls')) {
    const { verifyPolls } = await import('./polls.browser.mjs');
    await verifyPolls(browser, origin);
  }
  if (process.argv.includes('--poll-editor')) {
    const { verifyPollEditor } = await import('./poll-editor.browser.mjs');
    await verifyPollEditor(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--votes-ui')) {
    const { verifyVotesUI } = await import('./votes-ui.browser.mjs');
    await verifyVotesUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--matrix-ui')) {
    const { verifyMatrixUI } = await import('./matrix-ui.browser.mjs');
    await verifyMatrixUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--e2e')) {
    const { verifyE2E } = await import('./e2e.browser.mjs');
    await verifyE2E(browser, origin, {root});
  }
  if (process.argv.includes('--poll-lifecycle')) {
    const {verifyPollLifecycle}=await import('./poll-lifecycle.browser.mjs');
    await verifyPollLifecycle(browser,origin,{root});
  }
  if(process.argv.includes('--task-updates')){
    const {verifyTaskUpdates}=await import('./task-updates.browser.mjs');
    await verifyTaskUpdates(browser,origin,{root});
  }
  if(process.argv.includes('--search-theme')){
    const {verifySearchTheme}=await import('./search-theme.browser.mjs');
    await verifySearchTheme(browser,origin,{root});
  }
  if(process.argv.includes('--dashboard')){
    const {verifyDashboard}=await import('./dashboard.browser.mjs');
    await verifyDashboard(browser,origin,{root});
  }
  if (process.argv.includes('--tasks-ui')) {
    const { verifyTasksUI } = await import('./tasks-ui.browser.mjs');
    await verifyTasksUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--meeting-ui')) {
    const { verifyMeetingUI } = await import('./meeting-ui.browser.mjs');
    await verifyMeetingUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--confirmation-ui')) {
    const { verifyConfirmationUI } = await import('./confirmation-ui.browser.mjs');
    await verifyConfirmationUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  if (process.argv.includes('--recommendations-ui')) {
    const { verifyRecommendationsUI } = await import('./recommendations-ui.browser.mjs');
    await verifyRecommendationsUI(browser, origin, { root, screenshots: process.argv.includes('--screenshots') });
  }
  console.log(`PASS ${built ? 'T08 built same-origin' : 'T06 development proxy'}: direct routes/reload, real database health, live 503/recovery, structured 404, success/error/loading, no duplicate request, keyboard, 6 window widths, no external requests or local storage.`);
  if(process.argv.includes('--acceptance')){
    const folder=resolve(root,'Docs/evidence');await mkdir(folder,{recursive:true});
    await writeFile(resolve(folder,`${process.argv.includes('--search-theme')?'workflow-theme-acceptance':'t32'}-${process.env.PROTOTYPE_BROWSER||'chrome'}.json`),JSON.stringify({started_at:startedAt,finished_at:new Date().toISOString(),elapsed_seconds:(performance.now()-startedClock)/1000,browser:process.env.PROTOTYPE_BROWSER||'chrome',version:browser.version(),platform:process.platform,architecture:process.arch,node:process.version,mode:built?'built same-origin':'development proxy',suites:acceptanceFlags,result:'passed',database:'isolated temporary database; removed after run',human_review:false},null,2)+'\n');
  }
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  if (backend && backend.exitCode === null && !spawnError) {
    const closed = new Promise(done => backend.once('close', done));
    backend.kill();
    await closed;
  }
  // Only remove the exact temporary directory created by this check.
  assert.equal(dirname(temp), resolve(tmpdir()));
  assert.ok(basename(temp).startsWith('meetflow-t06-'));
  await rm(temp, { recursive: true });
}
