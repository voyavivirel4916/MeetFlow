"""T33 isolated HTTP performance, process restart and stopped-database restore checks."""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
from http.cookiejar import CookieJar
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from time import perf_counter, sleep, time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPCookieProcessor, Request

from app.common.config import Settings
from app.db.connection import database_path
from app.demo import seed, PASSWORD

ROOT=Path(__file__).resolve().parents[2]


def snapshot(path):
    with closing(sqlite3.connect(path)) as connection:
        names=[row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name:connection.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall() for name in names}


@contextmanager
def running(settings):
    env={key:value for key,value in os.environ.items() if not key.startswith('MEETFLOW_')}
    env.update(MEETFLOW_APP_ENV='test',MEETFLOW_DATA_DIR=str(settings.data_dir),MEETFLOW_PORT=str(settings.port),MEETFLOW_FRONTEND_DIR=str(settings.frontend_dir))
    # This is our own captured process tree; never stop the developer service.
    process=subprocess.Popen([sys.executable,'-m','app'],cwd=Path(__file__).parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Isolated server exited before readiness.')
            try:
                with build_opener().open(f'http://127.0.0.1:{settings.port}/api/v1/health',timeout=.3) as reply:
                    if reply.status==200:break
            except (URLError,TimeoutError):sleep(.1)
        else:raise RuntimeError('Isolated server readiness timeout.')
        yield
    finally:
        if process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=False)
            else:process.terminate()
        process.wait(timeout=10)


def verify():
    report={'started_at':datetime.now(timezone.utc).isoformat(),'environment':{'os':platform.platform(),'processor':platform.processor(),
        'logical_cpus':os.cpu_count(),'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
        'packages':{name:importlib.metadata.version(name) for name in ['fastapi','uvicorn','SQLAlchemy','pydantic']}},
        'dataset':{'members':20,'slots':15,'tasks':200},'method':'local HTTP sequential requests; 5 warmups then 30 samples; nearest-rank P95 = sorted sample 29',
        'isolation':'new temporary database and unused local port; developer database untouched'}
    report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='meetflow-delivery-') as directory:
        base=Path(directory)
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        settings=Settings(_env_file=None,app_env='test',data_dir=base/'data',port=port)
        dataset=seed(settings,member_count=20,slot_count=15,task_count=200)
        opener=build_opener(HTTPCookieProcessor(CookieJar()))
        def request(path,body=None):
            raw=None if body is None else json.dumps(body).encode()
            with opener.open(Request(f'http://127.0.0.1:{port}'+path,data=raw,headers={'Content-Type':'application/json'}),timeout=10) as response:
                assert response.status==200
                return json.loads(response.read())['data']
        endpoints={'recommendations':f"/api/v1/polls/{dataset['confirmed_poll_id']}/recommendations",'task_list':f"/api/v1/groups/{dataset['group_id']}/tasks?page=1&page_size=20"}
        with running(settings):
            request('/api/v1/auth/login',{'username':'demo_owner','password':PASSWORD})
            report['measurements']={}
            for name,path in endpoints.items():
                for _ in range(5):request(path)
                samples=[]
                for _ in range(30):
                    start=perf_counter();value=request(path);samples.append(round((perf_counter()-start)*1000,4))
                    assert len(value['items'])==(15 if name=='recommendations' else 20)
                p95=sorted(samples)[28]
                report['measurements'][name]={'milliseconds':samples,'p95_ms':p95,'max_ms':max(samples),'http_errors':0,'target_ms':1000,'passed':p95<=1000}
            expected={path:request(path) for path in [*endpoints.values(),f"/api/v1/meetings/{dataset['meeting_id']}",f"/api/v1/polls/{dataset['confirmed_poll_id']}/matrix"]}
        original=snapshot(database_path(settings))
        with running(settings):
            assert all(request(path)==value for path,value in expected.items())
        assert snapshot(database_path(settings))==original
        report['restart']={'new_process':True,'all_table_rows_equal':True,'authenticated_reads_equal':True}
        backup=base/'backup.sqlite3';shutil.copy2(database_path(settings),backup)
        with closing(sqlite3.connect(database_path(settings))) as connection:
            connection.execute("UPDATE meetings SET minutes='simulated temporary data fault'");connection.commit()
        assert snapshot(database_path(settings))!=original
        shutil.copy2(database_path(settings),base/'preserved-fault.sqlite3')
        shutil.copy2(backup,database_path(settings))
        assert snapshot(database_path(settings))==original
        with closing(sqlite3.connect(database_path(settings))) as connection:
            assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
            connection.execute('UPDATE sessions SET revoked_at=? WHERE revoked_at IS NULL',(int(time()*1000),))
            connection.commit()
        with running(settings):
            try:request('/api/v1/users/me')
            except HTTPError as error:assert error.code==401
            else:raise AssertionError('Restored sessions should have been revoked.')
            request('/api/v1/auth/login',{'username':'demo_owner','password':PASSWORD})
            assert all(request(path)==value for path,value in expected.items())
        report['restore']={'stopped_copy':True,'fault_copy_preserved':True,'all_table_rows_equal_before_session_revocation':True,
            'foreign_keys_valid':True,'old_session_rejected':True,'reauthenticated_reads_equal':True,
            'row_counts':{name:len(rows) for name,rows in original.items()}}
        report['result']='passed' if all(row['passed'] for row in report['measurements'].values()) else 'failed performance target'
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=verify();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'result':report['result'],'p95_ms':{name:row['p95_ms'] for name,row in report['measurements'].items()},'restart':True,'restore':True}))
    return 0 if report['result']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
