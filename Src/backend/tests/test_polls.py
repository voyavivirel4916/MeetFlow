import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.auth import dependencies
from app.common import clock
from app.common.times import format_ms, parse_rfc3339, to_ms
from app.db.connection import database_path
from app.polls.models import DraftIn
from test_auth import login
from test_auth_boundaries import simultaneous
from test_bootstrap import assert_error
from test_groups import create, data, join, other, owner

NOW = to_ms(parse_rfc3339('2026-10-27T00:00:00Z'))


@pytest.fixture
def setup(owner, other, settings, monkeypatch):
    now = [NOW]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    # Sessions were created before this fixture froze the business clock.
    # Align both timestamps so the fixed expiry never precedes a real-world
    # creation date as the calendar advances. Production auth is unchanged.
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE sessions SET created_at=?, expires_at=?', (NOW, NOW + 100_000_000))
    group = data(create(owner), 201)
    join(other, group['invite_code'])
    return group, now


def draft(**changes):
    value = dict(title='  课程讨论  ', description='讨论实现方案', location='2015A',
        response_deadline=format_ms(NOW + 60_000), participants=[{'user_id': 1, 'importance': 'REQUIRED'}, {'user_id': 2, 'importance': 'NORMAL'}],
        slots=[{'start_at': format_ms(NOW + 120_000), 'end_at': format_ms(NOW + 180_000)}])
    return dict(value, **changes)


def create_poll(owner, group, body=None):
    return owner.post(f"/api/v1/groups/{group['id']}/polls", json=draft() if body is None else body)


def rows(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall() for table in ['polls', 'participants', 'slots']}


def test_create_replace_read_and_publish_freeze(owner, other, setup, settings):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    assert poll['title'] == '课程讨论'
    assert poll['status'] == poll['effective_status'] == 'DRAFT'
    assert all(set(item) == {'user_id', 'username', 'importance', 'submitted_at'} and item['submitted_at'] is None for item in poll['participants'])
    assert data(other.get(f"/api/v1/polls/{poll['id']}")) == poll
    now[0] += 1000
    replacement = draft(title='更换主题', participants=[{'user_id': 2, 'importance': 'REQUIRED'}], slots=[])
    replaced = data(owner.put(f"/api/v1/polls/{poll['id']}", json=replacement))
    assert replaced['slots'] == [] and [item['user_id'] for item in replaced['participants']] == [2]
    assert replaced['updated_at'] == format_ms(now[0])
    assert data(owner.put(f"/api/v1/polls/{poll['id']}", json=draft()))['title'] == '课程讨论'
    opened = data(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}))
    assert opened['status'] == opened['effective_status'] == 'OPEN'
    before = rows(settings)
    assert_error(owner.put(f"/api/v1/polls/{poll['id']}", json=replacement), 409, 'STATE_CONFLICT')
    assert rows(settings) == before


def test_empty_arrays_and_past_deadline_can_be_saved_as_draft(owner, setup):
    group, _ = setup
    poll = data(create_poll(owner, group, draft(participants=[], slots=[], response_deadline=format_ms(NOW-1))), 201)
    assert poll['participants'] == poll['slots'] == []
    assert_error(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}), 422, 'VALIDATION_ERROR')


