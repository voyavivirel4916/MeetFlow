import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyConfirmationUI(browser,origin,{root,screenshots}){
 const contexts=[],errors=[];
 async function actor(username){const context=await browser.newContext({viewport:{width:1024,height:900}});contexts.push(context);const data={username,password:'confirmation-password',email:username+'@example.com'};const registered=await context.request.post(origin+'/api/v1/auth/register',{data});assert.equal(registered.status(),201);const id=(await registered.json()).data.id;assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username,password:data.password}})).status(),200);const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));return{context,page,id};}
 const ready=page=>page.waitForFunction(()=>document.querySelector('.time-matrix')&&!document.querySelector('.group-heading button')?.disabled);
 const shot=async(page,name)=>{if(screenshots){const folder=resolve(root,'Docs/images/t25');await mkdir(folder,{recursive:true});await page.screenshot({path:resolve(folder,name+'.png'),fullPage:name==='03-confirmed'});}};
 try{
 const owner=await actor('confirm_owner'),member=await actor('confirm_member');
 const group=(await(await owner.context.request.post(origin+'/api/v1/groups',{data:{name:'会议确认测试'}})).json()).data;
 assert.equal((await member.context.request.post(origin+'/api/v1/groups/join',{data:{invite_code:group.invite_code}})).status(),200);
 const now=Math.floor(Date.now()/60000)*60000;
 async function create(title){const response=await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`,{data:{title,location:'2015A',response_deadline:new Date(now+3600000).toISOString(),participants:[{user_id:owner.id,importance:'REQUIRED'},{user_id:member.id,importance:'REQUIRED'}],slots:[0,1].map(i=>({start_at:new Date(now+7200000+i*86400000).toISOString(),end_at:new Date(now+10800000+i*86400000).toISOString()}))}});assert.equal(response.status(),201);const poll=(await response.json()).data;assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/open`,{data:{}})).status(),200);return poll;}
 const poll=await create('确认有风险的时间'),page=owner.page,url=origin+`/polls/${poll.id}/results`;
 await page.goto(url);await ready(page);assert.equal(await page.getByRole('button',{name:'选择这个时间',exact:true}).count(),0);
 page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'结束收集',exact:true}).click();assert.equal(await page.getByRole('button',{name:'结束收集',exact:true}).count(),1);
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'结束收集',exact:true}).click();await page.getByRole('button',{name:'选择这个时间',exact:true}).first().waitFor();await ready(page);
 await member.page.goto(url);await ready(member.page);assert.equal(await member.page.getByRole('button',{name:'选择这个时间',exact:true}).count(),0);
 await page.getByRole('button',{name:'选择这个时间',exact:true}).nth(1).click();const dialog=page.getByRole('dialog',{name:'确认会议时间'});await dialog.waitFor();
 await dialog.getByRole('button',{name:'确认生成会议',exact:true}).click();await dialog.getByText('请先确认已了解这些风险。',{exact:true}).waitFor();await dialog.getByText('请填写有效理由，最多500个字符。',{exact:true}).waitFor();
 await dialog.getByRole('checkbox').check();await dialog.getByLabel('选择理由（必填）').fill('已与必到成员协调，采用这个时间。');
 assert.equal(await dialog.locator('.field-error').count(),0);
 for(const width of[1024,800,400]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.ok(await dialog.evaluate(el=>el.getBoundingClientRect().right<=innerWidth));}
 await page.setViewportSize({width:1024,height:900});await shot(page,'01-risk-dialog');
 let writes=0;const path=`**/api/v1/polls/${poll.id}/confirm`;
 // The server commits, but the response is lost. A read must reconcile without another POST.
 await page.route(path,async route=>{writes++;await route.fetch();await route.abort('failed');});
 await dialog.getByRole('button',{name:'确认生成会议',exact:true}).click();await dialog.getByRole('button',{name:'核对服务端结果',exact:true}).waitFor();assert.equal(await dialog.getByLabel('选择理由（必填）').inputValue(),'已与必到成员协调，采用这个时间。');assert.equal(await dialog.getByRole('button',{name:'确认生成会议',exact:true}).isDisabled(),true);
 await shot(page,'02-reconcile');await dialog.getByRole('button',{name:'核对服务端结果',exact:true}).click();await page.getByRole('heading',{name:'会议时间已确认',exact:true}).waitFor();assert.equal(writes,1);assert.equal(await dialog.isVisible(),false);
 await page.reload();await ready(page);await page.getByRole('heading',{name:'会议时间已确认',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'选择这个时间',exact:true}).count(),0);await shot(page,'03-confirmed');
 const actual=(await(await owner.context.request.get(origin+`/api/v1/polls/${poll.id}/meeting`)).json()).data;assert.equal(actual.selected_slot_id,poll.slots[1].id);assert.equal(actual.selection_reason,'已与必到成员协调，采用这个时间。');
 // Safe first choice needs no checkbox or reason; Esc exits without writing.
 const safe=await create('无冲突首选');for(const user of[owner,member])assert.equal((await user.context.request.put(origin+`/api/v1/polls/${safe.id}/votes/me`,{data:{votes:safe.slots.map(slot=>({slot_id:slot.id,availability:'AVAILABLE'}))}})).status(),200);
 assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${safe.id}/close`,{data:{}})).status(),200);
 await page.goto(origin+`/polls/${safe.id}/results`);await ready(page);await page.getByRole('button',{name:'选择这个时间',exact:true}).first().click();assert.equal(await dialog.getByRole('checkbox').count(),0);await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),false);
 await page.getByRole('button',{name:'选择这个时间',exact:true}).first().click();await dialog.getByRole('button',{name:'确认生成会议',exact:true}).click();await page.getByRole('heading',{name:'会议时间已确认',exact:true}).waitFor();
 assert.deepEqual(errors,[]);console.log('PASS T25 confirmation UI: owner/member, close/cancel, risks/reason, responsive dialog, lost response read reconciliation, reload and safe confirmation.');
 }finally{for(const context of contexts)await context.close();}
}
