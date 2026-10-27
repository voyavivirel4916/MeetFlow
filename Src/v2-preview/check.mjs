// Isolated visual prototype checks. No application APIs or developer database.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../..');
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const server=createServer(async(req,res)=>{
 const files={'/':'index.html','/style.css':'style.css','/app.js':'app.js'};
 const file=files[req.url];if(!file){res.writeHead(404);res.end();return}
 res.setHeader('Content-Type',{'index.html':'text/html; charset=utf-8','style.css':'text/css','app.js':'text/javascript'}[file]);
 res.end(await readFile(resolve(here,file)));
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
let browser;
const errors=[],screenshots=[],channel=process.env.MEETFLOW_BROWSER_CHANNEL||'chrome';
try{
 browser=await chromium.launch({channel,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',req=>assert.ok(req.url().startsWith(`http://127.0.0.1:${server.address().port}/`),'External request'));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 // Verify readable primary actions and consistent theme across selected surfaces.
 const theme=await page.evaluate(()=>{
  const luminance=color=>{
   const rgb=color.match(/[\d.]+/g).slice(0,3).map(v=>Number(v)/255)
    .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
   return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  };
  const style=getComputedStyle(document.querySelector('.primary'));
  const a=luminance(style.color),b=luminance(style.backgroundColor);
  return {contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),
   selected:getComputedStyle(document.querySelector('nav .active')).backgroundColor,
   avatar:getComputedStyle(document.querySelector('.avatar')).backgroundColor};
 });
 assert.ok(theme.contrast>=4.5,`Primary button contrast ${theme.contrast}`);
 assert.equal(theme.selected,theme.avatar);
 const screenshotDir=resolve(root,'Docs/images/v2-02');await mkdir(screenshotDir,{recursive:true});
 for(const width of [1440,975,390]){
  await page.setViewportSize({width,height:width===390?844:1000});
  for(const view of ['home','group','tasks']){
   await page.goto(`http://127.0.0.1:${server.address().port}/#${view}`);
   await page.locator('h1').waitFor();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${view}/${width} overflow`);
   const name=`${view}-${width}.png`;await page.screenshot({path:resolve(screenshotDir,name),fullPage:true});screenshots.push(name);
  }
 }
 await page.setViewportSize({width:1280,height:900});
 const tab=name=>page.getByRole('tab',{name,exact:true});
 await page.goto(`http://127.0.0.1:${server.address().port}/#tasks`);
 assert.equal(await page.locator('[data-task]').count(),3);
 await page.locator('[data-complete="1"]').click();
 assert.equal(await page.locator('[data-task]').count(),2);
 await tab('已完成').click();await page.locator('[data-complete="1"]').click();
 await tab('未完成').click();assert.equal(await page.locator('[data-task]').count(),3);
 await page.locator('[data-task="1"] [data-action="cancel-task"]').click();
 await page.locator('#action-dialog button[value="cancel"]').click();assert.equal(await page.locator('[data-task]').count(),3);
 await page.locator('[data-task="1"] [data-action="cancel-task"]').click();await page.locator('#confirm-action').click();await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
 await tab('已取消').click();assert.equal(await page.locator('[data-task]').count(),2);
 await page.locator('[data-task="1"] [data-action="restore-task"]').click();await page.locator('#confirm-action').click();await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
 await tab('未完成').click();await page.locator('[data-task="1"] [data-action="edit"]').click();
 await page.locator('#edit-form input[name="title"]').fill('修订后的接口测试');await page.locator('#edit-form button[type="submit"], #edit-form button.primary').click();
 await page.getByRole('textbox',{name:'搜索任务'}).fill('修订后');assert.equal(await page.locator('[data-task]').count(),1);
 await page.goto(`http://127.0.0.1:${server.address().port}/#group`);
 await page.locator('[data-poll="2"] [data-action="archive"]').click();await page.locator('#confirm-action').click();await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
 await page.locator('[data-poll="2"]').waitFor({state:'detached'});assert.equal(await page.locator('[data-poll="2"]').count(),0);await tab('历史').click();assert.equal(await page.locator('[data-poll="2"]').count(),1);
 await tab('当前').click();await page.locator('[data-poll="5"] [data-action="delete-poll"]').click();await page.locator('#confirm-action').click();await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
 await tab('回收站').click();await page.locator('[data-poll="5"] [data-action="restore-poll"]').click();await page.locator('#confirm-action').click();await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
 await tab('当前').click();assert.equal(await page.locator('[data-poll="5"]').count(),1);
 assert.deepEqual(errors,[]);
 const evidence={date:new Date().toISOString(),browser:channel,version:browser.version(),viewports:[1440,975,390],pages:['home','group','tasks'],screenshots,theme,checks:['primary-text-contrast','consistent-highlight','no-page-overflow','complete-reopen','cancel-return-restore','edit-search','archive','delete-restore','no-external-requests','no-page-errors'],result:'passed',production:false,human_review:false};
 await mkdir(resolve(root,'Docs/evidence'),{recursive:true});await writeFile(resolve(root,`Docs/evidence/v2-02-${channel}.json`),JSON.stringify(evidence,null,2)+'\n');
 console.log(`${channel}: V2-02 prototype checks passed; 9 screenshots.`);
}finally{await browser?.close();await new Promise(done=>server.close(done))}