@pytest.mark.parametrize('changes', [
    {'title': ''}, {'title': ' \n'}, {'title': 'x'*101}, {'title': 1}, {'title': '\ud800'},
    {'description': 'x'*10001}, {'location': 'x'*201}, {'location': '\x00'},
    {'response_deadline': '2026-10-27T10:00:00'}, {'response_deadline': NOW},
    {'participants': [{'user_id': True, 'importance': 'NORMAL'}]},
    {'participants': [{'user_id': 1, 'importance': 'ADMIN'}]},
    {'participants': [{'user_id': 1, 'importance': 'NORMAL', 'submitted_at': 'forged'}]},
    {'participants': [{'user_id': 1, 'importance': 'NORMAL'}]*2},
    {'slots': [{'start_at': format_ms(NOW+1000), 'end_at': format_ms(NOW+1000)}]},
    {'slots': [{'start_at': format_ms(NOW+2000), 'end_at': format_ms(NOW+1000)}]},
    {'slots': [{'id': 1, 'start_at': format_ms(NOW+1000), 'end_at': format_ms(NOW+2000)}]},
    {'slots': [{'start_at': '2026-10-27T09:00:00+08:00', 'end_at': '2026-10-27T09:01:00+08:00'},
               {'start_at': '2026-10-27T01:00:00Z', 'end_at': '2026-10-27T01:01:00Z'}]},
    {'status': 'OPEN'}, {'group_id': 2}, {'unknown': 'private-value'},
])
def test_invalid_draft_rejected_without_insert_or_echo(owner, setup, settings, changes):
    group, _ = setup
    response = owner.post(f"/api/v1/groups/{group['id']}/polls", content=json.dumps(draft(**changes)), headers={'Content-Type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert 'private-value' not in response.text
    assert rows(settings) == {'polls': [], 'participants': [], 'slots': []}


@pytest.mark.parametrize('value', ['2026-10-27', '2026-10-27 10:00:00Z', '2026-02-30T10:00:00Z',
    '2026-10-27T10:00:00+01:99', '2026-10-27T10:00:00+24:00', '2026-10-27T10:00:00+0800', None, 1])
def test_rfc3339_rejects_ambiguous_or_invalid_inputs(value):
    with pytest.raises(ValidationError):
        DraftIn.model_validate(draft(response_deadline=value))


def test_rfc3339_cross_day_fraction_and_unicode_limits(owner, setup):
    group, _ = setup
    poll = data(create_poll(owner, group, draft(title='😀'*100, description='😀'*10000, location='地'*200,
        response_deadline='2026-10-27T00:00:59.123987+08:00', slots=[])), 201)
    assert poll['response_deadline'] == '2026-10-26T16:00:59.123Z'
    assert poll['title'] == '😀'*100


def test_cross_group_participants_rejected_and_old_draft_preserved(owner, other, setup, settings):
    group, _ = setup
    poll = data(create_poll(owner, group), 201)
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute("INSERT INTO users(username,email,password_hash,created_at) VALUES('outsider','out@example.com','unused',0)")
    before = rows(settings)
    invalid = draft(participants=[{'user_id': 3, 'importance': 'NORMAL'}])
    assert_error(owner.put(f"/api/v1/polls/{poll['id']}", json=invalid), 422, 'VALIDATION_ERROR')
    assert_error(create_poll(owner, group, invalid), 422, 'VALIDATION_ERROR')
    assert rows(settings) == before


@pytest.mark.parametrize('method,path,body', [
    ('post', '/groups/1/polls', 'draft'), ('get', '/groups/1/polls', None), ('get', '/polls/1', None),
    ('put', '/polls/1', 'draft'), ('post', '/polls/1/open', {}), ('post', '/polls/1/close', {}), ('post', '/polls/1/cancel', {}),
])
def test_every_poll_endpoint_requires_session(client, method, path, body):
    payload = draft() if body == 'draft' else body
    response = getattr(client, method)('/api/v1'+path, **({'json': payload} if payload is not None else {}))
    assert_error(response, 401, 'UNAUTHENTICATED')


def test_member_cannot_write_and_nonmember_cannot_infer_existence(owner, other, setup, settings):
    group, _ = setup
    poll = data(create_poll(owner, group, draft(participants=[{'user_id': 1, 'importance': 'REQUIRED'}])), 201)
    before = rows(settings)
    assert_error(create_poll(other, group), 403, 'FORBIDDEN')
    assert_error(other.put(f"/api/v1/polls/{poll['id']}", json=draft()), 403, 'FORBIDDEN')
    for action in ['open', 'close', 'cancel']:
        assert_error(other.post(f"/api/v1/polls/{poll['id']}/{action}", json={}), 403, 'FORBIDDEN')
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('DELETE FROM group_members WHERE user_id=2')
    for action in ['', '/open', '/close', '/cancel']:
        call = other.get if not action else lambda path: other.post(path, json={})
        hidden = assert_error(call(f"/api/v1/polls/{poll['id']}{action}"), 404, 'NOT_FOUND')['error']
        missing = assert_error(call('/api/v1/polls/99999'+action), 404, 'NOT_FOUND')['error']
        assert hidden == missing
    assert_error(other.get(f"/api/v1/groups/{group['id']}/polls"), 404, 'NOT_FOUND')
    assert rows(settings) == before


@pytest.mark.parametrize('changes', [
    {'participants': []}, {'slots': []},
    {'slots': [{'start_at': format_ms(NOW+120_000+i*1000), 'end_at': format_ms(NOW+180_000+i*1000)} for i in range(16)]},
    {'response_deadline': format_ms(NOW)}, {'response_deadline': format_ms(NOW-1)},
    {'response_deadline': format_ms(NOW+120_000)}, {'response_deadline': format_ms(NOW+150_000)},
])
def test_invalid_publish_preserves_draft(owner, setup, settings, changes):
    group, _ = setup
    poll = data(create_poll(owner, group, draft(**changes)), 201)
    before = rows(settings)
    assert_error(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}), 422, 'VALIDATION_ERROR')
    assert rows(settings) == before


