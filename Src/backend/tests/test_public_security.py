import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.common.config import ConfigurationError, Settings, load_settings
from app.common.rate_limit import AuthLimiter
from app.db.migrate import upgrade
from app.main import create_app
from test_auth import register, login
from test_bootstrap import assert_error


def production(settings, **values):
    return Settings(_env_file=None, **{**settings.model_dump(), 'app_env': 'production',
                    'public_origin': 'https://meet.example', **values})


@pytest.mark.parametrize('values', [
    {'public_origin': ''}, {'public_origin': 'http://meet.example'},
    {'public_origin': 'https://meet.example/'}, {'public_origin': 'https://user@meet.example'},
    {'public_origin': 'https://meet.example?secret=value'}, {'public_origin': 'https://meet.example:0'},
    {'public_origin': 'https://meet.example\\evil'}, {'public_origin': 'https://localhost'},
    {'trusted_proxies': ['*']}, {'trusted_proxies': ['0.0.0.0/0']}, {'trusted_proxies': ['::/0']},
])
def test_public_configuration_fails_closed(settings, values):
    with pytest.raises(ValidationError):
        production(settings, **values)


def test_public_mode_requires_distinct_database_and_local_remains_local(settings):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env='production', public_origin='https://meet.example')
    with pytest.raises(ValidationError):
        Settings(_env_file=None, public_origin='https://meet.example')
    assert production(settings, bind_host='0.0.0.0', trusted_proxies=['127.0.0.1']).bind_host == '0.0.0.0'


def test_public_startup_error_is_sanitized(monkeypatch):
    monkeypatch.setenv('MEETFLOW_APP_ENV', 'production')
    monkeypatch.setenv('MEETFLOW_PUBLIC_ORIGIN', 'http://private-marker.invalid')
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert 'public_settings' in str(error.value)
    assert 'private-marker' not in str(error.value)


@pytest.fixture
def public_client(settings):
    config = production(settings)
    upgrade(config)
    with TestClient(create_app(config), base_url='https://meet.example', raise_server_exceptions=False) as client:
        yield client


def test_secure_login_logout_cookie_and_headers(public_client):
    assert register(public_client).status_code == 201
    response = login(public_client)
    assert response.status_code == 200
    for value in ['Secure', 'HttpOnly', 'SameSite=strict', 'Path=/']:
        assert value in response.headers['set-cookie']
    assert public_client.get('/api/v1/users/me').status_code == 200
    response = public_client.post('/api/v1/auth/logout', json={})
    assert 'Secure' in response.headers['set-cookie']
    assert public_client.get('/api/v1/users/me').status_code == 401
    assert response.headers['strict-transport-security'] == 'max-age=31536000'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_host_origin_transport_and_forwarded_headers(public_client):
    assert_error(public_client.get('/livez', headers={'Host': 'evil.example'}), 400, 'INVALID_INPUT')
    assert_error(public_client.get('http://meet.example/livez', headers={'X-Forwarded-Proto': 'https'}), 400, 'HTTPS_REQUIRED')
    assert_error(public_client.post('/api/v1/auth/login', json={}, headers={'Origin': 'https://evil.example'}), 403, 'CSRF_REJECTED')
    assert public_client.get('/api/v1/health', headers={'Origin': 'https://meet.example'}).status_code == 200


def test_rate_limit_before_validation_and_spoofing_cannot_reset(public_client):
    for _ in range(10):
        assert public_client.post('/api/v1/auth/login', json={}).status_code == 422
    response = public_client.post('/api/v1/auth/login/', json={}, headers={'X-Forwarded-For': '1.2.3.4'})
    assert_error(response, 429, 'RATE_LIMITED')
    assert 1 <= int(response.headers['retry-after']) <= 60
    assert public_client.get('/api/v1/health').status_code == 200
    for _ in range(5):
        assert public_client.post('/api/v1/auth/register', json={}).status_code == 422
    assert_error(public_client.post('/api/v1/auth/register', json={}), 429, 'RATE_LIMITED')


def test_limiter_window_clients_capacity_and_recovery():
    clock = [100]
    limiter = AuthLimiter(capacity=2, clock=lambda: clock[0])
    path = '/api/v1/auth/login'
    for _ in range(10):
        assert limiter.check(path, 'first') == 0
    assert limiter.check(path, 'first') == 60
    assert limiter.check(path, 'second') == 0
    assert limiter.check(path, 'third') == 60
    assert len(limiter.buckets) == 2
    clock[0] += 60
    assert limiter.check(path, 'third') == 0
    assert len(limiter.buckets) == 1


def test_rejected_public_credentials_do_not_reach_logs(public_client, caplog):
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        response = public_client.post('/api/v1/auth/login?token=private-marker', json={'password': 'private-marker'},
                                      headers={'Cookie': 'token=private-marker'})
    assert response.status_code == 422
    assert 'private-marker' not in caplog.text


@pytest.mark.anyio
async def test_proxy_headers_only_from_configured_peer():
    seen = []

    async def endpoint(scope, receive, send):
        seen.append((scope['scheme'], scope['client']))

    proxy = ProxyHeadersMiddleware(endpoint, trusted_hosts=['127.0.0.1'])
    scope = {'type': 'http', 'scheme': 'http', 'client': ('203.0.113.1', 3000),
             'headers': [(b'x-forwarded-proto', b'https'), (b'x-forwarded-for', b'198.51.100.2')]}
    await proxy(scope.copy(), None, None)
    assert seen[-1] == ('http', ('203.0.113.1', 3000))
    scope['client'] = ('127.0.0.1', 3000)
    await proxy(scope.copy(), None, None)
    assert seen[-1] == ('https', ('198.51.100.2', 0))
