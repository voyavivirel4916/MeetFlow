"""T11: independent HTTP clients, real SQLite locks, and commit fault injection."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.auth import dependencies, service
from app.common import clock
from app.db.connection import database_path
from app.main import create_app
from test_auth import PASSWORD, cookie, login, register, token
from test_bootstrap import assert_error


def simultaneous(settings, actions):
    # Each worker owns its app, engine connections and cookie jar.
    barrier = Barrier(len(actions))

    def run(action):
        with TestClient(create_app(settings), base_url='http://127.0.0.1',
                        raise_server_exceptions=False) as browser:
            barrier.wait(timeout=5)
            return action(browser)

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(run, action) for action in actions]
        return [future.result(timeout=10) for future in futures]


@pytest.mark.parametrize('duplicate', ['username', 'email'])
def test_concurrent_normalized_registration_inserts_one_account(client, settings, duplicate):
    def second(browser):
        return register(browser, username=' STUDENT ' if duplicate == 'username' else 'different',
                        email='other@example.com' if duplicate == 'username' else ' STUDENT@EXAMPLE.COM ')

    responses = simultaneous(settings, [register, second])
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert_error(next(response for response in responses if response.status_code == 409), 409, 'DUPLICATE_ACCOUNT')
    assert all('set-cookie' not in response.headers for response in responses)
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


def test_concurrent_independent_logins_and_one_logout_are_isolated(client, settings):
    register(client)

    def sign_in(browser):
        response = login(browser)
        assert response.status_code == 200
        return token(browser)

    first, second = simultaneous(settings, [sign_in, sign_in])
    assert first != second
    for raw in [first, second]:
        assert client.get('/api/v1/users/me', headers=cookie(raw)).status_code == 200
    assert client.post('/api/v1/auth/logout', json={}, headers=cookie(first)).status_code == 200
    assert_error(client.get('/api/v1/users/me', headers=cookie(first)), 401, 'UNAUTHENTICATED')
    assert client.get('/api/v1/users/me', headers=cookie(second)).status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL').fetchone()[0] == 1


def test_concurrent_duplicate_logout_is_idempotent(client, settings, monkeypatch):
    now = [1_800_000_000_000]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    register(client); login(client)
    raw = token(client)

    def sign_out(browser):
        return browser.post('/api/v1/auth/logout', json={}, headers=cookie(raw))

    responses = simultaneous(settings, [sign_out, sign_out])
    assert [response.status_code for response in responses] == [200, 200]
    assert all('max-age=0' in response.headers['set-cookie'].lower() for response in responses)
    assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')
    # A revoked token remains an idempotent logout after its original deadline.
    now[0] += service.SESSION_SECONDS * 1000
    assert sign_out(client).status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT revoked_at FROM sessions').fetchone()[0] == 1_800_000_000_000


def test_login_rotation_racing_with_old_cookie_logout_keeps_new_session(client, settings):
    register(client); login(client)
    old = token(client)

    def rotate(browser):
        response = browser.post('/api/v1/auth/login', json={'username': 'student', 'password': PASSWORD}, headers=cookie(old))
        assert response.status_code == 200
        return token(browser)

    def revoke(browser):
        return browser.post('/api/v1/auth/logout', json={}, headers=cookie(old))

    new, logout = simultaneous(settings, [rotate, revoke])
    assert logout.status_code == 200
    assert new and new != old
    assert_error(client.get('/api/v1/users/me', headers=cookie(old)), 401, 'UNAUTHENTICATED')
    assert client.get('/api/v1/users/me', headers=cookie(new)).status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL').fetchone()[0] == 1


@pytest.mark.parametrize('operation', ['register', 'login', 'logout'])
def test_commit_failure_rolls_back_all_writes_and_preserves_cookie(client, settings, monkeypatch, operation):
    register(client); login(client)
    raw = token(client)
    original = dependencies.make_engine
    observed = []

    def failing_engine(path):
        engine = original(path)

        @event.listens_for(engine, 'commit')
        def fail_commit(connection):
            # Prove the fault happens after all intended writes, not before INSERT/UPDATE.
            if operation == 'register':
                observed.append(connection.exec_driver_sql('SELECT COUNT(*) FROM users').scalar_one())
            else:
                observed.append(tuple(connection.exec_driver_sql(
                    'SELECT COUNT(*), SUM(revoked_at IS NOT NULL) FROM sessions').one()))
            raise OperationalError(None, None, sqlite3.OperationalError('injected commit failure'))
        return engine

    with monkeypatch.context() as patch:
        patch.setattr(dependencies, 'make_engine', failing_engine)
        if operation == 'register':
            response = register(client, username='another', email='another@example.com')
        elif operation == 'login':
            response = login(client)
        else:
            response = client.post('/api/v1/auth/logout', json={})
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert 'set-cookie' not in response.headers
    assert token(client) == raw
    assert observed == [2 if operation == 'register' else (2, 1) if operation == 'login' else (1, 1)]
    assert client.get('/api/v1/users/me').status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*), SUM(revoked_at IS NOT NULL) FROM sessions').fetchone() == (1, 0)
    # Recovery really works; no poisoned transaction/uniqueness state remains.
    if operation == 'register':
        assert register(client, username='another', email='another@example.com').status_code == 201
    elif operation == 'login':
        assert login(client).status_code == 200
        assert token(client) != raw
        assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')
    else:
        assert client.post('/api/v1/auth/logout', json={}).status_code == 200
        assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')


def test_logout_rechecks_expiry_after_waiting_for_write_lock(client, settings, monkeypatch):
    now = [1_800_000_000_000]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    register(client); login(client)
    raw = token(client)
    started = Event()
    original = dependencies.make_engine

    def observed_engine(path):
        engine = original(path)

        @event.listens_for(engine, 'before_cursor_execute')
        def before_write(_connection, _cursor, statement, _parameters, _context, _many):
            if statement == 'BEGIN IMMEDIATE':
                started.set()
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', observed_engine)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/v1/auth/logout', json={})
        try:
            assert started.wait(3), 'Logout did not reach the write lock.'
            now[0] += service.SESSION_SECONDS * 1000
        finally:
            blocker.rollback(); blocker.close()
        response = future.result(timeout=5)
    assert_error(response, 401, 'UNAUTHENTICATED')
    assert 'set-cookie' not in response.headers
    assert token(client) == raw
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT revoked_at FROM sessions').fetchone()[0] is None
