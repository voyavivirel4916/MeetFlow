"""T19: full matrix, unknowns, row/column counts and consistent read snapshots."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Event

import pytest
from sqlalchemy import event

from app.auth import dependencies
from app.common.times import format_ms
from app.db.connection import database_path, make_engine
from app.votes import service
from app.votes.models import VotesIn
from test_bootstrap import assert_error
from test_database import add_user
from test_groups import data, other, owner
from test_polls import NOW, create_poll, draft, rows, setup
from test_votes import answers


@pytest.fixture
def matrix_poll(owner, setup, settings):
    group, now = setup
    engine = make_engine(database_path(settings))
    try:
        with engine.begin() as connection:
            for identifier in [3, 4]:
                add_user(connection, identifier)
                connection.exec_driver_sql('INSERT INTO group_members VALUES (?,?,?)', (group['id'], identifier, NOW))
    finally:
        engine.dispose()
    body = draft(participants=[{'user_id': identifier, 'importance': 'REQUIRED' if identifier <= 2 else 'NORMAL'} for identifier in [1,2,3,4]],
        slots=[{'start_at': format_ms(NOW+120_000+i*60_000), 'end_at': format_ms(NOW+180_000+i*60_000)} for i in range(3)])
    poll = data(create_poll(owner, group, body), 201)
    data(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}))
    return poll, now


def path(poll):
    return f"/api/v1/polls/{poll['id']}/matrix"


def submit(actor, poll, values=None):
    return data(actor.put(f"/api/v1/polls/{poll['id']}/votes/me", json=answers(poll, values)))


def check_counts(matrix):
    fields = {'AVAILABLE':'available_count','MAYBE':'maybe_count','UNAVAILABLE':'unavailable_count',None:'unanswered_count'}
    assert len(matrix['cells']) == len(matrix['participants'])*len(matrix['slots'])
    assert len({(cell['user_id'],cell['slot_id']) for cell in matrix['cells']}) == len(matrix['cells'])
    for table, key, match, total in [('participants','user_id','user_id',len(matrix['slots'])), ('slots','id','slot_id',len(matrix['participants']))]:
        for item in matrix[table]:
            counts = Counter(cell['availability'] for cell in matrix['cells'] if cell[match] == item[key])
            assert {field:item[field] for field in fields.values()} == {field:counts[value] for value,field in fields.items()}
            assert sum(item[field] for field in fields.values()) == total
    progress = matrix['progress']
    assert progress['participant_count'] == len(matrix['participants'])
    assert progress['submitted_count'] == sum(item['submitted_at'] is not None for item in matrix['participants'])
    assert progress['submitted_count']+progress['unsubmitted_count'] == progress['participant_count']


def test_four_people_three_slots_all_unknown(owner, matrix_poll):
    poll, _ = matrix_poll
    result = data(owner.get(path(poll)))
    assert result['progress'] == {'participant_count':4,'submitted_count':0,'unsubmitted_count':4}
    assert len(result['cells']) == 12
    assert all(cell['availability'] is None for cell in result['cells'])
    assert [slot['unanswered_count'] for slot in result['slots']] == [4,4,4]
    assert [person['unanswered_count'] for person in result['participants']] == [3,3,3,3]
    assert [(slot['id'],slot['start_at'],slot['end_at']) for slot in result['slots']] == [(slot['id'],slot['start_at'],slot['end_at']) for slot in poll['slots']]
    check_counts(result)


def test_three_states_unknown_overwrite_and_latest_submission(owner, other, matrix_poll, settings):
    poll, now = matrix_poll
    submit(owner,poll)
    submit(other,poll,['MAYBE','UNAVAILABLE','AVAILABLE'])
    engine = make_engine(database_path(settings))
    try:
        service.save_votes(engine,3,poll['id'],VotesIn.model_validate(answers(poll,['UNAVAILABLE','AVAILABLE','MAYBE'])))
    finally:
        engine.dispose()
    matrix = data(other.get(path(poll)))
    assert matrix['progress'] == {'participant_count':4,'submitted_count':3,'unsubmitted_count':1}
    assert [(slot['available_count'],slot['maybe_count'],slot['unavailable_count'],slot['unanswered_count']) for slot in matrix['slots']] == [(1,1,1,1)]*3
    assert matrix['participants'][3]['submitted_at'] is None
    check_counts(matrix)
    now[0] += 1000
    submit(other,poll,['AVAILABLE'])
    updated = data(owner.get(path(poll)))
    assert updated['progress']['submitted_count'] == 3
    assert updated['participants'][1]['submitted_at'] == format_ms(now[0])
    assert [cell['availability'] for cell in updated['cells'] if cell['user_id'] == 2] == ['AVAILABLE']*3
    assert updated['slots'][0]['available_count'] == 2
    check_counts(updated)


def test_member_not_in_roster_can_read_but_outsider_and_anonymous_cannot(owner, other, setup, settings):
    group, _ = setup
    poll = data(create_poll(owner,group,draft(participants=[{'user_id':1,'importance':'NORMAL'}])),201)
    before = rows(settings)
    assert data(other.get(path(poll)))['progress']['participant_count'] == 1
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('DELETE FROM group_members WHERE user_id=2 AND group_id=?',(group['id'],))
    assert_error(other.get(path(poll)),404,'NOT_FOUND')
    assert_error(other.get('/api/v1/polls/99999/matrix'),404,'NOT_FOUND')
    other.cookies.clear()
    assert_error(other.get(path(poll)),401,'UNAUTHENTICATED')
    assert rows(settings) == before


@pytest.mark.parametrize('status',['DRAFT','OPEN','CLOSED','CONFIRMED','CANCELLED'])
def test_all_states_can_read_matrix_without_mutating_data(owner, matrix_poll, settings, status):
    poll, _ = matrix_poll
    submit(owner,poll)
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE polls SET status=? WHERE id=?',(status,poll['id']))
    before = rows(settings)
    matrix = data(owner.get(path(poll)))
    assert matrix['effective_status'] == status
    assert matrix['progress']['submitted_count'] == 1
    check_counts(matrix)
    assert rows(settings) == before


def test_exact_deadline_is_effectively_closed_but_get_does_not_close_in_storage(owner, matrix_poll, settings):
    poll, now = matrix_poll
    before = rows(settings)
    now[0] = NOW+60_000
    assert data(owner.get(path(poll)))['effective_status'] == 'CLOSED'
    assert rows(settings) == before


def test_empty_draft_and_nonchronological_slot_ids(owner, setup):
    group, _ = setup
    empty = data(create_poll(owner,group,draft(participants=[],slots=[])),201)
    matrix = data(owner.get(path(empty)))
    assert matrix['participants'] == matrix['slots'] == matrix['cells'] == []
    assert matrix['progress'] == {'participant_count':0,'submitted_count':0,'unsubmitted_count':0}
    check_counts(matrix)
    body = draft()
    body['slots'] = [{'start_at':format_ms(NOW+300_000),'end_at':format_ms(NOW+360_000)}, *body['slots']]
    poll = data(create_poll(owner,group,body),201)
    matrix = data(owner.get(path(poll)))
    assert [slot['id'] for slot in matrix['slots']] == [slot['id'] for slot in poll['slots']]
    assert matrix['slots'][0]['id'] > matrix['slots'][1]['id']
    check_counts(matrix)


def test_maximum_twenty_by_fifteen_uses_bounded_queries(owner, setup, settings, monkeypatch):
    group, _ = setup
    engine = make_engine(database_path(settings))
    try:
        with engine.begin() as connection:
            for identifier in range(3,21):
                add_user(connection,identifier)
                connection.exec_driver_sql('INSERT INTO group_members VALUES (?,?,?)',(group['id'],identifier,NOW))
    finally:
        engine.dispose()
    body = draft(participants=[{'user_id':identifier,'importance':'NORMAL'} for identifier in range(1,21)],
        slots=[{'start_at':format_ms(NOW+120_000+i*60_000),'end_at':format_ms(NOW+180_000+i*60_000)} for i in range(15)])
    poll = data(create_poll(owner,group,body),201)
    original = dependencies.make_engine
    queries = []
    def observed(path):
        engine = original(path)
        event.listen(engine,'before_cursor_execute',lambda _c,_cu,sql,_p,_ctx,_m: queries.append(sql) if sql.lstrip().startswith('SELECT') else None)
        return engine
    monkeypatch.setattr(dependencies,'make_engine',observed)
    matrix = data(owner.get(path(poll)))
    assert len(matrix['cells']) == 300
    assert len(queries) <= 8
    assert len([sql for sql in queries if 'FROM votes' in sql]) == 1
    check_counts(matrix)


def test_other_poll_answers_do_not_leak(owner, setup):
    group, _ = setup
    first = data(create_poll(owner,group),201)
    second = data(create_poll(owner,group),201)
    data(owner.post(f"/api/v1/polls/{first['id']}/open",json={}))
    submit(owner,first,['AVAILABLE'])
    result = data(owner.get(path(second)))
    assert all(cell['availability'] is None for cell in result['cells'])
    assert result['progress']['submitted_count'] == 0


def test_response_contains_only_public_roster_and_time_fields(owner, matrix_poll):
    result = data(owner.get(path(matrix_poll[0])))
    assert set(result) == {'poll_id','effective_status','participants','slots','cells','progress'}
    assert set(result['participants'][0]) == {'user_id','username','importance','submitted_at','available_count','maybe_count','unavailable_count','unanswered_count'}
    assert set(result['cells'][0]) == {'user_id','slot_id','availability'}


@pytest.mark.parametrize('identifier',['0','-1','abc','9223372036854775808'])
def test_invalid_path_identifier(owner,setup,identifier):
    assert_error(owner.get(f'/api/v1/polls/{identifier}/matrix'),422,'VALIDATION_ERROR')


def test_status_clock_sampled_after_answer_read(owner,matrix_poll,settings,monkeypatch):
    poll, now = matrix_poll
    original = dependencies.make_engine
    def observed(path):
        engine = original(path)
        @event.listens_for(engine,'after_cursor_execute')
        def crossed(_c,_cu,sql,_p,_ctx,_m):
            if 'FROM votes' in sql:
                now[0] = NOW+60_000
        return engine
    monkeypatch.setattr(dependencies,'make_engine',observed)
    assert data(owner.get(path(poll)))['effective_status'] == 'CLOSED'
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT status FROM polls').fetchone()[0] == 'OPEN'


def test_read_snapshot_does_not_mix_old_submission_time_and_new_answers(owner,other,matrix_poll,settings,monkeypatch):
    poll, now = matrix_poll
    submit(other,poll,['AVAILABLE'])
    old = data(owner.get(path(poll)))
    now[0] += 1000
    original = dependencies.make_engine
    reading, writing, release = Event(),Event(),Event()
    def observed(path):
        engine = original(path)
        @event.listens_for(engine,'before_cursor_execute')
        def pause(_c,_cu,sql,_p,_ctx,_m):
            if 'FROM votes' in sql and sql.lstrip().startswith('SELECT') and reading.is_set() is False:
                reading.set()
                assert release.wait(5)
        @event.listens_for(engine,'commit')
        def committing(_c):
            writing.set()
        return engine
    with monkeypatch.context() as patch:
        patch.setattr(dependencies,'make_engine',observed)
        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(owner.get,path(poll))
            try:
                assert reading.wait(3)
                writer = pool.submit(submit,other,poll,['UNAVAILABLE'])
                assert writing.wait(3)
            finally:
                release.set()
            snapshot = data(reader.result(timeout=5))
            writer.result(timeout=5)
    assert snapshot == old
    latest = data(owner.get(path(poll)))
    assert latest['participants'][1]['submitted_at'] == format_ms(now[0])
    assert [cell['availability'] for cell in latest['cells'] if cell['user_id'] == 2] == ['UNAVAILABLE']*3
    check_counts(latest)
