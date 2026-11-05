"""Create a Windows Python 3.11 environment from bundled, hash-checked wheels."""
import os
from pathlib import Path
import subprocess
import sys
import venv


def install(root, *, run=subprocess.run, create=None):
    root = Path(root).resolve()
    backend = root / 'Src/backend'
    environment = backend / '.venv'
    python = environment / 'Scripts/python.exe'
    requirements = backend / 'requirements.txt'
    wheels = root / 'wheelhouse'
    if not requirements.is_file() or not list(wheels.glob('*.whl')):
        raise ValueError('Incomplete package: extract the entire ZIP before installation.')
    if environment.exists():
        if environment.is_symlink() or not python.is_file() or not (environment / 'pyvenv.cfg').is_file():
            raise ValueError('Unrecognized environment; no files were replaced.')
    else:
        (create or (lambda target: venv.EnvBuilder(with_pip=True).create(target)))(environment)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    run([str(python), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheels),
         '--require-hashes', '-r', str(requirements)], cwd=backend, env=env, check=True)
    run([str(python), '-m', 'pip', 'check'], cwd=backend, env=env, check=True)
    print('Ready. Run the start-demo CMD file and keep its window open.')


if __name__ == '__main__':
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 11) or sys.maxsize <= 2**32:
        sys.exit('Use Windows and 64-bit Python 3.11. Node.js is not required.')
    try:
        install(Path(__file__).resolve().parent)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Installation did not complete: {error}', file=sys.stderr)
        sys.exit(1)
