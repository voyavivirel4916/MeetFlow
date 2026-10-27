"""T31 cross-module acceptance, using independent identities and real transactions."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.auth import dependencies
from app.common.times import format_ms
from app.db.connection import database_path
from app.main import create_app
from test_auth import register, login
from test_bootstrap import assert_error
from test_groups import data, other, owner
from test_meeting_content import meeting
from test_meetings import closed
from test_polls import setup
from test_votes import opened
from test_tasks import body, create_task, saved


def test_four_account_cross_module_workflow_and_outsider(settings):
    from app.db.migrate import upgrade
    from time import time
    upgrade(settings)
    now = int(time()*1000)
    with ExitStack() as stack:
        actors = [stack.enter_context(TestClient(create_app(settings),base_url='http://127.0.0.1',raise_server_exceptions=False)) for _ in range(5)]
        users = []
        for index, browser in enumerate(actors):
            users.append(data(register(browser, username=f'e2e_{index}', email=f'e2e_{index}@example.com'),201))
            data(login(browser,username=f'e2e_{index}'))
        lead,*_ = actors
        group = data(lead.post('/api/v1/groups',json={'name':'四账号验收'}),201)
        for browser in actors[1:4]:
            data(browser.post('/api/v1/groups/join',json={'invite_code':group['invite_code']}))
        poll = data(lead.post(f"/api/v1/groups/{group['id']}/polls",json={
            'title':'评审','response_deadline':format_ms(now+600000),
            'participants':[{'user_id':user['id'],'importance':'REQUIRED' if i<2 else 'NORMAL'} for i,user in enumerate(users[:4])],
            'slots':[{'start_at':format_ms(now+3600000+i*3600000),'end_at':format_ms(now+5400000+i*3600000)} for i in range(3)]}),201)
        path=f"/api/v1/polls/{poll['id']}"
        data(lead.post(path+'/open',json={}))
        assert_error(actors[4].get(path+'/matrix'),404,'NOT_FOUND')
        assert_error(actors[1].post(path+'/close',json={}),403,'FORBIDDEN')
        for index,browser in enumerate(actors[:4]):
            values=['AVAILABLE','MAYBE','UNAVAILABLE'] if index%2 else ['AVAILABLE','AVAILABLE','MAYBE']
            data(browser.put(path+'/votes/me',json={'votes':[{'slot_id':slot['id'],'availability':values[i]} for i,slot in enumerate(poll['slots'])]}))
        matrix=data(lead.get(path+'/matrix'))
        assert matrix['progress']['submitted_count']==4 and len(matrix['cells'])==12
        assert matrix['slots'][0]['available_count']==4
        ranking=data(lead.get(path+'/recommendations'))['items']
        assert ranking[0]['slot_id']==poll['slots'][0]['id']
        data(lead.post(path+'/close',json={}))
        confirmation={'slot_id':ranking[0]['slot_id']}
        confirmed=data(lead.post(path+'/confirm',json=confirmation),201)
        assert data(lead.post(path+'/confirm',json=confirmation))==confirmed
        assert_error(actors[4].get(f"/api/v1/meetings/{confirmed['id']}"),404,'NOT_FOUND')
        data(lead.patch(f"/api/v1/meetings/{confirmed['id']}",json={'agenda':'讨论分工','minutes':'已确定下一步'}))
        tasks=[]
        for index in [1,2]:
            request={'title':f'行动{index}','assignee_id':users[index]['id'],'due_at':format_ms(now+86400000),'client_request_id':str(uuid4())}
            task=data(lead.post(f"/api/v1/meetings/{confirmed['id']}/tasks",json=request),201)
            assert data(lead.post(f"/api/v1/meetings/{confirmed['id']}/tasks",json=request))==task
            tasks.append(task)
        assert_error(actors[3].patch(f"/api/v1/tasks/{tasks[0]['id']}/status",json={'status':'DONE'}),403,'FORBIDDEN')
        assert_error(actors[4].patch(f"/api/v1/tasks/{tasks[0]['id']}/status",json={'status':'DONE'}),404,'NOT_FOUND')
        for index,task in enumerate(tasks,1):
            completed=data(actors[index].patch(f"/api/v1/tasks/{task['id']}/status",json={'status':'DONE'}))
            assert data(actors[index].get('/api/v1/tasks/mine'))['items']==[]
            assert data(actors[index].get('/api/v1/tasks/mine?status=DONE'))['items']==[completed]
        assert data(actors[3].get(f"/api/v1/groups/{group['id']}/tasks?status=DONE"))['total']==2
        with sqlite3.connect(database_path(settings)) as connection:
            assert connection.execute('SELECT COUNT(*) FROM meetings').fetchone()[0]==1
            assert connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==2
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_task_deadline_is_rechecked_after_waiting_for_write_lock(owner,meeting,settings,monkeypatch):
    row,now=meeting
    request=body(now)
    started=Event();original=dependencies.make_engine
    def observed(path):
        engine=original(path)
        event.listen(engine,'before_cursor_execute',lambda _c,_cu,sql,_p,_ctx,_many:started.set() if sql=='BEGIN IMMEDIATE' else None)
        return engine
    monkeypatch.setattr(dependencies,'make_engine',observed)
    blocker=sqlite3.connect(database_path(settings));blocker.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(create_task,owner,row,request)
        try:
            assert started.wait(3)
            now[0]+=60000
        finally:blocker.rollback();blocker.close()
        assert_error(future.result(timeout=5),422,'VALIDATION_ERROR')
    assert saved(settings)==[]
