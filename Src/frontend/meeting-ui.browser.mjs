import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyMeetingUI(browser,origin,{root,screenshots}){
 const contexts=[],errors=[];
 async function actor(username){const context=await browser.newContext({viewport:{width:1280,height:960}});contexts.push(context);const credentials={username,password:'meeting-content-password'};const response=await context.request.post(origin+'/api/v1/auth/register',{data:{...credentials,email:username+'@example.com'}});assert.equal(response.status(),201);const id=(await response.json()).data.id;assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:credentials})).status(),200);const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));return{context,page,id};}
 const shot=async(page,name)=>{if(screenshots){const folder=resolve(root,'Docs/images/t27');await mkdir(folder,{recursive:true});await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();window.scrollTo(0,0);});await page.screenshot({path:resolve(folder,name+'.png'),fullPage:true});}};
 const ready=page=>page.waitForFunction(()=>document.querySelector('.meeting-content')&&!document.querySelector('.group-heading button')?.disabled);
 try{
 const owner=await actor('meeting_owner'),member=await actor('meeting_member'),outsider=await actor('meeting_outsider');
 const group=(await(await owner.context.request.post(origin+'/api/v1/groups',{data:{name:'会议内容测试'}})).json()).data;
 assert.equal((await member.context.request.post(origin+'/api/v1/groups/join',{data:{invite_code:group.invite_code}})).status(),200);
 const now=Math.floor(Date.now()/60000)*60000;
 const pollResponse=await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`,{data:{title:'方案评审与下一步',location:'计算机大楼2015A',response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'}],slots:[{start_at:new Date(now+7200000).toISOString(),end_at:new Date(now+10800000).toISOString()}]}});assert.equal(pollResponse.status(),201);const poll=(await pollResponse.json()).data;
 for(const action of['open','close'])assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/${action}`,{data:{}})).status(),200);
 const confirmation=await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/confirm`,{data:{slot_id:poll.slots[0].id,acknowledged:true,selection_reason:'已协调确认'}});assert.equal(confirmation.status(),201);const meeting=(await confirmation.json()).data;
 const page=owner.page,url=origin+`/meetings/${meeting.id}`,endpoint=`**/api/v1/meetings/${meeting.id}`;
 await page.goto(origin+`/polls/${poll.id}/results`);await page.getByRole('link',{name:'查看会议 →',exact:true}).click();await ready(page);assert.equal(page.url(),url);assert.equal(await page.getByRole('link',{name:'查看排期结果 →',exact:true}).getAttribute('class'),'button-link');
 await page.getByText('尚未填写议程。',{exact:true}).waitFor();await page.getByText('尚未填写纪要，讨论结束后在这里留下决定。',{exact:true}).waitFor();await shot(page,'03-empty');
 await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).click();const agenda=page.getByLabel('会议议程',{exact:true}),minutes=page.getByLabel('会议纪要',{exact:true}),save=page.getByRole('button',{name:'保存议程与纪要',exact:true});
 assert.equal(await save.isDisabled(),true);
 await agenda.fill('x'.repeat(10001));await save.click();await page.getByText('请输入有效文字，最多10000个字符。',{exact:true}).waitFor();
 await agenda.fill('1. 评审时间推荐方案\n2. 明确实现分工');await minutes.fill('结论：优先完成核心流程。\n下一步：分配实现任务。');assert.equal(await page.locator('.field-error').count(),0);await shot(page,'01-editor');
 // Failed refresh is explicit and does not throw away a dirty draft when cancelled.
 page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'刷新',exact:true}).click();assert.match(await agenda.inputValue(),/明确实现分工/);
 let writes=0;
 await page.route(endpoint,async route=>{if(route.request().method()==='PATCH'){writes++;await route.fetch();await route.abort('failed');}else await route.continue();});
 await save.click();await page.getByRole('button',{name:'核对保存结果',exact:true}).waitFor();assert.equal(await save.isDisabled(),true);assert.match(await minutes.inputValue(),/核心流程/);await page.getByRole('button',{name:'核对保存结果',exact:true}).click();await page.getByText('已核对，议程与纪要已保存。',{exact:true}).waitFor();assert.equal(writes,1);assert.equal(await page.evaluate(()=>window.meetingUnsafe),undefined);await shot(page,'02-saved');
 await page.unroute(endpoint);assert.equal((await owner.context.request.patch(origin+`/api/v1/meetings/${meeting.id}`,{data:{minutes:'结论：优先完成核心流程。\n<script>window.meetingUnsafe=true</script>'}})).status(),200);await page.reload();await ready(page);await page.getByText('1. 评审时间推荐方案\n2. 明确实现分工',{exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>window.meetingUnsafe),undefined);await page.getByText('<script>window.meetingUnsafe=true</script>',{exact:false}).waitFor();
 await member.page.goto(url);await ready(member.page);assert.equal(await member.page.getByRole('button',{name:'编辑议程与纪要',exact:true}).count(),0);assert.match(await member.page.locator('.meeting-content').innerText(),/核心流程/);assert.equal(await member.page.locator('textarea').count(),0);
 // A request lost before persistence must not be reported as saved or automatically resubmitted.
 await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).click();await minutes.fill('新的决定');
 await page.route(endpoint,async route=>{if(route.request().method()==='PATCH'){writes++;await route.abort('failed');}else await route.continue();});await save.click();await page.getByRole('button',{name:'核对保存结果',exact:true}).click();await page.getByRole('heading',{name:'服务端已保存的内容',exact:true}).waitFor();assert.equal(await minutes.inputValue(),'新的决定');assert.equal(writes,2);await page.getByRole('button',{name:'保留输入继续编辑',exact:true}).click();await page.unroute(endpoint);await save.click();await page.getByText('议程与纪要已保存。',{exact:true}).waitFor();
 await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).click();await agenda.fill('');await minutes.fill('');await save.click();await page.getByText('尚未填写议程。',{exact:true}).waitFor();
 // 503 keeps the complete last snapshot and blocks editing until a good read.
 await page.route(endpoint,route=>route.fulfill({status:503,contentType:'application/json',headers:{'X-Request-ID':'c07e357967c148068a4f9aa539c759e2'},body:JSON.stringify({error:{code:'STORAGE_UNAVAILABLE',message:'暂时无法读取'},request_id:'c07e357967c148068a4f9aa539c759e2'})}));await page.getByRole('button',{name:'刷新',exact:true}).click();await page.getByRole('heading',{name:'会议暂时无法读取',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).isDisabled(),true);await page.unroute(endpoint);await page.getByRole('button',{name:'重新读取会议',exact:true}).click();await ready(page);
 for(const width of[1440,1024,800,400]){await page.setViewportSize({width,height:960});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).click();assert.ok(await agenda.evaluate(el=>el.getBoundingClientRect().right<=innerWidth));await page.getByRole('button',{name:'取消编辑',exact:true}).click();}
 await outsider.page.goto(url);await outsider.page.getByRole('heading',{name:'未找到可访问的会议',exact:true}).waitFor();assert.equal(await outsider.page.locator('.meeting-overview').count(),0);
 await member.context.request.post(origin+'/api/v1/auth/logout',{data:{}});await member.page.getByRole('button',{name:'刷新',exact:true}).click();await member.page.waitForURL('**/login?**');assert.equal(await member.page.locator('.meeting-content').count(),0);
 assert.deepEqual(errors,[]);console.log('PASS T27 meeting UI: real result link, empty/content/edit/read-only, Unicode limits, plain text, save/reload, failed refresh, lost response saved/unsaved reconciliation, 4 widths and identity isolation.');
 }finally{for(const context of contexts)await context.close();}
}
