"""Check deployment locks without importing third-party runtime dependencies."""
from pathlib import Path
import re
import unittest

BACKEND = Path(__file__).resolve().parents[1] / 'backend'


def packages(name):
    text = (BACKEND / name).read_text(encoding='utf-8-sig')
    return dict(re.findall(r'^([a-zA-Z0-9_.-]+)==([^\s\\]+)', text, re.M))


class BackendDependencyTests(unittest.TestCase):
    def test_runtime_and_development_share_the_same_locked_versions(self):
        runtime = packages('requirements.txt')
        development = packages('requirements-dev.txt')
        self.assertTrue(runtime)
        self.assertLessEqual(runtime.items(), development.items())
        self.assertIn('-c requirements.txt', (BACKEND / 'requirements-dev.in').read_text())

    def test_every_locked_package_has_integrity_hashes(self):
        for name in ('requirements.txt', 'requirements-dev.txt'):
            text = (BACKEND / name).read_text(encoding='utf-8-sig')
            blocks = re.split(r'(?=^[a-zA-Z0-9_.-]+==)', text, flags=re.M)[1:]
            self.assertEqual(len(blocks), len(packages(name)))
            for block in blocks:
                self.assertRegex(block, r'--hash=sha256:[0-9a-f]{64}')


if __name__ == '__main__':
    unittest.main()