@pytest.mark.parametrize('status', ['DRAFT', 'OPEN', 'CLOSED', 'CONFIRMED', 'CANCELLED'])
@pytest.mark.parametrize('action', ['open', 'close', 'cancel'])
def test_complete_transition_matrix_and_idempotent_times(owner, setup, settings, status, action):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE polls SET status=? WHERE id=?', (status, poll['id']))
    now[0] += 1000
    allowed = {'open': {'DRAFT': 'OPEN'}, 'close': {'OPEN': 'CLOSED', 'CLOSED': 'CLOSED'},
               'cancel': {'DRAFT': 'CANCELLED', 'OPEN': 'CANCELLED', 'CLOSED': 'CANCELLED', 'CANCELLED': 'CANCELLED'}}
    before = rows(settings)
    response = owner.post(f"/api/v1/polls/{poll['id']}/{action}", json={})
    if status in allowed[action]:
        result = data(response)
        assert result['status'] == allowed[action][status]
        assert result['updated_at'] == (poll['updated_at'] if status == result['status'] else format_ms(now[0]))
    else:
        assert_error(response, 409, 'STATE_CONFLICT')
        assert rows(settings) == before


@pytest.mark.parametrize('offset,expected', [(-1000, 'OPEN'), (0, 'CLOSED'), (1000, 'CLOSED')])
def test_deadline_exact_boundary_reads_are_readonly(owner, other, setup, settings, offset, expected):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    owner.post(f"/api/v1/polls/{poll['id']}/open", json={})
    now[0] = NOW+60_000+offset
    before = rows(settings)
    detail = data(other.get(f"/api/v1/polls/{poll['id']}"))
    listing = data(other.get(f"/api/v1/groups/{group['id']}/polls"))['items'][0]
    assert detail['status'] == listing['status'] == 'OPEN'
    assert detail['effective_status'] == listing['effective_status'] == expected
    assert rows(settings) == before


@pytest.mark.parametrize('action', ['open', 'replace', 'close', 'cancel'])
def test_next_authorized_write_materializes_expiry_even_on_state_conflict(owner, setup, settings, action):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    owner.post(f"/api/v1/polls/{poll['id']}/open", json={})
    now[0] = NOW+60_000
    response = owner.put(f"/api/v1/polls/{poll['id']}", json=draft()) if action == 'replace' else owner.post(f"/api/v1/polls/{poll['id']}/{action}", json={})
    if action in {'open', 'replace'}:
        assert_error(response, 409, 'STATE_CONFLICT')
    else:
        assert data(response)['status'] == ('CANCELLED' if action == 'cancel' else 'CLOSED')
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT status FROM polls WHERE id=?', (poll['id'],)).fetchone()[0] == ('CANCELLED' if action == 'cancel' else 'CLOSED')


@pytest.mark.parametrize('query', ['page=0', 'page_size=51', 'page_size=0', 'page=no'])
def test_list_pagination_validation(owner, setup, query):
    group, _ = setup
    assert_error(owner.get(f"/api/v1/groups/{group['id']}/polls?{query}"), 422, 'VALIDATION_ERROR')


def test_list_pagination_and_batch_child_queries(owner, other, setup, monkeypatch):
    group, _ = setup
    ids = [data(create_poll(owner, group, draft(title=f'排期{i}')), 201)['id'] for i in range(3)]
    original = dependencies.make_engine
    selects = []

    def observed(path):
        engine = original(path)
        event.listen(engine, 'before_cursor_execute', lambda _c, _cu, sql, _p, _ctx, _m: selects.append(sql) if sql.startswith('SELECT') else None)
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', observed)
    listing = data(other.get(f"/api/v1/groups/{group['id']}/polls?page_size=2"))
    assert [item['id'] for item in listing['items']] == ids[::-1][:2]
    assert len([sql for sql in selects if 'FROM participants' in sql]) == 1
    assert len([sql for sql in selects if 'FROM slots' in sql]) == 1
    assert data(owner.get(f"/api/v1/groups/{group['id']}/polls?page=2&page_size=2"))['items'][0]['id'] == ids[0]
    assert data(owner.get(f"/api/v1/groups/{group['id']}/polls?page="+'9'*100))['items'] == []


@pytest.mark.parametrize('operation', ['create', 'replace', 'open', 'close', 'cancel'])
def test_commit_failure_rolls_back_whole_poll_write(owner, setup, settings, monkeypatch, operation):
    group, _ = setup
    poll = data(create_poll(owner, group), 201)
    if operation in {'close', 'cancel'}:
        owner.post(f"/api/v1/polls/{poll['id']}/open", json={})
    before = rows(settings)
    original = dependencies.make_engine
    reached = []

    def observed(path):
        engine = original(path)

        @event.listens_for(engine, 'commit')
        def fail(connection):
            reached.append(connection.exec_driver_sql('SELECT COUNT(*) FROM polls').scalar_one())
            raise OperationalError(None, None, sqlite3.OperationalError('injected commit failure'))
        return engine

    with monkeypatch.context() as patch:
        patch.setattr(dependencies, 'make_engine', observed)
        if operation == 'create':
            response = create_poll(owner, group)
        elif operation == 'replace':
            response = owner.put(f"/api/v1/polls/{poll['id']}", json=draft(title='替换后失败', participants=[], slots=[]))
        else:
            response = owner.post(f"/api/v1/polls/{poll['id']}/{operation}", json={})
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert reached == [2 if operation == 'create' else 1]
    assert rows(settings) == before


