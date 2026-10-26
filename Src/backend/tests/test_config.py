import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.common.config import BACKEND_ROOT, ConfigurationError, Settings, load_settings, prepare_runtime


def test_defaults_and_relative_paths_are_independent_of_shell_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    defaults = Settings(_env_file=None)
    assert defaults.bind_host == '127.0.0.1'
    assert defaults.port == 8000
    assert defaults.data_dir == BACKEND_ROOT / 'data'
    assert defaults.frontend_dir == BACKEND_ROOT.parent / 'frontend' / 'dist'
    custom = Settings(_env_file=None, data_dir='local-data', frontend_dir='../custom-build')
    assert custom.data_dir == BACKEND_ROOT / 'local-data'
    assert custom.frontend_dir == (BACKEND_ROOT.parent / 'custom-build').resolve()


def test_env_overrides_dotenv_and_unknown_dotenv_keys_are_rejected(tmp_path, monkeypatch):
    dotenv = tmp_path / '.env'
    dotenv.write_text('MEETFLOW_PORT=8123\n', encoding='utf-8')
    assert Settings(_env_file=dotenv).port == 8123
    monkeypatch.setenv('MEETFLOW_PORT', '8124')
    assert Settings(_env_file=dotenv).port == 8124
    dotenv.write_text('MEETFLOW_UNRECOGNIZED=example\n', encoding='utf-8')
    with pytest.raises(ValidationError):
        Settings(_env_file=dotenv)


@pytest.mark.parametrize('values', [
    {'port': 0}, {'port': 65536}, {'bind_host': '0.0.0.0'},
    {'app_env': 'production'}, {'log_level': 'trace'},
])
def test_invalid_or_nonlocal_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_config_failure_does_not_include_private_input(monkeypatch):
    monkeypatch.setenv('MEETFLOW_PORT', 'private-sentinel-value')
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    assert 'port' in str(caught.value)
    assert 'private-sentinel-value' not in str(caught.value)


def test_startup_checks_writeability_without_creating_or_clearing_database(settings):
    prepare_runtime(settings)
    assert settings.data_dir.is_dir()
    assert list(settings.data_dir.iterdir()) == []
    sentinel = settings.data_dir / 'existing.sqlite3'
    sentinel.write_bytes(b'existing-data-that-must-not-be-reinitialized')
    prepare_runtime(settings)
    assert sentinel.read_bytes() == b'existing-data-that-must-not-be-reinitialized'
    assert list(settings.data_dir.iterdir()) == [sentinel]


def test_unwritable_runtime_fails_with_sanitized_message(settings, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError('private-directory-details')
    monkeypatch.setattr('app.common.config.tempfile.TemporaryFile', denied)
    with pytest.raises(ConfigurationError) as caught:
        prepare_runtime(settings)
    assert 'not writable' in str(caught.value)
    assert 'private-directory-details' not in str(caught.value)


def test_cli_invalid_configuration_exits_before_starting_server():
    env = {key: value for key, value in os.environ.items() if not key.startswith('MEETFLOW_')}
    env['MEETFLOW_PORT'] = 'private-cli-value'
    result = subprocess.run([sys.executable, '-m', 'app'], cwd=BACKEND_ROOT, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert 'port' in result.stderr
    assert 'private-cli-value' not in result.stdout + result.stderr
    assert 'Uvicorn running' not in result.stdout + result.stderr
