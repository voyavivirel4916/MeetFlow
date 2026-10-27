"""T14 database invariants and upgrades; no poll service/API is implemented here."""
import sqlite3

from alembic import command
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.auth.passwords import hash_password
from app.auth.service import token_digest
from app.common.config import ConfigurationError, prepare_runtime
from app.db import migrate
from app.db.connection import database_path, make_engine, require_current_schema, write_transaction
from app.db.models import group_members, groups, participants, polls, sessions, slots
from app.main import create_app
from test_auth import PASSWORD, cookie, login
from test_database import add_group, add_user, engine


def add_poll(connection, identifier=1, group_id=1, **changes):
    values = dict(id=identifier, group_id=group_id, title='课程讨论', response_deadline=2000, created_at=1000, updated_at=1000)
    values.update(changes)
    connection.execute(insert(polls).values(**values))


@pytest.fixture
def structure(engine):
    with write_transaction(engine) as connection:
        for identifier in [1, 2, 3]:
            add_user(connection, identifier)
        add_group(connection)
        add_group(connection, id=2, owner_id=2, invite_code='SECONDGROUP1')
        connection.execute(insert(group_members), [dict(group_id=g, user_id=u, joined_at=1000) for g, u in [(1, 1), (1, 2), (2, 1), (2, 2)]])
        add_poll(connection)
        add_poll(connection, 2, 2)
    return engine


def test_empty_draft_defaults_and_required_group_index(structure):
    with structure.connect() as connection:
        row = connection.execute(select(polls).where(polls.c.id == 1)).mappings().one()
        assert (row['status'], row['description'], row['location']) == ('DRAFT', '', '')
        assert connection.execute(select(participants)).all() == []
        assert connection.execute(select(slots)).all() == []
        index = next(item for item in inspect(connection).get_indexes('polls') if item['name'] == 'ix_polls_group_status')
        assert index['column_names'] == ['group_id', 'status']


@pytest.mark.parametrize('changes', [
    {'id': 0}, {'group_id': 99}, {'title': ''}, {'title': 'x'*101}, {'description': 'x'*10001},
    {'location': 'x'*201}, {'status': 'ARCHIVED'}, {'status': 'open'}, {'status': None},
    {'response_deadline': None}, {'response_deadline': 1.5}, {'response_deadline': 'not-time'},
    {'created_at': 1.5}, {'updated_at': 'not-time'},
])
def test_poll_constraints_are_enforced_on_direct_writes(structure, changes):
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            add_poll(connection, 3, **changes)


@pytest.mark.parametrize('status', ['DRAFT', 'OPEN', 'CLOSED', 'CONFIRMED', 'CANCELLED'])
def test_all_designed_status_values_are_storable(structure, status):
    with write_transaction(structure) as connection:
        add_poll(connection, 3, status=status, title='组'*100, description='😀'*10000, location='地'*200)


def test_same_group_participants_nullable_submission_and_unique_membership(structure):
    values = dict(poll_id=1, group_id=1, user_id=1, importance='REQUIRED')
    with write_transaction(structure) as connection:
        connection.execute(insert(participants).values(**values))
        assert connection.execute(select(participants.c.submitted_at)).scalar_one() is None
        connection.execute(update(participants).values(submitted_at=3000))
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            connection.execute(insert(participants).values(**values))


@pytest.mark.parametrize('changes', [
    {'group_id': 2},  # This user belongs to both groups; the poll/group pair must still agree.
    {'user_id': 3}, {'user_id': 99}, {'poll_id': 99}, {'importance': 'OWNER'},
    {'importance': None}, {'submitted_at': 1.5}, {'submitted_at': 'not-time'},
])
def test_participant_cross_group_and_value_constraints(structure, changes):
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            connection.execute(insert(participants).values(**dict(poll_id=1, group_id=1, user_id=1, importance='NORMAL') | changes))


def test_slot_defaults_uniqueness_and_permitted_overlap_across_polls(structure):
    with write_transaction(structure) as connection:
        connection.execute(insert(slots), [dict(id=1, poll_id=1, start_at=3000, end_at=4000),
            dict(id=2, poll_id=2, start_at=3000, end_at=4000), dict(id=3, poll_id=1, start_at=3500, end_at=4500)])
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            connection.execute(insert(slots).values(poll_id=1, start_at=3000, end_at=4000))
    with structure.connect() as connection:
        unique = {tuple(item['column_names']) for item in inspect(connection).get_unique_constraints('slots')}
        assert {('poll_id', 'id'), ('poll_id', 'start_at', 'end_at')} <= unique


@pytest.mark.parametrize('changes', [
    {'id': 0}, {'poll_id': 99}, {'start_at': 4000}, {'start_at': 5000},
    {'start_at': 3000.5}, {'end_at': 4000.5}, {'start_at': None}, {'end_at': 'not-time'},
])
def test_slot_order_foreign_key_and_integer_milliseconds(structure, changes):
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            connection.execute(insert(slots).values(**dict(id=1, poll_id=1, start_at=3000, end_at=4000) | changes))


