"""V2 deletion, archive, access boundaries, races and transactional migration."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.common.config import ConfigurationError
from app.db import migrate
from app.db.connection import database_path, make_engine, write_transaction
from app.db.models import polls
from app.polls import service
from app.meetings import service as meeting_service
from app.meetings.models import ConfirmIn
from test_bootstrap import assert_error
from test_database import add_group, add_user, engine
from test_groups import create, data, other, owner
from test_meetings import closed, confirm, path
from test_meeting_content import meeting
from test_polls import setup, create_poll, draft, NOW
from test_votes import opened, answers
from test_task_structure import values


def listing(browser, group_id, view='current', **params):
    return browser.get(f'/api/v1/groups/{group_id}/polls', params={'view':view, **params})


def test_delete_restore_repeat_and_every_deleted_access_path(owner, other, setup, settings):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    base = path(poll)
    deleted = data(owner.post(base+'/delete', json={}))
    assert deleted['deleted_at'] is not None and deleted['status'] == 'DRAFT'
    now[0] += 1000
    assert data(owner.post(base+'/delete', json={})) == deleted
    assert data(listing(owner, group['id']))['total'] == 0
    assert data(listing(owner, group['id'], 'trash'))['items'] == [deleted]
    for browser in [owner, other]:
        for suffix in ['', '/votes/me', '/matrix', '/recommendations', '/meeting']:
            assert_error(browser.get(base+suffix),404,'NOT_FOUND')
        assert_error(browser.put(base,json=draft()),404,'NOT_FOUND')
        assert_error(browser.put(base+'/votes/me',json=answers(poll)),404,'NOT_FOUND')
        assert_error(confirm(browser,poll),404,'NOT_FOUND')
        for action in ['open','close','cancel','archive','unarchive']:
            assert_error(browser.post(base+'/'+action,json={}),404,'NOT_FOUND')
    assert_error(listing(other, group['id'], 'trash'),403,'FORBIDDEN')
    assert_error(other.post(base+'/restore',json={}),403,'FORBIDDEN')
    restored=data(owner.post(base+'/restore',json={}))
    assert restored['deleted_at'] is None and restored['status']=='DRAFT'
    assert data(owner.post(base+'/restore',json={}))==restored
    assert data(listing(other,group['id']))['items']==[restored]
    with sqlite3.connect(database_path(settings)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM participants').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM slots').fetchone()[0]==1


def test_open_requires_cancel_expired_open_can_be_deleted_and_not_reopened(owner, opened):
    poll,now=opened
    assert_error(owner.post(path(poll)+'/delete',json={}),409,'STATE_CONFLICT')
    now[0]+=60000
    deleted=data(owner.post(path(poll)+'/delete',json={}))
    assert deleted['status']=='CLOSED'
    restored=data(owner.post(path(poll)+'/restore',json={}))
    assert restored['status']=='CLOSED'
    assert_error(owner.put(path(poll)+'/votes/me',json=answers(poll)),409,'POLL_CLOSED')


def test_cancel_then_delete(owner, opened):
    poll,_=opened
    data(owner.post(path(poll)+'/cancel',json={}))
    assert data(owner.post(path(poll)+'/delete',json={}))['status']=='CANCELLED'


def test_archive_keeps_meeting_notes_tasks_and_owner_permissions(owner,other,meeting):
    from test_tasks import body, create_task
    row,now=meeting
    poll={'id':row['poll_id']}; base=path(poll)
    task=data(create_task(owner,row,body(now)),201)
    before=data(other.get(f"/api/v1/meetings/{row['id']}"))
    assert_error(owner.post(base+'/delete',json={}),409,'STATE_CONFLICT')
    for action in ['archive','unarchive']:
        assert_error(other.post(base+'/'+action,json={}),403,'FORBIDDEN')
    archived=data(owner.post(base+'/archive',json={}))
    assert archived['archived_at'] and not archived['deleted_at']
    now[0]+=1000
    assert data(owner.post(base+'/archive',json={}))==archived
    assert data(listing(owner,row['group_id']))['total']==0
    assert data(listing(other,row['group_id'],'history'))['items']==[archived]
    assert data(other.get(f"/api/v1/meetings/{row['id']}"))==before
    assert data(other.get('/api/v1/tasks/mine'))['items']==[task]
    assert data(owner.get(base))==archived
    assert data(confirm(owner,archived))==before
    current=data(owner.post(base+'/unarchive',json={}))
    assert current['archived_at'] is None
    assert data(owner.post(base+'/unarchive',json={}))==current


def test_wrong_state_bad_view_and_cross_group(owner,other,setup):
    group,_=setup
    poll=data(create_poll(owner,group),201)
    for action in ['archive','unarchive']:
        assert_error(owner.post(path(poll)+'/'+action,json={}),409,'STATE_CONFLICT')
    assert_error(listing(owner,group['id'],'invalid'),422,'VALIDATION_ERROR')
    another=data(create(other),201)
    for action in ['delete','restore','archive','unarchive']:
        assert_error(owner.post(f"/api/v1/polls/999/{action}",json={}),404,'NOT_FOUND')
    assert_error(listing(owner,another['id'],'trash'),404,'NOT_FOUND')


def test_visibility_pagination_totals(owner,setup):
    group,_=setup
    created=[data(create_poll(owner,group,draft(title=f'排期{i}')),201) for i in range(3)]
    data(owner.post(path(created[1])+'/delete',json={}))
    page=data(listing(owner,group['id'],page_size=1,page=2))
    assert page['total']==2 and len(page['items'])==1
    assert created[1]['id'] not in [p['id'] for p in page['items']]
    assert data(listing(owner,group['id'],'trash',page_size=1,page=2))['items']==[]


def test_delete_confirmation_race_has_only_one_winner(owner,closed,settings):
    poll,_=closed
    engine=make_engine(database_path(settings)); barrier=Barrier(2)
    def run(action):
        barrier.wait(timeout=5)
        try:
            if action=='delete':return service.organize_poll(engine,1,poll['id'],'delete')
            return meeting_service.confirm(engine,1,poll['id'],ConfirmIn(slot_id=poll['slots'][0]['id']))
        except Exception as e:return e
    try:
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(run,['delete','confirm']))
        from app.common.responses import ApiError
        errors=[r for r in results if isinstance(r,ApiError)]
        assert len(errors)==1 and errors[0].status in {404,409}
        with engine.connect() as conn:
            deleted=conn.execute(select(polls.c.deleted_at).where(polls.c.id==poll['id'])).scalar_one()
            count=conn.exec_driver_sql('SELECT COUNT(*) FROM meetings').scalar_one()
            assert (deleted is not None and count==0) or (deleted is None and count==1)
    finally:engine.dispose()


@pytest.mark.parametrize('changes',[{'archived_at':1000},{'deleted_at':1.5},{'archived_at':1.5,'status':'CONFIRMED'},
                                 {'deleted_at':1000,'status':'OPEN'},{'deleted_at':1000,'status':'CONFIRMED'},
                                 {'deleted_at':1000,'archived_at':1000,'status':'CONFIRMED'}])
def test_lifecycle_database_constraints(engine,changes):
    with write_transaction(engine) as conn:
        add_user(conn);add_group(conn)
        conn.exec_driver_sql("INSERT INTO polls (id,group_id,title,response_deadline,created_at,updated_at) VALUES (1,1,'test',2000,1000,1000)")
    with pytest.raises(IntegrityError):
        with write_transaction(engine) as conn:conn.execute(update(polls).where(polls.c.id==1).values(**changes))


@pytest.mark.parametrize('fail_first',[False,True])
def test_upgrade_preserves_all_old_data_and_rollback(settings,monkeypatch,fail_first):
    settings.data_dir.mkdir(parents=True)
    engine=make_engine(database_path(settings),existing_only=False)
    try:
        with write_transaction(engine) as conn:
            cfg=migrate.migration_config();cfg.attributes['connection']=conn;command.upgrade(cfg,'0005_tasks')
            add_user(conn);add_group(conn)
            conn.exec_driver_sql('INSERT INTO group_members VALUES (1,1,1000)')
            conn.exec_driver_sql("INSERT INTO polls (id,group_id,title,response_deadline,status,created_at,updated_at) VALUES (1,1,'old',2000,'CONFIRMED',1000,1000)")
            conn.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000)')
            conn.exec_driver_sql("INSERT INTO participants VALUES (1,1,1,'REQUIRED',1000)")
            conn.exec_driver_sql("INSERT INTO votes VALUES (1,1,1,'AVAILABLE',1000)")
            from app.db.models import meetings,tasks
            conn.execute(insert(meetings).values(**values()))
            conn.execute(insert(tasks).values(id=1,meeting_id=1,group_id=1,creator_id=1,assignee_id=1,title='old task',due_at=2000,
                status='DONE',completed_at=1500,client_request_id='621ff63b-2850-4c3c-a324-7201af5eb970',created_at=1000,updated_at=1500))
        with sqlite3.connect(database_path(settings)) as conn:
            names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'")]
            columns={n:[r[1] for r in conn.execute(f'PRAGMA table_info({n})')] for n in names}
            before={n:conn.execute(f'SELECT * FROM {n}').fetchall() for n in names}
        if fail_first:
            original=migrate.make_engine
            def faulty(*args,**kwargs):
                inst=original(*args,**kwargs)
                @event.listens_for(inst,'before_cursor_execute')
                def fail(_c,_cu,sql,_p,_ctx,_m):
                    if sql.startswith('CREATE INDEX ix_polls_group_visibility'):raise RuntimeError('injected')
                return inst
            with monkeypatch.context() as patch:
                patch.setattr(migrate,'make_engine',faulty)
                with pytest.raises(ConfigurationError):migrate.upgrade(settings)
            with sqlite3.connect(database_path(settings)) as conn:
                assert conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0005_tasks'
                assert [r[1] for r in conn.execute('PRAGMA table_info(polls)')]==columns['polls']
        migrate.upgrade(settings);migrate.upgrade(settings)
        with sqlite3.connect(database_path(settings)) as conn:
            assert before=={n:conn.execute(f'SELECT {",".join(columns[n])} FROM {n}').fetchall() for n in names}
            assert conn.execute('SELECT archived_at,deleted_at FROM polls').fetchall()==[(None,None)]
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:engine.dispose()
