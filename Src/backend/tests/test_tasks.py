import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.auth import dependencies
from app.common.times import format_ms
from app.db.connection import database_path, make_engine
from app.tasks import service
from app.tasks.models import TaskIn
from test_bootstrap import assert_error
from test_groups import create, data, other, owner
from test_meeting_content import meeting
from test_meetings import closed, confirm
from test_polls import setup
from test_votes import opened


def body(now, **changes):
    return dict(title='  实现核心流程  ', description='讨论\n方案', assignee_id=2,
                due_at=format_ms(now[0]+60000), client_request_id=str(uuid4())) | changes


def create_task(owner, meeting, payload):
    return owner.post(f"/api/v1/meetings/{meeting['id']}/tasks", json=payload)


def saved(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return connection.execute('SELECT * FROM tasks ORDER BY id').fetchall()


def test_create_retry_after_deadline_conflict_and_normalization(owner, other, meeting, settings):
    row, now = meeting
    payload = body(now)
    task = data(create_task(owner, row, payload), 201)
    assert task['title'] == '实现核心流程' and task['status'] == 'TODO' and task['completed_at'] is None
    assert task['assignee_id'] == 2 and task['creator_id'] == 1
    assert 'client_request_id' not in task
    now[0] += 120000
    before = saved(settings)
    assert data(create_task(owner, row, payload | {'title': '实现核心流程', 'client_request_id': payload['client_request_id'].upper()})) == task
    assert_error(create_task(owner, row, payload | {'title': '换任务'}), 409, 'STATE_CONFLICT')
    assert saved(settings) == before
    assert data(other.get('/api/v1/tasks/mine'))['items'] == [task]


@pytest.mark.parametrize('change', [{'title': ''}, {'title': ' '}, {'title':'x'*101}, {'description':'x'*10001}, {'title':'\x00'},
    {'assignee_id':True}, {'assignee_id':'2'}, {'assignee_id':999}, {'due_at':'bad'}, {'due_at':123},
    {'client_request_id':'bad'}, {'client_request_id':None}, {'status':'DONE'}, {'description':None}])
def test_invalid_create_has_no_partial_task(owner, meeting, settings, change):
    row, now = meeting
    assert_error(create_task(owner, row, body(now, **change)), 422, 'VALIDATION_ERROR')
    assert saved(settings) == []


def test_deadline_checks_server_clock_and_cross_group_assignee(owner, meeting, settings):
    row, now = meeting
    for delta in [-1, 0]:
        assert_error(create_task(owner, row, body(now, due_at=format_ms(now[0]+delta))), 422, 'VALIDATION_ERROR')
    assert_error(create_task(owner, row, body(now, assignee_id=3)), 422, 'VALIDATION_ERROR')
    assert saved(settings) == []


def test_permissions_and_complete_reopen_repeat(owner, other, meeting):
    row, now = meeting
    assert_error(create_task(other, row, body(now)), 403, 'FORBIDDEN')
    task = data(create_task(owner, row, body(now, assignee_id=1)), 201)
    path = f"/api/v1/tasks/{task['id']}/status"
    assert_error(other.patch(path, json={'status':'DONE','expected_version':1}), 403, 'FORBIDDEN')
    for state in ['IN_PROGRESS','DONE','TODO','DONE','IN_PROGRESS']:
        now[0] += 1000
        value = data(owner.patch(path, json={'status':state,'expected_version':task['version']}))
        task = value
        assert value['status'] == state
        assert (value['completed_at'] is not None) == (state == 'DONE')
        now[0] += 1000
        assert data(owner.patch(path, json={'status':state,'expected_version':value['version']})) == value
    assert data(owner.patch(path,json={'status':'CANCELLED','expected_version':task['version']}))['status']=='CANCELLED'
    assert_error(owner.patch('/api/v1/tasks/999/status',json={'status':'DONE','expected_version':1}),404,'NOT_FOUND')


def test_assignee_can_change_and_mine_default_excludes_done(owner, other, meeting):
    row, now = meeting
    first = data(create_task(owner, row, body(now)), 201)
    second = data(create_task(owner, row, body(now, due_at=format_ms(now[0]+120000))), 201)
    data(create_task(owner, row, body(now, assignee_id=1)), 201)
    data(other.patch(f"/api/v1/tasks/{first['id']}/status",json={'status':'DONE','expected_version':1}))
    assert [item['id'] for item in data(other.get('/api/v1/tasks/mine'))['items']] == [second['id']]
    assert data(other.get('/api/v1/tasks/mine?status=DONE'))['items'][0]['id'] == first['id']
    data(other.patch(f"/api/v1/tasks/{first['id']}/status",json={'status':'TODO','expected_version':2}))
    assert [item['id'] for item in data(other.get('/api/v1/tasks/mine'))['items']] == [first['id'], second['id']]
    path=f"/api/v1/groups/{row['group_id']}/tasks"
    assert data(other.get(path))['total'] == 3
    assert data(other.get(path+'?page=2&page_size=1'))['items'][0]['id'] != first['id']
    assert data(other.get(path+'?page=999999999999999999999999'))['items'] == []
    assert data(other.get(path+f"?meeting_id={row['id']}"))['total'] == 3
    for query in ['status=OTHER','page=0','page_size=51','meeting_id=0']:
        assert_error(other.get(path+'?'+query),422,'VALIDATION_ERROR')
    empty=data(create(owner),201)
    assert_error(other.get(f"/api/v1/groups/{empty['id']}/tasks"),404,'NOT_FOUND')
    assert_error(owner.get(f"/api/v1/groups/{empty['id']}/tasks?meeting_id={row['id']}"),422,'VALIDATION_ERROR')


def test_parallel_creation_is_unique_and_changed_payload_conflicts(owner, meeting, settings):
    row, now = meeting
    payload=TaskIn(**body(now))
    engine=make_engine(database_path(settings))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:service.create_task(engine,1,row['id'],payload),range(2)))
        assert results[0][0] == results[1][0]
        assert sorted(created for _,created in results) == [False, True]
        assert len(saved(settings)) == 1
    finally:engine.dispose()


@pytest.mark.parametrize('operation', ['create','status'])
@pytest.mark.parametrize('stage', ['write','commit'])
def test_failed_write_or_commit_preserves_previous_state(owner,meeting,settings,monkeypatch,operation,stage):
    row,now=meeting
    task=data(create_task(owner,row,body(now)),201)
    before=saved(settings);original=dependencies.make_engine
    def faulty(path):
        engine=original(path)
        def fail(*_):raise OperationalError(None,None,sqlite3.OperationalError('injected failure'))
        if stage=='commit':event.listen(engine,'commit',fail)
        else:
            @event.listens_for(engine,'before_cursor_execute')
            def before_sql(_c,_cu,sql,_p,_ctx,_many):
                if sql.startswith('INSERT INTO tasks') or sql.startswith('UPDATE tasks'):fail()
        return engine
    with monkeypatch.context() as patch:
        patch.setattr(dependencies,'make_engine',faulty)
        response=create_task(owner,row,body(now)) if operation=='create' else owner.patch(f"/api/v1/tasks/{task['id']}/status",json={'status':'DONE','expected_version':1})
        assert_error(response,503,'STORAGE_UNAVAILABLE')
    assert saved(settings)==before
