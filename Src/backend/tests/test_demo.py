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


def test_showcase_includes_v2_states_and_owner_dashboard(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.demo import PASSWORD
    result=seed(settings,showcase=True)
    assert result['task_count']==10
    assert result['poll_count']==9
    with sqlite3.connect(database_path(settings)) as db:
        assert db.execute('SELECT COUNT(*) FROM groups').fetchone()[0]==2
        assert db.execute('SELECT COUNT(*) FROM polls').fetchone()[0]==9
        assert db.execute('SELECT COUNT(*) FROM meetings').fetchone()[0]==3
        assert {r[0] for r in db.execute('SELECT DISTINCT status FROM tasks')}=={'TODO','IN_PROGRESS','DONE','CANCELLED'}
        assert db.execute('SELECT COUNT(*) FROM polls WHERE deleted_at IS NOT NULL').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM polls WHERE archived_at IS NOT NULL').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM participants WHERE poll_id=? AND submitted_at IS NOT NULL',(result['open_poll_id'],)).fetchone()[0]==3
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    with TestClient(create_app(settings),base_url='http://127.0.0.1') as client:
        assert client.post('/api/v1/auth/login',json={'username':'demo_owner','password':PASSWORD}).status_code==200
        dashboard=client.get('/api/v1/dashboard').json()['data']
        assert dashboard['groups']['total']==2
        assert dashboard['tasks']['total']==4
        assert dashboard['upcoming_meetings']['total']==3
        assert dashboard['pending_polls']['total']==1


def test_showcase_still_refuses_existing_directory_and_production(settings):
    seed(settings,showcase=True)
    before=database_path(settings).read_bytes()
    with pytest.raises(ValueError):seed(settings,showcase=True)
    assert database_path(settings).read_bytes()==before
    settings.app_env='production'
    with pytest.raises(ValueError):seed(settings,showcase=True)


@pytest.mark.parametrize('presentation_day',[2,6])
def test_showcase_dates_remain_open_on_presentation_day_without_freezing_real_time(settings, monkeypatch,presentation_day):
    from datetime import date
    from fastapi.testclient import TestClient
    from app.common import clock
    from app.common.times import parse_rfc3339, to_ms
    from app.main import create_app
    from app.demo import PASSWORD
    current=to_ms(parse_rfc3339('2026-10-31T16:30:12+08:00'))
    monkeypatch.setattr(clock,'now_ms',lambda:current)
    result=seed(settings,showcase=True,presentation_date=date(2026,11,presentation_day))
    with sqlite3.connect(database_path(settings)) as db:
        deadline=db.execute('SELECT response_deadline FROM polls WHERE id=?',(result['open_poll_id'],)).fetchone()[0]
        assert deadline==to_ms(parse_rfc3339(f'2026-11-{presentation_day+1:02}T10:00:00+08:00'))
        assert db.execute('SELECT created_at FROM polls WHERE id=?',(result['open_poll_id'],)).fetchone()[0]==current
    current=to_ms(parse_rfc3339(f'2026-11-{presentation_day:02}T23:59:00+08:00'))
    with TestClient(create_app(settings),base_url='http://127.0.0.1') as client:
        assert client.post('/api/v1/auth/login',json={'username':'demo_owner','password':PASSWORD}).status_code==200
        dashboard=client.get('/api/v1/dashboard').json()['data']
        assert dashboard['pending_polls']['total']==1
        assert dashboard['upcoming_meetings']['total']==3
    before=database_path(settings).read_bytes()
    with pytest.raises(ValueError):seed(settings,showcase=True,presentation_date=date(2026,11,presentation_day))
    assert database_path(settings).read_bytes()==before


@pytest.mark.parametrize('offset',[-1,366])
def test_invalid_presentation_date_does_not_create_directory(settings,offset):
    from datetime import datetime,timedelta
    from app.common import clock
    from app.demo import BEIJING
    today=datetime.fromtimestamp(clock.now_ms()/1000,BEIJING).date()
    with pytest.raises(ValueError):seed(settings,showcase=True,presentation_date=today+timedelta(days=offset))
    assert not settings.data_dir.exists()


def test_presentation_date_requires_explicit_showcase(settings):
    from datetime import datetime
    from app.demo import BEIJING
    with pytest.raises(ValueError):seed(settings,presentation_date=datetime.now(BEIJING).date())
    assert not settings.data_dir.exists()
