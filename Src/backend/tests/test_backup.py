import sqlite3

import pytest

from app.common.config import ConfigurationError
from app.db.backup import restore, snapshot
from app.db.connection import database_path
from test_auth import register, login


def test_live_backup_restore_and_session_revocation(client, settings, tmp_path):
    register(client); login(client)
    source = database_path(settings)
    backup = snapshot(source, tmp_path / 'backup.sqlite3')
    recovered = restore(backup, tmp_path / 'recovered')
    with sqlite3.connect(recovered) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
    assert client.get('/api/v1/users/me').status_code == 200
    with pytest.raises(FileExistsError):
        snapshot(source, backup)
    with pytest.raises(FileExistsError):
        restore(backup, recovered.parent)


def test_corrupt_and_missing_sources_leave_no_recovery_target(tmp_path):
    corrupt = tmp_path / 'bad.sqlite3'
    corrupt.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        restore(corrupt, tmp_path / 'recovery')
    assert not (tmp_path / 'recovery').exists()
    with pytest.raises(ConfigurationError):
        snapshot(tmp_path / 'missing', tmp_path / 'output')
    assert not (tmp_path / 'output').exists()
