// T09 exercises real browser cookies against the API, without implementing T10 UI.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';

const cookieName = 'meetflow_session';
const credentials = { username: 'browser_student', password: ' browser password 123 ' };

async function api(page, path, body) {
  return page.evaluate(async ({ path, body }) => {
    const response = await fetch('/api/v1' + path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      headers: body === undefined ? { Accept: 'application/json' } : { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    return { status: response.status, body: await response.json(), canReadCookieHeader: response.headers.has('set-cookie') };
  }, { path, body });
}

export async function verifyAuth(browser, page, origin) {
  const context = page.context();
  const registration = await api(page, '/auth/register', { ...credentials, email: 'browser-student@example.com' });
  assert.equal(registration.status, 201);
  assert.equal((await api(page, '/users/me')).status, 401);
  const duplicate = await api(page, '/auth/register', { ...credentials, email: 'different@example.com' });
  assert.equal(duplicate.status, 409);
  const wrong = await api(page, '/auth/login', { ...credentials, password: 'incorrect' });
  assert.equal(wrong.status, 401);
  const loggedIn = await api(page, '/auth/login', credentials);
  assert.equal(loggedIn.status, 200);
  assert.equal(loggedIn.canReadCookieHeader, false);
  const cookies = await context.cookies(origin);
  const session = cookies.find(cookie => cookie.name === cookieName);
  assert.ok(session);
  assert.equal(session.httpOnly, true);
  assert.equal(session.sameSite, 'Strict');
  assert.equal(session.path, '/');
  assert.equal(session.secure, false);
  assert.ok(Math.abs(session.expires - Date.now() / 1000 - 28800) < 60);
  assert.equal(await page.evaluate(() => document.cookie), '');
  assert.ok(!JSON.stringify(loggedIn.body).includes(session.value));
  assert.equal((await api(page, '/users/me')).body.data.id, registration.body.data.id);
  await page.reload();
  assert.equal((await api(page, '/users/me')).status, 200);

  // Different local ports are same-site; Origin protection must still stop this form.
  const hostile = createServer((_request, response) => response.writeHead(200, { 'Content-Type': 'text/html' })
    .end(`<form method="post" action="${origin}/api/v1/auth/logout"><button>attempt logout</button></form>`));
  await new Promise(done => hostile.listen(0, '127.0.0.1', done));
  const hostilePage = await context.newPage();
  try {
    await hostilePage.goto(`http://127.0.0.1:${hostile.address().port}/`);
    await Promise.all([
      hostilePage.waitForURL(origin + '/api/v1/auth/logout'),
      hostilePage.getByRole('button', { name: 'attempt logout' }).click(),
    ]);
    assert.match(await hostilePage.locator('body').innerText(), /CSRF_REJECTED/);
    assert.equal((await api(page, '/users/me')).status, 200);
  } finally {
    await hostilePage.close();
    await new Promise(done => hostile.close(done));
  }

  const independent = await browser.newContext();
  try {
    const second = await independent.newPage();
    await second.goto(origin + '/login');
    assert.equal((await api(second, '/users/me')).status, 401);
    assert.equal((await api(second, '/auth/login', credentials)).status, 200);
    assert.equal((await api(page, '/auth/logout', {})).status, 200);
    assert.equal((await api(page, '/users/me')).status, 401);
    assert.equal((await context.cookies(origin)).some(cookie => cookie.name === cookieName), false);
    assert.equal((await api(second, '/users/me')).status, 200);

    const replay = await context.request.get(origin + '/api/v1/users/me', { headers: { Cookie: `${cookieName}=${session.value}` } });
    assert.equal(replay.status(), 401);
    const repeat = await context.request.post(origin + '/api/v1/auth/logout', {
      headers: { Cookie: `${cookieName}=${session.value}`, 'Content-Type': 'application/json' }, data: {},
    });
    assert.equal(repeat.status(), 200);
  } finally { await independent.close(); }
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  console.log('PASS T09: real registration/login/logout, HttpOnly+Strict cookie, no token in JS/body, page refresh, same-site cross-origin form blocked, independent browser sessions and revoked-cookie replay.');
}
