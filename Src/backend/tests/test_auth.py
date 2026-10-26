import hashlib
import json
import logging
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.auth import service
from app.auth.passwords import hash_password, verify_password
from app.common import clock
from app.db.connection import database_path, make_engine
from app.db.models import sessions, users
from app.main import create_app
from test_bootstrap import assert_error

PASSWORD = '  有意义的密码123  '


def register(client, username='student', email='student@example.com', password=PASSWORD):
    return client.post('/api/v1/auth/register', json={'username': username, 'email': email, 'password': password})


def login(client, username='student', password=PASSWORD):
    return client.post('/api/v1/auth/login', json={'username': username, 'password': password})


def token(client):
    return client.cookies.get(service.COOKIE_NAME)


def cookie(raw):
    return {'Cookie': f'{service.COOKIE_NAME}={raw}'}


def test_registration_normalizes_and_does_not_log_in_or_expose_hash(client, settings):
    response = register(client, username='  STudent  ', email='  STUDENT@Example.COM  ')
    assert response.status_code == 201
    assert response.json()['data'] == {'id': 1, 'username': 'student', 'email': 'student@example.com'}
    assert response.headers['cache-control'] == 'no-store'
    assert 'set-cookie' not in response.headers
    assert token(client) is None
    assert_error(client.get('/api/v1/users/me'), 401, 'UNAUTHENTICATED')
    engine = make_engine(database_path(settings))
    try:
        with engine.connect() as connection:
            row = connection.execute(select(users)).mappings().one()
            assert row['password_hash'].startswith('scrypt$16384$8$1$')
            assert PASSWORD not in row['password_hash'] + response.text
            assert verify_password(PASSWORD, row['password_hash'])
            assert connection.execute(select(sessions)).all() == []
    finally:
        engine.dispose()


@pytest.mark.parametrize('duplicate', ['username', 'email'])
def test_duplicate_normalized_account_is_409(client, duplicate):
    assert register(client).status_code == 201
    response = register(client, username=' STUDENT ' if duplicate == 'username' else 'different',
                        email='other@example.com' if duplicate == 'username' else ' STUDENT@EXAMPLE.COM ')
    assert_error(response, 409, 'DUPLICATE_ACCOUNT')
    assert 'set-cookie' not in response.headers


