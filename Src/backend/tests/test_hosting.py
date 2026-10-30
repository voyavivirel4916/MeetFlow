from copy import deepcopy

import pytest
from starlette.testclient import TestClient

from app.common.config import ConfigurationError, Settings
from app.db.migrate import upgrade
from app.hosting import DomainSocketHeaders, expected_socket
from app.main import create_app
from test_bootstrap import assert_error
from test_auth import register, login

SOCKET = '/var/sockets/meet.example/app.sock'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_socket_entry_requires_matching_production_config(settings):
    with pytest.raises(ConfigurationError):expected_socket(settings, SOCKET)
    config=Settings(_env_file=None,app_env='production',public_origin='https://meet.example',
                    data_dir=settings.data_dir,frontend_dir=settings.frontend_dir)
    assert expected_socket(config,SOCKET)==SOCKET
    for value in [None, '', '/tmp/arbitrary.sock', '/var/sockets/evil.example/app.sock']:
        with pytest.raises(ConfigurationError):expected_socket(config,value)


@pytest.mark.anyio
async def test_uds_header_boundary_uses_final_ip_and_preserves_original_scope():
    seen=[]
    async def endpoint(scope,receive,send):seen.append(scope)
    app=DomainSocketHeaders(endpoint,SOCKET)
    original={'type':'http','scheme':'http','server':(SOCKET,None),'client':None,
        'headers':[(b'x-forwarded-proto',b'https'),(b'x-forwarded-for',b'fake-client, 198.51.100.7')]}
    before=deepcopy(original)
    await app(original,None,None)
    assert original==before
    assert seen[-1]['scheme']=='https'
    assert seen[-1]['client']==('198.51.100.7',0)
    original['headers']=[(b'x-forwarded-proto',b'https'),(b'x-forwarded-for',b'1.2.3.4, not-an-ip')]
    await app(original,None,None)
    assert seen[-1]['client'] is None


@pytest.mark.anyio
@pytest.mark.parametrize('changes',[
    {'server':('127.0.0.1',8000)}, {'client':('198.51.100.9',0)},
    {'headers':[(b'x-forwarded-proto',b'http')]},
    {'headers':[(b'x-forwarded-proto',b'https'),(b'x-forwarded-proto',b'http')]},
])
async def test_tcp_or_ambiguous_transport_never_reaches_app(changes):
    reached=[];messages=[]
    async def endpoint(*args):reached.append(True)
    async def send(message):messages.append(message)
    scope={'type':'http','scheme':'http','server':(SOCKET,None),'client':None,
           'headers':[(b'x-forwarded-proto',b'https')],**changes}
    await DomainSocketHeaders(endpoint,SOCKET)(scope,None,send)
    assert reached==[]
    assert messages[0]['status']==400


def test_real_production_login_and_limit_behind_uds(settings):
    config=Settings(_env_file=None,app_env='production',public_origin='https://meet.example',
                    data_dir=settings.data_dir,frontend_dir=settings.frontend_dir)
    upgrade(config)
    wrapped=DomainSocketHeaders(create_app(config),SOCKET)
    async def transport(scope,receive,send):
        if scope['type']=='http':scope=dict(scope,server=(SOCKET,None),client=None,scheme='http')
        await wrapped(scope,receive,send)
    with TestClient(transport,base_url='https://meet.example',headers={
            'X-Forwarded-Proto':'https','X-Forwarded-For':'fake, 198.51.100.7'}) as client:
        assert register(client).status_code==201
        assert 'Secure' in login(client).headers['set-cookie']
        assert client.get('/api/v1/users/me').status_code==200
        for i in range(9):
            assert client.post('/api/v1/auth/login',json={},headers={'X-Forwarded-For':f'fake-{i}, 198.51.100.7'}).status_code==422
        assert_error(client.post('/api/v1/auth/login',json={},headers={'X-Forwarded-For':'changed, 198.51.100.7'}),429,'RATE_LIMITED')
