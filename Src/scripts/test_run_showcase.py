from datetime import date, datetime, timedelta
import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from run_showcase import BEIJING, default_presentation_date, demo_environment, prepare_demo


class ShowcaseLauncherTests(unittest.TestCase):
    def fixture(self, root):
        for name in ['Src/backend/.venv/Scripts/python.exe', 'Src/frontend/dist/index.html']:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('fixture')

    def test_environment_is_local_and_does_not_inherit_production_or_mail(self):
        with patch.dict(os.environ, {'MEETFLOW_APP_ENV':'production','MEETFLOW_SMTP_PASSWORD':'secret'}):
            env=demo_environment(Path('root'),Path('demo'),8002)
        self.assertEqual(env['MEETFLOW_APP_ENV'],'local')
        self.assertEqual(env['MEETFLOW_BIND_HOST'],'127.0.0.1')
        self.assertEqual(env['MEETFLOW_SMTP_PASSWORD'],'')
        self.assertEqual(env['MEETFLOW_PUBLIC_ORIGIN'],'')

    def test_first_creation_then_reuse_keeps_changes_and_normal_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root)
            normal=root/'Src/backend/data/meetflow.sqlite3';normal.parent.mkdir();normal.write_bytes(b'normal')
            day=datetime.now(BEIJING).date()+timedelta(days=2)
            calls=[]
            def seed(command, **kwargs):
                calls.append(command)
                self.assertNotIn('MEETFLOW_DATA_DIR',kwargs['env'])
                target=Path(command[command.index('--data-dir')+1]);target.mkdir()
                (target/'meetflow.sqlite3').write_bytes(b'demo')
            _,_,env=prepare_demo(root,day,8002,run=seed)
            database=Path(env['MEETFLOW_DATA_DIR'])/'meetflow.sqlite3';database.write_bytes(b'edited')
            prepare_demo(root,day,8002,run=seed)
            self.assertEqual(len(calls),1)
            self.assertIn('--presentation-date',calls[0])
            self.assertEqual(database.read_bytes(),b'edited')
            self.assertEqual(normal.read_bytes(),b'normal')

    def test_unrecognized_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);day=datetime.now(BEIJING).date()
            target=root/'Src/backend/data'/f'showcase-for-{day.isoformat()}'
            target.mkdir(parents=True);(target/'keep.txt').write_text('keep')
            with self.assertRaises(ValueError):prepare_demo(root,day,8002)
            self.assertEqual((target/'keep.txt').read_text(),'keep')

    def test_failed_seed_does_not_claim_recognized_demo(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);day=datetime.now(BEIJING).date()
            def failure(*args, **kwargs):raise subprocess.CalledProcessError(2,args[0])
            with self.assertRaises(subprocess.CalledProcessError):prepare_demo(root,day,8002,run=failure)
            self.assertFalse((root/'Src/backend/data'/f'showcase-for-{day.isoformat()}'/'showcase.json').exists())

    def test_default_reuses_the_same_presentation_across_days_and_ignores_expired_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for day in ['2026-10-28','2026-11-02','2026-11-04']:
                marker=root/'Src/backend/data'/f'showcase-for-{day}'/'showcase.json'
                marker.parent.mkdir(parents=True)
                marker.write_text(json.dumps({'format':1,'presentation_date':day}),encoding='utf-8')
            for today in [date(2026,10,31),date(2026,11,1),date(2026,11,2)]:
                self.assertEqual(default_presentation_date(root,today),date(2026,11,2))
            self.assertEqual(default_presentation_date(root,date(2026,11,5)),date(2026,11,7))
