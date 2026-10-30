import httpx2 as httpx
import pytest
import asyncio
from functools import partial
from threading import Thread, Event
import a2wsgi

from app.common.config import ConfigurationError, Settings
from app.db.migrate import upgrade
from app.hosting_wsgi import PlatformClientAddress, create_wsgi_app
from test_auth import register, login
from test_bootstrap import assert_error


@pytest.fixture
def production(settings):
    return Settings(_env_file=None, app_env='production', public_origin='https://meet.example',
                    data_dir=settings.data_dir, frontend_dir=settings.frontend_dir)


@pytest.fixture
def wsgi_app(production, monkeypatch):
    upgrade(production)
    loop = asyncio.new_event_loop()
    ready = Event()
    loop.call_soon(ready.set)
    worker = Thread(target=loop.run_forever)
    worker.start()
    ready.wait(5)
    monkeypatch.setattr(a2wsgi, 'ASGIMiddleware', partial(a2wsgi.ASGIMiddleware, loop=loop))
    try:
        yield create_wsgi_app(production)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        worker.join(5)
        assert not worker.is_alive()
        loop.close()


def test_wsgi_entry_validates_runtime_without_lifespan(settings, production):
    with pytest.raises(ConfigurationError):
        create_wsgi_app(settings)
    with pytest.raises(ConfigurationError):
        create_wsgi_app(production)  # No current database schema.
    proxy = production.model_copy(update={'trusted_proxies':['127.0.0.1']})
    with pytest.raises(ConfigurationError):
        create_wsgi_app(proxy)


def test_wsgi_client_identity_uses_last_valid_address_without_mutating_environ():
    seen=[]
    def endpoint(environ, start):
        seen.append(environ)
        return [b'ok']
    app=PlatformClientAddress(endpoint)
    original={'wsgi.url_scheme':'http', 'HTTP_X_FORWARDED_PROTO':'https',
              'HTTP_X_FORWARDED_FOR':'spoofed, 198.51.100.2', 'REMOTE_ADDR':'10.0.0.1'}
    assert app(original,None)==[b'ok']
    assert seen[-1]['REMOTE_ADDR']=='198.51.100.2'
    assert seen[-1]['wsgi.url_scheme']=='http'
    assert original['REMOTE_ADDR']=='10.0.0.1'
    for address in ['', 'spoofed, invalid', '198.51.100.2,']:
        app(dict(original,HTTP_X_FORWARDED_FOR=address),None)
        assert seen[-1]['REMOTE_ADDR']==''


def client_for(app, scheme='https'):
    # WSGITransport builds wsgi.url_scheme from the URL, as a WSGI server does.
    return httpx.Client(transport=httpx.WSGITransport(app),base_url=f'{scheme}://meet.example',
                        headers={'X-Forwarded-For':'spoofed, 198.51.100.2'})


def test_wsgi_https_static_deeplink_login_and_security(wsgi_app):
    with client_for(wsgi_app) as client:
        assert client.get('/api/v1/health').status_code==200
        assert 'MeetFlow test build' in client.get('/groups/1').text
        assert client.get('/assets/app-test.js').status_code==200
        assert register(client).status_code==201
        response=login(client)
        assert response.status_code==200
        assert 'Secure' in response.headers['set-cookie']
        assert client.get('/api/v1/users/me').status_code==200
        assert 'max-age=' in response.headers['strict-transport-security']
        assert_error(client.get('/livez',headers={'Host':'evil.example'}),400,'INVALID_INPUT')
        assert_error(client.post('/api/v1/auth/logout',headers={'Origin':'https://evil.example'}),403,'CSRF_REJECTED')


def test_wsgi_http_and_forged_https_headers_are_rejected(wsgi_app):
    with client_for(wsgi_app,'http') as client:
        for headers in [{}, {'X-Forwarded-Proto':'https','X-Forwarded-Ssl':'on'}]:
            assert_error(client.get('/login',headers=headers),400,'HTTPS_REQUIRED')


def test_wsgi_limit_cannot_be_bypassed_by_changing_first_forwarded_ip(wsgi_app):
    with client_for(wsgi_app) as client:
        for i in range(10):
            assert client.post('/api/v1/auth/login',json={},headers={
                'X-Forwarded-For':f'fake-{i}, 198.51.100.2'}).status_code==422
        assert_error(client.post('/api/v1/auth/login',json={},headers={
            'X-Forwarded-For':'changed, 198.51.100.2'}),429,'RATE_LIMITED')


def test_wsgi_recreated_application_preserves_accounts_and_sessions(wsgi_app, production):
    with client_for(wsgi_app) as client:
        assert register(client).status_code==201
        assert login(client).status_code==200
        with client_for(create_wsgi_app(production)) as restarted:
            restarted.cookies.update(client.cookies)
            assert restarted.get('/api/v1/users/me').json()['data']['username']=='student'
