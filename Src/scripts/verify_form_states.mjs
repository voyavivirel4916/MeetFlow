// Verify the T04 specification examples independently of the business prototype.
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { readFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const html=await readFile(resolve(root,'Docs/ui/form-states.html'));
const server=createServer((req,res)=>res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'}).end(html));
await new Promise(done=>server.listen(0,'127.0.0.1',done));
let browser;
try{
 browser=await chromium.launch({channel:process.env.PROTOTYPE_BROWSER||'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 const pick=async state=>page.locator(`[data-scene="${state}"]`).click();
 const save=()=>page.locator('#preview button[type=submit]');
 const screenshot=async name=>{if(process.argv.includes('--screenshots')){const dir=resolve(root,'Docs/images/t04');await mkdir(dir,{recursive:true});await page.screenshot({path:resolve(dir,name+'.png'),fullPage:true});}};
 assert.equal(await page.locator('[data-scene]').count(),9);await screenshot('01-ready');
 await page.locator('#title').fill('需要保留的输入');
 await page.locator('input[value=yes]').focus();await page.keyboard.press('ArrowRight');
 assert.equal(await page.locator('input[value=maybe]').isChecked(),true);
 await pick('dirty');assert.ok((await page.locator('#summary').textContent()).includes('未保存更改'));
 await pick('uncertain');assert.equal(await save().isDisabled(),true);
 assert.equal(await page.locator('#title').inputValue(),'需要保留的输入');
 assert.ok((await page.getByRole('alert').textContent()).includes('尚未确认保存'));
 await pick('expired');assert.equal(await save().isDisabled(),true);
 assert.equal(await page.locator('#title').inputValue(),'需要保留的输入');
 await pick('loading');assert.equal(await page.locator('#preview').getAttribute('aria-busy'),'true');
 assert.equal(await page.evaluate(()=>document.activeElement.dataset.scene),'loading');
 assert.equal(await save().isDisabled(),true);
 for(const scene of ['empty','denied']){await pick(scene);assert.equal(await page.locator('#preview form').count(),0);}
 await pick('error');assert.equal(await page.locator('#title').getAttribute('aria-invalid'),'true');
 assert.equal(await page.evaluate(()=>document.activeElement.id),'summary');
 await page.locator('#locate').click();assert.equal(await page.evaluate(()=>document.activeElement.id),'title');
 await screenshot('02-error');
 await pick('ready');await save().click();assert.equal(await save().isDisabled(),true);
 assert.equal(await page.locator('#preview').getAttribute('aria-busy'),'true');
 await page.getByRole('status').filter({hasText:'已保存 ·'}).waitFor();
 assert.equal(await save().isDisabled(),false);
 const ratios=await page.locator('.chip').evaluateAll(chips=>{
  const luminance=color=>{const v=color.match(/[\d.]+/g).slice(0,3).map(n=>Number(n)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722;};
  return chips.map(chip=>{const s=getComputedStyle(chip),a=luminance(s.color),b=luminance(s.backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);});
 });
 assert.ok(ratios.every(ratio=>ratio>=4.5),'Status text contrast below 4.5:1');
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 await page.setViewportSize({width:800,height:720});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 console.log('PASS T04: 9 states, keyboard choices, error focus, preserved input, blocked duplicate submit, 4.5:1 status text contrast and 800px layout.');
}finally{if(browser)await browser.close();await new Promise(done=>server.close(done));}
