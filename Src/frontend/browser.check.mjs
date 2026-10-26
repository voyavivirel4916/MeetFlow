// Isolated development proxy or built same-origin delivery; never uses developer data.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, rename, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createNetServer } from 'node:net';
import { createServer } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
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
    server = await createServer({ configFile: resolve(here, 'vite.config.ts'), root: here,
      server: { host: '127.0.0.1', port: frontendPort, proxy: { '/api': target, '/livez': target } } });
    await server.listen();
    origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  }
  browser = await chromium.launch({ channel: process.env.PROTOTYPE_BROWSER || 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await page.goto(origin + '/');
  await page.getByRole('heading', { name: '我的小组', exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, '/groups');
  assert.equal(await page.getByRole('status').count(), 1);
  for (const [path, title] of [
    ['/groups/1', '小组空间'], ['/groups/1/polls/new', '发起排期'], ['/polls/1/edit', '编辑排期'],
    ['/polls/1/vote', '填写时间'], ['/polls/1/results', '排期结果'], ['/meetings/1', '会议与行动'],
    ['/tasks/mine', '我的待办'], ['/login', '登录'], ['/register', '注册'],
    ['/groups/0', '找不到这个页面'], ['/missing', '找不到这个页面'],
  ]) {
    await page.goto(origin + path);
    await page.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(await page.title(), `${title} · MeetFlow`);
  }
  assert.equal(requests.filter(url => new URL(url).pathname.startsWith('/api/')).length, 0);
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
    const dir = resolve(root, built ? 'Docs/images/t08' : 'Docs/images/t06');
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
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.textContent), '跳到主要内容');
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(() => document.activeElement.id), 'content');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.ok(requests.every(url => new URL(url).hostname === '127.0.0.1'));
  if (built) assert.ok(requests.every(url => new URL(url).origin === origin), 'Built UI must use one origin');
  assert.deepEqual(errors, []);
  console.log(`PASS ${built ? 'T08 built same-origin' : 'T06 development proxy'}: direct routes/reload, real database health, live 503/recovery, structured 404, success/error/loading, no duplicate request, keyboard, 6 window widths, no external requests or local storage.`);
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
