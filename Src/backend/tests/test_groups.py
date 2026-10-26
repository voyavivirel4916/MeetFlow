import json
import logging
import sqlite3
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.auth import dependencies
from app.common import clock
from app.db.connection import database_path
from app.groups import service
from app.main import create_app
from test_auth import login, register
from test_auth_boundaries import simultaneous
from test_bootstrap import assert_error


@pytest.fixture
def owner(client):
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    return client


@pytest.fixture
def other(settings):
    with TestClient(create_app(settings), base_url='http://127.0.0.1', raise_server_exceptions=False) as browser:
        assert register(browser, username='member', email='member@example.com').status_code == 201
        assert login(browser, username='member').status_code == 200
        yield browser


def create(browser, name='MeetFlow项目组', **changes):
    return browser.post('/api/v1/groups', json={'name': name, **changes})


def join(browser, code):
    return browser.post('/api/v1/groups/join', json={'invite_code': code})


def data(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['request_id'] == response.headers['X-Request-ID']
    return response.json()['data']


def fill_members(settings, group_id, target):
    # Capacity fixtures reuse the real registered hash; they are never production/demo data.
    with sqlite3.connect(database_path(settings)) as connection:
        count = connection.execute('SELECT COUNT(*) FROM group_members WHERE group_id=?', (group_id,)).fetchone()[0]
        password_hash = connection.execute('SELECT password_hash FROM users LIMIT 1').fetchone()[0]
        for number in range(count, target):
            username = f'seed_{group_id}_{number}'
            user_id = connection.execute('INSERT INTO users(username,email,password_hash,created_at) VALUES(?,?,?,?)',
                (username, username + '@example.com', password_hash, 1)).lastrowid
            connection.execute('INSERT INTO group_members VALUES(?,?,?)', (group_id, user_id, 1))


def test_ac02_four_accounts_repeat_join_reset_and_member_privacy(owner, settings):
    group = data(create(owner, '  软件工程小组  ', description='先排期，再行动'), 201)
    identifier, code = group['id'], group['invite_code']
    assert group == {'id': identifier, 'name': '软件工程小组', 'description': '先排期，再行动',
                     'owner_id': 1, 'member_count': 1, 'invite_code': code, 'invite_enabled': True}
    with ExitStack() as stack:
        members = []
        for number in range(3):
            browser = stack.enter_context(TestClient(create_app(settings), base_url='http://127.0.0.1'))
            username = f'student_{number}'
            register(browser, username=username, email=username + '@example.com')
            login(browser, username=username)
            joined = data(join(browser, '  ' + code.lower() + '  '))
            assert set(joined) == {'id', 'name', 'description', 'owner_id', 'member_count'}
            assert data(join(browser, code))['member_count'] == number + 2
            members.append(browser)
        assert data(owner.get(f'/api/v1/groups/{identifier}'))['member_count'] == 4
        for browser in [owner, *members]:
            roster = data(browser.get(f'/api/v1/groups/{identifier}/members'))['items']
            assert len(roster) == 4
            assert [row['role'] for row in roster] == ['OWNER', 'MEMBER', 'MEMBER', 'MEMBER']
            assert all(set(row) == {'user_id', 'username', 'role'} for row in roster)
        assert 'invite_code' not in data(members[0].get(f'/api/v1/groups/{identifier}'))
        assert 'invite_code' not in data(members[0].get('/api/v1/groups'))['items'][0]
        assert_error(members[0].post(f'/api/v1/groups/{identifier}/invite-code/reset', json={}), 403, 'FORBIDDEN')
        replacement = data(owner.post(f'/api/v1/groups/{identifier}/invite-code/reset', json={}))
        assert replacement['invite_code'] != code and replacement['invite_enabled'] is True
        assert_error(join(members[0], code), 404, 'NOT_FOUND')
        assert data(join(members[0], replacement['invite_code']))['member_count'] == 4
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 4


@pytest.mark.parametrize('method,path,body', [
    ('post', '/api/v1/groups', {'name': 'group'}), ('get', '/api/v1/groups', None),
    ('get', '/api/v1/groups/1', None), ('get', '/api/v1/groups/1/members', None),
    ('post', '/api/v1/groups/join', {'invite_code': 'ABCDEFGHIJKL'}),
    ('post', '/api/v1/groups/1/invite-code/reset', {}),
])
def test_all_group_endpoints_require_authentication(client, method, path, body):
    response = getattr(client, method)(path, **({'json': body} if body is not None else {}))
    assert_error(response, 401, 'UNAUTHENTICATED')


def test_nonmember_and_absent_group_have_identical_error_contract(owner, other):
    identifier = data(create(owner), 201)['id']
    for suffix in ['', '/members', '/invite-code/reset']:
        request = (lambda path: other.post(path, json={})) if suffix.endswith('/reset') else other.get
        hidden = assert_error(request(f'/api/v1/groups/{identifier}{suffix}'), 404, 'NOT_FOUND')['error']
        missing = assert_error(request('/api/v1/groups/99999' + suffix), 404, 'NOT_FOUND')['error']
        assert hidden == missing
    assert data(other.get('/api/v1/groups')) == {'items': [], 'page': 1, 'page_size': 20, 'total': 0}


@pytest.mark.parametrize('changes', [
    {'name': ''}, {'name': ' \n '}, {'name': 'x'*101}, {'name': 12}, {'name': None},
    {'name': '\ud800'}, {'description': 'x'*10001}, {'description': None}, {'description': 1},
    {'description': '\ud800'}, {'name': '\x00'}, {'description': 'text\x00'},
    {'owner_id': 999}, {'invite_code': 'ABCDEFGHIJKL'}, {'member_count': 1},
])
def test_invalid_create_does_not_insert(owner, settings, changes):
    response = owner.post('/api/v1/groups', content=json.dumps({'name': 'MeetFlow项目组', **changes}),
                          headers={'Content-Type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM groups').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 0


def test_text_boundaries_default_description_and_plain_text(owner):
    assert data(create(owner), 201)['description'] == ''
    description = '<script>alert(1)</script>' + '😀'*(10000-25)
    assert len(description) <= 10000
    group = data(create(owner, '组'*100, description=description), 201)
    assert group['description'] == description
    assert data(owner.get(f"/api/v1/groups/{group['id']}"))['description'] == description
    assert create(owner, '组'*100, description='😀'*10000).status_code == 201


@pytest.mark.parametrize('payload', [
    {}, {'invite_code': ''}, {'invite_code': 'a'*11}, {'invite_code': 'a'*13},
    {'invite_code': 'A'*11+'-'}, {'invite_code': 123}, {'invite_code': 'A'*10+'ß'},
    {'invite_code': 'ABCDEFGHIJKL', 'user_id': 1},
])
def test_invalid_join_is_422(owner, payload):
    assert_error(owner.post('/api/v1/groups/join', json=payload), 422, 'VALIDATION_ERROR')


@pytest.mark.parametrize('query', ['page=0', 'page=-1', 'page=x', 'page_size=0', 'page_size=51'])
def test_invalid_pagination(owner, query):
    assert_error(owner.get('/api/v1/groups?' + query), 422, 'VALIDATION_ERROR')


def test_own_groups_paginate_with_stable_tie_breaker(owner, other, monkeypatch):
    now = clock.now_ms()
    monkeypatch.setattr(clock, 'now_ms', lambda: now)
    first = data(create(owner, '第一组'), 201)
    second = data(create(owner, '第二组'), 201)
    data(create(other, '无关组'), 201)
    third = data(create(other, '加入的组'), 201)
    join(owner, third['invite_code'])
    result = data(owner.get('/api/v1/groups?page_size=2'))
    assert result['total'] == 3 and result['page'] == 1 and result['page_size'] == 2
    assert [row['id'] for row in result['items']] == [third['id'], second['id']]
    assert 'invite_code' not in result['items'][0]
    assert result['items'][1]['invite_code'] == second['invite_code']
    assert [row['id'] for row in data(owner.get('/api/v1/groups?page=2&page_size=2'))['items']] == [first['id']]
    assert data(owner.get('/api/v1/groups?page=' + '9'*100))['items'] == []


@pytest.mark.parametrize('identifier', ['0', '-1', 'nope', '9223372036854775808'])
def test_invalid_group_ids_are_validation_errors(owner, identifier):
    assert_error(owner.get('/api/v1/groups/' + identifier), 422, 'VALIDATION_ERROR')


def test_disabled_code_and_repeat_join_then_reset_enables_new_code(owner, other, settings):
    group = data(create(owner), 201)
    with sqlite3.connect(database_path(settings)) as connection:
        connection.execute('UPDATE groups SET invite_enabled=0 WHERE id=?', (group['id'],))
    assert_error(join(other, group['invite_code']), 404, 'NOT_FOUND')
    assert data(join(owner, group['invite_code']))['member_count'] == 1
    reset = data(owner.post(f"/api/v1/groups/{group['id']}/invite-code/reset", json={}))
    assert reset['invite_enabled'] is True
    assert_error(join(other, group['invite_code']), 404, 'NOT_FOUND')
    assert data(join(other, reset['invite_code']))['member_count'] == 2


@pytest.mark.parametrize('changes', [{'invite_code': 'ABCDEFGHIJKL'}, {'invite_enabled': False}])
def test_reset_rejects_client_selected_invite_fields(owner, changes):
    group = data(create(owner), 201)
    assert_error(owner.post(f"/api/v1/groups/{group['id']}/invite-code/reset", json=changes), 422, 'VALIDATION_ERROR')
    assert data(owner.get(f"/api/v1/groups/{group['id']}"))['invite_code'] == group['invite_code']


def test_concurrent_last_place_never_exceeds_twenty(owner, other, settings):
    group = data(create(owner), 201)
    fill_members(settings, group['id'], 19)
    assert register(owner, username='contender', email='contender@example.com').status_code == 201

    def contender(username):
        def action(browser):
            assert login(browser, username=username).status_code == 200
            return join(browser, group['invite_code'])
        return action

    responses = simultaneous(settings, [contender('member'), contender('contender')])
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert_error(next(row for row in responses if row.status_code == 409), 409, 'STATE_CONFLICT')
    assert data(join(owner, group['invite_code']))['member_count'] == 20
    assert len(data(owner.get(f"/api/v1/groups/{group['id']}/members"))['items']) == 20
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 20


def test_concurrent_same_member_join_at_capacity_is_idempotent(owner, other, settings):
    group = data(create(owner), 201)
    fill_members(settings, group['id'], 19)

    def action(browser):
        login(browser, username='member')
        return join(browser, group['invite_code'])

    responses = simultaneous(settings, [action, action])
    assert [response.status_code for response in responses] == [200, 200]
    assert [response.json()['data']['member_count'] for response in responses] == [20, 20]
    assert data(join(other, group['invite_code']))['member_count'] == 20


def test_code_collision_retries_create_and_reset_without_keeping_old_code(owner, monkeypatch):
    occupied = data(create(owner), 201)
    codes = iter([occupied['invite_code'], 'NEWGROUP0001'])
    monkeypatch.setattr(service, 'generate_invite_code', lambda: next(codes))
    group = data(create(owner), 201)
    assert group['invite_code'] == 'NEWGROUP0001'
    codes = iter([group['invite_code'], occupied['invite_code'], 'RESETCODE001'])
    result = data(owner.post(f"/api/v1/groups/{group['id']}/invite-code/reset", json={}))
    assert result['invite_code'] == 'RESETCODE001'
    assert_error(join(owner, group['invite_code']), 404, 'NOT_FOUND')


@pytest.mark.parametrize('operation', ['create', 'reset'])
def test_three_collisions_fail_cleanly(owner, settings, monkeypatch, operation):
    group = data(create(owner), 201)
    calls = []

    def same():
        calls.append(True)
        return group['invite_code']

    monkeypatch.setattr(service, 'generate_invite_code', same)
    response = create(owner) if operation == 'create' else owner.post(f"/api/v1/groups/{group['id']}/invite-code/reset", json={})
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert len(calls) == 3
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM groups').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 1
        assert connection.execute('SELECT invite_code FROM groups').fetchone()[0] == group['invite_code']


def test_owner_membership_insert_failure_leaves_no_orphan_group(owner, settings, monkeypatch):
    original = dependencies.make_engine

    def faulty_engine(path):
        engine = original(path)

        @event.listens_for(engine, 'before_cursor_execute')
        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.startswith('INSERT INTO group_members'):
                raise OperationalError(None, None, sqlite3.OperationalError('injected member insert failure'))
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', faulty_engine)
    assert_error(create(owner), 503, 'STORAGE_UNAVAILABLE')
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM groups').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['create', 'join', 'reset'])
def test_commit_failure_preserves_group_and_membership(owner, other, settings, monkeypatch, operation):
    group = data(create(owner), 201)
    original = dependencies.make_engine
    observed = []

    def faulty_engine(path):
        engine = original(path)

        @event.listens_for(engine, 'commit')
        def fail(connection):
            observed.append((connection.exec_driver_sql('SELECT COUNT(*) FROM groups').scalar_one(),
                             connection.exec_driver_sql('SELECT COUNT(*) FROM group_members').scalar_one(),
                             connection.exec_driver_sql('SELECT invite_code FROM groups WHERE id=?', (group['id'],)).scalar_one()))
            raise OperationalError(None, None, sqlite3.OperationalError('injected commit failure'))
        return engine

    with monkeypatch.context() as patch:
        patch.setattr(dependencies, 'make_engine', faulty_engine)
        if operation == 'create':
            response = create(owner)
        elif operation == 'join':
            response = join(other, group['invite_code'])
        else:
            response = owner.post(f"/api/v1/groups/{group['id']}/invite-code/reset", json={})
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert len(observed) == 1
    if operation == 'create':
        assert observed[0][:2] == (2, 2)
    elif operation == 'join':
        assert observed[0][:2] == (1, 2)
    else:
        assert observed[0][2] != group['invite_code']
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM groups').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM group_members').fetchone()[0] == 1
        assert connection.execute('SELECT invite_code FROM groups').fetchone()[0] == group['invite_code']
    assert data(join(other, group['invite_code']))['member_count'] == 2


def test_busy_join_is_503_and_does_not_add_member(owner, other, settings, monkeypatch):
    group = data(create(owner), 201)
    original = dependencies.make_engine

    def quick_engine(path):
        engine = original(path)
        event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA busy_timeout=10'))
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', quick_engine)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    try:
        assert_error(join(other, group['invite_code']), 503, 'DB_BUSY')
    finally:
        blocker.rollback(); blocker.close()
    assert data(owner.get(f"/api/v1/groups/{group['id']}"))['member_count'] == 1
    assert data(join(other, group['invite_code']))['member_count'] == 2


def test_invite_and_group_text_never_appear_in_request_logs(owner, other, caplog):
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        group = data(create(owner, 'private-group-marker', description='private-description-marker'), 201)
        join(other, group['invite_code'])
        owner.get(f"/api/v1/groups/{group['id']}/members")
    assert all(value not in caplog.text for value in [group['invite_code'], 'private-group-marker', 'private-description-marker'])
    assert 'user_id=1' in caplog.text
