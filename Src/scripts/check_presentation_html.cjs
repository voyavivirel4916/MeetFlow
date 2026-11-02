const {chromium}=require('playwright');
const path=require('path'),fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const remote=[];page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url())});
 await page.goto(require('url').pathToFileURL(path.resolve('Presentation/MeetFlow-网页演示.html')).href);
 await page.evaluate(()=>document.fonts.ready);
 const allErrors=[];
 for(let i=0;i<9;i++){
  assert.equal(await page.locator('.slide.active').count(),1);
  const errors=await page.locator('.slide.active').evaluate(s=>[...s.querySelectorAll('.item:not(svg)')].filter(e=>e.offsetLeft<0||e.offsetTop<0||e.offsetLeft+e.offsetWidth>1921||e.offsetTop+e.offsetHeight>1081||e.scrollHeight>e.clientHeight+3).map(e=>({text:e.textContent,height:e.clientHeight,scroll:e.scrollHeight,font:getComputedStyle(e).fontSize})));
  if(errors.length) allErrors.push({slide:i+1,errors});
  if(i<8)await page.keyboard.press('ArrowRight');
 }
 if(allErrors.length) console.error(JSON.stringify(allErrors));
 assert.deepEqual(allErrors,[],'slides must have no out-of-bounds or clipped content');
 assert.equal(await page.locator('#page').innerText(),'9 / 9');
 await page.keyboard.press('Home');assert.equal(await page.locator('#page').innerText(),'1 / 9');
 await page.setViewportSize({width:888,height:704});
 assert(await page.locator('.deck-stage').evaluate(e=>getComputedStyle(e).transform.startsWith('matrix(')));
 assert.deepEqual(remote,[],'offline deck must not load external resources');
 fs.writeFileSync('Presentation/html-check.json',JSON.stringify({slides:9,offline:true,navigation:true,viewports:['1440x900','888x704'],overflow_risks:[]},null,2));
 await browser.close();console.log('HTML: 9 slides, offline resources, navigation, viewport scaling and overflow checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