def test_publish_time_is_checked_after_write_lock_wait(owner, setup, settings, monkeypatch):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
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
        future = pool.submit(owner.post, f"/api/v1/polls/{poll['id']}/open", json={})
        try:
            assert started.wait(3)
            now[0] = NOW+60_000
        finally:
            blocker.rollback(); blocker.close()
        assert_error(future.result(timeout=5), 422, 'VALIDATION_ERROR')
    assert data(owner.get(f"/api/v1/polls/{poll['id']}"))['status'] == 'DRAFT'


def test_publish_racing_replace_preserves_frozen_consistent_structure(owner, setup, settings):
    group, _ = setup
    poll = data(create_poll(owner, group), 201)

    def action(kind):
        def run(browser):
            login(browser)
            if kind == 'open':
                return browser.post(f"/api/v1/polls/{poll['id']}/open", json={})
            return browser.put(f"/api/v1/polls/{poll['id']}", json=draft(title='竞争后的主题', participants=[{'user_id': 2, 'importance': 'NORMAL'}]))
        return run

    opened, replaced = simultaneous(settings, [action('open'), action('replace')])
    assert opened.status_code == 200
    assert replaced.status_code in {200, 409}
    final = data(owner.get(f"/api/v1/polls/{poll['id']}"))
    assert final['status'] == 'OPEN'
    assert final['title'] == ('竞争后的主题' if replaced.status_code == 200 else '课程讨论')
    assert len(final['participants']) == (1 if replaced.status_code == 200 else 2)
    assert len(final['slots']) == 1


def test_poll_text_and_times_are_not_in_request_logs(owner, setup, caplog):
    group, _ = setup
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        poll = data(create_poll(owner, group, draft(title='private-poll-marker', description='private-description-marker')), 201)
        owner.get(f"/api/v1/polls/{poll['id']}")
    assert 'private-poll-marker' not in caplog.text and 'private-description-marker' not in caplog.text


@pytest.mark.parametrize('operation', ['create', 'replace'])
def test_child_insert_failure_restores_entire_previous_structure(owner, setup, settings, monkeypatch, operation):
    group, _ = setup
    poll = data(create_poll(owner, group), 201)
    before = rows(settings)
    original = dependencies.make_engine

    def faulty(path):
        engine = original(path)

        @event.listens_for(engine, 'before_cursor_execute')
        def fail(_connection, _cursor, sql, _parameters, _context, _many):
            if sql.startswith('INSERT INTO slots'):
                raise OperationalError(None, None, sqlite3.OperationalError('injected child insert failure'))
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', faulty)
    payload = draft(title='不能留下的半份草稿', participants=[{'user_id': 2, 'importance': 'REQUIRED'}])
    response = create_poll(owner, group, payload) if operation == 'create' else owner.put(f"/api/v1/polls/{poll['id']}", json=payload)
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert rows(settings) == before


def test_read_crossing_deadline_uses_clock_after_child_query(owner, setup, settings, monkeypatch):
    group, now = setup
    poll = data(create_poll(owner, group), 201)
    owner.post(f"/api/v1/polls/{poll['id']}/open", json={})
    original = dependencies.make_engine
    started, release = Event(), Event()

    def observed(path):
        engine = original(path)

        @event.listens_for(engine, 'before_cursor_execute')
        def pause(_connection, _cursor, sql, _parameters, _context, _many):
            if 'FROM slots' in sql:
                started.set()
                assert release.wait(3)
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', observed)
    before = rows(settings)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner.get, f"/api/v1/polls/{poll['id']}")
        try:
            assert started.wait(3)
            now[0] = NOW+60_000
        finally:
            release.set()
        result = data(future.result(timeout=5))
    assert result['status'] == 'OPEN' and result['effective_status'] == 'CLOSED'
    assert rows(settings) == before


def test_busy_publish_does_not_change_draft_and_can_recover(owner, setup, settings, monkeypatch):
    group, _ = setup
    poll = data(create_poll(owner, group), 201)
    before = rows(settings)
    original = dependencies.make_engine

    def quick(path):
        engine = original(path)
        event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA busy_timeout=10'))
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', quick)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    try:
        assert_error(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}), 503, 'DB_BUSY')
    finally:
        blocker.rollback(); blocker.close()
    assert rows(settings) == before
    assert data(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}))['status'] == 'OPEN'
