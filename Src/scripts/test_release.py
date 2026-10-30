import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_release import ROOT, build

spec=importlib.util.spec_from_file_location('pa_installer',ROOT/'Deploy/pythonanywhere/install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class ReleaseTests(unittest.TestCase):
    def test_bundle_allowlist_excludes_secrets_data_and_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            fixtures=['Src/backend/app/main.py','Src/backend/migrations/env.py','Src/backend/requirements.txt',
                'Src/frontend/dist/index.html','Src/frontend/dist/assets/app.js','Deploy/pythonanywhere/install.py',
                'Deploy/pythonanywhere/README.md','Src/backend/.env','Src/backend/data/private.sqlite3',
                'Src/backend/.venv/private.py','Src/frontend/dist/.env','Src/frontend/dist/assets/private.sqlite3']
            for name in fixtures:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            output=root/'release.zip';build(output,root)
            with zipfile.ZipFile(output) as bundle:
                names=bundle.namelist()
                self.assertEqual(len(names),7)
                self.assertFalse(any('.env' in name or '.sqlite3' in name or '.venv' in name for name in names))
            before=output.read_bytes()
            with self.assertRaises(FileExistsError):build(output,root)
            self.assertEqual(output.read_bytes(),before)

    def test_installer_prepares_distinct_production_config_and_refuses_existing_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary);root=home/'meetflow-release'
            for name in ['frontend/dist/index.html','backend/app/hosting.py']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            probe=home/'meetflow-probe/probe.py';probe.parent.mkdir();probe.write_text('original')
            backend,actual,backup=installer.prepare(root,home,'mrrrxxxi.pythonanywhere.com')
            self.assertEqual(actual,probe)
            self.assertEqual(probe.read_text(),'original')
            config=(backend/'.env').read_text()
            self.assertIn('production',config)
            self.assertIn('meetflow-data',config)
            self.assertNotIn('SMTP_PASSWORD',config)
            with self.assertRaises(ValueError):installer.prepare(root,home,'mrrrxxxi.pythonanywhere.com')
            with self.assertRaises(ValueError):installer.inspect_layout(root,home,'https://evil.example/path')
