import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import inspect, insert, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.common.config import ConfigurationError, Settings
from app.db.connection import database_path, make_engine, require_current_schema, write_transaction
from app.db.migrate import upgrade
from app.db.models import groups, group_members, metadata, sessions, users


@pytest.fixture
def engine(settings):
    upgrade(settings)
    engine = make_engine(database_path(settings))
    yield engine
    engine.dispose()


def add_user(connection, identifier=1, **changes):
    values = dict(id=identifier, username=f'user_{identifier}', email=f'u{identifier}@example.test', password_hash='test-hash', created_at=1000)
    values.update(changes)
    connection.execute(insert(users).values(**values))


def add_group(connection, **changes):
    values = dict(id=1, name='课程小组', owner_id=1, invite_code='ABCDEFGHI123', created_at=1000, updated_at=1000)
    values.update(changes)
    connection.execute(insert(groups).values(**values))


def test_fresh_migration_has_implemented_tables_and_matches_model(engine, settings):
    require_current_schema(settings)
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == {'users', 'sessions', 'groups', 'group_members', 'polls', 'participants', 'slots', 'alembic_version'}
        context = MigrationContext.configure(connection, opts={'compare_type': True, 'compare_server_default': True})
        assert compare_metadata(context, metadata) == []
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one() == '0002_poll_structure'
        assert connection.execute(select(users)).all() == []


def test_migration_is_repeatable_and_preserves_existing_data(engine, settings):
    with write_transaction(engine) as connection:
        add_user(connection)
    upgrade(settings)
    upgrade(settings)
    with engine.connect() as connection:
        assert connection.execute(select(users.c.username)).all() == [('user_1',)]


def test_missing_readiness_or_connection_never_creates_database(settings):
    assert not settings.data_dir.exists()
    with pytest.raises(ConfigurationError, match='Database unavailable'):
        require_current_schema(settings)
    assert not settings.data_dir.exists()
    settings.data_dir.mkdir()
    with pytest.raises(ConfigurationError):
        require_current_schema(settings)
    assert list(settings.data_dir.iterdir()) == []


def test_unversioned_database_is_preserved_and_refused(settings):
    settings.data_dir.mkdir()
    path = database_path(settings)
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE private_data (value TEXT)')
        connection.execute("INSERT INTO private_data VALUES ('keep')")
    before = path.read_bytes()
    with pytest.raises(ConfigurationError, match='Unversioned'):
        upgrade(settings)
    assert path.read_bytes() == before


def test_unknown_version_is_preserved_and_refused(engine, settings):
    with write_transaction(engine) as connection:
        add_user(connection)
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = 'future_version'")
    before = database_path(settings).read_bytes()
    with pytest.raises(ConfigurationError, match='migration required'):
        require_current_schema(settings)
    with pytest.raises(ConfigurationError, match='Migration failed'):
        upgrade(settings)
    assert database_path(settings).read_bytes() == before


def test_each_connection_enables_foreign_keys_and_timeout(engine):
    for _ in range(2):
        with engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar_one() == 1
            assert connection.exec_driver_sql('PRAGMA busy_timeout').scalar_one() == 5000
            with pytest.raises(IntegrityError):
                add_group(connection, owner_id=99)


def test_transaction_rolls_back_owner_and_group_together(engine):
    with pytest.raises(RuntimeError):
        with write_transaction(engine) as connection:
            add_user(connection)
            add_group(connection)
            raise RuntimeError('service failure')
    with engine.connect() as connection:
        assert connection.execute(select(users)).all() == []
        assert connection.execute(select(groups)).all() == []


def test_failed_migration_rolls_back_ddl_and_preserves_data(engine, settings, monkeypatch):
    from app.db import migrate
    with write_transaction(engine) as connection:
        add_user(connection)

    def broken_upgrade(config, _target):
        connection = config.attributes['connection']
        connection.exec_driver_sql('CREATE TABLE incomplete_migration (id INTEGER)')
        connection.exec_driver_sql('DELETE FROM users')
        raise RuntimeError('private storage failure')

    monkeypatch.setattr(migrate.command, 'upgrade', broken_upgrade)
    with pytest.raises(ConfigurationError, match='Migration failed') as caught:
        upgrade(settings)
    assert 'private storage failure' not in str(caught.value)
    with engine.connect() as connection:
        assert 'incomplete_migration' not in inspect(connection).get_table_names()
        assert connection.execute(select(users.c.username)).all() == [('user_1',)]
    require_current_schema(settings)


def test_transaction_acquires_lock_before_writes(engine):
    with write_transaction(engine) as first:
        with engine.connect() as second:
            second.exec_driver_sql('PRAGMA busy_timeout=1')
            with pytest.raises(OperationalError, match='locked'):
                second.exec_driver_sql('BEGIN IMMEDIATE')
        add_user(first)
    with write_transaction(engine) as connection:
        add_user(connection, 2)


@pytest.mark.parametrize('changes', [
    {'id': 0}, {'username': 'ABCD'}, {'username': 'ab'}, {'username': 'abc-'},
    {'username': 'a' * 33}, {'email': 'UPPER@example.test'}, {'email': 'a' * 255},
])
def test_user_constraints(engine, changes):
    with pytest.raises(IntegrityError):
        with write_transaction(engine) as connection:
            add_user(connection, **changes)


def test_unique_accounts_session_digest_membership_and_delete_restriction(engine):
    with write_transaction(engine) as connection:
        add_user(connection)
        add_group(connection)
        connection.execute(insert(group_members).values(group_id=1, user_id=1, joined_at=1000))
        connection.execute(insert(sessions).values(user_id=1, token_hash='a' * 64, created_at=1000, expires_at=2000))
    cases = [
        insert(users).values(username='user_1', email='other@example.test', password_hash='x', created_at=1),
        insert(users).values(username='other', email='u1@example.test', password_hash='x', created_at=1),
        insert(sessions).values(user_id=1, token_hash='a' * 64, created_at=1, expires_at=2),
        insert(sessions).values(user_id=1, token_hash='plain-token', created_at=1, expires_at=2),
        insert(sessions).values(user_id=1, token_hash='b' * 64, created_at=2, expires_at=1),
        insert(group_members).values(group_id=1, user_id=1, joined_at=2000),
        insert(group_members).values(group_id=1, user_id=99, joined_at=2000),
        users.delete().where(users.c.id == 1),
        groups.delete().where(groups.c.id == 1),
    ]
    for statement in cases:
        with pytest.raises(IntegrityError):
            with write_transaction(engine) as connection:
                connection.execute(statement)


@pytest.mark.parametrize('changes', [{'name': ''}, {'name': 'a'*101}, {'description': 'a'*10001},
    {'invite_code': 'short'}, {'invite_code': 'abcdefghijkl'}])
def test_group_constraints(engine, changes):
    with write_transaction(engine) as connection:
        add_user(connection)
    with pytest.raises(IntegrityError):
        with write_transaction(engine) as connection:
            add_group(connection, **changes)


def test_separate_test_databases_and_non_ascii_paths(tmp_path):
    first = Settings(_env_file=None, app_env='test', data_dir=tmp_path / '测试库 % # 甲')
    second = Settings(_env_file=None, app_env='test', data_dir=tmp_path / '测试库 乙')
    upgrade(first)
    upgrade(second)
    one = make_engine(database_path(first))
    two = make_engine(database_path(second))
    try:
        with write_transaction(one) as connection:
            add_user(connection)
        with two.connect() as connection:
            assert connection.execute(select(users)).all() == []
    finally:
        one.dispose(); two.dispose()
    require_current_schema(first)
