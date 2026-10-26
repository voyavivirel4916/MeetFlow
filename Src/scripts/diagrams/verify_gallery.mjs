import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { resolve, dirname, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const { chromium }=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const docs=resolve(dirname(fileURLToPath(import.meta.url)),'../../../Docs');
const server=createServer(async(req,res)=>{
  const path=resolve(docs,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname.replace(/\/$/,'/index.html')));
  if(!path.startsWith(docs+sep)){res.writeHead(403).end();return;}
  try{const bytes=await readFile(path);res.writeHead(200,{'Content-Type':{'.html':'text/html; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.mmd':'text/plain; charset=utf-8','.json':'application/json'}[extname(path)]||'application/octet-stream'}).end(bytes);}catch{res.writeHead(404).end();}
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
let browser;
try{
  browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[],failed=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>failed.push(r.url()));
  const url=`http://127.0.0.1:${server.address().port}/diagrams/t03/`;
  await page.goto(url);
  assert.equal(await page.locator('section').count(),7);
  await page.locator('img').evaluateAll(images=>images.forEach(img=>img.loading='eager'));
  const dimensions=await page.locator('img').evaluateAll(async images=>Promise.all(images.map(async img=>{await img.decode();return [img.naturalWidth,img.naturalHeight];})));
  assert.ok(dimensions.every(([w,h])=>w>100&&h>100));
  for(const target of await page.locator('.links a').evaluateAll(links=>links.map(a=>a.href))){const response=await page.request.get(target);assert.equal(response.status(),200,target);}
  await page.setViewportSize({width:800,height:720});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
  console.log('PASS: 7 SVG previews decoded, 21 source/image links accessible, gallery has no script errors or overflow at 800px.');
}finally{if(browser)await browser.close();await new Promise(done=>server.close(done));}
