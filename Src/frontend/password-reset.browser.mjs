import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

export async function verifyPasswordReset(browser,origin,{root,issueReset}){
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const folder=resolve(root,'Docs/images/password-reset');await mkdir(folder,{recursive:true});
 try{
  const old='PreviousPassword123!',fresh='ChangedPassword123!';
  assert.equal((await context.request.post(origin+'/api/v1/auth/register',{data:{username:'reset_browser',email:'reset_browser@example.com',password:old}})).status(),201);
  assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username:'reset_browser',password:old}})).status(),200);
  await page.goto(origin+'/forgot-password');await page.getByRole('button',{name:'发送重置邮件',exact:true}).click();await page.getByRole('alert').waitFor();
  await page.getByLabel('注册邮箱',{exact:true}).fill('reset_browser@example.com');await page.getByRole('button',{name:'发送重置邮件',exact:true}).click();await page.getByText('密码找回暂未开放，请联系小组负责人。',{exact:true}).waitFor();
  assert.equal(await page.getByText('结果未确认，请先检查邮件，稍后再申请。',{exact:true}).count(),0);
  for(const width of [1440,390]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:resolve(folder,`request-${width}.png`),fullPage:true});}
  await page.goto(origin+'/reset-password');await page.getByText('重置链接无效，请从邮件打开完整链接，或重新申请。',{exact:true}).waitFor();assert.equal(await page.locator('form').count(),0);
  const token=issueReset('reset_browser@example.com');await page.goto(origin+'/reset-password#token='+token);await page.getByLabel('新密码',{exact:true}).waitFor();assert.equal(new URL(page.url()).hash,'');
  assert.equal(await page.locator('body').innerText().then(s=>s.includes(token)),false);
  await page.getByLabel('新密码',{exact:true}).fill(fresh);await page.getByLabel('确认新密码',{exact:true}).fill('not-matching');await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.getByText('两次输入的密码不一致。',{exact:true}).waitFor();
  await page.getByLabel('确认新密码',{exact:true}).fill(fresh);await page.getByRole('button',{name:'显示密码',exact:true}).click();assert.equal(await page.getByLabel('新密码',{exact:true}).getAttribute('type'),'text');await page.getByRole('button',{name:'隐藏密码',exact:true}).click();
  for(const width of [1440,390]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:resolve(folder,`confirm-${width}.png`),fullPage:true});}
  let writes=0;await page.route('**/api/v1/auth/password-reset/confirm',async route=>{writes++;await route.continue();});
  await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.getByRole('status').filter({hasText:'密码已重置，请重新登录。'}).waitFor();assert.equal(writes,1);
  assert.equal((await context.request.get(origin+'/api/v1/users/me')).status(),401);
  assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username:'reset_browser',password:fresh}})).status(),200);
  await page.goto(origin+'/reset-password#token='+token);await page.getByLabel('新密码',{exact:true}).fill(fresh);await page.getByLabel('确认新密码',{exact:true}).fill(fresh);await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.getByRole('alert').filter({hasText:'重置链接无效或已过期'}).waitFor();
  await context.request.post(origin+'/api/v1/auth/register',{data:{username:'reset_lost',email:'reset_lost@example.com',password:old}});
  const lostToken=issueReset('reset_lost@example.com');await page.goto(origin+'/reset-password#token='+lostToken);
  await page.getByLabel('新密码',{exact:true}).fill(fresh);await page.getByLabel('确认新密码',{exact:true}).fill(fresh);
  await page.unroute('**/api/v1/auth/password-reset/confirm');
  await page.route('**/api/v1/auth/password-reset/confirm',async route=>{await route.fetch();await route.abort('failed')});
  await page.getByRole('button',{name:'保存新密码',exact:true}).click();await page.getByText('结果未确认，可先用新密码登录核对；仍失败时重新申请链接。',{exact:true}).waitFor();
  assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username:'reset_lost',password:fresh}})).status(),200);
  assert.deepEqual(errors,[]);
  const evidence={date:new Date().toISOString(),browser:process.env.PROTOTYPE_BROWSER||'chrome',result:'passed',temporary_database:true,real_email_sent:false,checks:['mail-disabled-truthful','field-validation','missing-link','fragment-removed','secret-not-rendered','eye-toggle','real-one-use-reset','old-session-revoked','new-password-login','reused-link-rejected','lost-response-no-false-success','1440-and-390-no-overflow']};
  await writeFile(resolve(root,`Docs/evidence/password-reset-${evidence.browser}.json`),JSON.stringify(evidence,null,2)+'\n');
  console.log('PASS password reset pages: real temporary token, one-use reset, session revocation, disabled email and two widths');
 }finally{await context.close();}
}
