import os

import pytest
from fastapi.testclient import TestClient

from app.common.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for key in list(os.environ):
        if key.startswith('MEETFLOW_'):
            monkeypatch.delenv(key)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, app_env='test', data_dir=tmp_path / 'data')


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, base_url='http://127.0.0.1', raise_server_exceptions=False) as instance:
        yield instance
