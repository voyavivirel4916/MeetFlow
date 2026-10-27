from test_database import original_rows
import sqlite3

import pytest
from alembic import command
from sqlalchemy import event, insert
from sqlalchemy.exc import IntegrityError

from app.common.config import ConfigurationError
from app.db import migrate
from app.db.connection import database_path, make_engine, write_transaction
from app.db.models import meetings, tasks
from test_database import add_group, add_user, engine
from test_poll_structure import add_poll, structure
from test_meeting_structure import meeting_structure, values


@pytest.mark.parametrize('changes', [{'group_id':2},{'assignee_id':99},{'meeting_id':99},{'id':0},{'title':''},
    {'description':'x'*10001},{'due_at':1000},{'status':'OTHER'},{'status':'DONE'},{'completed_at':1500},
    {'due_at':2000.5},{'client_request_id':'bad'}])
def test_task_database_constraints(meeting_structure,changes):
    with write_transaction(meeting_structure) as connection:connection.execute(insert(meetings).values(**values()))
    fields=dict(id=1,meeting_id=1,group_id=1,creator_id=1,assignee_id=1,title='任务',description='',due_at=2000,status='TODO',
        completed_at=None,client_request_id='621ff63b-2850-4c3c-a324-7201af5eb970',created_at=1000,updated_at=1000)
    with pytest.raises(IntegrityError):
        with write_transaction(meeting_structure) as connection:connection.execute(insert(tasks).values(**(fields|changes)))


@pytest.mark.parametrize('fail_first',[False,True])
def test_upgrade_preserves_old_meeting_and_rolls_back_failed_ddl(settings,monkeypatch,fail_first):
    settings.data_dir.mkdir(parents=True)
    engine=make_engine(database_path(settings),existing_only=False)
    try:
        with write_transaction(engine) as connection:
            config=migrate.migration_config();config.attributes['connection']=connection;command.upgrade(config,'0004_meetings')
            add_user(connection);add_group(connection);connection.exec_driver_sql('INSERT INTO group_members VALUES (1,1,1000)')
            add_poll(connection);connection.exec_driver_sql('INSERT INTO slots VALUES (1,1,3000,4000)')
            connection.execute(insert(meetings).values(**values()))
        names=['users','sessions','groups','group_members','polls','participants','slots','votes','meetings']
        with sqlite3.connect(database_path(settings)) as connection:before={name:original_rows(connection, name) for name in names}
        if fail_first:
            original=migrate.make_engine
            def faulty(*args,**kwargs):
                instance=original(*args,**kwargs)
                @event.listens_for(instance,'before_cursor_execute')
                def fail(_c,_cu,sql,_p,_ctx,_m):
                    if sql.startswith('CREATE INDEX ix_tasks_group_created'):raise RuntimeError('injected failure')
                return instance
            with monkeypatch.context() as patch:
                patch.setattr(migrate,'make_engine',faulty)
                with pytest.raises(ConfigurationError):migrate.upgrade(settings)
            with sqlite3.connect(database_path(settings)) as connection:
                assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0004_meetings'
                assert not connection.execute("SELECT name FROM sqlite_master WHERE name IN ('tasks','uq_meetings_id_group')").fetchall()
        migrate.upgrade(settings);migrate.upgrade(settings)
        with sqlite3.connect(database_path(settings)) as connection:
            assert before=={name:original_rows(connection, name) for name in names}
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    finally:engine.dispose()
