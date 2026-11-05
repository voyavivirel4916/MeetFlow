const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const width of [1440,975,390]){
  await page.setViewportSize({width,height:1000});
  await page.goto('http://localhost:8770/');
  await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.locator('h1').innerText(),'时间凑好，\n事情做好。');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  for(const name of ['工作台','时间矩阵','我的任务']){
   await page.getByRole('tab',{name:new RegExp(name)}).click();
   assert.equal(await page.locator('[role=tabpanel]:visible').count(),1);
   const image=page.locator('[role=tabpanel]:visible img');
   await image.scrollIntoViewIfNeeded();
   await image.evaluate(e=>e.decode());
   assert(await image.evaluate(e=>e.naturalWidth>0));
  }
  await page.getByRole('tab',{name:/工作台/}).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('tab',{name:/时间矩阵/}).getAttribute('aria-selected'),'true');
  await page.locator('summary').first().click();assert(await page.locator('details').first().getAttribute('open')!==null);
  await page.getByRole('tab',{name:/工作台/}).click();
  await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:`Src/backend/data/presentation-work/site-${width}.png`,fullPage:true});
 }
 const download=await page.request.get('http://localhost:8770/downloads/MeetFlow-Windows-Demo.zip');
 assert.equal(download.status(),200);assert((await download.body()).length>1000000);
 assert.deepEqual(errors,[]);
 fs.writeFileSync('Site/checks.json',JSON.stringify({date:'2026-11-05',viewports:[1440,975,390],screenshots:'真实本地演示数据',tabs:true,keyboard:true,faq:true,download:true,horizontalOverflow:false,pageErrors:[]},null,2));
 await browser.close();console.log('Project site: responsive layouts, screenshots, tabs, keyboard, FAQ and download passed.');
})().catch(e=>{console.error(e);process.exit(1)});
