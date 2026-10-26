// Render local Mermaid sources to portable SVG/PNG and a static review gallery.
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, dirname, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const require=createRequire(import.meta.url);
const { chromium }=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const toolRoot=dirname(fileURLToPath(import.meta.url));
const root=resolve(toolRoot,'../../..');
const sourceDir=resolve(root,'Docs/diagrams/t03');
const output=resolve(root,'Docs/images/t03');
const catalog=JSON.parse(await readFile(resolve(sourceDir,'catalog.json'),'utf8'));
const mermaidPackage=JSON.parse(await readFile(resolve(toolRoot,'node_modules/mermaid/package.json'),'utf8'));
const sha=source=>createHash('sha256').update(source).digest('hex');
const escape=text=>text.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const server=createServer(async(req,res)=>{
  if(req.url==='/') {res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'}).end('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><body></body></html>');return;}
  const path=resolve(toolRoot,'.'+new URL(req.url,'http://localhost').pathname);
  if(!path.startsWith(toolRoot+sep)){res.writeHead(403).end();return;}
  try {const data=await readFile(path);res.writeHead(200,{'Content-Type':['.js','.mjs'].includes(extname(path))?'text/javascript':'application/octet-stream'}).end(data);}catch{res.writeHead(404).end();}
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
let browser;
try {
  browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1800,height:1200},deviceScaleFactor:1});
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.evaluate(async()=>{
    const {default:mermaid}=await import('/node_modules/mermaid/dist/mermaid.esm.min.mjs');
    window.mermaid=mermaid;
    mermaid.initialize({startOnLoad:false,securityLevel:'strict',htmlLabels:false,theme:'base',fontFamily:'Microsoft YaHei, Segoe UI, sans-serif',
      themeVariables:{fontSize:'17px',primaryColor:'#f0eff7',primaryTextColor:'#303755',primaryBorderColor:'#9399bf',lineColor:'#8185a1',secondaryColor:'#f9eddb',tertiaryColor:'#fbfaf6',noteBkgColor:'#fff2da',noteTextColor:'#625741',actorBkg:'#efedf7',actorBorder:'#9399bf',actorTextColor:'#303755',edgeLabelBackground:'#fffdfa'},
      flowchart:{htmlLabels:false,useMaxWidth:false,nodeSpacing:30,rankSpacing:50},
      sequence:{useMaxWidth:false,actorFontSize:16,messageFontSize:15,noteFontSize:14,wrap:false,diagramMarginX:30,diagramMarginY:25},
      er:{useMaxWidth:false,fontSize:16,entityPadding:15}});
  });
  await mkdir(output,{recursive:true});
  const rendered=[];
  for(const diagram of catalog.diagrams) {
    const source=(await readFile(resolve(sourceDir,diagram.id+'.mmd'),'utf8')).replace(/\r\n/g,'\n');
    const digest=sha(source);
    const result=await page.evaluate(async({source,id})=>{
      const rendered=await window.mermaid.render('mf'+id.replaceAll('-',''),source);
      const holder=document.createElement('div');holder.innerHTML=rendered.svg;
      const svg=new XMLSerializer().serializeToString(holder.querySelector('svg'));
      const doc=new DOMParser().parseFromString(svg,'image/svg+xml');
      if(doc.querySelector('parsererror'))throw new Error(doc.querySelector('parsererror').textContent+' SVG prefix: '+svg.slice(0,350));
      const el=doc.documentElement, view=el.getAttribute('viewBox').split(/\s+/).map(Number);
      const width=Math.ceil(view[2])+2,height=Math.ceil(view[3])+2;
      el.setAttribute('width',String(width));el.setAttribute('height',String(height));el.style.maxWidth='none';
      return {svg:new XMLSerializer().serializeToString(el),width,height};
    },{source,id:diagram.id});
    const svg=result.svg.replace('<svg ',`<svg data-source-sha256="${digest}" aria-label="${escape(diagram.title)}" `);
    await writeFile(resolve(output,diagram.id+'.svg'),svg);
    const ratio=Math.min(1,2400/result.width,3600/result.height);
    const width=Math.ceil(result.width*ratio),height=Math.ceil(result.height*ratio);
    await page.setViewportSize({width:width+40,height:height+40});
    await page.evaluate(({svg,width,height})=>{
      document.body.style.cssText='margin:0;background:#fffdfa';
      const stage=document.createElement('div');stage.id='stage';stage.style.cssText=`width:${width}px;height:${height}px;background:#fffdfa;overflow:hidden`;
      stage.innerHTML=svg;document.body.replaceChildren(stage);
      const el=stage.querySelector('svg');el.style.cssText=`display:block;max-width:none;width:${width}px;height:${height}px`;
    },{svg,width,height});
    await page.evaluate(()=>document.fonts.ready);
    const png=await page.locator('#stage').screenshot({animations:'disabled'});
    await writeFile(resolve(output,diagram.id+'.png'),png);
    rendered.push({...diagram,source:`../../diagrams/t03/${diagram.id}.mmd`,sha256:digest,svg_sha256:sha(svg),png_sha256:sha(png),width,height});
    console.log(`OK ${diagram.id}: ${width}x${height}`);
  }
  await writeFile(resolve(output,'manifest.json'),JSON.stringify({baseline:catalog.baseline,mermaid_version:mermaidPackage.version,diagrams:rendered},null,2)+'\n');
  const cards=rendered.map(d=>`<section id="${d.id}"><div class="caption"><h2>${escape(d.title)}</h2><span>${d.requirements.join(' · ')}</span></div><div class="links"><a href="../../images/t03/${d.id}.svg" target="_blank">打开矢量图 / 缩放查看</a><a href="../../images/t03/${d.id}.png" target="_blank">PNG</a><a href="${d.id}.mmd">Mermaid图源</a></div><a href="../../images/t03/${d.id}.svg" target="_blank"><img src="../../images/t03/${d.id}.svg" alt="${escape(d.title)}" loading="lazy"></a></section>`).join('\n');
  await writeFile(resolve(sourceDir,'index.html'),`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MeetFlow · T03设计图</title><style>body{margin:0;background:#f5f3ed;color:#303755;font:14px "Microsoft YaHei",sans-serif}main{max-width:1280px;margin:auto;padding:40px 28px}h1{font-size:30px}p{line-height:1.9;color:#7c7786}nav{display:flex;flex-wrap:wrap;gap:12px;margin:25px 0}a{color:#535d9a}nav a{padding:9px 12px;background:white;border-radius:5px;text-decoration:none}section{background:#fffdfa;border:1px solid #e1ddd8;border-radius:10px;padding:25px;margin:25px 0;scroll-margin:15px}.caption{display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}.caption h2{font-size:19px}.caption span{font-size:10px;color:#a59aaa}.links{display:flex;gap:18px;font-size:12px;margin:12px 0 22px}img{display:block;width:100%;height:auto;max-height:1100px;object-fit:contain;object-position:top}footer{font-size:12px;color:#9991a0;margin-top:30px}</style></head><body><main><p>MEETFLOW / T03 · 2026-10-26</p><h1>让需求、原型和设计对上。</h1><p>${escape(catalog.baseline)}。图示表达计划中的正式系统；原型的演示与简化项见15号核对记录。点击图片可单独打开矢量图并缩放，PNG可直接放入报告。</p><nav>${rendered.map(d=>`<a href="#${d.id}">${escape(d.title)}</a>`).join('')}</nav>${cards}<footer>本页只使用仓库中的本地图片，无外部资源。图源与导出哈希见 Docs/images/t03/manifest.json。</footer></main></body></html>\n`);
} finally {if(browser)await browser.close();await new Promise(done=>server.close(done));}
