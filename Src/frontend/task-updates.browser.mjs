import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyTaskUpdates(browser,origin,{root}){
 const contexts=[],errors=[];
 const post=async(a,path,data)=>{const r=await a.context.request.post(origin+'/api/v1/'+path,{data});assert.ok(r.ok(),`${path} ${await r.text()}`);return(await r.json()).data};
 async function actor(username){const context=await browser.newContext({viewport:{width:1280,height:1000}});contexts.push(context);const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));const a={context,page};a.id=(await post(a,'auth/register',{username,email:username+'@example.com',password:'TaskUpdatesDemo123!'})).id;await post(a,'auth/login',{username,password:'TaskUpdatesDemo123!'});return a}
 const ready=p=>p.waitForFunction(()=>document.querySelector('.task-panel')&&!document.querySelector('.task-panel .section-heading button')?.disabled);
 const row=(p,id)=>p.locator(`[data-task="${id}"]`);
 async function confirm(p){await p.locator('.task-action-dialog').getByRole('button',{name:'确认',exact:true}).click();await p.locator('.task-action-dialog').waitFor({state:'hidden'});await ready(p)}
 try{
  const owner=await actor('update_owner'),member=await actor('update_member'),observer=await actor('update_observer');
  const group=await post(owner,'groups',{name:'任务跟进小组'});for(const a of [member,observer])await post(a,'groups/join',{invite_code:group.invite_code});
  const now=Date.now();const poll=await post(owner,`groups/${group.id}/polls`,{title:'任务调整讨论',response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'}],slots:[{start_at:new Date(now+7200000).toISOString(),end_at:new Date(now+10800000).toISOString()}]});
  for(const a of ['open','close'])await post(owner,`polls/${poll.id}/${a}`,{});
  const meeting=await post(owner,`polls/${poll.id}/confirm`,{slot_id:poll.slots[0].id,acknowledged:true,selection_reason:'验证会后任务调整'});
  const task=await post(owner,`meetings/${meeting.id}/tasks`,{title:'完善接口说明',description:'核对错误场景',assignee_id:member.id,due_at:new Date(now+86400000).toISOString(),client_request_id:crypto.randomUUID()});
  await post(owner,`meetings/${meeting.id}/tasks`,{title:'整理汇报材料',description:'准备下一次小组汇报',assignee_id:owner.id,due_at:new Date(now+172800000).toISOString(),client_request_id:crypto.randomUUID()});
  const page=owner.page;await page.goto(origin+`/meetings/${meeting.id}`);await ready(page);
  await row(page,task.id).getByRole('button',{name:'编辑',exact:true}).click();
  const editFolder=resolve(root,'Docs/images/v2-11');await mkdir(editFolder,{recursive:true});
  for(const width of [1280,390]){
   await page.setViewportSize({width,height:900});
   const bounds=await page.locator('.task-edit-dialog').boundingBox();assert.ok(bounds&&bounds.x>=0&&bounds.x+bounds.width<=width);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.locator('.task-edit-dialog').screenshot({path:resolve(editFolder,`editor-${width}.png`)});
  }
  await page.setViewportSize({width:1280,height:1000});
  await page.locator('#edit-task-title').fill('更新后的接口说明');await page.locator('.task-edit-dialog').getByRole('button',{name:'保存修改',exact:true}).click();
  await page.locator('.task-edit-dialog').waitFor({state:'detached'});await ready(page);
  await row(page,task.id).getByRole('heading',{name:'更新后的接口说明',exact:true}).waitFor();
  await row(page,task.id).getByRole('button',{name:'取消',exact:true}).click();await confirm(page);
  assert.equal(await row(page,task.id).getByRole('checkbox').count(),0);
  await row(page,task.id).getByRole('button',{name:'恢复',exact:true}).click();await confirm(page);
  await member.page.goto(origin+'/tasks/mine');await ready(member.page);
  assert.equal(await row(member.page,task.id).getByRole('button',{name:'编辑',exact:true}).count(),0);
  await row(member.page,task.id).getByRole('checkbox').click();await ready(member.page);await row(member.page,task.id).waitFor({state:'detached'});
  await member.page.getByRole('combobox',{name:'任务状态',exact:true}).selectOption('DONE');await ready(member.page);
  await row(member.page,task.id).getByRole('checkbox').click();await ready(member.page);
  await member.page.getByRole('combobox',{name:'任务状态',exact:true}).selectOption('');await ready(member.page);
  // Deliberate stale edit: another member changes progress while owner is editing.
  await page.getByRole('button',{name:'刷新任务',exact:true}).click();await ready(page);
  await row(page,task.id).getByRole('button',{name:'编辑',exact:true}).click();await page.locator('#edit-task-title').fill('保留本次输入');
  await row(member.page,task.id).getByRole('combobox').selectOption('IN_PROGRESS');await ready(member.page);
  await page.locator('.task-edit-dialog').getByRole('button',{name:'保存修改',exact:true}).click();
  await page.getByRole('heading',{name:'修改结果需要核对',exact:true}).waitFor();
  assert.equal(await page.locator('#edit-task-title').inputValue(),'保留本次输入');assert.ok(await page.locator('#edit-task-title').isDisabled());
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'关闭并刷新列表',exact:true}).click();await ready(page);
  // One write reaches the server, but its response is lost.
  let writes=0;await page.route(`**/api/v1/tasks/${task.id}/status`,async route=>{writes++;await route.fetch();await route.abort('failed')});
  await row(page,task.id).getByRole('checkbox').click();await page.getByRole('heading',{name:'任务状态需要核对',exact:true}).waitFor();
  assert.equal(writes,1);await page.getByRole('button',{name:'核对最新任务',exact:true}).click();await ready(page);assert.equal(writes,1);await page.unroute(`**/api/v1/tasks/${task.id}/status`);
  assert.equal(await row(page,task.id).getByRole('checkbox').getAttribute('aria-checked'),'true');
  const folder=resolve(root,'Docs/images/v2-11');await mkdir(folder,{recursive:true});
  for(const width of [1440,975,390]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});await page.screenshot({path:resolve(folder,`meeting-${width}.png`),fullPage:true});await page.locator('.task-panel').screenshot({path:resolve(folder,`tasks-${width}.png`)})}
  await observer.page.goto(origin+`/meetings/${meeting.id}`);await ready(observer.page);assert.equal(await observer.page.locator('.task-management').count(),0);assert.equal(await observer.page.locator('.task-complete').count(),0);
  assert.deepEqual(errors,[]);
  const evidence={date:new Date().toISOString(),browser:process.env.PROTOTYPE_BROWSER||'chrome',version:browser.version(),checks:['edit-cancel-restore','assignee-complete-reopen','stale-edit-input-preserved','lost-status-response-no-retry','observer-readonly','three-viewports'],result:'passed',temporary_database:true,human_review:false};
  await mkdir(resolve(root,'Docs/evidence'),{recursive:true});await writeFile(resolve(root,`Docs/evidence/v2-11-${evidence.browser}.json`),JSON.stringify(evidence,null,2)+'\n');console.log('PASS V2-11 task editing/cancellation/completion UI');
 }finally{for(const c of contexts)await c.close()}
}