@pytest.mark.parametrize('changes', [
    {'username': 'ab'}, {'username': 'a'*33}, {'username': 'has-dash'}, {'username': '中文用户名'},
    {'username': 123}, {'email': 'invalid-address'}, {'email': 'name <student@example.com>'},
    {'email': 'student@localhost'}, {'email': 'a'*245+'@example.com'}, {'email': 12},
    {'password': 'short'}, {'password': ' '*8}, {'password': 'a'*129}, {'password': 12345678},
    {'password': '\ud800' * 8}, {'role': 'OWNER'}, {'unknown': 'secret-value'},
])
def test_registration_invalid_input_is_rejected_without_echo_or_insert(client, settings, changes):
    payload = {'username': 'student', 'email': 'student@example.com', 'password': PASSWORD, **changes}
    response = client.post('/api/v1/auth/register', content=json.dumps(payload), headers={'Content-Type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert PASSWORD not in response.text
    assert 'secret-value' not in response.text
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0


def test_password_salts_differ_and_whitespace_is_significant():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second
    assert verify_password(PASSWORD, first)
    assert not verify_password(PASSWORD.strip(), first)
    assert not verify_password('wrong-password', first)


@pytest.mark.parametrize('encoded', ['', 'plain', 'scrypt$1073741824$8$1$00$00', 'scrypt$16384$8$1$bad$bad'])
def test_malformed_hash_never_authenticates_or_runs_unbounded_parameters(encoded):
    assert not verify_password(PASSWORD, encoded)


def test_login_cookie_and_persistent_digest_only_session(client, settings, monkeypatch):
    now = 1_800_000_000_000
    monkeypatch.setattr(clock, 'now_ms', lambda: now)
    register(client)
    response = login(client, username=' STUDENT ')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    header = response.headers['set-cookie'].lower()
    assert all(flag in header for flag in ['httponly', 'samesite=strict', 'path=/', 'max-age=28800'])
    assert 'secure' not in header and 'domain=' not in header
    raw = token(client)
    assert raw and len(raw) == 43
    assert raw not in response.text
    assert set(response.json()['data']) == {'id', 'username', 'email'}
    with sqlite3.connect(database_path(settings)) as connection:
        row = connection.execute('SELECT token_hash,created_at,expires_at,revoked_at FROM sessions').fetchone()
    assert row == (hashlib.sha256(raw.encode()).hexdigest(), now, now + 28_800_000, None)
    assert raw != row[0]
    me = client.get('/api/v1/users/me')
    assert me.status_code == 200 and me.json()['data'] == response.json()['data']
    assert me.headers['cache-control'] == 'no-store'
    assert 'set-cookie' not in me.headers  # No sliding renewal.


def test_unknown_and_wrong_password_share_the_same_failure_and_real_hash_path(client, monkeypatch):
    register(client)
    calls = []
    original = service.verify_password

    def tracked(password, encoded):
        calls.append(encoded)
        return original(password, encoded)

    monkeypatch.setattr(service, 'verify_password', tracked)
    wrong = login(client, password='wrong')
    unknown = login(client, username='unknown')
    assert_error(wrong, 401, 'UNAUTHENTICATED')
    assert_error(unknown, 401, 'UNAUTHENTICATED')
    assert wrong.json()['error'] == unknown.json()['error']
    assert len(calls) == 2 and all(item.startswith('scrypt$') for item in calls)
    assert 'set-cookie' not in wrong.headers and token(client) is None


def test_exact_eight_hour_boundary_and_no_automatic_renewal(client, monkeypatch):
    start = 1_800_000_000_000
    now = [start]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    register(client); login(client)
    raw = token(client)
    now[0] = start + 28_800_000 - 1
    assert client.get('/api/v1/users/me', headers=cookie(raw)).status_code == 200
    now[0] += 1
    assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')
    assert_error(client.post('/api/v1/auth/logout', json={}, headers=cookie(raw)), 401, 'UNAUTHENTICATED')


def test_logout_revokes_old_cookie_and_repeat_logout_is_idempotent(client, settings, monkeypatch):
    now = [1_800_000_000_000]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    register(client); login(client)
    raw = token(client)
    now[0] += 1
    response = client.post('/api/v1/auth/logout', json={})
    assert response.json()['data'] == {'logged_out': True}
    assert 'max-age=0' in response.headers['set-cookie'].lower()
    assert token(client) is None
    assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')
    now[0] += 20
    again = client.post('/api/v1/auth/logout', json={}, headers=cookie(raw))
    assert again.status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT revoked_at FROM sessions').fetchone()[0] == 1_800_000_000_001


@pytest.mark.parametrize('raw', [None, '', 'bad', 'x'*44, 'x'*1000, '!'*43, '伪'*43])
def test_missing_or_invalid_tokens_are_rejected(client, raw):
    headers = {} if raw is None else cookie(raw)
    # Non-ASCII bytes cannot be an HTTP header; exercise its validation directly.
    if raw and not raw.isascii():
        assert service.token_digest(raw) is None
        return
    assert_error(client.get('/api/v1/users/me', headers=headers), 401, 'UNAUTHENTICATED')
    assert_error(client.post('/api/v1/auth/logout', json={}, headers=headers), 401, 'UNAUTHENTICATED')


def test_unknown_well_formed_token_is_not_a_session(client):
    raw = secrets.token_urlsafe(32)
    assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')
    assert_error(client.post('/api/v1/auth/logout', json={}, headers=cookie(raw)), 401, 'UNAUTHENTICATED')


def test_login_rotates_current_session_but_keeps_other_browser_sessions(client):
    register(client); login(client)
    first = token(client)
    client.cookies.clear()
    login(client)
    independent = token(client)
    login(client)
    replacement = token(client)
    assert len({first, independent, replacement}) == 3
    assert client.get('/api/v1/users/me', headers=cookie(first)).status_code == 200
    assert_error(client.get('/api/v1/users/me', headers=cookie(independent)), 401, 'UNAUTHENTICATED')
    assert client.get('/api/v1/users/me', headers=cookie(replacement)).status_code == 200


def test_failed_login_keeps_existing_session(client):
    register(client); login(client)
    current = token(client)
    assert_error(login(client, password='incorrect'), 401, 'UNAUTHENTICATED')
    assert token(client) == current
    assert client.get('/api/v1/users/me').status_code == 200


def test_cookie_remains_valid_after_app_restart(client, settings):
    register(client); login(client)
    raw = token(client)
    with TestClient(create_app(settings), base_url='http://127.0.0.1') as restarted:
        assert restarted.get('/api/v1/users/me', headers=cookie(raw)).status_code == 200
        assert restarted.post('/api/v1/auth/logout', json={}, headers=cookie(raw)).status_code == 200
    assert_error(client.get('/api/v1/users/me', headers=cookie(raw)), 401, 'UNAUTHENTICATED')


def test_credentials_tokens_emails_and_request_values_are_not_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        register(client, email='private-email@example.com')
        login(client)
        raw = token(client)
        client.get('/api/v1/users/me')
        client.post('/api/v1/auth/logout', json={})
    assert all(secret not in caplog.text for secret in [PASSWORD, raw, 'private-email@example.com'])
    assert 'user_id=1' in caplog.text


def test_storage_failure_is_503_and_does_not_create_database(client, settings):
    path = database_path(settings)
    saved = path.with_name('saved.sqlite3')
    path.rename(saved)
    try:
        response = register(client)
        assert_error(response, 503, 'STORAGE_UNAVAILABLE')
        assert 'set-cookie' not in response.headers
        assert not path.exists()
    finally:
        saved.rename(path)


def test_expiry_is_checked_after_a_blocked_read(client, settings, monkeypatch):
    from app.auth import dependencies
    now = [1_800_000_000_000]
    monkeypatch.setattr(clock, 'now_ms', lambda: now[0])
    register(client); login(client)
    started = Event()
    original = dependencies.make_engine

    def observed_engine(path):
        engine = original(path)

        @event.listens_for(engine, 'before_cursor_execute')
        def before_read(_connection, _cursor, statement, _parameters, _context, _many):
            if 'sessions JOIN users' in statement:
                started.set()
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', observed_engine)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN EXCLUSIVE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, '/api/v1/users/me')
        try:
            assert started.wait(3), 'Reader did not enter its database query.'
            now[0] += 28_800_000
        finally:
            blocker.rollback(); blocker.close()
        assert_error(future.result(timeout=5), 401, 'UNAUTHENTICATED')


def test_busy_logout_keeps_cookie_and_session_active(client, settings, monkeypatch):
    from app.auth import dependencies
    register(client); login(client)
    raw = token(client)
    original = dependencies.make_engine

    def quick_engine(path):
        engine = original(path)
        event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA busy_timeout=10'))
        return engine

    monkeypatch.setattr(dependencies, 'make_engine', quick_engine)
    blocker = sqlite3.connect(database_path(settings))
    blocker.execute('BEGIN IMMEDIATE')
    try:
        response = client.post('/api/v1/auth/logout', json={})
        assert_error(response, 503, 'DB_BUSY')
        assert 'set-cookie' not in response.headers
        assert token(client) == raw
    finally:
        blocker.rollback(); blocker.close()
    assert client.get('/api/v1/users/me').status_code == 200


def test_session_insert_failure_does_not_revoke_existing_login(client, settings, monkeypatch):
    register(client); login(client)
    raw = token(client)
    monkeypatch.setattr(service.secrets, 'token_urlsafe', lambda _length: raw)
    response = login(client)
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert 'set-cookie' not in response.headers
    assert token(client) == raw
    assert client.get('/api/v1/users/me').status_code == 200
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
