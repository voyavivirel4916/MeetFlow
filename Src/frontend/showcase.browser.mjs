// Run against the explicitly seeded, disposable showcase, never the normal workspace.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const origin=process.env.MEETFLOW_SHOWCASE_ORIGIN||'http://localhost:8001';
assert.equal(origin,'http://localhost:8001','Use only the dedicated local showcase.');
const root=resolve(import.meta.dirname,'../..'),folder=resolve(root,'Docs/images/v2-showcase');
await mkdir(folder,{recursive:true});
const browser=await chromium.launch({channel:process.env.PROTOTYPE_BROWSER||'chrome',headless:true});
const context=await browser.newContext(),page=await context.newPage(),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(origin+'/login');await page.getByLabel('用户名',{exact:true}).fill('demo_owner');await page.getByLabel('密码',{exact:true}).fill('MeetFlowDemo2026!');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL(origin+'/dashboard');await page.locator('[data-count="tasks"]').waitFor();
 assert.equal(await page.locator('[data-count="tasks"]').innerText(),'4');
 assert.equal(await page.locator('[data-count="meetings"]').innerText(),'3');
 assert.equal(await page.locator('[data-count="polls"]').innerText(),'1');
 const ready=()=>page.waitForFunction(()=>!document.querySelector('.task-panel .section-heading button')?.disabled);
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1000});
  for(const [name,path] of [['dashboard','/dashboard'],['group','/groups/1'],['tasks','/tasks/mine']]){
   await page.goto(origin+path);await page.getByRole('heading',{level:1}).waitFor();
   if(name==='dashboard')await page.locator('[data-count="tasks"]').waitFor();
   else{await page.locator('.task-list>li').first().waitFor();await ready();}
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   if(name==='group')assert.equal(await page.locator('.poll-list>li').count(),6);
   if(name==='tasks')assert.equal(await page.locator('.task-list>li').count(),4);
   await page.screenshot({path:resolve(folder,`${name}-${width}.png`),fullPage:true});
  }
 }
 await page.goto(origin+'/groups/1');await page.locator('.poll-list>li').first().waitFor();
 for(const label of ['历史','回收站']){
  await page.getByRole('navigation',{name:'排期分类',exact:true}).getByRole('button',{name:label,exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.poll-list-card .refresh-icon')?.disabled);
  assert.equal(await page.locator('.poll-list>li').count(),1);
 }
 await page.goto(origin+'/tasks/mine');await page.locator('.task-list>li').first().waitFor();await ready();
 for(const label of ['已完成','已取消']){
  await page.getByRole('navigation',{name:'任务分类',exact:true}).getByRole('button',{name:label,exact:true}).click();await ready();assert.equal(await page.locator('.task-list>li').count(),1);
 }
 assert.deepEqual(errors,[]);
 await writeFile(resolve(root,`Docs/evidence/v2-showcase-${process.env.PROTOTYPE_BROWSER||'chrome'}.json`),JSON.stringify({date:new Date().toISOString(),result:'passed',demo_only:true,origin,groups:2,polls:9,meetings:3,tasks:10,checks:['real-login','dashboard-counts','history-and-trash','completed-and-cancelled','1440-and-390-no-overflow']},null,2)+'\n');
 console.log('PASS rich V2 showcase: live login, dashboard, poll categories, task states and responsive pages');
}finally{await context.close();await browser.close();}
