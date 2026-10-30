"""Allowlisted deployment archive: backend source and built frontend, no user data."""
import argparse
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def build(output, root=ROOT):
    backend, frontend = root / 'Src/backend', root / 'Src/frontend/dist'
    if not (frontend / 'index.html').is_file():
        raise ValueError('Build the frontend before packaging.')
    files = {}
    for folder in ['app', 'migrations']:
        for source in (backend / folder).rglob('*.py'):
            if '__pycache__' not in source.parts:
                files['backend/' + source.relative_to(backend).as_posix()] = source
    files['backend/requirements.txt'] = backend / 'requirements.txt'
    for source in frontend.rglob('*'):
        if source.is_file() and (source.name == 'index.html' and source.parent == frontend or
                source.is_relative_to(frontend / 'assets') and source.suffix in
                {'.js', '.css', '.svg', '.png', '.jpg', '.webp', '.woff2', '.ico'}):
            files['frontend/dist/' + source.relative_to(frontend).as_posix()] = source
    files['install.py'] = root / 'Deploy/pythonanywhere/install.py'
    files['DEPLOY.md'] = root / 'Deploy/pythonanywhere/README.md'
    if any(source.is_symlink() or not source.resolve().is_relative_to(root.resolve()) for source in files.values()):
        raise ValueError('Release source must be a regular file inside the workspace.')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, source in sorted(files.items()):
            bundle.write(source, 'meetflow-release/' + name)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(f'Packaged {build(args.output)} allowlisted files.')
