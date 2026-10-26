"""Run explicitly: python -m app.db.migrate. No seed, downgrade or startup DDL."""
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.common.config import ConfigurationError, load_settings, prepare_runtime
from app.db.connection import database_path, make_engine


def migration_config():
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'migrations'))
    return config


def upgrade(settings):
    prepare_runtime(settings)
    engine = make_engine(database_path(settings), existing_only=False)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            if tables and 'alembic_version' not in tables:
                raise ConfigurationError('Unversioned database; preserve it and inspect before migrating.')
            connection.rollback()
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                config = migration_config()
                config.attributes['connection'] = connection
                command.upgrade(config, 'head')
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except ConfigurationError:
        raise
    except Exception:
        raise ConfigurationError('Migration failed; preserve the database and inspect its version.') from None
    finally:
        engine.dispose()


def main():
    try:
        upgrade(load_settings())
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    print('Database is at the current migration head.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
