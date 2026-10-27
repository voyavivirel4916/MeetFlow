import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

export async function verifyMatrixUI(browser, origin, { root, screenshots }) {
  const contexts = [], errors = [], password = 'matrix-ui-password';
  const account = async username => {
    const context = await browser.newContext({ viewport:{width:1440,height:1000},timezoneId:'America/Los_Angeles' });
    contexts.push(context);
    const response = await context.request.post(origin+'/api/v1/auth/register',{data:{username,password,email:username+'@example.com'}});
    assert.equal(response.status(),201);
    const id = (await response.json()).data.id;
    assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username,password}})).status(),200);
    const page = await context.newPage(); page.on('pageerror',error=>errors.push(error.message));
    return {context,page,id};
  };
  const refresh = page=>page.getByRole('button',{name:'刷新',exact:true});
  const ready = page=>page.waitForFunction(()=>document.querySelector('.time-matrix') && !document.querySelector('.group-heading button')?.disabled);
  const cell = (page,user,slot)=>page.locator(`td[data-user="${user.id}"][data-slot="${slot.id}"]`);
  const shot = async(page,name)=>{
    if (!screenshots) return;
    const directory = resolve(root,'Docs/images/t20'); await mkdir(directory,{recursive:true});
    await page.screenshot({path:resolve(directory,name+'.png'),fullPage:true});
  };
  const reply = (route,status,code,message)=>route.fulfill({status,contentType:'application/json',headers:{'X-Request-ID':'c07e357967c148068a4f9aa539c759e2'},
    body:JSON.stringify({error:{code,message},request_id:'c07e357967c148068a4f9aa539c759e2'})});
  try {
    const owner = await account('matrix_owner'), member = await account('matrix_member'), idle = await account('matrix_idle'), quiet = await account('matrix_quiet'), observer = await account('matrix_observer'), outside = await account('matrix_outside');
    const group = (await (await owner.context.request.post(origin+'/api/v1/groups',{data:{name:'一起拼出好时间'}})).json()).data;
    for(const actor of [member,idle,quiet,observer]) assert.equal((await actor.context.request.post(origin+'/api/v1/groups/join',{data:{invite_code:group.invite_code}})).status(),200);
    const now = Math.floor(Date.now()/60000)*60000;
    const create = async(title,participants,slots)=>{
      const response = await owner.context.request.post(origin+`/api/v1/groups/${group.id}/polls`,{data:{title,description:'确定方案边界，安排下一轮分工。',location:'计算机大楼2015A',response_deadline:new Date(now+3600_000).toISOString(),participants,slots}});
      assert.equal(response.status(),201); return (await response.json()).data;
    };
    const times = Array.from({length:3},(_,i)=>({start_at:new Date(now+7200_000+i*86400_000).toISOString(),end_at:new Date(now+10800_000+i*86400_000).toISOString()}));
    const poll = await create('课程方案评审',[owner,member,idle,quiet].map((person,index)=>({user_id:person.id,importance:index<2?'REQUIRED':'NORMAL'})),times);
    assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/open`,{data:{}})).status(),200);
    const submit = async(actor,values)=>{
      const response = await actor.context.request.put(origin+`/api/v1/polls/${poll.id}/votes/me`,{data:{votes:poll.slots.map((slot,index)=>({slot_id:slot.id,availability:values[index%values.length]}))}});
      assert.equal(response.status(),200);
    };
    await submit(owner,['AVAILABLE','MAYBE','UNAVAILABLE']);
    await submit(member,['MAYBE','UNAVAILABLE','AVAILABLE']);
    await submit(quiet,['UNAVAILABLE','AVAILABLE','MAYBE']);
    const page = owner.page, groupUrl = origin+`/groups/${group.id}`, url = origin+`/polls/${poll.id}/results`, path = `**/api/v1/polls/${poll.id}/matrix`;
    await page.goto(groupUrl); await page.getByRole('link',{name:'查看矩阵 →',exact:true}).click(); await ready(page);
    await page.getByText('3/4 人已提交',{exact:true}).waitFor();
    assert.match(await page.getByText(/^未提交：/).innerText(),/matrix_idle/);
    assert.equal((await cell(page,owner,poll.slots[0]).innerText()).replace(/\s+/g,' ').trim(),'✓ 有空');
    assert.equal((await cell(page,owner,poll.slots[1]).innerText()).replace(/\s+/g,' ').trim(),'~ 勉强');
    assert.equal((await cell(page,owner,poll.slots[2]).innerText()).replace(/\s+/g,' ').trim(),'× 没空');
    assert.equal((await cell(page,idle,poll.slots[0]).innerText()).replace(/\s+/g,' ').trim(),'— 未填');
    assert.equal(await page.locator('.matrix-me').count(),1);
    const nameBox=await page.locator('.matrix-me .matrix-person-name strong').boundingBox();
    const badgeBox=await page.locator('.matrix-me .role-badge').boundingBox();
    assert.ok(Math.abs((nameBox.y+nameBox.height/2)-(badgeBox.y+badgeBox.height/2))<2,'Required badge aligns beside name');
    assert.ok(badgeBox.x>nameBox.x,'Required badge is on the right');
    assert.equal(await page.locator('.time-matrix tbody .matrix-state').first().evaluate(element=>getComputedStyle(element).fontSize),'15px');
    assert.equal(await page.locator('.time-matrix tbody tr').count(),4);
    assert.equal(await page.locator('.time-matrix tbody td[data-slot]').count(),12);
    assert.equal((await page.locator('.slot-counts').first().innerText()).replace(/\s+/g,' '),'有空 1 勉强 1 没空 1 未填 1');
    assert.match(await page.locator('.time-matrix thead').innerText(),/\d{4}-\d{2}-\d{2}/);
    await shot(page,'03-matrix');
    // Self entry, unsaved choices stay outside group statistics.
    await page.getByRole('link',{name:'填写我的时间',exact:true}).click();
    await page.locator('.vote-fields:not([disabled])').waitFor();
    await page.locator(`#vote-${poll.slots[0].id}-UNAVAILABLE`).check();
    page.once('dialog',dialog=>dialog.accept()); await page.getByRole('link',{name:'查看时间矩阵 →',exact:true}).click(); await ready(page);
    assert.match(await cell(page,owner,poll.slots[0]).innerText(),/有空/);
    await submit(idle,['AVAILABLE']);
    await page.getByText('3/4 人已提交',{exact:true}).waitFor();
    await refresh(page).click(); await page.getByText('4/4 人已提交',{exact:true}).waitFor();
    await page.getByText('所有参与者均已提交。',{exact:true}).waitFor();
    assert.match(await cell(page,idle,poll.slots[0]).innerText(),/有空/);
    // Busy refresh: one read, old results labelled as stale and button disabled.
    let reads = 0, release;
    const delay = new Promise(done=>{release=done;});
    await page.route(path,async route=>{reads++;await delay;await route.continue();});
    await refresh(page).click();
    await page.getByRole('button',{name:'正在刷新…',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'正在刷新…',exact:true}).isDisabled(),true);
    await page.getByText('下方保留上次读取的结果，请刷新成功后再核对。',{exact:true}).waitFor();
    release(); await ready(page); await page.unroute(path); assert.equal(reads,1);
    // Server read error keeps the old snapshot, never pretends it is empty.
    await page.route(path,route=>reply(route,503,'STORAGE_UNAVAILABLE','暂时无法读取矩阵。'));
    await refresh(page).click(); await page.getByRole('heading',{name:'时间矩阵暂时无法读取',exact:true}).waitFor();
    assert.equal(await page.locator('.time-matrix tbody tr').count(),4);
    await shot(page,'04-stale');
    await page.unroute(path); await page.getByRole('button',{name:'重新读取矩阵',exact:true}).click(); await ready(page);
    // A malformed 200 with fabricated progress is also a failed refresh.
    await page.route(path,async route=>{const response=await route.fetch();const body=await response.json();body.data.progress.submitted_count=99;await route.fulfill({response,body:JSON.stringify(body)});});
    await refresh(page).click(); await page.getByText('矩阵数据不完整或统计不一致，请重新读取。',{exact:true}).waitFor();
    await page.getByText('4/4 人已提交',{exact:true}).waitFor();
    await page.unroute(path); await page.getByRole('button',{name:'重新读取矩阵',exact:true}).click(); await ready(page);
    // A 404 during refresh clears the old private snapshot.
    await page.route(path,route=>reply(route,404,'NOT_FOUND','未找到可访问的排期。'));
    await refresh(page).click(); await page.getByRole('heading',{name:'未找到可访问的排期',exact:true}).waitFor();
    assert.equal(await page.locator('.time-matrix').count(),0);
    assert.equal(await page.getByText(poll.title,{exact:true}).count(),0);
    await page.unroute(path); await page.getByRole('button',{name:'重新读取矩阵',exact:true}).click(); await ready(page);
    // Group members outside the participant roster can read; strangers cannot.
    await observer.page.route(path,route=>route.abort()); await observer.page.goto(url);
    await observer.page.getByRole('heading',{name:'时间矩阵暂时无法读取',exact:true}).waitFor();
    assert.equal(await observer.page.locator('.matrix-progress').count(),0);
    await observer.page.unroute(path); await observer.page.getByRole('button',{name:'重新读取矩阵',exact:true}).click(); await ready(observer.page);
    assert.equal(await observer.page.getByRole('link',{name:'填写我的时间',exact:true}).count(),0);
    assert.equal(await observer.page.locator('.time-matrix tbody tr').count(),4);
    await outside.page.goto(url); await outside.page.getByRole('heading',{name:'未找到可访问的排期',exact:true}).waitFor();
    assert.equal(await outside.page.locator('.time-matrix').count(),0);
    // Draft with no participants/times is an empty state, not a failed request.
    const empty = await create('尚未完善的草稿',[],[]);
    await observer.page.goto(origin+`/polls/${empty.id}/results`);
    await observer.page.getByText('负责人尚未选择参与者。',{exact:true}).waitFor();
    await observer.page.getByText('0/0 人已提交',{exact:true}).waitFor();
    assert.equal(await observer.page.locator('.time-matrix').count(),0);
    assert.equal(await observer.page.getByText('所有参与者均已提交。',{exact:true}).count(),0);
    // 20 participants and 15 candidates: bounded page width, horizontal scroll and sticky names.
    const all = [owner,member,idle,quiet,observer].map(actor=>actor.id);
    for(let i=0;i<15;i++){
      const context=await browser.newContext();
      try{
        const username=`matrix_seed_${String(i).padStart(2,'0')}`;
        const registered=await context.request.post(origin+'/api/v1/auth/register',{data:{username,password,email:username+'@example.com'}});
        assert.equal(registered.status(),201);all.push((await registered.json()).data.id);
        assert.equal((await context.request.post(origin+'/api/v1/auth/login',{data:{username,password}})).status(),200);
        assert.equal((await context.request.post(origin+'/api/v1/groups/join',{data:{invite_code:group.invite_code}})).status(),200);
      }finally{await context.close();}
    }
    const maximum = await create('20人的时间拼图',all.map(user_id=>({user_id,importance:'NORMAL'})),Array.from({length:15},(_,i)=>({start_at:new Date(now+7200_000+i*86400_000).toISOString(),end_at:new Date(now+10800_000+i*86400_000).toISOString()})));
    await page.goto(origin+`/polls/${maximum.id}/results`); await ready(page);
    assert.equal(await page.locator('.time-matrix tbody tr').count(),20);
    assert.equal(await page.locator('.time-matrix tbody td[data-slot]').count(),300);
    await page.getByText('0/20 人已提交',{exact:true}).waitFor();
    for(const width of [1440,1024,800,400]){
      await page.setViewportSize({width,height:1000});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Matrix page overflow ${width}`);
      const region=page.getByRole('region',{name:'时间矩阵，可横向滚动',exact:true});
      await region.focus(); await page.keyboard.press('ArrowRight');
      await page.waitForFunction(()=>document.querySelector('.matrix-scroll').scrollLeft>0);
      const before=await page.locator('.time-matrix tbody th').first().boundingBox();
      await region.evaluate(element=>{element.scrollLeft=700;});
      const after=await page.locator('.time-matrix tbody th').first().boundingBox();
      assert.ok(Math.abs(before.x-after.x)<2,'Names stay fixed while scrolling');
      await region.evaluate(element=>{element.scrollLeft=0;});
    }
    await page.setViewportSize({width:1440,height:1000});await shot(page,'05-maximum');
    await page.goto(url);await ready(page);
    assert.equal((await owner.context.request.post(origin+`/api/v1/polls/${poll.id}/close`,{data:{}})).status(),200);
    await refresh(page).click();await ready(page);
    await page.getByText('已关闭',{exact:true}).waitFor();
    assert.equal(await page.getByRole('link',{name:'填写我的时间',exact:true}).count(),0);
    assert.equal(await page.locator('.time-matrix tbody tr').count(),4);
    // Expired session and another account never reuse the old private snapshot.
    await owner.context.request.post(origin+'/api/v1/auth/logout',{data:{}});
    await refresh(page).click();await page.getByRole('heading',{name:'欢迎回来',exact:true}).waitFor();
    await page.locator('#username').fill('matrix_outside');await page.locator('#password').fill(password);await page.locator('button[type=submit]').click();
    await page.getByRole('heading',{name:'未找到可访问的排期',exact:true}).waitFor();
    assert.equal(await page.locator('.time-matrix').count(),0);
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    assert.deepEqual(errors,[]);
    console.log('PASS T20 UI: matrix entries, four states/required/current member, row/column counts/progress, saved-only/manual refresh, stale 503/protocol/404, empty draft, observer/outside rights, 20x15 keyboard scroll/sticky names at 4 widths, closed view and expired/new session.');
  }catch(error){
    console.error('T20 failure',error,'Page errors:',errors);
    for(const context of contexts)for(const page of context.pages())if(await page.locator('main').count())console.error('T20 diagnostic',page.url(),(await page.locator('main').innerText({timeout:1000})).slice(0,2600));
    throw error;
  }finally{for(const context of contexts)await context.close();}
}
