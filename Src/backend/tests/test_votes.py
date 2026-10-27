from test_database import original_rows
"""T17 real database/API checks: own complete answers, atomicity and lock ordering."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from alembic import command
import pytest
from sqlalchemy import event, insert
from sqlalchemy.exc import IntegrityError, OperationalError

from app.auth import dependencies
from app.common.times import format_ms
from app.db.connection import database_path, make_engine, write_transaction, require_current_schema
from app.db.migrate import migration_config, upgrade
from app.db.models import votes
from test_database import add_group, add_user
from test_poll_structure import add_poll
from test_auth import login
from test_auth_boundaries import simultaneous
from test_bootstrap import assert_error
from test_groups import data, other, owner
from test_polls import NOW, create_poll, draft, setup


@pytest.fixture
def opened(owner, setup):
    group, now = setup
    poll = data(create_poll(owner, group, draft(slots=[
        {'start_at': format_ms(NOW+120_000+i*60_000), 'end_at': format_ms(NOW+180_000+i*60_000)}
        for i in range(3)])), 201)
    data(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}))
    return poll, now


def url(poll):
    return f"/api/v1/polls/{poll['id']}/votes/me"


def answers(poll, availability=None):
    values = availability or ['AVAILABLE', 'MAYBE', 'UNAVAILABLE']
    return {'votes': [{'slot_id': slot['id'], 'availability': values[i % len(values)]} for i, slot in enumerate(poll['slots'])]}


def stored(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return {name: connection.execute(f'SELECT * FROM {name} ORDER BY 1,2').fetchall() for name in ['votes', 'participants']}


def test_complete_save_override_and_own_only_read(owner, other, opened, settings):
    poll, now = opened
    assert data(owner.get(url(poll))) == {'poll_id': poll['id'], 'submitted_at': None, 'votes': []}
    first = data(owner.put(url(poll), json=answers(poll)))
    assert first == dict(poll_id=poll['id'], submitted_at=format_ms(now[0]), **answers(poll))
    assert data(other.get(url(poll)))['votes'] == []
    data(other.put(url(poll), json=answers(poll, ['MAYBE'])))
    now[0] += 1000
    replacement = answers(poll, ['UNAVAILABLE'])
    replacement['votes'].reverse()
    saved = data(owner.put(url(poll), json=replacement))
    assert saved['submitted_at'] == format_ms(now[0])
    assert saved['votes'] == answers(poll, ['UNAVAILABLE'])['votes']
    assert data(owner.get(url(poll))) == saved
    assert data(owner.put(url(poll), json=replacement)) == saved
    assert data(other.get(url(poll)))['votes'] == answers(poll, ['MAYBE'])['votes']
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM votes').fetchone()[0] == 6
        assert connection.execute('SELECT DISTINCT updated_at FROM votes WHERE user_id=1').fetchall() == [(now[0],)]
    roster = data(owner.get(f"/api/v1/polls/{poll['id']}"))['participants']
    assert roster[0]['submitted_at'] == saved['submitted_at']


@pytest.mark.parametrize('bad', [
    {}, {'votes': []}, {'votes': None}, {'votes': [{'slot_id': True, 'availability': 'AVAILABLE'}]},
    {'votes': [{'slot_id': '1', 'availability': 'AVAILABLE'}]},
    {'votes': [{'slot_id': 0, 'availability': 'AVAILABLE'}]},
    {'votes': [{'slot_id': 9223372036854775808, 'availability': 'AVAILABLE'}]},
    {'votes': [{'slot_id': 1, 'availability': 'UNKNOWN'}]},
    {'votes': [{'slot_id': 1, 'availability': None}]},
    {'votes': [{'slot_id': 1, 'availability': 'AVAILABLE', 'user_id': 2}]},
    {'votes': [{'slot_id': 1, 'availability': 'AVAILABLE'}]*2},
    {'votes': [{'slot_id': i+1, 'availability': 'AVAILABLE'} for i in range(16)]},
])
def test_invalid_body_keeps_all_previous_answers(owner, opened, settings, bad):
    poll, _ = opened
    data(owner.put(url(poll), json=answers(poll)))
    before = stored(settings)
    assert_error(owner.put(url(poll), json=bad), 422, 'VALIDATION_ERROR')
    assert stored(settings) == before


@pytest.mark.parametrize('change', ['missing', 'extra', 'foreign', 'actor', 'timestamp'])
def test_incomplete_cross_poll_and_impersonation_rejected(owner, opened, setup, settings, change):
    poll, _ = opened
    data(owner.put(url(poll), json=answers(poll)))
    body = answers(poll)
    if change == 'missing':
        body['votes'].pop()
    elif change == 'extra':
        body['votes'].append({'slot_id': 999999, 'availability': 'MAYBE'})
    elif change == 'foreign':
        second = data(create_poll(owner, setup[0]), 201)
        body['votes'][0]['slot_id'] = second['slots'][0]['id']
    elif change == 'actor':
        body['user_id'] = 2
    else:
        body['submitted_at'] = 'forged'
    before = stored(settings)
    assert_error(owner.put(url(poll), json=body), 422, 'VALIDATION_ERROR')
    assert stored(settings) == before


@pytest.mark.parametrize('method', ['get', 'put'])
def test_auth_nonparticipant_outsider_and_bad_ids(client, owner, other, setup, settings, method):
    group, _ = setup
    poll = data(create_poll(owner, group, draft(participants=[{'user_id': 1, 'importance': 'NORMAL'}])), 201)
    body = {'json': answers(poll)} if method == 'put' else {}
    before = stored(settings)
    # owner is the main client's cookie jar; explicitly remove it for anonymous access.
    raw_cookie = client.cookies.get('meetflow_session')
    client.cookies.clear()
    assert_error(getattr(client, method)(url(poll), **body), 401, 'UNAUTHENTICATED')
    client.cookies.set('meetflow_session', raw_cookie)
    assert_error(getattr(other, method)(url(poll), **body), 403, 'FORBIDDEN')
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('DELETE FROM group_members WHERE group_id=? AND user_id=2', (group['id'],))
    assert_error(getattr(other, method)(url(poll), **body), 404, 'NOT_FOUND')
    assert_error(getattr(other, method)('/api/v1/polls/999999/votes/me', **body), 404, 'NOT_FOUND')
    assert_error(getattr(owner, method)('/api/v1/polls/0/votes/me', **body), 422, 'VALIDATION_ERROR')
    assert stored(settings) == before


@pytest.mark.parametrize('status', ['DRAFT', 'CLOSED', 'CANCELLED', 'CONFIRMED'])
def test_other_states_block_write_allow_existing_read(owner, opened, settings, status):
    poll, _ = opened
    saved = data(owner.put(url(poll), json=answers(poll)))
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE polls SET status=? WHERE id=?', (status, poll['id']))
    before = stored(settings)
    assert_error(owner.put(url(poll), json=answers(poll, ['MAYBE'])), 409, 'POLL_CLOSED' if status == 'CLOSED' else 'STATE_CONFLICT')
    assert data(owner.get(url(poll))) == saved
    assert stored(settings) == before


def test_deadline_boundary_and_get_never_writes(owner, opened, settings):
    poll, now = opened
    now[0] = NOW+60_000-1
    saved = data(owner.put(url(poll), json=answers(poll)))
    before = stored(settings)
    now[0] += 1
    assert data(owner.get(url(poll))) == saved
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT status FROM polls').fetchone()[0] == 'OPEN'
    assert_error(owner.put(url(poll), json=answers(poll, ['MAYBE'])), 409, 'POLL_CLOSED')
    assert stored(settings) == before
    assert data(owner.get(f"/api/v1/polls/{poll['id']}"))['status'] == 'CLOSED'


@pytest.mark.parametrize('stage', ['insert', 'timestamp', 'commit', 'integrity'])
def test_failed_transaction_restores_entire_answer_and_timestamp(owner, opened, settings, monkeypatch, stage):
    poll, now = opened
    data(owner.put(url(poll), json=answers(poll)))
    before = stored(settings)
    now[0] += 1000
    original = dependencies.make_engine
    reached = []

    def faulty(path):
        engine = original(path)
        def fail(connection):
            reached.append(connection.exec_driver_sql('SELECT COUNT(*) FROM votes').scalar_one())
            kind = IntegrityError if stage == 'integrity' else OperationalError
            raise kind(None, None, sqlite3.IntegrityError('injected') if stage == 'integrity' else sqlite3.OperationalError('injected'))
        @event.listens_for(engine, 'before_cursor_execute')
        def execute(connection, _cursor, sql, _params, _context, _many):
            if (stage in {'insert', 'integrity'} and sql.startswith('INSERT INTO votes')) or (stage == 'timestamp' and sql.startswith('UPDATE participants')):
                fail(connection)
        if stage == 'commit':
            event.listen(engine, 'commit', fail)
        return engine

    with monkeypatch.context() as patch:
        patch.setattr(dependencies, 'make_engine', faulty)
        response = owner.put(url(poll), json=answers(poll, ['MAYBE']))
    assert_error(response, 409 if stage == 'integrity' else 503, 'STATE_CONFLICT' if stage == 'integrity' else 'STORAGE_UNAVAILABLE')
    assert reached
    assert stored(settings) == before


def test_lock_wait_crosses_deadline_before_business_check(owner, opened, settings, monkeypatch):
    poll, now = opened
    before = stored(settings)
    original = dependencies.make_engine
    started = Event()
    def observed(path):
        engine = original(path)
        event.listen(engine, 'before_cursor_execute', lambda _c, _cu, sql, _p, _ctx, _m: started.set() if sql == 'BEGIN IMMEDIATE' else None)
        return engine
    monkeypatch.setattr(dependencies, 'make_engine', observed)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner.put, url(poll), json=answers(poll))
        try:
            assert started.wait(3)
            now[0] = NOW+60_000
        finally:
            blocker.rollback(); blocker.close()
        assert_error(future.result(timeout=5), 409, 'POLL_CLOSED')
    assert stored(settings) == before


def test_concurrent_same_actor_never_mixes_answers(owner, opened, settings):
    poll, _ = opened
    def action(value):
        def run(browser):
            login(browser)
            return browser.put(url(poll), json=answers(poll, [value]))
        return run
    responses = simultaneous(settings, [action('AVAILABLE'), action('UNAVAILABLE')])
    assert [response.status_code for response in responses] == [200, 200]
    final = data(owner.get(url(poll)))
    assert final in [response.json()['data'] for response in responses]
    assert len({item['availability'] for item in final['votes']}) == 1
    assert len(stored(settings)['votes']) == 3


def test_close_racing_vote_is_serialized(owner, opened, settings):
    poll, _ = opened
    def vote(browser):
        login(browser)
        return browser.put(url(poll), json=answers(poll))
    def close(browser):
        login(browser)
        return browser.post(f"/api/v1/polls/{poll['id']}/close", json={})
    saved, closed = simultaneous(settings, [vote, close])
    assert closed.status_code == 200
    assert saved.status_code in {200, 409}
    final = data(owner.get(url(poll)))
    assert final['votes'] == (answers(poll)['votes'] if saved.status_code == 200 else [])
    assert data(owner.get(f"/api/v1/polls/{poll['id']}"))['status'] == 'CLOSED'


@pytest.mark.parametrize('changes', [
    {'availability': 'UNKNOWN'}, {'availability': None}, {'updated_at': 1.5},
    {'poll_id': 999}, {'slot_id': 999}, {'user_id': 999}, {'poll_id': 2},
])
def test_database_rejects_invalid_values_and_cross_poll_keys(owner, opened, settings, changes):
    poll, _ = opened
    engine = make_engine(database_path(settings))
    try:
        with pytest.raises(IntegrityError):
            with write_transaction(engine) as connection:
                connection.execute(insert(votes).values(**(dict(poll_id=poll['id'], slot_id=poll['slots'][0]['id'],
                    user_id=1, availability='AVAILABLE', updated_at=NOW) | changes)))
    finally:
        engine.dispose()
    assert stored(settings)['votes'] == []


def test_busy_vote_keeps_old_results_then_recovers(owner, opened, settings, monkeypatch):
    poll, _ = opened
    data(owner.put(url(poll), json=answers(poll)))
    before = stored(settings)
    original = dependencies.make_engine
    def quick(path):
        engine = original(path)
        event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA busy_timeout=10'))
        return engine
    monkeypatch.setattr(dependencies, 'make_engine', quick)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    try:
        assert_error(owner.put(url(poll), json=answers(poll, ['MAYBE'])), 503, 'DB_BUSY')
    finally:
        blocker.rollback(); blocker.close()
    assert stored(settings) == before
    assert data(owner.put(url(poll), json=answers(poll, ['MAYBE'])))['votes'] == answers(poll, ['MAYBE'])['votes']


def test_cross_origin_write_is_rejected_without_changes(owner, opened, settings):
    poll, _ = opened
    before = stored(settings)
    response = owner.put(url(poll), json=answers(poll), headers={'Origin': 'https://evil.example'})
    assert response.status_code == 403
    assert stored(settings) == before


def test_upgrade_from_poll_schema_preserves_records_and_is_repeatable(settings):
    settings.data_dir.mkdir(parents=True)
    engine = make_engine(database_path(settings), existing_only=False)
    try:
        with write_transaction(engine) as connection:
            config = migration_config()
            config.attributes['connection'] = connection
            command.upgrade(config, '0002_poll_structure')
            add_user(connection)
            add_group(connection)
            connection.exec_driver_sql('INSERT INTO group_members VALUES (1,1,1000)')
            add_poll(connection, status='OPEN')
            connection.exec_driver_sql("INSERT INTO participants VALUES (1,1,1,'REQUIRED',NULL)")
            connection.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000)')
        with sqlite3.connect(database_path(settings)) as connection:
            before = {table: original_rows(connection, table)
                for table in ['users', 'groups', 'group_members', 'polls', 'participants', 'slots']}
        upgrade(settings)
        upgrade(settings)
        require_current_schema(settings)
        with sqlite3.connect(database_path(settings)) as connection:
            assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0006_poll_lifecycle'
            assert connection.execute('SELECT * FROM votes').fetchall() == []
            assert {table: original_rows(connection, table) for table in before} == before
    finally:
        engine.dispose()
