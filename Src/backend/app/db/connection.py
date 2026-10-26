from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.pool import NullPool

from app.common.config import ConfigurationError


def database_path(settings):
    return settings.data_dir / 'meetflow.sqlite3'


def make_engine(path: Path, *, existing_only: bool = True):
    # SQLite URI rw refuses a missing file. Only the explicit migration uses rwc.
    uri = path.resolve().as_uri() + ('?mode=rw' if existing_only else '?mode=rwc')
    engine = create_engine(URL.create('sqlite+pysqlite', database=uri,
                                     query={'uri': 'true'}),
                           connect_args={'timeout': 5, 'check_same_thread': False},
                           poolclass=NullPool)

    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=5000')

    return engine


@contextmanager
def write_transaction(engine):
    """Acquire the write lock before services recheck state and server time."""
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def require_current_schema(settings, *, writable: bool = False):
    from app.db.migrate import migration_config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from app.db.models import metadata

    engine = make_engine(database_path(settings))
    try:
        with engine.connect() as connection:
            if writable:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            current = MigrationContext.configure(connection).get_current_heads()
            expected = ScriptDirectory.from_config(migration_config()).get_heads()
            if set(current) != set(expected):
                raise ConfigurationError('Database migration required; run python -m app.db.migrate.')
            for table in metadata.sorted_tables:
                # Validate the migrated columns without loading user records.
                connection.execute(table.select().limit(0))
            if writable:
                # Exercise actual SQLite write permission, then leave all data unchanged.
                connection.exec_driver_sql('UPDATE alembic_version SET version_num = version_num')
            connection.rollback()
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError('Database unavailable; check the local database and migrations.') from None
    finally:
        engine.dispose()
