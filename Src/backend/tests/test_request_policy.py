import json

import pytest

from app.common.request_policy import JSON_LIMIT
from test_auth import PASSWORD, login, register
from test_bootstrap import assert_error


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://localhost', 'http://127.0.0.1:5173',
    'null', 'http://127.0.0.1.evil.example', 'http://user@127.0.0.1',
    'http://127.0.0.1/path', 'http://127.0.0.1?query=value', 'http://[invalid',
    'http://127.0.0.1:0', ' http://127.0.0.1'])
def test_cross_origin_rejected_before_credentials_or_database_work(client, origin):
    assert_error(client.get('/api/v1/health', headers={'Origin': origin}), 403, 'CSRF_REJECTED')
    response = client.post('/api/v1/auth/register', json={}, headers={'Origin': origin})
    assert_error(response, 403, 'CSRF_REJECTED')
    assert 'set-cookie' not in response.headers


@pytest.mark.parametrize('origin', ['http://127.0.0.1', 'http://127.0.0.1:80'])
def test_same_origin_accepted(client, origin):
    assert client.get('/api/v1/health', headers={'Origin': origin, 'Sec-Fetch-Site': 'same-origin'}).status_code == 200


def test_duplicate_origin_headers_rejected(client):
    response = client.get('/api/v1/health', headers=[('Origin', 'http://127.0.0.1'), ('Origin', 'http://127.0.0.1')])
    assert_error(response, 403, 'CSRF_REJECTED')


@pytest.mark.parametrize('site', ['cross-site', 'same-site', 'unexpected'])
def test_cross_site_fetch_rejected_even_without_origin(client, site):
    assert_error(client.get('/api/v1/users/me', headers={'Sec-Fetch-Site': site}), 403, 'CSRF_REJECTED')


@pytest.mark.parametrize('content_type', [None, 'text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data'])
def test_write_requires_json(client, content_type):
    headers = {} if content_type is None else {'Content-Type': content_type}
    response = client.post('/api/v1/auth/register', content='{}', headers=headers)
    assert_error(response, 400, 'INVALID_INPUT')


def test_json_content_type_with_charset_and_native_clients_work(client):
    body = json.dumps({'username': 'student', 'email': 'student@example.com', 'password': PASSWORD})
    response = client.post('/api/v1/auth/register', content=body, headers={'Content-Type': 'application/json; charset=utf-8'})
    assert response.status_code == 201
    assert login(client).status_code == 200
    assert client.post('/api/v1/auth/logout', json={'extra': 'private-value'}).status_code == 422


@pytest.mark.parametrize('streamed', [False, True])
def test_body_above_limit_is_rejected_with_or_without_content_length(client, streamed):
    content = b' ' * (JSON_LIMIT + 1)
    response = client.post('/api/v1/auth/register', content=iter([content[:100], content[100:]]) if streamed else content,
                           headers={'Content-Type': 'application/json'})
    assert_error(response, 413, 'PAYLOAD_TOO_LARGE')


def test_body_at_exact_limit_can_be_parsed(client):
    payload = json.dumps({'username': 'student', 'email': 'student@example.com', 'password': 'password123'}).encode()
    body = payload + b' ' * (JSON_LIMIT - len(payload))
    assert len(body) == JSON_LIMIT
    response = client.post('/api/v1/auth/register', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 201


def test_false_small_content_length_does_not_bypass_actual_limit(client):
    response = client.post('/api/v1/auth/register', content=b' ' * (JSON_LIMIT + 1),
                           headers={'Content-Type': 'application/json', 'Content-Length': '1'})
    assert_error(response, 413, 'PAYLOAD_TOO_LARGE')


@pytest.mark.parametrize('length', ['-1', 'invalid', '99999999999999999999'])
def test_invalid_or_excessive_declared_length_is_rejected(client, length):
    response = client.post('/api/v1/auth/register', content='{}',
                           headers={'Content-Type': 'application/json', 'Content-Length': length})
    assert_error(response, 413 if length.startswith('9') else 400, 'PAYLOAD_TOO_LARGE' if length.startswith('9') else 'INVALID_INPUT')


def test_malformed_json_does_not_echo_secrets(client):
    response = client.post('/api/v1/auth/login', content='{"password":"private-value"', headers={'Content-Type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert 'private-value' not in response.text


def test_cross_site_logout_does_not_revoke_session(client):
    register(client); login(client)
    response = client.post('/api/v1/auth/logout', json={}, headers={'Origin': 'https://evil.example'})
    assert_error(response, 403, 'CSRF_REJECTED')
    assert 'set-cookie' not in response.headers
    assert client.get('/api/v1/users/me').status_code == 200
