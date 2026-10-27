import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError

from app.auth import dependencies
from app.db.connection import database_path
from test_auth import login
from test_auth_boundaries import simultaneous
from test_bootstrap import assert_error
from test_groups import create, data, other, owner
from test_matrix import submit
from test_polls import NOW, create_poll, draft, setup
from test_votes import opened


def path(poll):
    return f"/api/v1/polls/{poll['id']}"


def confirm(browser, poll, index=0, **changes):
    return browser.post(path(poll)+'/confirm',content=json.dumps({'slot_id':poll['slots'][index]['id'],**changes}),headers={'Content-Type':'application/json'})


@pytest.fixture
def closed(owner,other,opened):
    poll,now=opened
    submit(owner,poll,['AVAILABLE'])
    submit(other,poll,['MAYBE'])
    data(owner.post(path(poll)+'/close',json={}))
    return poll,now


def stored(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return {table:connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() for table in ['polls','meetings','participants','votes']}


def test_confirm_snapshot_same_slot_retry_and_other_slot_conflict(owner,other,closed,settings):
    poll,now=closed
    assert data(owner.get(path(poll)+'/meeting')) is None
    meeting=data(confirm(owner,poll),201)
    assert (meeting['poll_id'],meeting['group_id'],meeting['selected_slot_id']) == (poll['id'],poll['group_id'],poll['slots'][0]['id'])
    assert (meeting['start_at'],meeting['end_at'],meeting['title'],meeting['location']) == (poll['slots'][0]['start_at'],poll['slots'][0]['end_at'],poll['title'],poll['location'])
    assert meeting['agenda']==meeting['minutes']==meeting['selection_reason']==''
    before=stored(settings)
    now[0]+=1000
    assert data(confirm(owner,poll,selection_reason='不能覆盖原理由'))==meeting
    assert data(other.get(path(poll)+'/meeting'))==meeting
    assert_error(confirm(owner,poll,1,acknowledged=True,selection_reason='改时间'),409,'STATE_CONFLICT')
    assert stored(settings)==before
    assert data(owner.get(path(poll)))['status']=='CONFIRMED'


@pytest.mark.parametrize('value',['UNAVAILABLE',None])
@pytest.mark.parametrize('ack,reason',[(False,''),(True,''),(False,'仍需讨论')])
def test_required_risks_need_both_ack_and_reason(owner,opened,settings,value,ack,reason):
    poll,_=opened
    if value is not None:submit(owner,poll,[value])
    data(owner.post(path(poll)+'/close',json={}))
    before=stored(settings)
    assert_error(confirm(owner,poll,acknowledged=ack,selection_reason=reason),400,'ACK_REQUIRED')
    assert stored(settings)==before
    meeting=data(confirm(owner,poll,acknowledged=True,selection_reason=' 已核对必到成员安排 '),201)
    assert meeting['selection_reason']=='已核对必到成员安排'


def test_nonfirst_safe_candidate_needs_reason_but_required_maybe_is_not_unavailable(owner,closed,settings):
    poll,_=closed
    assert_error(confirm(owner,poll,1),400,'ACK_REQUIRED')
    assert data(confirm(owner,poll,1,acknowledged=True,selection_reason='成员同意稍后讨论'),201)['selected_slot_id']==poll['slots'][1]['id']


def test_required_maybe_warning_does_not_add_an_undocumented_mandatory_reason(owner,opened):
    poll,_=opened
    submit(owner,poll,['MAYBE'])
    data(owner.post(path(poll)+'/close',json={}))
    assert data(confirm(owner,poll),201)['selected_slot_id']==poll['slots'][0]['id']


@pytest.mark.parametrize('status',['DRAFT','OPEN','CANCELLED','CONFIRMED'])
def test_only_closed_can_create_a_meeting(owner,closed,settings,status):
    poll,_=closed
    with sqlite3.connect(database_path(settings)) as connection:connection.execute('UPDATE polls SET status=? WHERE id=?',(status,poll['id']))
    before=stored(settings)
    assert_error(confirm(owner,poll,acknowledged=True,selection_reason='已核对'),409,'STATE_CONFLICT')
    assert stored(settings)==before


@pytest.mark.parametrize('changes',[
    {'slot_id':True},{'slot_id':'1'},{'slot_id':0},{'slot_id':9223372036854775808},
    {'acknowledged':'true'},{'acknowledged':1},{'selection_reason':None},{'selection_reason':'字'*501},
    {'selection_reason':'\x00'},{'selection_reason':'\ud800'},{'score':999},{'group_id':2},
])
def test_strict_body_and_invalid_text_leave_state_unchanged(owner,closed,settings,changes):
    poll,_=closed
    before=stored(settings)
    assert_error(confirm(owner,poll,**changes),422,'VALIDATION_ERROR')
    assert stored(settings)==before


def test_foreign_slot_and_permissions(owner,other,closed,setup,settings):
    poll,_=closed
    second=data(create_poll(owner,setup[0]),201)
    assert_error(confirm(owner,poll,slot_id=second['slots'][0]['id']),422,'VALIDATION_ERROR')
    assert_error(confirm(other,poll),403,'FORBIDDEN')
    foreign_group=data(create(other),201)
    foreign=data(create_poll(other,foreign_group,draft(participants=[],slots=[])),201)
    assert_error(owner.post(path(foreign)+'/confirm',json={'slot_id':1}),404,'NOT_FOUND')
    assert_error(owner.get(path(foreign)+'/meeting'),404,'NOT_FOUND')
    other.cookies.clear()
    assert_error(confirm(other,poll),401,'UNAUTHENTICATED')
    assert_error(other.get(path(poll)+'/meeting'),401,'UNAUTHENTICATED')
    assert data(owner.get(path(poll)+'/meeting')) is None


@pytest.mark.parametrize('different',[False,True])
def test_parallel_confirms_create_one_meeting(owner,closed,settings,different):
    poll,_=closed
    def action(index):
        def run(browser):
            login(browser)
            return confirm(browser,poll,index,acknowledged=True,selection_reason='已核对安排')
        return run
    responses=simultaneous(settings,[action(0),action(1 if different else 0)])
    assert sorted(response.status_code for response in responses)==([201,409] if different else [200,201])
    assert len(stored(settings)['meetings'])==1
    if not different:assert responses[0].json()['data']==responses[1].json()['data']


@pytest.mark.parametrize('stage',['poll_update','commit'])
def test_mid_transaction_or_commit_failure_rolls_back_meeting_and_status(owner,closed,settings,monkeypatch,stage):
    poll,_=closed
    before=stored(settings);original=dependencies.make_engine;reached=[]
    def faulty(path):
        engine=original(path)
        def fail(connection):
            reached.append(connection.exec_driver_sql('SELECT COUNT(*) FROM meetings').scalar_one())
            raise OperationalError(None,None,sqlite3.OperationalError('injected meeting failure'))
        @event.listens_for(engine,'before_cursor_execute')
        def before(connection,_cursor,sql,_params,_ctx,_many):
            if stage=='poll_update' and sql.startswith('UPDATE polls'):fail(connection)
        if stage=='commit':event.listen(engine,'commit',fail)
        return engine
    with monkeypatch.context() as patch:
        patch.setattr(dependencies,'make_engine',faulty)
        response=confirm(owner,poll)
    assert_error(response,503,'STORAGE_UNAVAILABLE')
    assert reached==[1]
    assert stored(settings)==before


def test_confirm_waiting_for_lock_rechecks_current_time(owner,other,opened,settings,monkeypatch):
    poll,now=opened
    submit(owner,poll,['AVAILABLE'])
    original=dependencies.make_engine;started=Event()
    def observed(path):
        engine=original(path)
        event.listen(engine,'before_cursor_execute',lambda _c,_cu,sql,_p,_ctx,_many:started.set() if sql=='BEGIN IMMEDIATE' else None)
        return engine
    monkeypatch.setattr(dependencies,'make_engine',observed)
    blocker=sqlite3.connect(database_path(settings));blocker.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(confirm,owner,poll)
        try:
            assert started.wait(3);now[0]=NOW+60_000
        finally:blocker.rollback();blocker.close()
        assert future.result(timeout=5).status_code==201
    assert data(owner.get(path(poll)))['status']=='CONFIRMED'


def test_busy_confirm_keeps_state_and_can_retry(owner,closed,settings,monkeypatch):
    poll,_=closed
    before=stored(settings);original=dependencies.make_engine
    def quick(path):
        engine=original(path);event.listen(engine,'connect',lambda connection,_:connection.execute('PRAGMA busy_timeout=10'));return engine
    monkeypatch.setattr(dependencies,'make_engine',quick)
    blocker=sqlite3.connect(database_path(settings));blocker.execute('BEGIN IMMEDIATE')
    try:assert_error(confirm(owner,poll),503,'DB_BUSY')
    finally:blocker.rollback();blocker.close()
    assert stored(settings)==before
    assert confirm(owner,poll).status_code==201


def test_cancel_racing_confirmation_has_one_terminal_result(owner,closed,settings):
    poll,_=closed
    def choose(browser):
        login(browser);return confirm(browser,poll)
    def cancel(browser):
        login(browser);return browser.post(path(poll)+'/cancel',json={})
    chosen,cancelled=simultaneous(settings,[choose,cancel])
    assert (chosen.status_code,cancelled.status_code) in {(201,409),(409,200)}
    assert len(stored(settings)['meetings'])==(1 if chosen.status_code==201 else 0)


def test_expected_unique_conflict_reloads_original_but_does_not_swallow_other_integrity_errors(owner,closed,settings,monkeypatch):
    from app.meetings import service
    poll,_=closed
    original_meeting=data(confirm(owner,poll),201)
    # Force the uniqueness recovery branch; normal BEGIN IMMEDIATE serialization avoids this race.
    with sqlite3.connect(database_path(settings)) as connection:connection.execute("UPDATE polls SET status='CLOSED' WHERE id=?",(poll['id'],))
    original_find=service._find;calls=[]
    def miss_once(connection,poll_id):
        calls.append(poll_id)
        return None if len(calls)==1 else original_find(connection,poll_id)
    with monkeypatch.context() as patch:
        patch.setattr(service,'_find',miss_once)
        assert data(confirm(owner,poll))==original_meeting


def test_other_integrity_errors_are_storage_failures_not_false_duplicate_success(owner,closed,settings,monkeypatch):
    poll,_=closed;before=stored(settings);original=dependencies.make_engine
    def faulty(path):
        engine=original(path)
        @event.listens_for(engine,'before_cursor_execute')
        def fail(_c,_cu,sql,_p,_ctx,_many):
            if sql.startswith('INSERT INTO meetings'):
                error=sqlite3.IntegrityError('FOREIGN KEY constraint failed');error.sqlite_errorcode=sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
                raise IntegrityError(None,None,error)
        return engine
    with monkeypatch.context() as patch:
        patch.setattr(dependencies,'make_engine',faulty)
        assert_error(confirm(owner,poll),503,'STORAGE_UNAVAILABLE')
    assert stored(settings)==before
