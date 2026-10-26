"""Bounded read-only diagnosis for the stopped administrator backup."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from urllib.parse import unquote, urlsplit

CANDIDATE = '86c9cfd610f07c5ed3d0881339014f9ed1aec090'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT/'exploration-runs/40330276649-1-activate'
EXPECTED = {'activate.py': 'dcd2fe1814a9886f8779f84aeb0a12ea0313211008960a93dfa9ccdf45d28630', 'prepare.py': '59c8711a0dd4878f245b2c4c93fa6cfdd863e353d7c4ab9cea92977b0c1924f0', 'canary_schema_upgrade.py': 'd9ced5e93f9c918fa2316d72938d5e009c7544af713b88cff1dd8238d0092a5f', 'wp31_database_snapshot.py': 'be1dfff189275eaf4ce18c415b39a947afd6ba775a31e2a400a42a2409ca6ff8', 'db_facts.py': '3230684bda017ca99fc50bbfdc1618cbd935df82dce4e0dd46fc900c57bc8dd7', 'db_facts_control.py': '3230684bda017ca99fc50bbfdc1618cbd935df82dce4e0dd46fc900c57bc8dd7', 'grant_runtime.py': 'cc4d07c52160746711159e81ad6871c5a53034bb0c29ed04e1f43c043339de92', 'facts_guard.py': '2eae1ece722ef6d70e011270b3e8b300a269d75aedc0d813213647d759c87f3e'}  # Filled from the exact released Git commit; never from remote files.


def error_category(raw):
    value = raw.decode('utf-8', errors='replace').lower()
    for token, category in (
        ('no space left on device','DISK_FULL'), ('permission denied','PERMISSION_DENIED'),
        ('password authentication failed','DATABASE_AUTHENTICATION'),
        ('certificate verify failed','TLS_VERIFICATION'), ('could not translate host name','DNS'),
        ('connection refused','CONNECTION_REFUSED'), ('connection timed out','CONNECTION_TIMEOUT'),
        ('server version mismatch','POSTGRES_VERSION_MISMATCH'),
        ('syntax error','SQL_SYNTAX'), ('does not exist','MISSING_OBJECT'),
        ('wp31_database_snapshot_import=fail','SNAPSHOT_IMPORT'),
        ('validationerror','CONFIGURATION_VALIDATION'), ('modulenotfounderror','MISSING_MODULE'),
    ):
        if token in value:
            return category
    return 'UNCLASSIFIED_COMMAND_FAILURE'


def probe(name, args, *, env=None, timeout=180):
    try:
        result=subprocess.run(args, env=env, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(json.dumps({'probe':name,'status':'FAIL','category':'TIMEOUT'}), flush=True)
        return None
    report={'probe':name,'status':'PASS' if result.returncode == 0 else 'FAIL'}
    if result.returncode:
        report.update(category=error_category(result.stderr), exit_code=result.returncode)
    print(json.dumps(report), flush=True)
    return result.stdout if result.returncode == 0 else None


def verify_sources():
    assert EXPECTED and SOURCE.resolve() == SOURCE
    for name, digest in EXPECTED.items():
        path=SOURCE/name
        assert path.is_file() and not path.is_symlink() and path.resolve() == path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'SOURCE_HASH_CHANGED'


def main():
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert socket.gethostname() == 'journey-next-staging' and ROOT.resolve() == ROOT
    verify_sources()
    sys.path.insert(0,str(SOURCE))
    from canary_schema_upgrade import DATABASE
    spec=importlib.util.spec_from_file_location('original_admin_activation', SOURCE/'activate.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original=json.loads(module.read_file(SOURCE/'manifest.json'))
    assert original['candidate'] == CANDIDATE and original['package_run_id'] == '40328731784'
    app=module.Activation(json.loads(json.dumps(original)),SOURCE)
    assert not (app.new/'activation-receipt.json').exists(), 'ALREADY_ACTIVATED'
    state=json.loads(module.read_file(app.new/'schema-upgrade-prepared.json'))
    normalized=json.loads(json.dumps(state['manifest']))
    assert normalized['old_images'] == app.old_images
    normalized['old_images']={}
    for service in ('api','web'):
        assert re.fullmatch('sha256:[0-9a-f]{64}',normalized['images'][service])
        normalized['images'][service]=original['images'][service]
    assert normalized == original, 'PREPARED_PACKAGE_CHANGED'
    app.manifest=state['manifest']
    app.verify_base()
    app.verify_prepared()
    print(json.dumps({'preconditions':'PASS','production_switched':False,
                      'disk_free_bytes':shutil.disk_usage(ROOT).free}), flush=True)
    assert app.backup.resolve() == app.backup and app.backup.is_dir()
    allowed={'before.json','restored.json','canary.dump','canary.dump.enc','verify.dump',
             'restore.env','migration-rehearsal.json','backup-receipt.json','snapshot-exchange'}
    entries=[]
    for path in app.backup.iterdir():
        assert path.name in allowed and not path.is_symlink(), 'UNEXPECTED_BACKUP_ENTRY'
        info=path.stat()
        entries.append({'name':path.name,'size':info.st_size,'mode':oct(info.st_mode & 0o777),
                        'uid':info.st_uid,'gid':info.st_gid,'directory':path.is_dir()})
    print(json.dumps({'backup_inventory':entries}), flush=True)
    files=[]
    for name in ('db_facts_control.py','wp31_database_snapshot.py'):
        info=(SOURCE/name).stat()
        files.append({'name':name,'mode':oct(info.st_mode & 0o777),'uid':info.st_uid,'gid':info.st_gid})
    print(json.dumps({'probe_file_modes':files}), flush=True)
    prefix=['docker','run','--rm','--network','host','--env-file',str(app.new/'secrets/migration.env'),
            '-e','PGOPTIONS=-c default_transaction_read_only=on','-e','REQUIRE_READ_ONLY=true',
            '-v',str(app.new/'secrets/volcengine-rds-ca.pem')+':/run/secrets/volcengine-rds-ca.pem:ro']
    probe('DATABASE_READ',prefix+[app.images['api'],'python','-c',
          "from sqlalchemy import text; from journey_api.db import engine; c=engine.connect(); assert c.execute(text('SHOW transaction_read_only')).scalar_one() == 'on'; assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0047_learner_notification_reads'"])
    probe('DATABASE_FACTS',prefix+['-v',str(SOURCE/'db_facts_control.py')+':/tmp/db_facts.py:ro',
          app.images['api'],'python','/tmp/db_facts.py'],timeout=600)
    probe('SNAPSHOT_EXPORT_IMPORT',prefix+['-v',str(SOURCE/'wp31_database_snapshot.py')+':/tmp/wp31_database_snapshot.py:ro',
          app.images['api'],'python','-c',
          "import sys; sys.path.insert(0,'/tmp'); from wp31_database_snapshot import export_snapshot,import_snapshot; from journey_api.db import engine; a=engine.connect(); b=engine.connect(); snap=export_snapshot(a); import_snapshot(b,snap); b.rollback(); a.rollback(); b.close(); a.close()"])
    migration=module.env_values(module.read_file(app.new/'secrets/migration.env'))
    parsed=urlsplit(migration['DATABASE_URL'])
    env=os.environ.copy()
    env.update(PGPASSWORD=unquote(parsed.password or ''),PGSSLMODE='verify-full',
               PGSSLROOTCERT='/run/secrets/volcengine-rds-ca.pem',PGOPTIONS='-c default_transaction_read_only=on')
    pg=['docker','run','--rm','--network','host','-e','PGPASSWORD','-e','PGSSLMODE','-e','PGSSLROOTCERT','-e','PGOPTIONS',
        '-v',str(app.new/'secrets/volcengine-rds-ca.pem')+':/run/secrets/volcengine-rds-ca.pem:ro',
        app.images['dbrestore'],'pg_dump','-h',parsed.hostname,'-p',str(parsed.port or 5432),
        '-U',unquote(parsed.username or ''),'-d',DATABASE,
        '--format=custom','--no-owner','--no-acl','--file=/dev/null']
    probe('READ_ONLY_DUMP_TO_NULL',pg,env=env,timeout=600)
    app.verify_base()
    print(json.dumps({'diagnosis_complete':True,'business_writes':0,'services_switched':False}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'diagnosis':'STOP','error_type':type(exc).__name__}), flush=True)
        raise SystemExit(1)
