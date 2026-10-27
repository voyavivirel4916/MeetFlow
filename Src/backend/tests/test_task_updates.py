import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import event,select

from app.common.config import ConfigurationError
from app.db import migrate
from app.db.connection import database_path,make_engine,write_transaction
from app.db.models import tasks
from app.tasks import service
from app.tasks.models import TaskUpdate
from test_bootstrap import assert_error
from test_groups import owner,other,data,create
from test_polls import setup
from test_votes import opened
from test_meetings import closed
from test_meeting_content import meeting
from test_tasks import body,create_task,saved


def edit(browser,task,**fields):
    return browser.patch(f"/api/v1/tasks/{task['id']}",json={'expected_version':task['version'],**fields})


def state(browser,task,status):
    return browser.patch(f"/api/v1/tasks/{task['id']}/status",json={'expected_version':task['version'],'status':status})


def test_edit_after_deadline_preserves_original_creation_request(owner,other,meeting,settings):
    row,now=meeting; payload=body(now);task=data(create_task(owner,row,payload),201)
    now[0]+=120000
    changed=data(edit(owner,task,title=' 新名称 ',description='新说明',assignee_id=1))
    assert changed['title']=='新名称' and changed['assignee_id']==1 and changed['due_at']==task['due_at']
    assert changed['version']==2
    assert_error(edit(other,changed,title='越权'),403,'FORBIDDEN')
    assert_error(edit(owner,changed,due_at=task['due_at']),422,'VALIDATION_ERROR')
    assert data(create_task(owner,row,payload))==changed
    assert_error(create_task(owner,row,payload|{'title':'新名称'}),409,'STATE_CONFLICT')
    assert data(other.get('/api/v1/tasks/mine'))['total']==0
    assert data(owner.get('/api/v1/tasks/mine'))['items']==[changed]


def test_cancel_restore_permissions_completion_and_default_filters(owner,other,meeting):
    row,now=meeting;task=data(create_task(owner,row,body(now)),201)
    assert_error(state(other,task,'CANCELLED'),403,'FORBIDDEN')
    cancelled=data(state(owner,task,'CANCELLED'))
    assert cancelled['completed_at'] is None and cancelled['version']==2
    assert data(other.get('/api/v1/tasks/mine'))['total']==0
    assert data(other.get('/api/v1/tasks/mine?status=CANCELLED'))['items']==[cancelled]
    assert_error(state(other,cancelled,'TODO'),403,'FORBIDDEN')
    assert_error(state(owner,cancelled,'DONE'),409,'STATE_CONFLICT')
    restored=data(state(owner,cancelled,'TODO'))
    done=data(state(other,restored,'DONE'))
    assert done['completed_at'] is not None
    assert_error(state(owner,done,'CANCELLED'),409,'STATE_CONFLICT')
    reopened=data(state(other,done,'TODO'))
    assert reopened['completed_at'] is None
    assert data(state(owner,reopened,'CANCELLED'))['status']=='CANCELLED'


def test_old_versions_cannot_overwrite_edits_or_status(owner,other,meeting):
    row,now=meeting;task=data(create_task(owner,row,body(now)),201)
    changed=data(edit(owner,task,title='新内容'))
    assert_error(edit(owner,task,description='旧页面写入'),409,'VERSION_CONFLICT')
    assert_error(state(other,task,'DONE'),409,'VERSION_CONFLICT')
    assert data(state(other,changed,'DONE'))['version']==3
    assert_error(owner.patch(f"/api/v1/tasks/{task['id']}/status",json={'status':'DONE'}),422,'VALIDATION_ERROR')


@pytest.mark.parametrize('changes',[{}, {'title':None},{'description':None},{'assignee_id':None},{'due_at':None},
                                 {'title':' '},{'title':'\x00'},{'assignee_id':999}, {'status':'DONE'},
                                 {'expected_version':True},{'expected_version':0},{'due_at':'2026-10-28T12:00'}])
def test_invalid_edits_do_not_change_storage(owner,meeting,settings,changes):
    row,now=meeting;task=data(create_task(owner,row,body(now)),201);before=saved(settings)
    assert_error(edit(owner,task,**changes),422,'VALIDATION_ERROR')
    assert saved(settings)==before


