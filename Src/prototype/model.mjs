// Prototype-only state and rules. The production service must enforce them again.
export const people = [
  { id: 'ma', name: '马若曦', short: '马', role: '负责人' },
  { id: 'chen', name: '陈明强', short: '陈', role: '成员' },
  { id: 'lin', name: '林同学', short: '林', role: '演示成员' },
  { id: 'zhou', name: '周同学', short: '周', role: '演示成员' },
];
export const choices = { yes: '有空', maybe: '勉强', no: '没空' };
const value = { yes: 2, maybe: 1, no: -2 };
export function futureDate(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
export function fresh() {
  return { version: 1, user: 'ma', group: true, title: 'MeetFlow 第一版需求评审',
    description: '对齐核心流程，确认推荐规则与任务分工。',
    deadline: `${futureDate(2)}T18:00`, required: ['ma', 'chen'], participants: people.map(p => p.id),
    slots: [0,1,2].map((n) => ({ id: n+1, start: `${futureDate(n+3)}T19:00`, end: `${futureDate(n+3)}T20:00` })),
    status: 'DRAFT', votes: {}, meeting: null, tasks: [] };
}
export function scenario(kind) {
  const state = fresh();
  state.status = kind === 'conflict' ? 'CLOSED' : 'OPEN';
  state.votes = { ma: ['yes','yes','yes'], chen: ['yes','no','maybe'], lin: ['no','yes','yes'], zhou: ['no','yes','maybe'] };
  if (kind === 'unknown') delete state.votes.chen;
  if (kind === 'conflict') state.votes.chen = ['no','no','no'];
  return state;
}
export function effectiveStatus(state, now=Date.now()) {
  return state.status === 'OPEN' && new Date(state.deadline).getTime() <= now ? 'CLOSED' : state.status;
}
export function rank(state) {
  return state.slots.map((slot, i) => {
    let base=0, conflicts=0, unknown=0, requiredUnknown=0, available=0, maybe=0, no=0, requiredMaybe=0;
    for (const id of state.participants) {
      const answer = state.votes[id]?.[i];
      const required = state.required.includes(id);
      if (!answer) { unknown++; if(required) requiredUnknown++; continue; }
      base += value[answer] * (required ? 3 : 1);
      if(answer === 'yes') available++;
      if(answer === 'maybe') { maybe++; if(required) requiredMaybe++; }
      if(answer === 'no') { no++; if(required) conflicts++; }
    }
    return { ...slot, base, conflicts, unknown, requiredUnknown, requiredMaybe, available, maybe, no,
      score: base - 20*conflicts - 2*unknown };
  }).sort((a,b) => a.conflicts-b.conflicts || b.score-a.score || b.available-a.available || a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || a.id-b.id);
}
function owner(state) { if(state.user !== 'ma') throw new Error('只有小组负责人可以操作。'); }
export function validateDraft(state, now=Date.now()) {
  if(!state.title.trim() || state.title.length>100) throw new Error('请填写100字以内的排期主题。');
  if(!state.participants.length || new Set(state.participants).size !== state.participants.length || state.participants.some(id=>!people.some(p=>p.id===id))) throw new Error('请选择有效的小组参与者。');
  if(state.required.some(id=>!state.participants.includes(id))) throw new Error('必到成员必须在参与者中。');
  if(state.slots.length<1 || state.slots.length>15) throw new Error('候选时段须为1～15个。');
  const deadline = new Date(state.deadline).getTime();
  if(!Number.isFinite(deadline) || deadline<=now) throw new Error('收集截止时间必须晚于当前时间。');
  const unique = new Set();
  for(const s of state.slots) {
    const start=new Date(s.start).getTime(), end=new Date(s.end).getTime();
    if(!Number.isFinite(start) || !Number.isFinite(end) || end<=start || start<=deadline) throw new Error('候选结束须晚于开始，且开始须晚于收集截止。');
    const key=`${start}/${end}`;
    if(unique.has(key)) throw new Error('候选时段不能重复。');
    unique.add(key);
  }
}
export function publish(state, now=Date.now()) {
  owner(state);
  if(state.status!=='DRAFT') throw new Error('只有草稿可以发布。');
  validateDraft(state,now); state.status='OPEN';
}
export function saveVotes(state, answers, now=Date.now(), fail=false) {
  if(effectiveStatus(state,now)!=='OPEN') throw new Error('排期已关闭，无法继续填写。');
  if(!state.participants.includes(state.user)) throw new Error('只有本次参与者可以填写。');
  if(answers.length!==state.slots.length || answers.some(a=>!Object.hasOwn(choices,a))) throw new Error('请为每个候选时段选择一个状态。');
  if(fail) throw new Error('本次模拟保存失败。输入已保留，请重试。');
  state.votes[state.user]=[...answers];
}
export function closePoll(state) {
  owner(state);
  if(effectiveStatus(state)!=='OPEN') throw new Error('当前排期不在收集中。');
  state.status='CLOSED';
}
export function cancelPoll(state) {
  owner(state);
  if(!['DRAFT','OPEN','CLOSED'].includes(state.status)) throw new Error('当前排期不能取消。');
  state.status='CANCELLED';
}
export function risk(state, id) {
  const ranked=rank(state), slot=ranked.find(s=>s.id===id);
  if(!slot) throw new Error('候选时段不存在。');
  return { slot, required: !!(slot.conflicts || slot.requiredUnknown || ranked[0].id!==id) };
}
export function confirmMeeting(state, id, reason='', acknowledged=false) {
  owner(state);
  if(state.meeting) {
    if(state.meeting.slotId===id) return state.meeting;
    throw new Error('这次排期已确认其他时段，不能重复生成会议。');
  }
  if(effectiveStatus(state)!=='CLOSED') throw new Error('请先关闭收集，再确认会议。');
  const warning=risk(state,id);
  if(warning.required && (!acknowledged || !reason.trim())) throw new Error('请确认风险，并填写选择该时段的理由。');
  state.status='CONFIRMED';
  state.meeting={ slotId:id, reason:reason.trim(), agenda:'', minutes:'' };
  return state.meeting;
}
export function saveMinutes(state, agenda, minutes) {
  owner(state);
  if(!state.meeting) throw new Error('请先确认会议。');
  if(agenda.length>2000 || minutes.length>10000) throw new Error('议程或纪要超过长度限制。');
  state.meeting.agenda=agenda; state.meeting.minutes=minutes;
}
export function addTask(state, { title, assignee, due, requestId }, now=Date.now()) {
  owner(state);
  if(!state.meeting) throw new Error('请先确认会议。');
  const existing=state.tasks.find(t=>t.requestId===requestId);
  if(existing) return existing;
  if(!title.trim() || title.length>100 || !people.some(p=>p.id===assignee) || !requestId || !Number.isFinite(new Date(due).getTime()) || new Date(due).getTime()<=now) throw new Error('请填写100字以内的任务、组内执行人和未来截止时间。');
  const task={ id:state.tasks.length+1, title:title.trim(), assignee, due, requestId, status:'TODO', completedAt:null };
  state.tasks.push(task); return task;
}
export function setTaskStatus(state, id, status, now=Date.now()) {
  const task=state.tasks.find(t=>t.id===id);
  if(!task || !['TODO','IN_PROGRESS','DONE'].includes(status)) throw new Error('任务或状态无效。');
  if(state.user!=='ma' && task.assignee!==state.user) throw new Error('只有负责人和执行人可以更新任务状态。');
  task.status=status; task.completedAt=status==='DONE' ? now : null;
}
export function personalTasks(state, includeDone=false) {
  return state.tasks.filter(t=>t.assignee===state.user && (includeDone || t.status!=='DONE'));
}