@pytest.mark.parametrize('operation', ['member_delete', 'poll_delete', 'poll_move', 'group_delete'])
def test_parent_changes_cannot_orphan_participants_or_slots(structure, operation):
    with write_transaction(structure) as connection:
        connection.execute(insert(participants).values(poll_id=1, group_id=1, user_id=1, importance='NORMAL'))
        connection.execute(insert(slots).values(poll_id=1, start_at=3000, end_at=4000))
    statement = {
        'member_delete': group_members.delete().where(group_members.c.group_id == 1, group_members.c.user_id == 1),
        'poll_delete': polls.delete().where(polls.c.id == 1),
        'poll_move': polls.update().where(polls.c.id == 1).values(group_id=2),
        'group_delete': groups.delete().where(groups.c.id == 1),
    }[operation]
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            connection.execute(statement)


def test_draft_children_can_be_replaced_explicitly_and_failure_rolls_back_all(structure):
    with pytest.raises(IntegrityError):
        with write_transaction(structure) as connection:
            add_poll(connection, 3)
            connection.execute(insert(participants).values(poll_id=3, group_id=1, user_id=1, importance='NORMAL'))
            connection.execute(insert(slots).values(poll_id=3, start_at=4000, end_at=3000))
    with structure.connect() as connection:
        assert connection.execute(select(polls.c.id).order_by(polls.c.id)).scalars().all() == [1, 2]
        assert connection.execute(select(participants)).all() == []
    with write_transaction(structure) as connection:
        connection.execute(insert(participants).values(poll_id=1, group_id=1, user_id=1, importance='NORMAL'))
        connection.execute(insert(slots).values(poll_id=1, start_at=3000, end_at=4000))
        connection.execute(slots.delete().where(slots.c.poll_id == 1))
        connection.execute(participants.delete().where(participants.c.poll_id == 1))
        connection.execute(insert(slots).values(poll_id=1, start_at=5000, end_at=6000))


def legacy_database(settings):
    prepare_runtime(settings)
    engine = make_engine(database_path(settings), existing_only=False)
    with write_transaction(engine) as connection:
        config = migrate.migration_config()
        config.attributes['connection'] = connection
        command.upgrade(config, '0001_core')
        add_user(connection, password_hash=hash_password(PASSWORD))
        add_group(connection)
        connection.execute(insert(group_members).values(group_id=1, user_id=1, joined_at=1000))
        connection.execute(insert(sessions).values(user_id=1, token_hash=token_digest('A'*43), created_at=0, expires_at=9_000_000_000_000))
    engine.dispose()


def core_snapshot(settings):
    with sqlite3.connect(database_path(settings)) as connection:
        return {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
                for table in ['users', 'sessions', 'groups', 'group_members']}


def test_legacy_upgrade_preserves_every_core_row_cookie_and_password(settings):
    legacy_database(settings)
    before = core_snapshot(settings)
    with pytest.raises(ConfigurationError, match='migration required'):
        require_current_schema(settings)
    migrate.upgrade(settings)
    migrate.upgrade(settings)
    require_current_schema(settings)
    assert core_snapshot(settings) == before
    with TestClient(create_app(settings), base_url='http://127.0.0.1') as client:
        assert client.get('/api/v1/users/me', headers=cookie('A'*43)).status_code == 200
        assert login(client, username='user_1').status_code == 200
        assert client.get('/api/v1/groups').json()['data']['total'] == 1


def test_real_second_migration_failure_rolls_back_ddl_and_keeps_old_revision(settings, monkeypatch):
    legacy_database(settings)
    before = core_snapshot(settings)
    original = migrate.make_engine

    def failing_engine(*args, **kwargs):
        engine = original(*args, **kwargs)

        @event.listens_for(engine, 'before_cursor_execute')
        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().startswith('CREATE TABLE slots'):
                raise RuntimeError('injected migration failure')
        return engine

    with monkeypatch.context() as patch:
        patch.setattr(migrate, 'make_engine', failing_engine)
        with pytest.raises(ConfigurationError, match='Migration failed'):
            migrate.upgrade(settings)
    assert core_snapshot(settings) == before
    with sqlite3.connect(database_path(settings)) as connection:
        assert connection.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0001_core'
        assert not {'polls', 'participants', 'slots'} & {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    migrate.upgrade(settings)
    require_current_schema(settings)


def test_destructive_downgrade_is_refused_without_data_loss(structure, settings):
    with pytest.raises(RuntimeError, match='Destructive downgrade is disabled'):
        with write_transaction(structure) as connection:
            config = migrate.migration_config()
            config.attributes['connection'] = connection
            command.downgrade(config, '0001_core')
    require_current_schema(settings)
    with structure.connect() as connection:
        assert connection.execute(select(polls.c.id)).scalars().all() == [1, 2]