def test_parallel_edit_and_status_only_one_version_wins(owner,meeting,settings):
    row,now=meeting;task=data(create_task(owner,row,body(now)),201)
    engine=make_engine(database_path(settings));barrier=Barrier(2)
    def run(action):
        barrier.wait(timeout=5)
        try:
            if action=='edit':return service.edit_task(engine,1,task['id'],TaskUpdate(expected_version=1,title='并发编辑'))
            return service.change_status(engine,2,task['id'],'DONE',1)
        except Exception as e:return e
    try:
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,['edit','status']))
        from app.common.responses import ApiError
        errors=[r for r in results if isinstance(r,ApiError)]
        assert len(errors)==1 and errors[0].code=='VERSION_CONFLICT'
        with engine.connect() as conn:
            actual=conn.execute(select(tasks)).mappings().one()
            assert actual['version']==2
            assert (actual['title']=='并发编辑' and actual['status']=='TODO') or (actual['title']==task['title'] and actual['status']=='DONE')
    finally:engine.dispose()


@pytest.mark.parametrize('fail_first',[False,True])
def test_old_task_upgrade_keeps_rows_and_creation_snapshot(owner,meeting,settings,monkeypatch,fail_first):
    # Seed a separate 0006 database with legacy rows; no running connection
    # is downgraded and no developer data is used.
    from app.common.config import Settings
    from test_database import add_user,add_group
    from test_poll_structure import add_poll
    from test_meeting_structure import values
    legacy=Settings(_env_file=None,app_env='test',data_dir=settings.data_dir.parent/'legacy',frontend_dir=settings.frontend_dir)
    legacy.data_dir.mkdir();engine=make_engine(database_path(legacy),existing_only=False)
    try:
        with write_transaction(engine) as conn:
            cfg=migrate.migration_config();cfg.attributes['connection']=conn;command.upgrade(cfg,'0006_poll_lifecycle')
            add_user(conn);add_group(conn);conn.exec_driver_sql('INSERT INTO group_members VALUES (1,1,1000)')
            add_poll(conn,status='CONFIRMED');conn.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000)')
            from app.db.models import meetings
            conn.execute(meetings.insert().values(**values()))
            conn.exec_driver_sql("INSERT INTO tasks (id,meeting_id,group_id,creator_id,assignee_id,title,due_at,status,completed_at,client_request_id,created_at,updated_at) VALUES (1,1,1,1,1,'旧任务',2000,'DONE',1500,'621ff63b-2850-4c3c-a324-7201af5eb970',1000,1500)")
        with engine.connect() as conn:
            columns=[r[1] for r in conn.exec_driver_sql('PRAGMA table_info(tasks)')]
            before=conn.exec_driver_sql('SELECT * FROM tasks').all()
        if fail_first:
            original=migrate.make_engine
            def faulty(*args,**kwargs):
                inst=original(*args,**kwargs)
                @event.listens_for(inst,'before_cursor_execute')
                def fail(_c,_cu,sql,_p,_ctx,_m):
                    if sql.startswith('UPDATE tasks SET creation_payload'):raise RuntimeError('injected failure')
                return inst
            with monkeypatch.context() as patch:
                patch.setattr(migrate,'make_engine',faulty)
                with pytest.raises(ConfigurationError):migrate.upgrade(legacy)
            with engine.connect() as conn:
                assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()=='0006_poll_lifecycle'
                assert [r[1] for r in conn.exec_driver_sql('PRAGMA table_info(tasks)')]==columns
                assert conn.exec_driver_sql('SELECT * FROM tasks').all()==before
        migrate.upgrade(legacy);migrate.upgrade(legacy)
        with engine.connect() as conn:
            assert conn.exec_driver_sql('SELECT '+','.join(columns)+' FROM tasks').all()==before
            version,payload=conn.exec_driver_sql('SELECT version,creation_payload FROM tasks').one()
            assert version==1 and json.loads(payload)['title']=='旧任务'
            assert conn.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
    finally:engine.dispose()
