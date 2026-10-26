// Run with PLAYWRIGHT_MODULE_PATH pointing to an installed playwright package.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { dirname, resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const require=createRequire(import.meta.url);
const { chromium }=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root=dirname(fileURLToPath(import.meta.url));
const screenshots=resolve(root,'../../Docs/images/prototype');
const saveScreenshots=process.argv.includes('--screenshots');
const server=createServer(async(req,res)=>{
  const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname.replace(/\/$/,'/index.html')));
  if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
  try { const content=await readFile(path);res.writeHead(200,{'Content-Type':({'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'})[extname(path)]||'application/octet-stream'});res.end(content); }catch {res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await chromium.launch({channel:process.env.PROTOTYPE_BROWSER||'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1080},timezoneId:'Asia/Shanghai',locale:'zh-CN'});
  const page=await context.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  const go=async view=>{await page.locator(`[data-nav="${view}"]`).click();await page.waitForURL(`**/#${view}`);};
  const shot=async name=>{if(saveScreenshots){await mkdir(screenshots,{recursive:true});await page.screenshot({path:resolve(screenshots,`${name}.png`),fullPage:true,style:'#toast { visibility:hidden !important; }'});}};
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.getByRole('heading',{name:'把时间凑齐，让协作继续。'}).waitFor();await shot('01-group');
  await go('draft');await shot('02-draft');
  await page.getByRole('button',{name:'发布并开始收集'}).click();
  await page.waitForURL('**/#vote');
  assert.equal(await page.locator('.time-card').count(),3);
  await page.getByRole('button',{name:'保存我的全部答案'}).click();
  await page.getByRole('alert').filter({hasText:'请为每个候选时段'}).waitFor();
  for(const id of [1,2,3]) await page.locator(`input[name="slot-${id}"][value="yes"]`).check();
  await page.locator('input[name="slot-2"][value="maybe"]').check();
  await page.locator('input[name="slot-3"][value="no"]').check();
  assert.equal(await page.locator('#vote-count').textContent(),'3 / 3 块已选');
  await page.locator('input[name="slot-1"][value="yes"]').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('.time-card').first().getAttribute('data-answer'),'maybe');
  await page.keyboard.press('ArrowLeft');
  assert.equal(await page.locator('.time-card').first().getAttribute('data-answer'),'yes');
  await page.locator('#simulate-failure').check();await page.getByRole('button',{name:'保存我的全部答案'}).click();
  await page.getByRole('alert').filter({hasText:'模拟保存失败'}).waitFor();
  assert.equal(await page.locator('input[type=radio]:checked').count(),3);
  assert.deepEqual(await page.locator('input[type=radio]:checked').evaluateAll(inputs=>inputs.map(input=>input.value)),['yes','maybe','no']);
  await shot('03-vote');
  await page.locator('input[name="slot-2"][value="yes"]').check();
  await page.locator('input[name="slot-3"][value="yes"]').check();
  await page.getByRole('button',{name:'保存我的全部答案'}).click();await page.waitForURL('**/#results');
  assert.equal(await page.locator('[data-confirm]').count(),0);
  // Fill the other three accounts without replacing the poll or the owner's answers.
  for(const id of ['chen','lin','zhou']) {
    await page.locator('#user').selectOption(id);await go('vote');
    for(const slot of [1,2,3])await page.locator(`input[name="slot-${slot}"][value="yes"]`).check();
    await page.getByRole('button',{name:'保存我的全部答案'}).click();await page.waitForURL('**/#results');
  }
  await page.locator('#user').selectOption('ma');
  assert.equal(await page.locator('.matrix-piece.yes').count(),12);
  assert.equal(await page.locator('.puzzle-strip .puzzle-piece').count(),12);
  await page.getByRole('button',{name:'关闭收集',exact:true}).click();
  await page.locator('[data-confirm="1"]').click();await page.getByRole('button',{name:'确认并进入会议'}).click();
  await page.waitForURL('**/#meeting');
  await page.locator('textarea[name="agenda"]').fill('确认第一版需求与分工');
  await page.locator('textarea[name="minutes"]').fill('本次结论：第一版聚焦本地桌面使用。\n陈明强复核时间填写页，马若曦整理需求边界。\n下次讨论前，双方在任务列表更新进度。');
  await page.getByRole('button',{name:'保存议程与纪要'}).click();
  for(const [title,assignee] of [['复核时间填写页','chen'],['整理需求边界','ma']]) {
    await page.locator('#task-form input[name="title"]').fill(title);
    await page.locator('#task-form select[name="assignee"]').selectOption(assignee);
    await page.getByRole('button',{name:'＋ 创建任务',exact:true}).click();
  }
  assert.equal(await page.locator('[data-task]').count(),2);await shot('06-meeting');
  await page.locator('textarea[name="minutes"]').fill('纯文本安全检查：<script>window.injected = true</script>');
  await page.getByRole('button',{name:'保存议程与纪要'}).click();
  await page.locator('#user').selectOption('chen');
  assert.equal(await page.locator('textarea[name="minutes"]').getAttribute('readonly'),'');
  assert.equal(await page.locator('#task-form').count(),0);
  await go('tasks');assert.equal(await page.locator('[data-task]').count(),1);
  await page.locator('[data-task="1"]').selectOption('DONE');assert.equal(await page.locator('[data-task]').count(),0);
  await page.locator('#include-done').check();await page.locator('[data-task="1"]').selectOption('TODO');
  await page.locator('#include-done').uncheck();assert.equal(await page.locator('[data-task]').count(),1);
  await shot('07-personal-tasks');await go('meeting');
  assert.equal(await page.locator('[data-task="1"]').inputValue(),'TODO');
  await page.reload();assert.equal(await page.locator('[data-task]').count(),2);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  // Warning scenarios, non-first selection and the required confirmation fields.
  await page.locator('#scenario').selectOption('unknown');await page.waitForURL('**/#results');
  assert.equal(await page.locator('.matrix-piece.unknown').count(),3);
  assert.equal(await page.locator('.puzzle-strip .puzzle-piece.unknown').count(),3);
  await page.getByText('必到成员 陈明强 尚未填写。',{exact:true}).waitFor();await shot('04-required-unknown');
  await page.getByRole('button',{name:'关闭收集',exact:true}).click();await page.locator('[data-confirm="1"]').click();
  assert.equal(await page.locator('#confirm-form textarea[required]').count(),1);
  await page.getByRole('button',{name:'返回讨论'}).click();
  await page.locator('#scenario').selectOption('conflict');await shot('05-all-conflict');
  await page.getByText('所有候选时段都有必到冲突。',{exact:true}).waitFor();
  await page.locator('[data-confirm="1"]').click();
  await page.locator('#confirm-form textarea').fill('已线下协调，由成员会后补充意见。');
  await page.locator('#confirm-form input[type=checkbox]').check();await shot('08-confirm-risk');
  await page.getByRole('button',{name:'确认并进入会议'}).click();await page.waitForURL('**/#meeting');
  // Desktop minimum viewport: the page itself should not scroll horizontally.
  await page.setViewportSize({width:1280,height:720});await go('results');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  // A narrow/resized window must not let positioned cards cover the fixed nav.
  for(const width of [1024,800,640]) {
    await page.setViewportSize({width,height:width===640?520:720});
    for(const view of ['group','vote','results']) {
    await go(view);
    await page.evaluate(()=>window.scrollTo(220,180));
    const layout=await page.evaluate(()=>{
      const sidebar=document.querySelector('.sidebar'), rect=sidebar.getBoundingClientRect();
      const points=[120,300,500].filter(y=>y<innerHeight);
      return { overflow:document.documentElement.scrollWidth>innerWidth,
        navOnTop:points.every(y=>sidebar.contains(document.elementFromPoint(rect.width/2,y))) };
    });
    assert.equal(layout.navOnTop,true,`Sidebar hit targets covered at ${width}px`);
    assert.equal(layout.overflow,false,`Whole-page horizontal overflow at ${width}px`);
    await page.evaluate(()=>window.scrollTo(0,0));
    }
  }
  await go('group');
  await shot('09-compact-window');
  // Fifteen candidates stay in a locally scrolling board, without squeezing labels.
  await page.evaluate(()=>{
    const key='meetflow-t02-prototype-v1', s=JSON.parse(localStorage.getItem(key));
    const start=new Date(s.slots[0].start).getTime();
    s.slots=Array.from({length:15},(_,i)=>({id:i+1,start:new Date(start+i*86400000).toISOString(),end:new Date(start+i*86400000+3600000).toISOString()}));
    s.votes={};s.status='OPEN';s.meeting=null;s.tasks=[];
    localStorage.setItem(key,JSON.stringify(s));
  });
  await page.reload();await go('results');
  assert.equal(await page.locator('.matrix-piece').count(),60);
  assert.ok(await page.locator('.matrix-wrap').evaluate(el=>el.scrollWidth>el.clientWidth));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS: four accounts, keyboard choices, mixed-answer failed-save retention, puzzle states, 15 slots, close/confirm, minutes, tasks, permissions, reopen, persistence, warnings, XSS text; 1280×720, 1024px, 800px, 640×520 nav stacking and overflow.');
  if(saveScreenshots)console.log('Saved 9 screenshots to Docs/images/prototype.');
} finally { if(browser)await browser.close();await new Promise(resolve=>server.close(resolve)); }
