import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyPollLifecycle(browser,origin,{root}){
 const contexts=[],errors=[];
 const call=async(actor,path,data)=>{
  const response=await actor.context.request.post(origin+'/api/v1/'+path,{data});
  assert.ok(response.ok(),`${path}: ${response.status()} ${await response.text()}`);
  return (await response.json()).data;
 };
 const actor=async username=>{
  const context=await browser.newContext({viewport:{width:1280,height:1000}});contexts.push(context);
  const a={context,page:await context.newPage()};a.page.on('pageerror',e=>errors.push(e.message));
  a.id=(await call(a,'auth/register',{username,email:username+'@example.com',password:'LifecycleDemo123!'})).id;
  await call(a,'auth/login',{username,password:'LifecycleDemo123!'});return a;
 };
 const ready=page=>page.waitForFunction(()=>document.querySelector('.poll-list-card')&&!document.querySelector('.poll-list-card .refresh-icon')?.disabled);
 const confirm=async page=>{await page.locator('.poll-organize-dialog button').filter({hasText:'确认'}).click();await page.locator('.poll-organize-dialog').waitFor({state:'hidden'});await ready(page)};
 try{
  const owner=await actor('lifecycle_owner'),member=await actor('lifecycle_member');
  const group=await call(owner,'groups',{name:'第二版排期管理',description:'用于排期整理与恢复验证'});
  await call(member,'groups/join',{invite_code:group.invite_code});
  const now=Date.now();const draft=title=>({title,response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'}],slots:[{start_at:new Date(now+7200000).toISOString(),end_at:new Date(now+10800000).toISOString()}]});
  const first=await call(owner,`groups/${group.id}/polls`,draft('可删除的旧草稿'));
  const confirmed=await call(owner,`groups/${group.id}/polls`,draft('已确认的阶段会议'));
  await call(owner,`polls/${confirmed.id}/open`,{});await call(owner,`polls/${confirmed.id}/close`,{});
  const meeting=await call(owner,`polls/${confirmed.id}/confirm`,{slot_id:confirmed.slots[0].id,acknowledged:true,selection_reason:'验证归档保留会议'});
  const opened=await call(owner,`groups/${group.id}/polls`,draft('仍在收集的排期'));await call(owner,`polls/${opened.id}/open`,{});
  const page=owner.page;await page.goto(origin+`/groups/${group.id}`);await ready(page);
  const row=id=>page.locator(`[data-poll="${id}"]`);
  await row(first.id).getByRole('button',{name:'删除',exact:true}).click();await page.locator('.poll-organize-dialog').getByRole('button',{name:'返回',exact:true}).click();
  assert.equal(await row(first.id).count(),1);
  await row(first.id).getByRole('button',{name:'删除',exact:true}).click();await confirm(page);await row(first.id).waitFor({state:'detached'});
  await page.locator('.poll-view-tabs').getByRole('button',{name:'回收站',exact:true}).click();await ready(page);
  assert.equal(await row(first.id).locator('a').count(),0);
  await row(first.id).getByRole('button',{name:'恢复',exact:true}).click();await confirm(page);
  await page.locator('.poll-view-tabs').getByRole('button',{name:'当前',exact:true}).click();await ready(page);
  await row(confirmed.id).getByRole('button',{name:'归档',exact:true}).click();await confirm(page);
  await page.locator('.poll-view-tabs').getByRole('button',{name:'历史',exact:true}).click();await ready(page);
  assert.equal(await row(confirmed.id).count(),1);
  assert.ok((await member.context.request.get(origin+`/api/v1/meetings/${meeting.id}`)).ok());
  await row(confirmed.id).getByRole('button',{name:'取消归档',exact:true}).click();await confirm(page);
  await page.locator('.poll-view-tabs').getByRole('button',{name:'当前',exact:true}).click();await ready(page);
  // Commit succeeds but response is lost: no automatic write retry; reconcile by read.
  let writes=0;
  await page.route(`**/api/v1/polls/${first.id}/delete`,async route=>{writes++;await route.fetch();await route.abort('failed')});
  await row(first.id).getByRole('button',{name:'删除',exact:true}).click();await page.locator('.poll-organize-dialog button').filter({hasText:'确认'}).click();
  await page.getByRole('heading',{name:'请核对排期状态',exact:true}).waitFor();
  assert.equal(writes,1);assert.ok(await row(first.id).getByRole('button',{name:'删除',exact:true}).isDisabled());
  await page.getByRole('button',{name:'核对最新排期',exact:true}).click();await ready(page);await row(first.id).waitFor({state:'detached'});assert.equal(writes,1);
  await page.unroute(`**/api/v1/polls/${first.id}/delete`);
  await row(opened.id).getByRole('button',{name:'取消排期',exact:true}).click();await confirm(page);
  assert.ok(await row(opened.id).getByRole('button',{name:'删除',exact:true}).isVisible());
  const folder=resolve(root,'Docs/images/v2-08');await mkdir(folder,{recursive:true});
  for(const width of [1440,975,390]){
   await page.setViewportSize({width,height:900});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);
   const boxes=await page.locator('.poll-list>li').evaluateAll(rows=>rows.map(r=>({status:r.querySelector('.role-badge').getBoundingClientRect().x,action:r.querySelector('.poll-row-actions').getBoundingClientRect().x})));
   for(const box of boxes){assert.ok(Math.abs(box.status-boxes[0].status)<1);assert.ok(Math.abs(box.action-boxes[0].action)<1)}
   await page.screenshot({path:resolve(folder,`current-${width}.png`),fullPage:true});
  }
  await member.page.goto(origin+`/groups/${group.id}`);await ready(member.page);
  assert.equal(await member.page.locator('.poll-row-actions').count(),0);
  assert.equal(await member.page.locator('.poll-view-tabs').getByRole('button',{name:'回收站',exact:true}).count(),0);
  assert.deepEqual(errors,[]);
  const evidence={date:new Date().toISOString(),browser:process.env.PROTOTYPE_BROWSER||'chrome',version:browser.version(),result:'passed',temporary_database:true,human_review:false,checks:['delete-return-restore','archive-unarchive','meeting-preserved','lost-response-reconciliation','cancel-before-delete','member-management-hidden','three-viewports-column-alignment']};
  await mkdir(resolve(root,'Docs/evidence'),{recursive:true});await writeFile(resolve(root,`Docs/evidence/v2-08-${evidence.browser}.json`),JSON.stringify(evidence,null,2)+'\n');
  console.log('PASS V2-08 poll organization UI');
 }finally{for(const context of contexts)await context.close()}
}
