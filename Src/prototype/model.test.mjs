import test from 'node:test';
import assert from 'node:assert/strict';
import { fresh, scenario, rank, publish, validateDraft, effectiveStatus, saveVotes, closePoll, cancelPoll, confirmMeeting, saveMinutes, addTask, setTaskStatus, personalTasks, futureDate } from './model.mjs';

test('published example independently yields 8, -16, 7 and T1/T3/T2',()=>{
  const s=scenario('normal');s.votes.chen=['yes','no',null];
  const result=rank(s);
  assert.deepEqual(result.map(r=>[r.id,r.score]),[[1,8],[3,7],[2,-16]]);
  assert.equal(result[1].requiredUnknown,1);
  assert.equal(result[1].unknown,1);
  s.participants.reverse();s.slots.reverse();
  s.votes=Object.fromEntries(Object.entries(s.votes).map(([id,answers])=>[id,[...answers].reverse()]));
  assert.deepEqual(rank(s).map(r=>[r.id,r.score]),result.map(r=>[r.id,r.score]));
});
test('ties use start, end, then numeric slot identifier',()=>{
  const s=scenario('unknown');s.votes={};
  s.slots=[{id:3,start:'2099-01-02T19:00',end:'2099-01-02T20:00'},
    {id:2,start:'2099-01-01T19:00',end:'2099-01-01T20:00'},
    {id:1,start:'2099-01-01T19:00',end:'2099-01-01T20:00'},
    {id:4,start:'2099-01-01T19:00',end:'2099-01-01T21:00'}];
  assert.deepEqual(rank(s).map(r=>r.id),[1,2,4,3]);
});
test('draft rejects duplicate, reversed, excess slots and foreign participants',()=>{
  for(const mutate of [s=>s.slots.push({...s.slots[0],id:4}),s=>s.slots[0].end=s.slots[0].start,
    s=>s.slots=Array.from({length:16},()=>({...s.slots[0]})),s=>s.participants.push('outsider'),
    s=>s.required.push('outsider'),s=>s.deadline=s.slots[0].start]) {
    const s=fresh();mutate(s);assert.throws(()=>validateDraft(s));assert.equal(s.status,'DRAFT');
  }
});
test('only owner publishes; published structure cannot be republished',()=>{
  const s=fresh();s.user='chen';assert.throws(()=>publish(s));s.user='ma';publish(s);
  assert.equal(s.status,'OPEN');assert.throws(()=>publish(s));
});
test('incomplete and simulated failed writes retain the previous full answer',()=>{
  const s=scenario('normal'), before=structuredClone(s.votes);
  assert.throws(()=>saveVotes(s,['yes']));assert.deepEqual(s.votes,before);
  assert.throws(()=>saveVotes(s,['no','no','no'],Date.now(),true));assert.deepEqual(s.votes,before);
  s.user='chen';saveVotes(s,['yes','maybe','no']);assert.deepEqual(s.votes.ma,before.ma);
});
test('deadline allows one second before, refuses exact instant and afterwards',()=>{
  const s=scenario('normal'), cutoff=new Date(s.deadline).getTime();
  saveVotes(s,['yes','yes','yes'],cutoff-1000);
  for(const now of [cutoff,cutoff+1000]) {
    assert.equal(effectiveStatus(s,now),'CLOSED');
    assert.throws(()=>saveVotes(s,['no','no','no'],now));
  }
  assert.deepEqual(s.votes.ma,['yes','yes','yes']);
});
test('unknown and all-conflict scenarios are honestly classified',()=>{
  const unknown=scenario('unknown');assert.ok(rank(unknown).every(r=>r.requiredUnknown===1));
  const conflict=scenario('conflict');assert.ok(rank(conflict).every(r=>r.conflicts>0));
});
test('confirmation needs closed state and risk acknowledgment with reason',()=>{
  const s=scenario('unknown');assert.throws(()=>confirmMeeting(s,1));closePoll(s);
  assert.throws(()=>confirmMeeting(s,1,'',true));assert.throws(()=>confirmMeeting(s,1,'已协调',false));
  const meeting=confirmMeeting(s,1,'已线下协调',true);
  assert.equal(s.status,'CONFIRMED');assert.equal(confirmMeeting(s,1),meeting);
  assert.throws(()=>confirmMeeting(s,2,'改选',true));
});
test('non-first slot needs reason even without conflicts; member cannot confirm',()=>{
  const s=scenario('normal');s.votes=Object.fromEntries(s.participants.map(id=>[id,['yes','yes','yes']]));closePoll(s);
  assert.throws(()=>confirmMeeting(s,2));s.user='chen';assert.throws(()=>confirmMeeting(s,1));
  s.user='ma';confirmMeeting(s,2,'成员偏好第二天',true);
});
test('cancelled poll cannot vote, confirm or reopen',()=>{
  const s=scenario('normal');cancelPoll(s);
  assert.throws(()=>saveVotes(s,['yes','yes','yes']));assert.throws(()=>confirmMeeting(s,1));assert.throws(()=>publish(s));
});
function meetingState(){const s=scenario('normal');closePoll(s);confirmMeeting(s,rank(s)[0].id);return s;}
test('minutes remain literal text and only the owner can save',()=>{
  const s=meetingState();saveMinutes(s,'议程','<script>alert(1)</script>');
  assert.equal(s.meeting.minutes,'<script>alert(1)</script>');s.user='chen';
  assert.throws(()=>saveMinutes(s,'',''));assert.equal(s.meeting.agenda,'议程');
});
test('task creation validates owner, membership, future due date and retry identity',()=>{
  const s=meetingState(), data={title:'完成填写页',assignee:'chen',due:`${futureDate(7)}T18:00`,requestId:'one'};
  const task=addTask(s,data);assert.equal(addTask(s,data),task);assert.equal(s.tasks.length,1);
  assert.throws(()=>addTask(s,{...data,requestId:'two',assignee:'outsider'}));
  assert.throws(()=>addTask(s,{...data,requestId:'two',due:'2020-01-01T10:00'}));
  s.user='chen';assert.throws(()=>addTask(s,{...data,requestId:'two'}));
});
test('only assignee or owner updates; completion and reopening share one task',()=>{
  const s=meetingState();const t=addTask(s,{title:'复核',assignee:'chen',due:`${futureDate(7)}T18:00`,requestId:'a'});
  s.user='lin';assert.throws(()=>setTaskStatus(s,t.id,'DONE'));
  s.user='chen';assert.equal(personalTasks(s).length,1);setTaskStatus(s,t.id,'DONE',123);
  assert.equal(t.completedAt,123);assert.equal(personalTasks(s).length,0);assert.equal(personalTasks(s,true)[0],t);
  setTaskStatus(s,t.id,'TODO');assert.equal(t.completedAt,null);assert.equal(personalTasks(s)[0],t);
});
