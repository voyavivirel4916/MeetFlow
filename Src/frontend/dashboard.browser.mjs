import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyDashboard(browser,origin,{root}){
 const contexts=[],errors=[];
 async function post(actor,path,data){const r=await actor.context.request.post(origin+'/api/v1/'+path,{data});assert.ok(r.ok(),`${path} ${await r.text()}`);return(await r.json()).data}
 async function actor(username){const context=await browser.newContext({viewport:{width:1440,height:1000}});contexts.push(context);const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));const a={context,page};a.id=(await post(a,'auth/register',{username,email:username+'@example.com',password:'DashboardDemo123!'})).id;await post(a,'auth/login',{username,password:'DashboardDemo123!'});return a}
 const ready=p=>p.waitForFunction(()=>document.querySelector('[data-count="tasks"]')&&!document.querySelector('.dashboard-heading button')?.disabled);
 try{
  const owner=await actor('dashboard_owner'),member=await actor('dashboard_member'),outsider=await actor('dashboard_outside');
  const group=await post(owner,'groups',{name:'软件工程课程小组'});await post(member,'groups/join',{invite_code:group.invite_code});
  const now=Date.now();const draft=title=>({title,response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'}],slots:[{start_at:new Date(now+7200000).toISOString(),end_at:new Date(now+10800000).toISOString()}]});
  const pending=await post(owner,`groups/${group.id}/polls`,draft('第二版需求讨论'));await post(owner,`polls/${pending.id}/open`,{});
  const confirmed=await post(owner,`groups/${group.id}/polls`,draft('阶段汇报准备'));for(const a of ['open','close'])await post(owner,`polls/${confirmed.id}/${a}`,{});
  const meeting=await post(owner,`polls/${confirmed.id}/confirm`,{slot_id:confirmed.slots[0].id,acknowledged:true,selection_reason:'用于工作台验证'});
  for(const title of ['完善接口说明','准备汇报材料'])await post(owner,`meetings/${meeting.id}/tasks`,{title,assignee_id:owner.id,due_at:new Date(now+86400000).toISOString(),client_request_id:crypto.randomUUID()});
  const page=owner.page;await page.goto(origin+'/');await page.waitForURL('**/dashboard');await ready(page);
  assert.equal(await page.locator('[data-count="polls"]').innerText(),'1');assert.equal(await page.locator('[data-count="meetings"]').innerText(),'1');assert.equal(await page.locator('[data-count="tasks"]').innerText(),'2');
  await page.locator('[data-pending-poll]').getByRole('link',{name:'填写时间',exact:true}).click();await page.waitForURL(`**/polls/${pending.id}/vote`);
  await page.locator('aside nav a[href="/dashboard"]').click();await ready(page);
  const folder=resolve(root,'Docs/images/v2-13');await mkdir(folder,{recursive:true});
  for(const width of [1440,975,390]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});await page.screenshot({path:resolve(folder,`dashboard-${width}.png`),fullPage:true})}
  await page.getByRole('checkbox',{name:'完成：完善接口说明',exact:true}).click();await ready(page);await page.locator('[data-count="tasks"]').filter({hasText:'1'}).waitFor();assert.equal(await page.locator('.success-note').count(),0);
  const savedTask=await page.locator('[data-dashboard-task]').innerText();
  const fail=route=>route.fulfill({status:503,contentType:'application/json',headers:{'X-Request-ID':'c07e357967c148068a4f9aa539c759e2'},body:JSON.stringify({error:{code:'STORAGE_UNAVAILABLE',message:'工作台暂不可读'},request_id:'c07e357967c148068a4f9aa539c759e2'})});
  await page.route('**/api/v1/dashboard',fail);await page.locator('.dashboard-heading button').click();await page.getByRole('heading',{name:'工作台暂时无法读取',exact:true}).waitFor();assert.equal(await page.locator('[data-dashboard-task]').innerText(),savedTask);assert.ok(await page.locator('[data-dashboard-task] button').isDisabled());
  await page.reload();await page.getByRole('heading',{name:'工作台暂时无法读取',exact:true}).waitFor();assert.equal(await page.locator('.dashboard-summary').count(),0);
  await page.unroute('**/api/v1/dashboard');await page.getByRole('button',{name:'重新读取工作台',exact:true}).click();await ready(page);
  await member.page.goto(origin+'/dashboard');await ready(member.page);assert.equal(await member.page.locator('[data-count="polls"]').innerText(),'0');assert.equal(await member.page.locator('[data-count="meetings"]').innerText(),'0');assert.equal(await member.page.locator('[data-dashboard-task]').count(),0);
  await outsider.page.goto(origin+'/dashboard');await ready(outsider.page);assert.equal(await outsider.page.locator('.dashboard-group').count(),0);
  assert.deepEqual(errors,[]);
  const evidence={date:new Date().toISOString(),browser:process.env.PROTOTYPE_BROWSER||'chrome',version:browser.version(),result:'passed',checks:['root-dashboard','real-snapshot-counts','vote-link','task-completion-refresh-no-banner','stale-read-preserved','initial-failure-no-fake-zero','nonparticipant-and-outside-scopes','three-viewports'],temporary_database:true,human_review:false};
  await mkdir(resolve(root,'Docs/evidence'),{recursive:true});await writeFile(resolve(root,`Docs/evidence/v2-13-${evidence.browser}.json`),JSON.stringify(evidence,null,2)+'\n');console.log('PASS V2-13 personal dashboard UI');
 }finally{for(const c of contexts)await c.close()}
}
