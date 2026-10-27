import sqlite3

from alembic import command
import pytest
from sqlalchemy import event, insert
from sqlalchemy.exc import IntegrityError

from app.common.config import ConfigurationError
from app.db import migrate
from app.db.connection import database_path, make_engine, write_transaction, require_current_schema
from app.db.models import meetings
from test_database import add_group, add_user, engine
from test_poll_structure import add_poll, structure


@pytest.fixture
def meeting_structure(structure):
    with write_transaction(structure) as connection:
        connection.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000),(2,2,3000,4000)')
    return structure


def values(**changes):
    return dict(id=1,poll_id=1,group_id=1,selected_slot_id=1,title='课程会议',location='2015A',start_at=3000,end_at=4000,
        selection_reason='',agenda='',minutes='',created_at=2000,updated_at=2000,**changes)


@pytest.mark.parametrize('changes',[
    {'group_id':2},{'selected_slot_id':2},{'poll_id':99},{'selected_slot_id':99},{'id':0},
    {'title':''},{'title':'字'*101},{'location':'地'*201},{'selection_reason':'字'*501},
    {'start_at':4000},{'end_at':2000},{'updated_at':0.5},{'minutes':'字'*10001},
])
def test_database_constraints(meeting_structure,changes):
    with pytest.raises(IntegrityError):
        with write_transaction(meeting_structure) as connection:
            connection.execute(insert(meetings).values(**(values()|changes)))


def test_poll_uniqueness_and_group_index(meeting_structure):
    with write_transaction(meeting_structure) as connection:
        connection.execute(insert(meetings).values(**values()))
        assert connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='index' AND name='ix_meetings_group_id'").fetchone()
    with pytest.raises(IntegrityError):
        with write_transaction(meeting_structure) as connection:
            connection.execute(insert(meetings).values(**(values()|{'id':2})))


@pytest.mark.parametrize('fail_first',[False,True])
def test_vote_database_upgrade_preserves_rows_and_rolls_back_failed_ddl(settings,monkeypatch,fail_first):
    settings.data_dir.mkdir(parents=True)
    engine=make_engine(database_path(settings),existing_only=False)
    try:
        with write_transaction(engine) as connection:
            config=migrate.migration_config();config.attributes['connection']=connection;command.upgrade(config,'0003_votes')
            add_user(connection);add_group(connection)
            connection.exec_driver_sql('INSERT INTO group_members VALUES (1,1,1000)')
            add_poll(connection,status='OPEN')
            connection.exec_driver_sql("INSERT INTO participants VALUES (1,1,1,'REQUIRED',1000)")
            connection.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000)')
            connection.exec_driver_sql("INSERT INTO votes VALUES (1,1,1,'AVAILABLE',1000)")
        with sqlite3.connect(database_path(settings)) as connection:
            names=['users','sessions','groups','group_members','polls','participants','slots','votes']
            before={name:connection.execute(f'SELECT * FROM {name}').fetchall() for name in names}
        if fail_first:
            original=migrate.make_engine
            def faulty(*args,**kwargs):
                instance=original(*args,**kwargs)
                @event.listens_for(instance,'before_cursor_execute')
                def fail(_c,_cu,sql,_p,_ctx,_m):
                    if sql.startswith('CREATE INDEX ix_meetings_group_id'):raise RuntimeError('injected migration failure')
                return instance
            with monkeypatch.context() as patch:
                patch.setattr(migrate,'make_engine',faulty)
                with pytest.raises(ConfigurationError):migrate.upgrade(settings)
            with sqlite3.connect(database_path(settings)) as connection:
                assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0003_votes'
                assert not connection.execute("SELECT name FROM sqlite_master WHERE name='meetings'").fetchall()
        migrate.upgrade(settings);migrate.upgrade(settings);require_current_schema(settings)
        with sqlite3.connect(database_path(settings)) as connection:
            assert {name:connection.execute(f'SELECT * FROM {name}').fetchall() for name in names}==before
            assert connection.execute('SELECT COUNT(*) FROM meetings').fetchone()[0]==0
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:engine.dispose()
