"""Prepare the first full deployment, preserving the existing probe for rollback."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def inspect_layout(root, home, domain):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.pythonanywhere\.com', domain):
        raise ValueError('Expected the account subdomain on pythonanywhere.com.')
    root, home = root.resolve(), home.resolve()
    backend, frontend = root / 'backend', root / 'frontend' / 'dist'
    if not (frontend / 'index.html').is_file() or not (backend / 'app' / 'hosting.py').is_file():
        raise ValueError('Extract the complete release archive first.')
    data = home / 'meetflow-data'
    if (data / 'meetflow.sqlite3').exists():
        raise ValueError('An existing production database was found; use the backup/update procedure.')
    probe = home / 'meetflow-probe' / 'probe.py'
    backup = probe.with_name('probe.py.before-meetflow')
    if not probe.is_file() or backup.exists() or (backend / '.env').exists():
        raise ValueError('Probe/installation state changed; preserve files and review before retrying.')
    return backend, frontend, data, probe, backup


def prepare(root, home, domain):
    backend, frontend, data, probe, backup = inspect_layout(root, home, domain)
    values = {'MEETFLOW_APP_ENV': 'production', 'MEETFLOW_PUBLIC_ORIGIN': 'https://' + domain,
              'MEETFLOW_DATA_DIR': str(data), 'MEETFLOW_FRONTEND_DIR': str(frontend),
              'MEETFLOW_TRUSTED_PROXIES': '[]'}
    # The new installation has no SMTP credentials and no demo accounts.
    with (backend / '.env').open('x', encoding='utf-8') as file:
        for name, value in values.items():
            file.write(name + '=' + json.dumps(value) + '\n')
    os.chmod(backend / '.env', 0o600)
    return backend, probe, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    home = Path.home()
    python = home / 'meetflow-probe' / 'venv' / 'bin' / 'python'
    if os.name != 'posix' or not python.is_file():
        parser.error('Run this inside the PythonAnywhere Bash console after extracting the archive.')
    try:
        inspect_layout(root, home, args.domain)
    except ValueError as error:
        parser.error(str(error))
    # Install before modifying any running application file.
    subprocess.run([str(python), '-m', 'pip', 'install', '--no-cache-dir', '--require-hashes',
                    '-r', str(root / 'backend' / 'requirements.txt')], check=True)
    try:
        backend, probe, backup = prepare(root, home, args.domain)
    except ValueError as error:
        parser.error(str(error))
    env = {k: v for k, v in os.environ.items() if not k.startswith('MEETFLOW_')}
    subprocess.run([str(python), '-m', 'app.db.migrate'], cwd=backend, env=env, check=True)
    subprocess.run([str(python), '-c', 'from app.common.config import load_settings; '
                    'from app.main import validate_runtime; validate_runtime(load_settings())'],
                   cwd=backend, env=env, check=True)
    with backup.open('xb') as file:
        file.write(probe.read_bytes())
    wrapper = ('import sys\n' + f'sys.path.insert(0, {str(backend)!r})\n'
               'from app.hosting import create_socket_app\napp = create_socket_app()\n')
    probe.write_text(wrapper, encoding='utf-8')
    print('MeetFlow prepared. Original probe preserved; no local/demo database was uploaded.')
    print('Reload with: pa website reload --domain ' + args.domain)


if __name__ == '__main__':
    main()
