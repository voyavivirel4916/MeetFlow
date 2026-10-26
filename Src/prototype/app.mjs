import { people, choices, fresh, scenario, rank, effectiveStatus, publish, saveVotes, closePoll, cancelPoll, risk, confirmMeeting, saveMinutes, addTask, setTaskStatus, personalTasks, validateDraft, futureDate } from './model.mjs';

const $ = (q) => document.querySelector(q);
const key = 'meetflow-t02-prototype-v1';
let state = fresh(), dirty=false, includeDone=false;
try { const saved=JSON.parse(localStorage.getItem(key)); if(saved?.version===1) state=saved; } catch { /* Start with fresh demo data. */ }
const esc = (s) => String(s??'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const person = id => people.find(p=>p.id===id);
const date = s => s ? new Date(s).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'short'}) : '';
const time = s => s ? new Date(s).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false}) : '';
const when = slot => `${date(slot.start)} · ${time(slot.start)}–${time(slot.end)}`;
const names={group:'我的小组',draft:'发起排期',vote:'填写时间',results:'时间与推荐',meeting:'会议与任务',tasks:'我的待办'};
const statuses={DRAFT:'草稿',OPEN:'收集中',CLOSED:'已关闭',CONFIRMED:'已确认',CANCELLED:'已取消'};
const taskNames={TODO:'待办',IN_PROGRESS:'进行中',DONE:'已完成'};
const me=()=>state.user==='ma';
const status=()=>effectiveStatus(state);
const badge=()=>`<span class="pill ${status().toLowerCase()}">${statuses[status()]}</span>`;
const persist=()=>{ localStorage.setItem(key,JSON.stringify(state)); dirty=false; };
const notify=(message)=>{ $('#toast').textContent=message; $('#toast').classList.add('visible'); clearTimeout(notify.timer); notify.timer=setTimeout(()=>$('#toast').classList.remove('visible'),4000); };
const heading=(title, subtitle, actions='')=>`<div class="page-heading"><div><div class="eyebrow">MEETFLOW / 小组协作</div><h1>${title}</h1><p class="muted">${subtitle}</p></div><div class="actions">${actions}</div></div>`;
const button=(text, id, primary=false)=>`<button class="button ${primary?'primary':''}" id="${id}">${text}</button>`;
const empty=(title, description, link='', label='')=>`<div class="panel empty"><span class="empty-icon">◷</span><h2>${title}</h2><p>${description}</p>${link?`<a class="button primary" href="#${link}">${label}</a>`:''}</div>`;
const stepper=(n)=>`<div class="stepper">${['设置排期','填写时间','推荐与确认','会议与跟进'].map((t,i)=>`${i?'<b></b>':''}<span class="${n===i?'current':''}"><i>${i+1}</i>${t}</span>`).join('')}</div>`;
const progress=()=>state.participants.filter(id=>state.votes[id]?.length===state.slots.length).length;
function failure(message, scope='app') { const el=document.querySelector(`#${scope} .error-box`); if(el){el.textContent=message;el.classList.remove('hidden');el.setAttribute('role','alert');}else notify(message); }
function perform(fn, success, rerender=true) {
  try { fn();persist();if(rerender)render();if(success)notify(success);return true; } catch(e) {failure(e.message);return false;}
}
function navigate(view){location.hash=view;if(location.hash===`#${view}`)render();}
function leave(){ return !dirty || window.confirm('当前输入尚未保存，确定离开吗？'); }
function groupView() {
  return heading('把时间凑齐，让协作继续。','一个小组，一次共识，一份能持续跟进的行动清单。',me()?'<a class="button primary" href="#draft">＋ 发起排期</a>':'')+`
  <div class="two-col"><div><section class="panel hero"><div class="section-label">当前小组 / COURSE PROJECT</div><h2>软件工程 · MeetFlow 项目组</h2><p>从第一版需求评审开始，把讨论变成有负责人、有截止时间的具体行动。</p><a class="button" href="#${status()==='DRAFT'?'draft':status()==='CONFIRMED'?'meeting':'results'}">进入当前协作 <span>↗</span></a><div class="statline"><span><strong>04</strong> 演示成员</span><span><strong>01</strong> 当前排期</span><span><strong>${String(state.tasks.filter(t=>t.status!=='DONE').length).padStart(2,'0')}</strong> 待跟进任务</span></div></section>
  <section class="panel"><div class="panel-title"><div><h2>当前排期</h2><p class="muted">每个人的时间，都值得被看见。</p></div>${badge()}</div><div class="poll-card"><div class="date-tile">候选时间<strong>${new Date(state.slots[0].start).getDate()}</strong>日起</div><div><h3>${esc(state.title)}</h3><p class="muted">${state.slots.length} 个候选时段 · ${state.participants.length} 位参与者</p></div><a class="button small" href="#${status()==='DRAFT'?'draft':status()==='CONFIRMED'?'meeting':'results'}">查看详情 →</a></div><div class="progress"><span style="width:${progress()/state.participants.length*100}%"></span></div><p class="muted">${progress()} / ${state.participants.length} 人已提交${status()==='DRAFT'?' · 发布后开始收集':''}</p></section>
  <div class="note">先约好时间，再把共识带到下一步。会议确认后，可以保存纪要并分配任务。</div></div>
  <aside><section class="panel"><div class="panel-title"><h2>小组成员</h2><span class="pill">4 人</span></div>${people.map(p=>`<div class="member"><span class="avatar">${p.short}</span><div><strong>${p.name}</strong><p>${p.id===state.user?'当前模拟账号':p.role==='演示成员'?'用于展示四人协作':'项目组成员'}</p></div><span class="pill">${p.id==='ma'?'负责人':'成员'}</span></div>`).join('')}</section><section class="panel"><h3>这次协作如何进行？</h3><ol class="aside-list"><li>负责人设置候选与必到成员</li><li>每位参与者填写空闲状态</li><li>查看推荐并确认会议</li><li>保存纪要，持续跟进任务</li></ol></section></aside></div>`;
}
function draftView() {
  if(status()!=='DRAFT') return heading('排期设置', '已发布的候选时间和参与者保持固定。')+stepper(0)+empty(`当前排期${statuses[status()]}`, '可以查看时间矩阵和推荐结果。需要重新体验创建流程，可使用上方“重置演示”。','results','查看结果');
  if(!me())return heading('排期设置','由小组负责人发起排期。')+empty('当前账号没有编辑权限','切换到马若曦，可以体验负责人设置排期的流程。');
  return heading('为下一次讨论，找到共同时间。','先确定参与者与候选时段，发布后开始收集。')+stepper(0)+`<form id="draft-form"><div class="two-col"><section class="panel"><div class="panel-title"><h2>排期信息</h2><span class="pill">草稿</span></div><label class="field">排期主题<input name="title" maxlength="100" value="${esc(state.title)}" required></label><label class="field">讨论说明<textarea name="description" maxlength="2000">${esc(state.description)}</textarea></label><label class="field">收集截止时间（北京时间）<input type="datetime-local" name="deadline" value="${state.deadline}" required></label><div class="panel-title"><h3>候选时段 <span class="muted">${state.slots.length} / 15</span></h3><button class="text-button" type="button" id="add-slot">＋ 添加时段</button></div><div class="muted" style="margin-bottom:12px">开始与结束时间均为北京时间，须晚于收集截止。</div>${state.slots.map((s,i)=>`<div class="slot-edit"><span>${String(i+1).padStart(2,'0')}</span><input aria-label="候选${i+1}开始" type="datetime-local" name="start-${s.id}" value="${s.start}" required><input aria-label="候选${i+1}结束" type="datetime-local" name="end-${s.id}" value="${s.end}" required><button class="text-button" type="button" data-remove="${s.id}" aria-label="删除候选${i+1}">×</button></div>`).join('')}<div class="error-box hidden"></div><div class="form-foot"><span class="muted">发布后，候选时段与参与者不可修改。</span><div class="actions"><button class="button" name="intent" value="save">保存草稿</button><button class="button primary" name="intent" value="publish">发布并开始收集 →</button></div></div></section><aside><section class="panel"><div class="panel-title"><h2>谁来参加？</h2><span class="pill">必到权重 3</span></div><p class="muted">勾选参与者，并标记需要优先协调的必到成员。</p>${people.map(p=>`<div class="check-row"><input id="part-${p.id}" type="checkbox" name="participant" value="${p.id}" ${state.participants.includes(p.id)?'checked':''}><label for="part-${p.id}">${p.name}</label><label><input aria-label="${p.name}必到" type="checkbox" name="required" value="${p.id}" ${state.required.includes(p.id)?'checked':''}> 必到</label></div>`).join('')}</section><div class="note">必到成员的“没空”和“未填写”会单独提示，推荐不会替你自动确认会议。</div></aside></div></form>`;
}
function voteView() {
  if(['DRAFT','CANCELLED'].includes(status())) return heading('填写你的空闲时间','每个人都提交后，更容易找到合适的共同时间。')+empty(status()==='DRAFT'?'排期尚未发布':'排期已取消','等待负责人发布有效排期后，参与者即可填写。',me()?'draft':'group',me()?'设置并发布':'返回小组');
  if(!state.participants.includes(state.user))return empty('你不是本次排期参与者','可以查看组内结果，但不能代替参与者填写。','results','查看结果');
  const editable=status()==='OPEN', answers=state.votes[state.user]||[];
  return heading('这几个时间，你方便吗？',esc(state.title),badge())+stepper(1)+`<div class="two-col"><section class="panel"><div class="panel-title"><div><h2>${person(state.user).name}的空闲状态</h2><p class="muted">${answers.length?'已提交，可在截止前修改本人答案。':'逐项选择后，一次提交全部答案。'}</p></div><span class="pill">${state.slots.length} 个时段</span></div>${!editable?'<div class="note warn">收集已结束，当前答案只读。可以继续查看推荐结果。</div>':''}<form id="vote-form">${state.slots.map((s,i)=>`<div class="vote-row"><div><strong>${date(s.start)}</strong><p>${time(s.start)} — ${time(s.end)} · 候选 ${i+1}</p></div><div class="segmented" role="group" aria-label="候选${i+1}空闲状态">${Object.entries(choices).map(([val,label])=>`<label><input type="radio" name="slot-${s.id}" value="${val}" ${answers[i]===val?'checked':''} ${editable?'':'disabled'}><span>${val==='yes'?'✓':val==='maybe'?'~':'×'} ${label}</span></label>`).join('')}</div></div>`).join('')}<div class="error-box hidden"></div><div class="form-foot"><a class="text-button" href="#results">先看大家的时间</a>${editable?'<button class="button primary" type="submit">保存我的全部答案 →</button>':'<a class="button primary" href="#results">查看推荐结果 →</a>'}</div>${editable?'<label class="check-row muted" style="margin-top:15px"><input type="checkbox" id="simulate-failure">演示一次保存失败（输入保留）</label>':''}</form></section><aside><section class="panel"><h2>填写进度</h2><div class="progress"><span style="width:${progress()/state.participants.length*100}%"></span></div><p class="muted">${progress()} / ${state.participants.length} 人已提交</p>${state.participants.map(id=>`<div class="member"><span class="avatar">${person(id).short}</span><strong>${person(id).name}</strong><span class="pill ${state.votes[id]?'yes':'unknown'}">${state.votes[id]?'已提交':'未填写'}</span></div>`).join('')}</section><div class="note"><strong>填写小提示</strong><p>有空：可以参加<br>勉强：需要协调<br>没空：无法参加<br>未填写：未知，不代表有空</p></div><p class="muted">收集截止：${date(state.deadline)} ${time(state.deadline)}</p></aside></div>`;
}
function resultsView() {
  if(status()==='DRAFT')return heading('时间与推荐','发布后，在这里汇总每个人的空闲状态。')+empty('等待开始收集','先设置参与者、必到成员和候选时间。','draft','查看排期设置');
  if(status()==='CANCELLED')return empty('这次排期已取消','当前排期不能继续填写或确认会议。','group','返回小组');
  const ranked=rank(state), allConflict=ranked.every(s=>s.conflicts>0), missing=state.required.filter(id=>!state.votes[id]);
  const action=status()==='OPEN'&&me()?button('关闭收集','close-poll'):status()==='CONFIRMED'?'<a class="button primary" href="#meeting">进入会议 →</a>':'';
  return heading('让每个人的时间，一目了然。',esc(state.title),action)+stepper(2)+`${allConflict?'<div class="note warn"><strong>所有候选时段都有必到冲突。</strong> 当前没有满足全部必到成员的时段。请先协调；如仍确认，需明确风险并说明理由。</div>':''}${missing.length?`<div class="note warn"><strong>必到成员 ${missing.map(id=>person(id).name).join('、')} 尚未填写。</strong> 他们是否能参加仍未知，不能据此判断“全员可参加”。</div>`:''}<div class="two-col"><div><section class="panel"><div class="panel-title"><div><h2>大家的时间</h2><p class="muted">${progress()} / ${state.participants.length} 人已提交 · 只汇总本次参与者</p></div>${badge()}</div><div class="matrix-wrap"><table class="matrix"><thead><tr><th>参与者</th>${state.slots.map((s,i)=>`<th>候选 ${i+1}<br>${date(s.start)}<br>${time(s.start)}–${time(s.end)}</th>`).join('')}</tr></thead><tbody>${state.participants.map(id=>`<tr><td><span class="person"><span class="avatar">${person(id).short}</span>${person(id).name}</span>${state.required.includes(id)?'<br><small>必到成员</small>':''}</td>${state.slots.map((s,i)=>`<td><span class="pill ${state.votes[id]?.[i]||'unknown'}">${choices[state.votes[id]?.[i]]||'未填写'}</span></td>`).join('')}</tr>`).join('')}<tr><td>有空 / 勉强 / 没空 / 未填</td>${state.slots.map(s=>{const r=ranked.find(r=>r.id===s.id);return `<td>${r.available} / ${r.maybe} / ${r.no} / ${r.unknown}</td>`;}).join('')}</tr></tbody></table></div><div class="actions" style="margin-top:20px"><a class="button small" href="#vote">填写 / 修改我的答案</a><button class="text-button" id="refresh">↻ 手动刷新</button></div></section><section class="panel"><h3>推荐依据</h3><p class="muted">先考虑必到成员冲突，再比较得分与有空人数。得分用于辅助选择，最终会议时间由负责人确认。</p><details><summary>展开评分与排序规则</summary><p>必到权重3，普通成员权重1。有空2分、勉强1分、没空−2分；每名必到没空额外扣20，每名未填写扣2。</p><p>排序：必到没空人数升序 → 得分降序 → 有空人数降序 → 开始时间 → 结束时间 → 候选ID。</p></details>${me()&&['OPEN','CLOSED'].includes(status())?'<button class="text-button danger" id="cancel-poll">取消本次排期</button>':''}</section></div><aside><div class="panel-title"><div><h2>建议时段</h2><p class="muted">供讨论参考，不自动确认。</p></div><span class="pill">${ranked.length} 个</span></div>${ranked.map((s,i)=>`<section class="rank-card ${i===0?'best':''}"><div class="rank-head"><span class="rank-number">${String(i+1).padStart(2,'0')}</span><h3>候选 ${state.slots.findIndex(t=>t.id===s.id)+1}</h3><span class="score">${s.score}<small>分</small></span></div><p class="muted" style="margin-top:10px">${when(s)}</p><div class="rank-metrics"><span>${s.available}人有空</span><span>${s.conflicts}名必到没空</span><span>${s.requiredUnknown}名必到未填</span></div><div class="rank-foot"><p>${s.conflicts?'存在必到冲突':s.requiredUnknown?'必到可用性未知':s.requiredMaybe?'必到成员需协调':'必到成员均有空'}<br>基础${s.base} − 冲突${s.conflicts*20} − 未填${s.unknown*2}</p>${me()&&status()==='CLOSED'?`<button class="button small ${i===0?'primary':''}" data-confirm="${s.id}">选这个时段</button>`:''}</div></section>`).join('')}${status()==='OPEN'?'<div class="note">仍在收集，可继续填写。负责人关闭收集后才能确认会议。</div>':''}${!me()?'<div class="note">会议时间由小组负责人确认。</div>':''}</aside></div>`;
}
function taskRows(tasks) {
  return tasks.length? tasks.map(t=>`<div class="task-row ${t.status==='DONE'?'done':''}"><span class="avatar">${person(t.assignee).short}</span><div><h3>${esc(t.title)}</h3><p>${person(t.assignee).name} · 截止 ${date(t.due)} ${time(t.due)}</p></div><select aria-label="任务${t.id}状态" data-task="${t.id}" ${me()||t.assignee===state.user?'':'disabled'}>${Object.entries(taskNames).map(([k,v])=>`<option value="${k}" ${k===t.status?'selected':''}>${v}</option>`).join('')}</select></div>`).join(''):'<div class="empty"><span class="empty-icon">✓</span><h3>暂时没有任务</h3><p>让会议里的下一步，有明确的负责人和截止时间。</p></div>';
}
function meetingView() {
  if(!state.meeting)return heading('会议与任务','把讨论的共识，变成接下来的行动。')+stepper(3)+empty('会议时间还没有确定','负责人从已关闭的排期中确认一个时段后，即可记录纪要和创建任务。','results','查看排期与推荐');
  const slot=state.slots.find(s=>s.id===state.meeting.slotId), readonly=me()?'':'readonly';
  return heading('时间已定，接着把事情做好。',esc(state.title),'<a class="button" href="#results">查看排期依据</a>')+stepper(3)+`<div class="meeting-banner"><div><div class="section-label">已确认会议</div><h2>${when(slot)}</h2><p>${state.participants.length} 位参与者 · 负责人 马若曦${state.meeting.reason?` · 选择理由：${esc(state.meeting.reason)}`:''}</p></div><span class="pill confirmed">已确认</span></div><div class="two-col"><div><section class="panel"><div class="panel-title"><h2>议程与纪要</h2><span class="pill">${me()?'负责人可编辑':'成员只读'}</span></div><form id="minutes-form"><label class="field">会议议程<textarea name="agenda" maxlength="2000" placeholder="这次需要讨论什么？" ${readonly}>${esc(state.meeting.agenda)}</textarea></label><label class="field">会议纪要<textarea name="minutes" maxlength="10000" rows="6" placeholder="记录结论、待确认事项与下一步。" ${readonly}>${esc(state.meeting.minutes)}</textarea></label><div class="error-box hidden"></div>${me()?'<div class="form-foot"><span class="muted">按纯文本保存与展示。</span><button class="button primary">保存议程与纪要</button></div>':''}</form></section><section class="panel"><div class="panel-title"><div><h2>会议任务</h2><p class="muted">${state.tasks.filter(t=>t.status==='DONE').length} / ${state.tasks.length} 项已完成</p></div><a class="text-button" href="#tasks">我的待办 ↗</a></div>${taskRows(state.tasks)}</section></div><aside>${me()?`<section class="panel"><div class="panel-title"><h2>把下一步写下来</h2><span class="pill">新任务</span></div><form id="task-form"><label class="field">任务内容<input name="title" maxlength="100" required placeholder="例如：完善时间填写页原型"></label><label class="field">执行人<select name="assignee">${people.map(p=>`<option value="${p.id}">${p.name}</option>`).join('')}</select></label><label class="field">截止时间（北京时间）<input type="datetime-local" name="due" value="${futureDate(7)}T18:00" required></label><div class="error-box hidden"></div><button class="button primary" style="width:100%">＋ 创建任务</button></form></section>`:'<div class="note">任务由负责人创建和指派，你可以更新分配给自己的任务状态。</div>'}<div class="note"><strong>持续跟进</strong><p>负责人和执行人可以更新任务。标记完成后，任务从默认个人待办中移除；重新打开后会再次出现。</p></div></aside></div>`;
}
function tasksView() {
  const tasks=personalTasks(state,includeDone);
  return heading('把下一步，一件件完成。',`${person(state.user).name}的个人任务 · 与会议任务保持一致。`)+`<div class="panel"><div class="toolbar"><h2>我的待办 <span class="pill">${tasks.length} 项</span></h2><label class="check-row"><input type="checkbox" id="include-done" ${includeDone?'checked':''}>包含已完成</label></div>${taskRows(tasks)}<div class="form-foot"><span class="muted">仅显示分配给当前模拟账号的任务。</span><a class="button small" href="#meeting">返回会议</a></div></div>`;
}
function showConfirm(id) {
  const info=risk(state,id), modal=$('#confirm-dialog');
  modal.innerHTML=`<h2 id="confirm-title">确认这次会议时间</h2><p class="muted">${esc(state.title)}</p><div class="note" style="margin-top:18px">${when(info.slot)}</div>${info.required?`<div class="note warn">这个选择需要进一步确认：${info.slot.conflicts?`${info.slot.conflicts}名必到成员没空；`:''}${info.slot.requiredUnknown?`${info.slot.requiredUnknown}名必到成员未填写；`:''}${rank(state)[0].id!==id?'所选时段不是第一推荐。':''}</div>`:''}${info.slot.requiredMaybe?'<div class="note warn">有必到成员选择“勉强”，建议先沟通协调。</div>':''}<form id="confirm-form">${info.required?'<label class="field">选择理由<textarea name="reason" maxlength="500" required placeholder="例如：已线下协调，由成员会后补充意见。"></textarea></label><label class="check-row"><input type="checkbox" name="ack" required>我已了解上述风险，仍确认该时段。</label>':'<p class="muted">确认后将生成唯一会议，排期不再允许改期。</p>'}<div class="error-box hidden"></div><div class="actions"><button type="button" class="button" id="dismiss">返回讨论</button><button class="button primary">确认并进入会议 →</button></div></form>`;
  modal.showModal();
  $('#dismiss').onclick=()=>modal.close();
  $('#confirm-form').onsubmit=e=>{
    e.preventDefault();const form=new FormData(e.target);
    try { confirmMeeting(state,id,form.get('reason')||'',form.get('ack')==='on');persist();modal.close();navigate('meeting');notify('会议时间已确认。'); }catch(err){failure(err.message,'confirm-dialog');}
  };
}
function readDraft(form) {
  const data=new FormData(form);
  return {...state,title:data.get('title'),description:data.get('description'),deadline:data.get('deadline'),participants:data.getAll('participant'),required:data.getAll('required'),slots:state.slots.map(s=>({...s,start:data.get(`start-${s.id}`),end:data.get(`end-${s.id}`)}))};
}
function bind(view) {
  $('#draft-form')?.addEventListener('submit',e=>{
    e.preventDefault();const candidate=readDraft(e.target);
    try { if(e.submitter?.value==='publish'){publish(candidate);state=candidate;persist();navigate('vote');notify('排期已发布，候选和参与者已固定。');}else{validateDraft(candidate);state=candidate;persist();notify('草稿已保存。');} }catch(err){failure(err.message);}
  });
  $('#add-slot')?.addEventListener('click',()=>{
    if(state.slots.length>=15){failure('最多添加15个候选时段。');return;}
    state=readDraft($('#draft-form'));state.slots.push({id:Math.max(...state.slots.map(s=>s.id))+1,start:`${futureDate(6)}T19:00`,end:`${futureDate(6)}T20:00`});render();dirty=true;
  });
  document.querySelectorAll('[data-remove]').forEach(el=>el.onclick=()=>{ if(state.slots.length<=1){failure('至少保留一个候选时段。');return;}state=readDraft($('#draft-form'));state.slots=state.slots.filter(s=>s.id!==Number(el.dataset.remove));render();dirty=true; });
  $('#vote-form')?.addEventListener('submit',e=>{
    e.preventDefault();const form=new FormData(e.target), answers=state.slots.map(s=>form.get(`slot-${s.id}`));
    const fail=$('#simulate-failure')?.checked;
    if($('#simulate-failure'))$('#simulate-failure').checked=false;
    if(perform(()=>saveVotes(state,answers,Date.now(),fail),'全部答案已保存。',false))navigate('results');
  });
  $('#close-poll')?.addEventListener('click',()=>{ if(window.confirm('关闭后，所有参与者都不能再修改答案。确定关闭吗？'))perform(()=>closePoll(state),'收集已关闭，可以确认会议。'); });
  $('#cancel-poll')?.addEventListener('click',()=>{ if(window.confirm('取消后不能重新开启。确定取消本次排期吗？'))perform(()=>cancelPoll(state),'排期已取消。'); });
  $('#refresh')?.addEventListener('click',()=>{render();notify('已刷新本机演示结果。');});
  document.querySelectorAll('[data-confirm]').forEach(el=>el.onclick=()=>showConfirm(Number(el.dataset.confirm)));
  $('#minutes-form')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);perform(()=>saveMinutes(state,f.get('agenda'),f.get('minutes')),'议程与纪要已保存。');});
  let requestId=crypto.randomUUID();
  $('#task-form')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);if(perform(()=>addTask(state,{title:f.get('title'),assignee:f.get('assignee'),due:f.get('due'),requestId}),'任务已创建。'))requestId=crypto.randomUUID();});
  document.querySelectorAll('[data-task]').forEach(el=>el.onchange=()=>perform(()=>setTaskStatus(state,Number(el.dataset.task),el.value),'任务状态已更新。'));
  $('#include-done')?.addEventListener('change',e=>{includeDone=e.target.checked;render();});
  document.querySelectorAll('main input,main textarea').forEach(el=>el.addEventListener('input',()=>{if(!el.closest('#task-form') && el.id!=='simulate-failure' && el.id!=='include-done')dirty=true;}));
}
function render() {
  let view=location.hash.slice(1)||'group';if(!Object.hasOwn(names,view))view='group';
  document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===view);if(el.dataset.nav===view)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  $('#breadcrumb').textContent=`工作空间 / ${names[view]}`;
  $('#profile-name').textContent=person(state.user).name;$('#profile-role').textContent=me()?'负责人':'成员';$('#avatar').textContent=person(state.user).short;
  $('#user').innerHTML=people.map(p=>`<option value="${p.id}" ${state.user===p.id?'selected':''}>${p.name}${p.id==='ma'?' · 负责人':''}</option>`).join('');
  $('#app').innerHTML=({group:groupView,draft:draftView,vote:voteView,results:resultsView,meeting:meetingView,tasks:tasksView}[view])();
  bind(view);
}
document.addEventListener('click',e=>{if(e.target.closest('a[href^="#"]')&&!leave())e.preventDefault();});
$('#user').onchange=e=>{if(!leave()){render();return;}state.user=e.target.value;persist();render();notify(`已切换到${person(state.user).name}`);};
$('#scenario').onchange=e=>{if(!e.target.value)return;if(!leave()){e.target.value='';return;}state=scenario(e.target.value);persist();e.target.value='';navigate('results');notify('演示场景已载入。');};
$('#reset').onclick=()=>{if(!window.confirm('重置会清除本机原型里的答案、纪要和任务。继续吗？'))return;state=fresh();persist();navigate('group');notify('已回到初始演示。');};
window.addEventListener('hashchange',()=>{dirty=false;render();window.scrollTo(0,0);});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
render();
