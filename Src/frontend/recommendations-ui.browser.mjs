import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';

export async function verifyRecommendationsUI(browser,origin,{root,screenshots}){
  const contexts=[],errors=[],password='recommendation-password';
  const actor=async username=>{
    const context=await browser.newContext({viewport:{width:1440,height:1000}});contexts.push(context);
    const result=await context.request.post(origin+'/api/v1/auth/register',{data:{username,password,email:username+'@example.com'}});
    assert.equal(result.status(),201);const id=(await result.json()).data.id;
    assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username,password}})).status(),200);
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));return{context,page,id};
  };
  const ready=page=>page.waitForFunction(()=>document.querySelector('.time-matrix')&&!document.querySelector('.group-heading button')?.disabled);
  const refresh=page=>page.getByRole('button',{name:'刷新',exact:true});
  const shot=async(page,name)=>{if(!screenshots)return;await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();window.scrollTo(0,0);});const folder=resolve(root,'Docs/images/t23');await mkdir(folder,{recursive:true});await page.screenshot({path:resolve(folder,name+'.png'),fullPage:true});};
  const reply=(route,status,code,message)=>route.fulfill({status,contentType:'application/json',headers:{'X-Request-ID':'c07e357967c148068a4f9aa539c759e2'},body:JSON.stringify({error:{code,message},request_id:'c07e357967c148068a4f9aa539c759e2'})});
  try{
    const owner=await actor('ranking_owner'),required=await actor('ranking_required'),no=await actor('ranking_busy'),maybe=await actor('ranking_maybe'),observer=await actor('ranking_observer');
    const group=(await(await owner.context.request.post(origin+'/api/v1/groups',{data:{name:'一起把讨论安排好'}})).json()).data;
    for(const user of[required,no,maybe,observer])assert.equal((await user.context.request.post(origin+'/api/v1/groups/join',{data:{invite_code:group.invite_code}})).status(),200);
    const now=Math.floor(Date.now()/60000)*60000;
    const response=await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`,{data:{title:'下一轮方案讨论',location:'计算机大楼2015A',response_deadline:new Date(now+3600_000).toISOString(),
      participants:[owner,required,no,maybe].map((user,index)=>({user_id:user.id,importance:index<2?'REQUIRED':'NORMAL'})),slots:Array.from({length:4},(_,index)=>({start_at:new Date(now+7200_000+index*86400_000).toISOString(),end_at:new Date(now+10800_000+index*86400_000).toISOString()}))}});
    assert.equal(response.status(),201);const poll=(await response.json()).data;
    const url=origin+`/polls/${poll.id}/results`,path=`**/api/v1/polls/${poll.id}/recommendations`,page=owner.page;
    let reads=0;
    await page.route(path,route=>{reads++;return route.continue();});
    await page.goto(url);await page.getByText('发布排期后可以查看推荐时间。',{exact:true}).waitFor();assert.equal(reads,0);
    await page.unroute(path);
    assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/open`,{data:{}})).status(),200);
    const submit=async(user,values)=>assert.equal((await user.context.request.put(origin+`/api/v1/polls/${poll.id}/votes/me`,{data:{votes:poll.slots.map((slot,index)=>({slot_id:slot.id,availability:values[index%values.length]}))}})).status(),200);
    await submit(owner,['AVAILABLE']);await submit(no,['UNAVAILABLE']);await submit(maybe,['MAYBE']);
    await refresh(page).click();await ready(page);
    await page.getByText('还有必到成员未填写，出席情况尚未确定。',{exact:true}).waitFor();
    await page.getByText('每个候选时间都有成员没空，请先查看冲突；排名不代表全员可参加。',{exact:true}).waitFor();
    assert.equal(await page.locator('.recommendation-item').count(),3);
    assert.equal(await page.locator('.recommendation-item .risk-unknown').count(),3);
    assert.equal((await page.locator('.recommendation-score strong').first().innerText()).trim(),'3');
    await page.locator('.recommendation-reason summary').first().click();
    assert.match(await page.locator('.recommendation-reason').first().innerText(),/基础分5.*最终分3/);
    assert.match(await page.locator('.recommendation-reason').first().innerText(),/ranking_busy/);
    assert.doesNotMatch(await page.locator('.recommendation-reason').first().innerText(),/所有参与者均已填写有空/);
    await shot(page,'03-required-unknown');
    await page.getByRole('button',{name:'展开其余 1 个候选',exact:true}).click();assert.equal(await page.locator('.recommendation-item').count(),4);
    await page.getByRole('button',{name:'收起其余候选',exact:true}).click();
    // A saved update does not silently replace the visible recommendations; a failed refresh retains the complete old snapshot.
    await submit(required,['AVAILABLE','MAYBE','UNAVAILABLE','AVAILABLE']);
    await page.route(path,route=>reply(route,503,'STORAGE_UNAVAILABLE','推荐暂时无法读取。'));
    await refresh(page).click();await page.getByRole('heading',{name:'排期结果暂时无法读取',exact:true}).waitFor();
    await page.getByText('3/4 人已提交',{exact:true}).waitFor();assert.equal(await page.locator('.risk-unknown').count(),3);
    await shot(page,'04-read-failure');
    await page.unroute(path);await page.getByRole('button',{name:'重新读取矩阵',exact:true}).click();await ready(page);
    await page.getByText('4/4 人已提交',{exact:true}).waitFor();
    assert.deepEqual(await page.locator('.recommendation-item').evaluateAll(elements=>elements.map(element=>Number(element.dataset.recommendation))),[poll.slots[0].id,poll.slots[3].id,poll.slots[1].id]);
    assert.equal(await page.locator('.risk-unknown').count(),0);assert.equal(await page.locator('.risk-maybe').count(),1);
    await page.getByRole('button',{name:'展开其余 1 个候选',exact:true}).click();assert.equal(await page.locator('.risk-conflict').count(),1);
    assert.equal((await page.locator('.recommendation-score strong').last().innerText()).trim(),'-21');
    await shot(page,'05-ranked-risks');
    for(const width of[1440,1024,800,400]){await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Ranking overflow ${width}`);}
    await page.setViewportSize({width:1440,height:1000});
    await page.route(path,async route=>{const response=await route.fetch();const body=await response.json();body.data.items[0].available_count=99;await route.fulfill({response,body:JSON.stringify(body)});});
    await refresh(page).click();await page.getByText('填写结果已更新或推荐数据不一致，请刷新。',{exact:true}).waitFor();assert.equal(await page.locator('.recommendation-item').count(),4);
    await page.unroute(path);await page.getByRole('button',{name:'重新读取矩阵',exact:true}).click();await ready(page);
    // HTML-like server text remains inert text inside the disclosure.
    await page.route(path,async route=>{const response=await route.fetch();const body=await response.json();body.data.items[0].reason='<img src=x onerror=alert(1)>';await route.fulfill({response,body:JSON.stringify(body)});});
    await refresh(page).click();await ready(page);if(!await page.locator('.recommendation-reason').first().evaluate(element=>element.open))await page.locator('.recommendation-reason summary').first().click();
    await page.getByText('<img src=x onerror=alert(1)>',{exact:true}).waitFor();assert.equal(await page.locator('.recommendations-section img').count(),0);
    await page.unroute(path);await refresh(page).click();await ready(page);
    await observer.page.goto(url);await ready(observer.page);assert.equal(await observer.page.locator('.recommendation-item').count(),3);assert.equal(await observer.page.getByRole('link',{name:'填写我的时间',exact:true}).count(),0);
    await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/close`,{data:{}});await refresh(page).click();await ready(page);assert.equal(await page.locator('.recommendation-item').count(),4);
    await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/cancel`,{data:{}});await refresh(page).click();await page.getByText('排期已取消，不再生成推荐。',{exact:true}).waitFor();assert.equal(await page.locator('.recommendation-item').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS T23 UI: draft/cancel, server ranking/scores/reasons, required unknown/maybe/unavailable and all-conflict warnings, expand/collapse, refresh snapshot consistency, 503/malformed responses, inert server text, member visibility, closed readback and 4 widths.');
  }catch(error){console.error('T23 failure',error,'Page errors:',errors);for(const context of contexts)for(const page of context.pages())if(await page.locator('main').count())console.error(page.url(),(await page.locator('main').innerText({timeout:1000})).slice(0,3000));throw error;}
  finally{for(const context of contexts)await context.close();}
}
