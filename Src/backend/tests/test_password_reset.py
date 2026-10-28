from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import pytest
from sqlalchemy import select

from app.auth import reset
from app.common import clock
from app.common.responses import ApiError
from app.db.connection import database_path, make_engine
from app.db.models import password_resets
from test_auth import register, login
from test_bootstrap import assert_error

REQUEST = '/api/v1/auth/password-reset/request'
CONFIRM = '/api/v1/auth/password-reset/confirm'


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(reset, 'configured', lambda settings: True)
    monkeypatch.setattr(reset, 'deliver', lambda settings, email, token: sent.append((email, token)))
    return sent


def test_disabled_mail_does_not_claim_a_message_was_sent(client):
    assert_error(client.post(REQUEST, json={'email': 'student@example.com'}), 503, 'MAIL_UNAVAILABLE')


def test_reset_single_use_hides_accounts_and_revokes_sessions(client, settings, mail):
    register(client); login(client)
    unknown = client.post(REQUEST, json={'email': 'unknown@example.com'})
    known = client.post(REQUEST, json={'email': ' STUDENT@example.com '})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json()['data'] == known.json()['data']
    assert len(mail) == 1
    token = mail[0][1]
    engine = make_engine(database_path(settings))
    with engine.connect() as db:
        assert token not in str(db.execute(select(password_resets)).all())
    engine.dispose()
    assert client.post(REQUEST, json={'email': 'student@example.com'}).status_code == 202
    assert len(mail) == 1
    response = client.post(CONFIRM, json={'token': token, 'password': 'NewPassword123!'})
    assert response.status_code == 200
    assert client.get('/api/v1/users/me').status_code == 401
    assert login(client).status_code == 401
    assert login(client, password='NewPassword123!').status_code == 200
    assert_error(client.post(CONFIRM, json={'token': token, 'password': 'AnotherPassword123!'}), 400, 'RESET_INVALID')


def test_new_link_invalidates_old_and_expiry_is_server_checked(client, settings, mail, monkeypatch):
    register(client)
    now = clock.now_ms()
    monkeypatch.setattr(clock, 'now_ms', lambda: now)
    client.post(REQUEST, json={'email': 'student@example.com'})
    old = mail[-1][1]
    now += 60001
    client.post(REQUEST, json={'email': 'student@example.com'})
    fresh = mail[-1][1]
    assert old != fresh
    assert_error(client.post(CONFIRM, json={'token': old, 'password': 'NewPassword123!'}), 400, 'RESET_INVALID')
    now += 15 * 60 * 1000
    assert_error(client.post(CONFIRM, json={'token': fresh, 'password': 'NewPassword123!'}), 400, 'RESET_INVALID')


@pytest.mark.parametrize('password', ['        ', 'short', '\ud80012345678'])
def test_invalid_password_is_validation_error(client, password):
    assert_error(client.post(CONFIRM, content=json.dumps({'token': 'a' * 43, 'password': password}),
                             headers={'Content-Type': 'application/json'}), 422, 'VALIDATION_ERROR')


def test_parallel_use_only_one_password_change(client, settings, mail):
    register(client)
    client.post(REQUEST, json={'email': 'student@example.com'})
    engine = make_engine(database_path(settings))
    def consume(_):
        try:
            reset.consume(engine, mail[0][1], 'NewPassword123!')
            return 200
        except ApiError as error:
            return error.status
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(consume, range(2))) == [200, 400]
    finally:
        engine.dispose()


def test_old_password_login_cannot_finish_after_reset(client, settings, mail, monkeypatch):
    from app.auth import service
    from app.auth.models import LoginIn
    from test_auth import PASSWORD
    register(client)
    client.post(REQUEST, json={'email': 'student@example.com'})
    engine = make_engine(database_path(settings))
    verified, resume = Event(), Event()
    original = service.verify_password
    def blocked(password, encoded):
        result = original(password, encoded)
        verified.set()
        assert resume.wait(10)
        return result
    monkeypatch.setattr(service, 'verify_password', blocked)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.login, engine, LoginIn(username='student', password=PASSWORD), None)
            assert verified.wait(10)
            try:
                reset.consume(engine, mail[0][1], 'NewPassword123!')
            finally:
                resume.set()
            with pytest.raises(ApiError) as error:
                future.result(timeout=10)
            assert error.value.status == 401
    finally:
        resume.set(); engine.dispose()


def test_smtp_transport_link_and_sanitized_failure(settings, monkeypatch, caplog):
    settings.public_origin = 'https://meet.example'
    settings.smtp_sender = 'sender@example.com'
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs):
            assert kwargs['timeout'] == 10
            assert kwargs['context'].check_hostname
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(reset.smtplib, 'SMTP_SSL', SMTP)
    reset.deliver(settings, 'student@example.com', 'private-token')
    body = sent[0].get_content()
    assert '/reset-password#token=private-token' in body
    def fail(*args, **kwargs): raise RuntimeError('private-token student@example.com')
    monkeypatch.setattr(reset.smtplib, 'SMTP_SSL', fail)
    reset.deliver(settings, 'student@example.com', 'private-token')
    assert 'PASSWORD_RESET_DELIVERY_FAILED' in caplog.text
    assert 'private-token' not in caplog.text
    assert 'student@example.com' not in caplog.text
