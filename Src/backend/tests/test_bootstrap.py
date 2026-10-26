import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.common.config import ConfigurationError, Settings
from app.common.responses import ApiError, InputModel
from app.main import create_app
from app.db.migrate import upgrade


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert body['error']['code'] == code
    assert body['request_id'] == response.headers['X-Request-ID']
    assert re.fullmatch(r'[0-9a-f]{32}', body['request_id'])
    return body


def test_liveness_has_request_id_and_health_checks_database(client, settings):
    response = client.get('/livez')
    assert response.status_code == 200
    assert response.json()['data'] == {'status': 'ok'}
    assert response.json()['request_id'] == response.headers['X-Request-ID']
    assert client.get('/api/v1/health').json()['data'] == {'status': 'ok'}


def test_ids_are_server_generated_and_request_values_are_not_logged(client, caplog):
    marker = 'private-request-value'
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        first = client.get('/livez', headers={'X-Request-ID': marker, 'Cookie': f'session={marker}'})
        second = client.get('/api/v1/missing/' + marker + '?password=' + marker,
                            headers={'Authorization': 'Bearer ' + marker})
    assert first.json()['request_id'] != marker
    assert first.json()['request_id'] != second.json()['request_id']
    assert marker not in caplog.text
    assert marker not in second.text
    assert 'route=/livez' in caplog.text
    assert 'route=/{path:path}' in caplog.text


def test_unknown_route_and_wrong_method_have_consistent_envelopes(client):
    assert_error(client.get('/api/v1/not-implemented'), 404, 'NOT_FOUND')
    response = client.post('/livez', json={})
    assert_error(response, 405, 'INVALID_INPUT')
    assert 'GET' in response.headers['allow']


@pytest.mark.parametrize('host', ['example.com', '127.0.0.1.example.com', 'localhost.example.com'])
def test_host_outside_local_allowlist_is_rejected(client, host):
    assert_error(client.get('/livez', headers={'Host': host}), 400, 'INVALID_INPUT')


def test_validation_errors_do_not_echo_body_values(app, client):
    class TestInput(InputModel):
        count: int

    @app.post('/_test/validate')
    def validate(body: TestInput):
        return {'count': body.count}

    response = client.post('/_test/validate', json={'count': 'private-body-value', 'extra': 'private-extra-value'})
    data = assert_error(response, 422, 'VALIDATION_ERROR')
    assert {field['type'] for field in data['error']['details']['fields']} == {'int_parsing', 'extra_forbidden'}
    assert 'private-body-value' not in response.text
    assert 'private-extra-value' not in response.text
    assert 'input' not in response.text


def test_expected_business_error_preserves_public_code(app, client):
    @app.get('/_test/conflict')
    def conflict():
        raise ApiError(409, 'STATE_CONFLICT', '当前状态不支持该操作。')
    app.router.routes.insert(0, app.router.routes.pop())
    assert_error(client.get('/_test/conflict'), 409, 'STATE_CONFLICT')


def test_unhandled_failure_is_generic_in_response_and_logs(app, client, caplog):
    @app.get('/_test/failure')
    def fail():
        raise RuntimeError('private-exception-value')
    app.router.routes.insert(0, app.router.routes.pop())
    with caplog.at_level(logging.INFO, logger='meetflow.requests'):
        response = client.get('/_test/failure')
    assert_error(response, 500, 'INTERNAL_ERROR')
    assert 'private-exception-value' not in response.text + caplog.text
    assert 'Traceback' not in response.text + caplog.text


def test_openapi_is_local_and_interactive_cdn_docs_are_disabled(client):
    schema = client.get('/openapi.json').json()
    assert '/livez' in schema['paths']
    assert '/api/v1/auth/login' in schema['paths']
    assert client.get('/docs').status_code == 404
    assert client.get('/redoc').status_code == 404


def test_startup_fails_when_data_directory_is_a_file(tmp_path):
    path = tmp_path / 'not-a-directory'
    path.write_text('keep me', encoding='utf-8')
    app = create_app(Settings(_env_file=None, app_env='test', data_dir=path))
    with pytest.raises(ConfigurationError):
        with TestClient(app, base_url='http://127.0.0.1'):
            pass
    assert path.read_text(encoding='utf-8') == 'keep me'


def test_app_factory_keeps_runtime_configuration_isolated(tmp_path, settings):
    first_config = settings.model_copy(update={'data_dir': tmp_path / 'first'})
    second_config = settings.model_copy(update={'data_dir': tmp_path / 'second'})
    upgrade(first_config)
    upgrade(second_config)
    first = create_app(first_config)
    second = create_app(second_config)
    with TestClient(first, base_url='http://127.0.0.1'), TestClient(second, base_url='http://127.0.0.1'):
        assert first.state.settings.data_dir != second.state.settings.data_dir
        assert first.state.settings.data_dir.is_dir()
        assert second.state.settings.data_dir.is_dir()
