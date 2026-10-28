import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifySearchTheme(browser,origin,{root}){
 const contexts=[],errors=[];
 async function post(a,path,data){const r=await a.context.request.post(origin+'/api/v1/'+path,{data});assert.ok(r.ok(),`${path} ${await r.text()}`);return(await r.json()).data}
 async function actor(username){const context=await browser.newContext({viewport:{width:1440,height:1000}});contexts.push(context);const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));const a={context,page};a.id=(await post(a,'auth/register',{username,email:username+'@example.com',password:'SearchThemeDemo123!'})).id;await post(a,'auth/login',{username,password:'SearchThemeDemo123!'});return a}
 const pollReady=p=>p.waitForFunction(()=>document.querySelector('.poll-list-card .refresh-icon')&&!document.querySelector('.poll-list-card .refresh-icon').disabled);
 const taskReady=p=>p.waitForFunction(()=>document.querySelector('.task-panel .section-heading button')&&!document.querySelector('.task-panel .section-heading button').disabled);
 try{
  const owner=await actor('theme_owner'),member=await actor('theme_member');
  const group=await post(owner,'groups',{name:'软件工程课程小组',description:'集中安排讨论，记录会议和跟进任务。'});await post(member,'groups/join',{invite_code:group.invite_code});
  const now=Date.now(),keyword='接口 / 20%_';
  const draft=title=>({title,response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'},{user_id:member.id,importance:'NORMAL'}],slots:[{start_at:new Date(now+7200000).toISOString(),end_at:new Date(now+10800000).toISOString()}]});
  const poll=await post(owner,`groups/${group.id}/polls`,draft('第二版需求讨论'));await post(owner,`polls/${poll.id}/open`,{});
  const confirmed=await post(owner,`groups/${group.id}/polls`,draft('阶段汇报准备'));for(const a of ['open','close'])await post(owner,`polls/${confirmed.id}/${a}`,{});
  const meeting=await post(owner,`polls/${confirmed.id}/confirm`,{slot_id:confirmed.slots[0].id,acknowledged:true,selection_reason:'验证整体界面和任务搜索'});
  const searchable=await post(owner,`groups/${group.id}/polls`,draft(keyword+'核对'));
  const taskBody=title=>({title,assignee_id:owner.id,due_at:new Date(now+86400000).toISOString(),client_request_id:crypto.randomUUID()});
  await post(owner,`meetings/${meeting.id}/tasks`,taskBody(keyword+'说明'));await post(owner,`meetings/${meeting.id}/tasks`,{...taskBody('准备汇报材料'),assignee_id:member.id});
  const page=owner.page,groupUrl=origin+`/groups/${group.id}`;
  await page.goto(groupUrl);await pollReady(page);await taskReady(page);
  const search=page.getByRole('search',{name:'排期搜索',exact:true});
  await search.getByRole('searchbox').fill(keyword);await search.getByRole('button',{name:'搜索',exact:true}).click();await pollReady(page);
  assert.equal(await page.locator('.poll-list>li').count(),1);assert.equal(await page.locator('.poll-list>li').getAttribute('data-poll'),String(searchable.id));
  await page.locator('.poll-view-tabs').getByRole('button',{name:'历史',exact:true}).click();await pollReady(page);assert.equal(await page.locator('.poll-list>li').count(),0);
  await page.locator('.poll-view-tabs').getByRole('button',{name:'当前',exact:true}).click();await pollReady(page);assert.equal(await page.locator('.poll-list>li').count(),1);
  const pollRoute=`**/api/v1/groups/${group.id}/polls?*`;
  await page.route(pollRoute,route=>route.fulfill({status:503,contentType:'application/json',headers:{'X-Request-ID':'c07e357967c148068a4f9aa539c759e2'},body:JSON.stringify({error:{code:'STORAGE_UNAVAILABLE',message:'搜索暂不可读'},request_id:'c07e357967c148068a4f9aa539c759e2'})}));
  await search.getByRole('searchbox').fill('读取失败的新查询');await search.getByRole('button',{name:'搜索',exact:true}).click();
  await page.getByRole('heading',{name:'排期列表暂时无法读取',exact:true}).waitFor();assert.equal(await page.locator('.poll-list>li').count(),1);assert.ok(await page.locator('.poll-row-actions button').isDisabled());
  await page.unroute(pollRoute);await page.getByRole('button',{name:'重新读取排期',exact:true}).click();await pollReady(page);
  await search.getByRole('button',{name:'清除',exact:true}).click();await pollReady(page);assert.equal(await page.locator('.poll-list>li').count(),3);
  const taskSearch=page.getByRole('search',{name:'任务搜索',exact:true});await taskSearch.getByRole('searchbox').fill(keyword);await taskSearch.getByRole('button',{name:'搜索',exact:true}).click();await taskReady(page);assert.equal(await page.locator('.task-list>li').count(),1);
  await taskSearch.getByRole('button',{name:'清除',exact:true}).click();await taskReady(page);assert.equal(await page.locator('.task-list>li').count(),2);
  const folder=resolve(root,'Docs/images/workflow-theme');await mkdir(folder,{recursive:true});
  const paths={dashboard:'/dashboard',group:`/groups/${group.id}`,tasks:'/tasks/mine',vote:`/polls/${poll.id}/vote`,editor:`/polls/${searchable.id}/edit`,matrix:`/polls/${poll.id}/results`,meeting:`/meetings/${meeting.id}`};
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1000});
   for(const [name,path] of Object.entries(paths)){
    await page.goto(origin+path);await page.getByRole('heading',{level:1}).waitFor();
    if(name==='dashboard')await page.locator('[data-count="tasks"]').waitFor();
    if(name==='group')await pollReady(page);
    if(['tasks','meeting'].includes(name))await taskReady(page);
    if(name==='matrix')await page.locator('.time-matrix').waitFor();
    if(name==='vote')await page.locator('.vote-card').waitFor();
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}/${width} overflow`);
    assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).fontSize),'14px');
    {
      assert.equal(await page.locator('.shell').evaluate(el=>getComputedStyle(el).getPropertyValue('--brand').trim()),'#7250a1');
      if(['dashboard','group','tasks'].includes(name))assert.equal(await page.locator('.eyebrow').count(),0);
      if(width===1440)assert.equal(Math.round((await page.locator('.shell>aside').boundingBox()).width),208);
    }
    if(name==='tasks'){
      const tabs=page.getByRole('navigation',{name:'任务分类',exact:true});
      await tabs.getByRole('button',{name:'已完成',exact:true}).click();await taskReady(page);
      assert.equal(await page.getByLabel('任务状态',{exact:true}).inputValue(),'DONE');
      await tabs.getByRole('button',{name:'已取消',exact:true}).click();await taskReady(page);
      assert.equal(await page.getByLabel('任务状态',{exact:true}).inputValue(),'CANCELLED');
      await tabs.getByRole('button',{name:'未完成',exact:true}).click();await taskReady(page);
      assert.equal(await page.getByLabel('任务状态',{exact:true}).inputValue(),'');
    }
    await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});
    await page.screenshot({path:resolve(folder,`${name}-${width}.png`),fullPage:true});
   }
  }
  await page.locator('.task-list>li').first().getByRole('button',{name:'编辑',exact:true}).click();
  const modal=await page.locator('.task-edit-dialog').boundingBox();assert.ok(modal&&modal.x>=0&&modal.x+modal.width<=390);
  await page.locator('.task-edit-dialog').screenshot({path:resolve(folder,'task-editor-390.png')});
  await page.locator('.task-edit-dialog').getByRole('button',{name:'取消编辑',exact:true}).click();
  await page.goto(groupUrl);await pollReady(page);await page.setViewportSize({width:1440,height:1000});
  const positions=await page.evaluate(()=>({poll:document.querySelector('.poll-list-card').getBoundingClientRect().x,member:document.querySelector('.members-card').getBoundingClientRect().x}));assert.ok(positions.member>positions.poll);
  for(let i=0;i<21;i++)await post(owner,`meetings/${meeting.id}/tasks`,taskBody('分页任务'+i));
  await page.getByRole('button',{name:'刷新任务',exact:true}).click();await taskReady(page);await page.getByRole('button',{name:'下一页任务',exact:true}).click();await taskReady(page);
  const form=page.getByRole('search',{name:'任务搜索',exact:true});await form.getByRole('searchbox').fill(keyword);await form.getByRole('button',{name:'搜索',exact:true}).click();await taskReady(page);assert.equal(await page.locator('.task-list>li').count(),1);assert.equal(await page.getByRole('button',{name:'上一页任务',exact:true}).count(),0);
  await page.goto(origin+'/groups');await page.locator('.group-card').first().waitFor();
  for(const width of [1440,888,390]){
    await page.setViewportSize({width,height:1000});
    const card=page.locator('.group-card').first();
    for(const property of ['borderTopRightRadius','borderBottomRightRadius'])assert.equal(await card.evaluate((el,key)=>getComputedStyle(el)[key],property),'12px');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:resolve(folder,`groups-${width}.png`),fullPage:true});
  }
  const context=await browser.newContext({viewport:{width:390,height:844}});contexts.push(context);const login=await context.newPage();await login.goto(origin+'/login');await login.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();assert.ok(await login.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.equal(await login.evaluate(()=>getComputedStyle(document.documentElement).fontSize),'14px');
  await login.screenshot({path:resolve(folder,'login-390.png'),fullPage:true});
  await login.setViewportSize({width:1440,height:1000});await login.screenshot({path:resolve(folder,'login-1440.png'),fullPage:true});
  await login.goto(origin+'/register');await login.locator('#email').waitFor();await login.setViewportSize({width:390,height:1000});assert.ok(await login.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await login.screenshot({path:resolve(folder,'register-390.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  const evidence={date:new Date().toISOString(),browser:process.env.PROTOTYPE_BROWSER||'chrome',version:browser.version(),checks:['literal-special-character-search','view-and-query-combination','task-search-before-pagination','clear-query','sample-members-on-right','seven-pages-two-viewports','mobile-login-register-and-rounded-group-card'],result:'passed',temporary_database:true,human_review:false};await mkdir(resolve(root,'Docs/evidence'),{recursive:true});await writeFile(resolve(root,`Docs/evidence/workflow-theme-${evidence.browser}.json`),JSON.stringify(evidence,null,2)+'\n');console.log('PASS shared purple workflow style, rounded groups, live search and task tabs');
 }finally{for(const c of contexts)await c.close()}
}
