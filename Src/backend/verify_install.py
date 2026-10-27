"""T34 fresh runtime installation from locked wheels, migration, demo and HTTP startup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    wheels=args.wheelhouse.resolve()
    if not wheels.is_dir():parser.error('A local wheelhouse for the locked runtime requirements is required.')
    report={'started_at':datetime.now(timezone.utc).isoformat(),'method':'fresh virtual environment; local wheels; --require-hashes; pip check; new demo database; real HTTP startup',
        'requirements_sha256':hashlib.sha256((HERE/'requirements.txt').read_bytes()).hexdigest(),'python':sys.version.split()[0],
        'wheel_count':len(list(wheels.glob('*.whl'))),'network_used':False,'developer_database_modified':False}
    with tempfile.TemporaryDirectory(prefix='meetflow-install-') as directory:
        root=Path(directory).resolve();environment=root/'venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        commands=[[str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--find-links',str(wheels),'--require-hashes','-r',str(HERE/'requirements.txt')],
                  [str(python),'-m','pip','check']]
        for command in commands:
            result=subprocess.run(command,cwd=HERE,capture_output=True,text=True,timeout=120)
            if result.returncode:raise RuntimeError('Fresh installation check failed: '+result.stderr[-2000:]+result.stdout[-2000:])
        script="""
from pathlib import Path
import json,socket,sys
from contextlib import closing
import sqlite3
from urllib.request import urlopen
from app.common.config import Settings
from app.demo import seed
from app.db.connection import database_path
from verify_delivery import running
with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
settings=Settings(_env_file=None,app_env='test',data_dir=Path(sys.argv[1])/'data',port=port)
data=seed(settings)
with running(settings):
 with urlopen(f'http://127.0.0.1:{port}/api/v1/health') as response:assert response.status==200
with closing(sqlite3.connect(database_path(settings))) as connection:
 assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]==4
 assert connection.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==2
 assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
print(json.dumps({'fresh_runtime':True,'migration':True,'demo_four_accounts':True,'http_health':True}))
"""
        result=subprocess.run([str(python),'-c',script,str(root)],cwd=HERE,capture_output=True,text=True,timeout=90)
        if result.returncode:raise RuntimeError('Fresh runtime startup failed: '+result.stderr[-2000:])
        report['checks']=json.loads(result.stdout)
        report['result']='passed'
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS fresh runtime installation, strict hashes, pip check, migration, demo and HTTP health.')


if __name__=='__main__':main()
