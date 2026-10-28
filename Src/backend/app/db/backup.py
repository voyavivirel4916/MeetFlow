"""Explicit SQLite snapshots and non-overwriting recovery into a new directory."""
import argparse
from contextlib import closing
import sqlite3
from pathlib import Path

from app.common.config import ConfigurationError


def verify(connection):
    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ConfigurationError('Backup integrity check failed.')
    if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ConfigurationError('Backup relationship check failed.')
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone():
        raise ConfigurationError('Unversioned backup is not supported.')


def snapshot(source: Path, destination: Path, *, revoke_sessions=False):
    source, destination = source.resolve(), destination.absolute()
    if not source.is_file() or source == destination.resolve():
        raise ConfigurationError('Source database must exist and differ from destination.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: never replace an existing database, backup or symlink.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(destination)) as copy:
                original.backup(copy)
                verify(copy)
                if revoke_sessions:
                    copy.execute('DELETE FROM sessions')
                    if copy.execute("SELECT 1 FROM sqlite_master WHERE name='password_resets'").fetchone():
                        copy.execute('DELETE FROM password_resets')
                    copy.commit()
                    verify(copy)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def restore(source: Path, directory: Path):
    # Recovery is deliberately separate from changing the running service's data_dir.
    directory = directory.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    try:
        return snapshot(source, directory / 'meetflow.sqlite3', revoke_sessions=True)
    except BaseException:
        directory.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'restore'])
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        (snapshot if args.action == 'create' else restore)(args.source, args.destination)
    except (OSError, sqlite3.Error, ConfigurationError):
        print('Backup/recovery failed. Existing targets are never overwritten; check paths and database integrity.')
        return 2
    print('Verified snapshot created.' if args.action == 'create' else 'Recovered into new directory; old sessions revoked. Service configuration unchanged.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
