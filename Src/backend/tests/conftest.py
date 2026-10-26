import os

import pytest
from fastapi.testclient import TestClient

from app.common.config import Settings
from app.main import create_app
from app.db.migrate import upgrade


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith('MEETFLOW_'):
            monkeypatch.delenv(key)


@pytest.fixture
def settings(tmp_path):
    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True)
    (frontend / 'index.html').write_text('<!doctype html><title>MeetFlow test build</title><div id="app"></div><script type="module" src="/assets/app-test.js"></script>', encoding='utf-8')
    (frontend / 'assets/app-test.js').write_text('console.log("test asset")', encoding='utf-8')
    return Settings(_env_file=None, app_env='test', data_dir=tmp_path / 'data', frontend_dir=frontend)


@pytest.fixture
def app(settings):
    upgrade(settings)
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1', raise_server_exceptions=False) as instance:
        yield instance
