"""Start an isolated, persistent local showcase without modifying normal data."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BEIJING = timezone(timedelta(hours=8))


def default_presentation_date(root, today):
    candidates = []
    for marker in (root / 'Src/backend/data').glob('showcase-for-*/showcase.json'):
        if marker.is_symlink() or marker.parent.is_symlink():
            continue
        try:
            value = json.loads(marker.read_text(encoding='utf-8'))
            day = date.fromisoformat(value['presentation_date'])
            if (value == {'format': 1, 'presentation_date': day.isoformat()}
                    and marker.parent.name == f'showcase-for-{day.isoformat()}'
                    and today <= day <= today + timedelta(days=365)):
                candidates.append(day)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return min(candidates) if candidates else today + timedelta(days=2)


def demo_environment(root, directory, port):
    env = {name: value for name, value in os.environ.items() if not name.startswith('MEETFLOW_')}
    env.update(MEETFLOW_APP_ENV='local', MEETFLOW_BIND_HOST='127.0.0.1',
               MEETFLOW_PUBLIC_ORIGIN='', MEETFLOW_TRUSTED_PROXIES='[]',
               MEETFLOW_SMTP_HOST='', MEETFLOW_SMTP_USERNAME='',
               MEETFLOW_SMTP_PASSWORD='', MEETFLOW_SMTP_SENDER='',
               MEETFLOW_DATA_DIR=str(directory), MEETFLOW_PORT=str(port),
               MEETFLOW_FRONTEND_DIR=str(root / 'Src/frontend/dist'))
    return env


def prepare_demo(root, presentation_date, port, *, run=subprocess.run):
    today = datetime.now(BEIJING).date()
    if not today <= presentation_date <= today + timedelta(days=365):
        raise ValueError('Use today or a presentation date within the next 365 days.')
    backend = root / 'Src/backend'
    python = backend / '.venv/Scripts/python.exe'
    if not python.is_file() or not (root / 'Src/frontend/dist/index.html').is_file():
        raise ValueError('Install local dependencies and build the frontend first.')
    directory = backend / 'data' / f'showcase-for-{presentation_date.isoformat()}'
    marker = directory / 'showcase.json'
    expected = {'format': 1, 'presentation_date': presentation_date.isoformat()}
    if directory.is_symlink() or marker.is_symlink():
        raise ValueError('Showcase links are not supported.')
    env = demo_environment(root, directory, port)
    if directory.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != expected:
            raise ValueError('Existing directory is not a recognized showcase; it was not modified.')
        if not (directory / 'meetflow.sqlite3').is_file():
            raise ValueError('Showcase database is missing; it was not recreated.')
    else:
        seed_env = dict(env)
        # The CLI receives the target explicitly. Leaving DATA_DIR in its
        # environment would make the seeder treat this target as normal data.
        seed_env.pop('MEETFLOW_DATA_DIR', None)
        run([str(python), '-m', 'app.demo', '--data-dir', str(directory), '--showcase',
             '--presentation-date', presentation_date.isoformat()], cwd=backend, env=seed_env, check=True)
        with marker.open('x', encoding='utf-8') as stream:
            json.dump(expected, stream)
    return python, backend, env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presentation-date', type=date.fromisoformat)
    parser.add_argument('--port', type=int, default=8002)
    args = parser.parse_args(argv)
    if args.presentation_date is None:
        args.presentation_date = default_presentation_date(ROOT, datetime.now(BEIJING).date())
    if not 1024 <= args.port <= 65535:
        parser.error('Use a local port from 1024 to 65535.')
    try:
        # Refuse occupied ports before seeding; never stop another service.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', args.port))
        python, backend, env = prepare_demo(ROOT, args.presentation_date, args.port)
        print(f'Local demo: http://localhost:{args.port}/login', flush=True)
        print(f'Presentation date (Beijing): {args.presentation_date}; existing demo progress is preserved.', flush=True)
        print('Demo-only login: demo_owner / MeetFlowDemo2026!', flush=True)
        print('Keep this window open; Ctrl+C stops this demo only.', flush=True)
        return subprocess.run([str(python), '-m', 'app'], cwd=backend, env=env).returncode
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('Demo could not start. Check the port, build and demo directory; normal data was not changed.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
