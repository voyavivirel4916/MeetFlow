import sqlite3

import pytest

from app.common.config import Settings
from app.db.connection import database_path
from app.demo import seed


def test_demo_is_fresh_reproducible_and_has_full_workflow_samples(settings):
    result=seed(settings)
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]==4
        assert connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==2
        assert connection.execute("SELECT COUNT(*) FROM polls WHERE status='OPEN'").fetchone()[0]==1
        assert connection.execute('SELECT COUNT(*) FROM meetings').fetchone()[0]==1
        assert connection.execute('SELECT COUNT(*) FROM participants WHERE poll_id=? AND submitted_at IS NULL',(result['open_poll_id'],)).fetchone()[0]==4
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    before=database_path(settings).read_bytes()
    with pytest.raises(ValueError):seed(settings)
    assert database_path(settings).read_bytes()==before


def test_demo_refuses_normal_or_preexisting_directory(settings):
    with pytest.raises(ValueError):seed(Settings(_env_file=None))
    settings.data_dir.mkdir(parents=True)
    marker=settings.data_dir/'keep.txt';marker.write_text('untouched')
    with pytest.raises(ValueError):seed(settings)
    assert marker.read_text()=='untouched'


def test_demo_rejects_dimensions_before_creating_files(settings):
    with pytest.raises(ValueError):seed(settings,member_count=21)
    assert not settings.data_dir.exists()
