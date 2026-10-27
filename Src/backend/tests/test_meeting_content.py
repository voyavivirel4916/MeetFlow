import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from fastapi.testclient import TestClient

from app.auth import dependencies
from app.db.connection import database_path, make_engine
from app.main import create_app
from test_auth import login, register
from test_bootstrap import assert_error
from test_groups import create, data, other, owner
from test_meetings import closed, confirm
from test_polls import create_poll, draft, setup
from test_votes import opened


@pytest.fixture
def meeting(owner, closed):
    poll, now = closed
    return data(confirm(owner, poll), 201), now


def url(meeting):
    return f"/api/v1/meetings/{meeting['id']}"


def snapshot(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return connection.execute('SELECT * FROM meetings ORDER BY id').fetchall()


def test_partial_update_clear_plain_text_and_repeat(owner, other, meeting):
    row, now = meeting
    assert data(other.get(url(row))) == row
    now[0] += 1000
    text = '  <script>alert(1)</script>\n讨论🧩  '
    saved = data(owner.patch(url(row), json={'agenda': text}))
    assert saved['agenda'] == text and saved['minutes'] == ''
    assert saved['updated_at'] != row['updated_at']
    for key in row.keys() - {'agenda', 'minutes', 'updated_at'}:
        assert saved[key] == row[key]
    now[0] += 1000
    assert data(owner.patch(url(row), json={'agenda': text})) == saved
    minutes = data(owner.patch(url(row), json={'minutes': '结论\n下一步'}))
    assert minutes['agenda'] == text and minutes['minutes'] == '结论\n下一步'
    cleared = data(owner.patch(url(row), json={'agenda': '', 'minutes': ''}))
    assert cleared['agenda'] == cleared['minutes'] == ''
    assert data(other.get(url(row))) == cleared
    assert data(other.get(f"/api/v1/polls/{row['poll_id']}/meeting")) == cleared
    assert owner.get(url(row)).headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('body', [{}, {'agenda': None}, {'minutes': None}, {'agenda': 1}, {'minutes': []},
    {'title': '更换标题'}, {'start_at': '2026-10-27T00:00:00Z'}, {'selection_reason': '换理由'},
    {'agenda': 'x'*10001}, {'minutes': '😀'*10001}, {'agenda': '\x00'}, {'minutes': '\ud800'}])
def test_invalid_patch_is_atomic(owner, meeting, settings, body):
    row, _ = meeting
    before = snapshot(settings)
    response = owner.patch(url(row), content=json.dumps(body), headers={'Content-Type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert snapshot(settings) == before


def test_exact_unicode_limit_and_nonempty_partial_payload(owner, meeting):
    row, _ = meeting
    assert len(data(owner.patch(url(row), json={'agenda': '😀'*10000}))['agenda']) == 10000


def test_access_boundary_and_authentication(owner, other, meeting, settings):
    row, _ = meeting
    assert_error(other.patch(url(row), json={'agenda': '代写'}), 403, 'FORBIDDEN')
    with TestClient(create_app(settings), base_url='http://127.0.0.1', raise_server_exceptions=False) as client:
        assert_error(client.get(url(row)), 401, 'UNAUTHENTICATED')
        assert_error(client.patch(url(row), json={'agenda': ''}), 401, 'UNAUTHENTICATED')
        data(register(client, username='outsider', email='outsider@example.com'), 201)
        data(login(client, 'outsider'))
        assert_error(client.get(url(row)), 404, 'NOT_FOUND')
        assert_error(client.patch(url(row), json={'agenda': '跨组'}), 404, 'NOT_FOUND')
        assert_error(client.get(f"/api/v1/groups/{row['group_id']}/meetings"), 404, 'NOT_FOUND')
    assert_error(owner.get('/api/v1/meetings/99999'), 404, 'NOT_FOUND')


def test_list_stable_pagination_group_scope_and_empty(owner, other, meeting):
    row, _ = meeting
    # More than one result at the same time verifies the deterministic id tie-break.
    group = {'id': row['group_id']}
    for index in range(2):
        poll = data(create_poll(owner, group, draft(title=f'会议{index}')), 201)
        data(owner.post(f"/api/v1/polls/{poll['id']}/open", json={}))
        data(owner.post(f"/api/v1/polls/{poll['id']}/close", json={}))
        data(confirm(owner, poll, acknowledged=True, selection_reason='协调确认'), 201)
    path = f"/api/v1/groups/{row['group_id']}/meetings"
    all_rows = data(other.get(path))
    assert all_rows['total'] == 3
    ids = [item['id'] for item in all_rows['items']]
    assert ids == sorted(ids, reverse=True)
    assert data(other.get(path+'?page=2&page_size=1'))['items'][0]['id'] == ids[1]
    assert data(other.get(path+'?page=999999999999999999999999'))['items'] == []
    empty = data(create(owner), 201)
    assert data(owner.get(f"/api/v1/groups/{empty['id']}/meetings")) == {'items': [], 'page': 1, 'page_size': 20, 'total': 0}
    for query in ['page=0', 'page_size=0', 'page_size=51', 'page=x']:
        assert_error(owner.get(path+'?'+query), 422, 'VALIDATION_ERROR')


@pytest.mark.parametrize('stage', ['update', 'commit'])
def test_failed_save_rolls_back_both_fields(owner, meeting, settings, monkeypatch, stage):
    row, _ = meeting
    before = snapshot(settings)
    def fail_update(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith('UPDATE meetings'):
            raise OperationalError(None, None, sqlite3.OperationalError('injected write failure'))
    def fail_commit(connection):
        raise OperationalError(None, None, sqlite3.OperationalError('injected commit failure'))
    handler, name = (fail_update, 'before_cursor_execute') if stage == 'update' else (fail_commit, 'commit')
    original = dependencies.make_engine
    def faulty(path):
        engine = original(path)
        event.listen(engine, name, handler)
        return engine
    with monkeypatch.context() as patch:
        patch.setattr(dependencies, 'make_engine', faulty)
        assert_error(owner.patch(url(row), json={'agenda': 'new', 'minutes': 'new'}), 503, 'STORAGE_UNAVAILABLE')
    assert snapshot(settings) == before


def test_parallel_partial_updates_preserve_both_fields(owner, meeting, settings):
    from app.meetings import service
    from app.meetings.models import MeetingUpdate
    row, _ = meeting
    engine = make_engine(database_path(settings))
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(service.update_meeting, engine, 1, row['id'], MeetingUpdate(**body))
                       for body in [{'agenda': '议程'}, {'minutes': '纪要'}]]
            for future in futures:
                future.result()
    finally:
        engine.dispose()
    saved = data(owner.get(url(row)))
    assert saved['agenda'] == '议程' and saved['minutes'] == '纪要'
