"""Public page resource checks and portable-package safety contracts."""
import importlib.util
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('a', 'link', 'script', 'img'):
            target = attrs.get('href') or attrs.get('src')
            if target:
                self.links.append(target)


class SiteChecks(unittest.TestCase):
    def test_public_release_record_matches_download(self):
        record = json.loads((ROOT / 'Docs/evidence/project-site-release-20261105.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(record['http_status'], 200)
        self.assertEqual(record['download_status'], 200)
        self.assertTrue(record['download_matches_local'])
        self.assertFalse(record['public_application'])
        digest = hashlib.sha256((ROOT / 'Site/downloads/MeetFlow-Windows-Demo.zip').read_bytes()).hexdigest()
        self.assertEqual(digest.lower(), record['download_sha256'].lower())

    def test_all_local_resources_exist_and_no_local_demo_link(self):
        html = (ROOT / 'Site/index.html').read_text(encoding='utf-8')
        parser = Resources()
        parser.feed(html)
        for target in parser.links:
            if not target.startswith(('http:', 'https:', '#')):
                self.assertTrue((ROOT / 'Site' / target).is_file(), target)
        self.assertFalse(any('localhost' in link or '127.0.0.1' in link for link in parser.links))
        for claim in ['虚构演示', '不含你的真实数据库', 'Python 3.11', '不会', '未公布真人试用成效']:
            self.assertIn(claim, html)

    def test_package_contains_no_credentials_or_user_data(self):
        with zipfile.ZipFile(ROOT / 'Site/downloads/MeetFlow-Windows-Demo.zip') as bundle:
            names = bundle.namelist()
        for name in names:
            self.assertTrue(name.startswith('MeetFlow-demo/'))
            self.assertNotIn('..', Path(name).parts)
            for forbidden in ('/.git/', '/data/', '/node_modules/', '/__pycache__/', '/.venv/'):
                self.assertNotIn(forbidden, name)
            self.assertFalse(Path(name).name.startswith('.env'))
            self.assertNotIn(Path(name).suffix, ('.sqlite3', '.db', '.log'))
        for required in ('启动演示.cmd', '首次安装.cmd', 'install_demo.py',
                         '另一台电脑演示说明.md', 'Src/frontend/dist/index.html',
                         'Src/scripts/run_showcase.py', 'Deploy/local-showcase.json'):
            self.assertIn('MeetFlow-demo/' + required, names)
        self.assertTrue(any('/wheelhouse/' in name for name in names))

    def test_deployment_only_uploads_site(self):
        workflow = (ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8')
        self.assertIn('path: Site', workflow)
        self.assertIn('pages: write', workflow)
        self.assertNotIn('path: .\n', workflow)


class InstallerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('portable_installer', ROOT / 'Deploy/portable/install_demo.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def fixture(self, folder):
        root = Path(folder)
        (root / 'Src/backend').mkdir(parents=True)
        (root / 'Src/backend/requirements.txt').write_text('example==1')
        (root / 'wheelhouse').mkdir()
        (root / 'wheelhouse/example.whl').write_bytes(b'fixture')
        return root

    def test_install_uses_offline_hashes_and_new_venv(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            calls, creates = [], []
            self.module.install(root, run=lambda *a, **k: calls.append((a, k)), create=lambda p: creates.append(p))
            self.assertEqual(creates, [root / 'Src/backend/.venv'])
            command = calls[0][0][0]
            self.assertIn('--no-index', command)
            self.assertIn('--require-hashes', command)
            self.assertEqual(calls[1][0][0][-2:], ['pip', 'check'])

    def test_partial_environment_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.fixture(folder)
            environment = root / 'Src/backend/.venv'
            environment.mkdir()
            marker = environment / 'keep.txt'
            marker.write_text('keep')
            with self.assertRaises(ValueError):
                self.module.install(root)
            self.assertEqual(marker.read_text(), 'keep')

    def test_incomplete_package_does_not_create_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.module.install(Path(folder))
            self.assertFalse((Path(folder) / 'Src/backend/.venv').exists())


if __name__ == '__main__':
    unittest.main()
