import os
import sqlite3
import stat
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.common.config import BACKEND_ROOT, ConfigurationError
from app.db.connection import database_path, make_engine, write_transaction
from app.db.migrate import upgrade
from app.main import create_app
from test_bootstrap import assert_error


@pytest.mark.parametrize('path', ['/', '/groups', '/groups/1', '/polls/2/vote', '/polls/2/results', '/meetings/3', '/tasks/mine', '/missing-page'])
def test_spa_deep_links_receive_only_the_entry_document(client, settings, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert response.text == (settings.frontend_dir / 'index.html').read_text(encoding='utf-8')
    assert response.headers['cache-control'] == 'no-cache'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert len(response.headers['x-request-id']) == 32


def test_head_and_static_asset_serving(client):
    page = client.head('/polls/1/vote')
    assert page.status_code == 200
    assert page.content == b''
    assert int(page.headers['content-length']) > 0
    asset = client.get('/assets/app-test.js')
    assert asset.status_code == 200
    assert 'javascript' in asset.headers['content-type']
    assert 'test asset' in asset.text
    assert client.head('/assets/app-test.js').content == b''


@pytest.mark.parametrize('path', ['/api', '/api/v1', '/api/v1/missing', '/api/v2/health', '/assets/missing.js', '/assets/missing', '/favicon.ico', '/.env', '/secret.sqlite3', '/docs', '/redoc'])
def test_api_and_missing_files_never_fall_back_to_html(client, path):
    response = client.get(path)
    assert_error(response, 404, 'NOT_FOUND')
    assert response.headers['content-type'].startswith('application/json')


def test_static_requests_cannot_escape_the_build(client, settings):
    secret = settings.frontend_dir.parent / 'private.txt'
    secret.write_text('private-file-marker', encoding='utf-8')
    for path in ['/assets/%2e%2e/%2e%2e/private.txt', '/assets/%2e%2e/index.html', '/%2eenv', '/assets/%5c..%5cprivate.txt']:
        response = client.get(path)
        assert response.status_code == 404
        assert 'private-file-marker' not in response.text


def test_health_is_public_read_only_uncached_and_has_no_private_metadata(client, settings):
    path = database_path(settings)
    before = path.read_bytes()
    response = client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'data': {'status': 'ok'}, 'request_id': response.headers['X-Request-ID']}
    assert response.headers['cache-control'] == 'no-store'
    assert str(path) not in response.text
    assert path.read_bytes() == before
    assert client.post('/api/v1/health').status_code == 405


def test_missing_database_after_startup_is_not_recreated_and_liveness_stays_independent(client, settings):
    path = database_path(settings)
    saved = path.with_name('preserved.sqlite3')
    path.rename(saved)
    try:
        body = assert_error(client.get('/api/v1/health'), 503, 'STORAGE_UNAVAILABLE')
        assert str(path) not in str(body)
        assert not path.exists()
        assert client.get('/livez').status_code == 200
    finally:
        saved.rename(path)
    assert client.get('/api/v1/health').status_code == 200


@pytest.mark.parametrize('damage', ['revision', 'table'])
def test_health_detects_schema_damage_without_leaking_storage_details(client, settings, damage):
    engine = make_engine(database_path(settings))
    try:
        with write_transaction(engine) as connection:
            connection.exec_driver_sql("UPDATE alembic_version SET version_num = 'private-future-version'" if damage == 'revision' else 'DROP TABLE users')
    finally:
        engine.dispose()
    response = client.get('/api/v1/health')
    assert_error(response, 503, 'STORAGE_UNAVAILABLE')
    assert response.headers['cache-control'] == 'no-store'
    assert 'private-future-version' not in response.text


@pytest.mark.parametrize('problem', ['missing', 'unversioned', 'unknown', 'corrupt'])
def test_startup_refuses_unready_database_without_repairing_it(settings, problem):
    path = database_path(settings)
    if problem == 'missing':
        pass
    elif problem == 'corrupt':
        settings.data_dir.mkdir()
        path.write_bytes(b'private-corrupt-database-value')
    elif problem == 'unversioned':
        settings.data_dir.mkdir()
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE existing_data (value TEXT)')
    else:
        upgrade(settings)
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'unknown'")
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(ConfigurationError) as caught:
        with TestClient(create_app(settings), base_url='http://127.0.0.1'):
            pass
    assert 'private-corrupt-database-value' not in str(caught.value)
    assert (path.read_bytes() if path.exists() else None) == before


def test_startup_checks_actual_database_write_permission(settings):
    upgrade(settings)
    path = database_path(settings)
    mode = path.stat().st_mode
    path.chmod(stat.S_IREAD)
    try:
        with pytest.raises(ConfigurationError):
            with TestClient(create_app(settings), base_url='http://127.0.0.1'):
                pass
    finally:
        path.chmod(mode)


@pytest.mark.parametrize('problem', ['missing', 'empty', 'no-assets', 'missing-bundle', 'external-bundle'])
def test_startup_refuses_incomplete_frontend_build(settings, problem):
    upgrade(settings)
    if problem == 'missing':
        settings.frontend_dir = settings.frontend_dir.parent / 'not-built'
    elif problem == 'empty':
        (settings.frontend_dir / 'index.html').write_bytes(b'')
    elif problem == 'missing-bundle':
        (settings.frontend_dir / 'assets/app-test.js').rename(settings.frontend_dir / 'assets/renamed.js')
    elif problem == 'external-bundle':
        (settings.frontend_dir / 'index.html').write_text('<script type="module" src="https://example.test/remote.js"></script>', encoding='utf-8')
    else:
        settings.frontend_dir = settings.frontend_dir.parent / 'index-only'
        settings.frontend_dir.mkdir()
        (settings.frontend_dir / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    with pytest.raises(ConfigurationError, match='npm run build'):
        with TestClient(create_app(settings), base_url='http://127.0.0.1'):
            pass


def test_startup_write_probe_preserves_existing_database(settings):
    upgrade(settings)
    path = database_path(settings)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO users VALUES (1, 'student', 'student@example.test', 'test-hash', 1000)")
    before = path.read_bytes()
    with TestClient(create_app(settings), base_url='http://127.0.0.1') as client:
        assert client.get('/api/v1/health').status_code == 200
    assert path.read_bytes() == before


@pytest.mark.parametrize('problem', ['missing-db', 'missing-build'])
def test_cli_startup_failure_is_concise_and_does_not_bind_a_port(settings, problem):
    if problem == 'missing-build':
        upgrade(settings)
    env = {key: value for key, value in os.environ.items() if not key.startswith('MEETFLOW_')}
    env.update(MEETFLOW_DATA_DIR=str(settings.data_dir), MEETFLOW_FRONTEND_DIR=str(settings.frontend_dir / 'private-missing-build'))
    result = subprocess.run([sys.executable, '-m', 'app'], cwd=BACKEND_ROOT, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert 'Uvicorn running' not in result.stdout + result.stderr
    assert 'Traceback' not in result.stderr
    assert 'private-missing-build' not in result.stderr
