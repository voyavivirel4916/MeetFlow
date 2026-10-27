import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export async function verifyE2E(browser,origin,{root}){
 const contexts=[],actors=[],errors=[],started=new Date().toISOString();
 const local=ms=>new Date(ms+8*3600000).toISOString().slice(0,16);
 const taskReady=page=>page.waitForFunction(()=>document.querySelector('.task-panel')&&!document.querySelector('.task-panel .section-heading button')?.disabled);
 try{
 for(let i=0;i<4;i++){
  const context=await browser.newContext({viewport:{width:1280,height:900}});contexts.push(context);
  const username=`acceptance_${i}`,password='acceptance-password';
  assert.equal((await context.request.post(origin+'/api/v1/auth/register',{data:{username,password,email:username+'@example.com'}})).status(),201);
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin+'/login');await page.getByLabel('用户名',{exact:true}).fill(username);await page.getByLabel('密码',{exact:true}).fill(password);await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/groups');
  const user=(await(await context.request.get(origin+'/api/v1/users/me')).json()).data;
  actors.push({context,page,id:user.id,username});
 }
 const owner=actors[0],page=owner.page;
 await page.getByLabel('小组名称（必填）',{exact:true}).fill('四账号完整流程验收');await page.locator('.group-form-card form').getByRole('button',{name:'创建小组',exact:true}).click();await page.waitForURL(/\/groups\/\d+$/);
 const groupUrl=page.url(),groupId=Number(new URL(groupUrl).pathname.split('/')[2]);await page.locator('#current-invite').waitFor();const code=await page.locator('#current-invite').inputValue();
 for(const actor of actors.slice(1)){await actor.page.getByRole('button',{name:'邀请码加入',exact:true}).click();await actor.page.getByLabel('邀请码（必填）',{exact:true}).fill(code);await actor.page.getByRole('button',{name:'加入小组',exact:true}).click();await actor.page.waitForURL(groupUrl);}
 await page.goto(groupUrl+ '/polls/new');await page.locator('#poll-title').fill('从排期到任务的完整演示');await page.locator('#poll-location').fill('计算机大楼2015A');
 const now=Math.floor(Date.now()/60000)*60000;await page.locator('#poll-deadline').fill(local(now+3600000));
 for(const actor of actors)await page.getByRole('checkbox',{name:`选择 ${actor.username}`,exact:true}).check();
 for(const actor of actors.slice(0,2))await page.getByRole('checkbox',{name:`${actor.username} 必到`,exact:true}).check();
 for(let i=0;i<3;i++){await page.getByRole('button',{name:'＋ 添加候选时间',exact:true}).click();await page.getByLabel('开始（北京时间）',{exact:true}).nth(i).fill(local(now+7200000+i*86400000));await page.getByLabel('结束（北京时间）',{exact:true}).nth(i).fill(local(now+10800000+i*86400000));}
 await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.waitForURL(/\/polls\/\d+\/edit$/);const pollId=Number(new URL(page.url()).pathname.split('/')[2]);
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'发布收集',exact:true}).click();await page.getByText('排期已发布，候选时间和参与者已冻结。',{exact:true}).waitFor();
 const poll=(await(await owner.context.request.get(origin+`/api/v1/polls/${pollId}`)).json()).data;
 for(const [index,actor] of actors.entries()){
  await actor.page.goto(origin+`/polls/${pollId}/vote`);
  for(const [i,slot] of poll.slots.entries())await actor.page.locator(`#vote-${slot.id}-${i===0?'AVAILABLE':i===1?(index<2?'MAYBE':'AVAILABLE'):'UNAVAILABLE'}`).check();
  await actor.page.getByRole('button',{name:'保存我的选择',exact:true}).click();await actor.page.getByText('你的选择已保存。',{exact:true}).waitFor();
 }
 await page.goto(origin+`/polls/${pollId}/results`);await page.getByText('4/4 人已提交',{exact:true}).waitFor();
 const ranking=(await(await owner.context.request.get(origin+`/api/v1/polls/${pollId}/recommendations`)).json()).data.items;assert.equal(ranking[0].slot_id,poll.slots[0].id);assert.equal(ranking[0].available_count,4);
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'结束收集',exact:true}).click();await page.getByRole('button',{name:'选择这个时间',exact:true}).first().click();await page.getByRole('dialog',{name:'确认会议时间'}).getByRole('button',{name:'确认生成会议',exact:true}).click();await page.getByRole('link',{name:'查看会议 →',exact:true}).click();await taskReady(page);
 const meetingId=Number(new URL(page.url()).pathname.split('/')[2]);await page.getByRole('button',{name:'编辑议程与纪要',exact:true}).click();await page.getByLabel('会议议程',{exact:true}).fill('评审核心流程，确定后续分工。');await page.getByLabel('会议纪要',{exact:true}).fill('已确定会议时间，由两位执行人分别推进。');await page.getByRole('button',{name:'保存议程与纪要',exact:true}).click();await page.getByText('议程与纪要已保存。',{exact:true}).waitFor();
 for(let i=1;i<=2;i++){
  await page.getByRole('button',{name:'＋ 添加任务',exact:true}).click();await page.getByLabel('任务标题',{exact:true}).fill(`演示行动${i}`);await page.getByLabel('执行人',{exact:true}).selectOption(String(actors[i].id));await page.getByLabel('截止时间（北京时间）',{exact:true}).fill(local(now+172800000));await page.getByRole('button',{name:'创建任务',exact:true}).click();await page.locator('.task-list>li').nth(i-1).waitFor();await taskReady(page);
 }
 for(let i=1;i<=2;i++){const actor=actors[i];await actor.page.goto(origin+'/tasks/mine');await taskReady(actor.page);await actor.page.getByLabel(`演示行动${i}的状态`,{exact:true}).selectOption(i===1?'DONE':'IN_PROGRESS');await taskReady(actor.page);assert.equal(await actor.page.locator('.task-list>li').count(),i===1?0:1);}
 await actors[3].page.goto(origin+`/meetings/${meetingId}`);await taskReady(actors[3].page);assert.equal(await actors[3].page.locator('.task-status select').count(),0);assert.equal(await actors[3].page.getByRole('button',{name:'＋ 添加任务',exact:true}).count(),0);
 await page.goto(groupUrl);await taskReady(page);assert.equal(await page.locator('.task-list>li').count(),2);
 const actual=(await(await owner.context.request.get(origin+`/api/v1/groups/${groupId}/tasks`)).json()).data;assert.deepEqual(actual.items.map(item=>item.status),['DONE','IN_PROGRESS']);assert.deepEqual(errors,[]);
 const folder=resolve(root,'Docs/evidence');await mkdir(folder,{recursive:true});await writeFile(resolve(folder,'t36-e2e.json'),JSON.stringify({started_at:started,finished_at:new Date().toISOString(),browser:browser.version(),independent_browser_contexts:4,registration_fixture:'API registration; all subsequent business operations use UI',group_members:4,candidates:3,submissions:4,meetings:1,tasks:2,final_task_states:['DONE','IN_PROGRESS'],steps:['UI login','UI create/join group','UI draft and publish','UI four-person voting','UI matrix and recommendations','UI close and confirm','UI agenda and minutes','UI two-task creation','UI assignee updates and group readback'],result:'passed',human_usability:false},null,2)+'\n');
 console.log('PASS E2E-01: four separate browser sessions, UI login -> group/join -> 3-slot draft/publish -> four votes -> ranking -> confirmation -> minutes -> 2 tasks -> assignee statuses and group readback.');
 }finally{for(const context of contexts)await context.close();}
}
