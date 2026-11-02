const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const folder = path.join(root, 'Presentation/assets');
fs.mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const origin = 'http://localhost:8002';
  try {
    await page.goto(origin + '/login');
    await page.getByLabel('用户名', { exact: true }).fill('demo_owner');
    await page.getByLabel('密码', { exact: true }).fill('MeetFlowDemo2026!');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.waitForURL(origin + '/dashboard');
    await page.locator('[data-count="tasks"]').waitFor();
    await page.screenshot({ path: path.join(folder, 'dashboard.png') });
    await page.goto(origin + '/polls/1/results');
    await page.locator('.matrix-card tbody tr').first().waitFor();
    await page.locator('.matrix-card').screenshot({ path: path.join(folder, 'matrix.png') });
    await page.goto(origin + '/polls/3/results');
    await page.locator('.recommendations-section').waitFor();
    await page.locator('.recommendations-section').screenshot({ path: path.join(folder, 'required-risk.png') });
    assert.equal((await context.request.get(origin + '/api/v1/health')).status(), 200);
    console.log('Captured real, read-only showcase pages on localhost:8002.');
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
