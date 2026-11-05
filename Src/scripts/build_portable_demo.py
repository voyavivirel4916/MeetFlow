"""Package only application code, built UI and runtime wheels; never user data."""
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sources(root=ROOT):
    root = Path(root).resolve()
    backend = root / 'Src/backend'
    files = {}
    for directory in ('app', 'migrations'):
        for source in (backend / directory).rglob('*.py'):
            if '__pycache__' not in source.parts:
                files[source.relative_to(root).as_posix()] = source
    for name in ('Src/backend/requirements.txt', 'Src/scripts/run_showcase.py',
                 'Deploy/local-showcase.json', '启动演示.cmd'):
        files[name] = root / name
    frontend = root / 'Src/frontend/dist'
    for source in frontend.rglob('*'):
        if source.is_file() and (source == frontend / 'index.html' or
                source.is_relative_to(frontend / 'assets') and source.suffix in
                {'.js', '.css', '.svg', '.png', '.jpg', '.webp', '.woff2', '.ico'}):
            files[source.relative_to(root).as_posix()] = source
    required = {name.lower().replace('-', '_') for name in re.findall(
        r'^([A-Za-z0-9_-]+)==', (backend / 'requirements.txt').read_text(encoding='utf-8'), re.M)}
    included = set()
    for wheel in (backend / '.venv/wheelhouse-t09').glob('*.whl'):
        name = wheel.name.split('-')[0].lower().replace('-', '_')
        if name in required:
            files['wheelhouse/' + wheel.name] = wheel
            included.add(name)
    if included != required:
        raise ValueError('Runtime wheels missing: ' + ', '.join(sorted(required - included)))
    for name in ('install_demo.py', '首次安装.cmd', '另一台电脑演示说明.md'):
        files[name] = root / 'Deploy/portable' / name
    if not (frontend / 'index.html').is_file():
        raise ValueError('Build the frontend first.')
    for source in files.values():
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
            raise ValueError('Package input must be a regular workspace file.')
    return files


def build(output, root=ROOT):
    files = sources(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, source in sorted(files.items()):
            bundle.write(source, 'MeetFlow-demo/' + name)
    return len(files)


if __name__ == '__main__':
    print(f'Packaged {build(ROOT / "Site/downloads/MeetFlow-Windows-Demo.zip")} safe files.')
