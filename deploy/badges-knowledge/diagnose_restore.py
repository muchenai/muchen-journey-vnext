"""Diagnose one stopped release without changing production services or data."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time

CANDIDATE = '2bab0cefe55447c9d64af81dd5c52f5db67db09c'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/41592358400-1-activate'
EXPECTED = {"activate.py":"f080d6365e614793b57660362a4ce24aa5d2058f36d9a3101508cc32ca44523a","prepare.py":"59c8711a0dd4878f245b2c4c93fa6cfdd863e353d7c4ab9cea92977b0c1924f0","canary_schema_upgrade.py":"d9ced5e93f9c918fa2316d72938d5e009c7544af713b88cff1dd8238d0092a5f","wp31_database_snapshot.py":"be1dfff189275eaf4ce18c415b39a947afd6ba775a31e2a400a42a2409ca6ff8","db_facts.py":"3230684bda017ca99fc50bbfdc1618cbd935df82dce4e0dd46fc900c57bc8dd7","db_facts_control.py":"3230684bda017ca99fc50bbfdc1618cbd935df82dce4e0dd46fc900c57bc8dd7","grant_runtime.py":"47328593f43eda5b70ed26dc5e63580176ba76c772c8135ee73020183f6e5eb4","facts_guard.py":"8b39b57abd0fbc291b696ea0a0c12c9137f0297fc8704033ccee8c03b73d559c","restore_backup.py":"f03c9c3933f862aa10b74aafe45c9b9306757e42515c1c54a24780f5dc0e0d33","diagnose_backup.py":"eaecdca5bab87facb68e5f11610208fb4f1298d5619b878e0df85c1375128416"}


def report(**values):
    print(json.dumps(values), flush=True)


def classify(raw):
    value = raw.decode(errors='replace').lower()
    categories = [('no space left on device','DISK_FULL'), ('permission denied','PERMISSION_DENIED'),
        ('password authentication failed','AUTHENTICATION'), ('is not running','CONTAINER_EXITED'),
        ('connection refused','CONNECTION_REFUSED'), ('does not exist','MISSING_OBJECT'),
        ('invalid locale','LOCALE'), ('incompatible with server','POSTGRES_VERSION'),
        ('directory exists but is not empty','PGDATA_NOT_EMPTY'), ('out of memory','OUT_OF_MEMORY')]
    return next((label for token,label in categories if token in value), 'UNCLASSIFIED')


def command(args, timeout=30):
    return subprocess.run(args, capture_output=True, timeout=timeout)


def load_release():
    assert ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
    for name, expected in EXPECTED.items():
        path = SOURCE / name
        assert path.is_file() and not path.is_symlink() and path.resolve() == path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'SOURCE_CHANGED'
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('badge_knowledge_activation', SOURCE / 'activate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = json.loads(module.read_file(SOURCE / 'manifest.json'))
    assert original['candidate'] == CANDIDATE and original['package_run_id'] == '41590266968'
    assert original['migrations'] == {'from':'0051_community_modules','to':'0052_knowledge_publication'}
    app = module.Activation(json.loads(json.dumps(original)), SOURCE)
    assert not (app.new / 'activation-receipt.json').exists(), 'ALREADY_ACTIVATED'
    state = json.loads(module.read_file(app.new / 'schema-upgrade-prepared.json'))
    normalized = json.loads(json.dumps(state['manifest']))
    assert normalized['old_images'] == app.old_images
    normalized['old_images'] = {}
    for name in ('api','web'):
        assert re.fullmatch('sha256:[0-9a-f]{64}', normalized['images'][name])
        normalized['images'][name] = original['images'][name]
    assert normalized == original, 'PREPARED_PACKAGE_CHANGED'
    app.manifest = state['manifest']
    app.verify_base()
    app.verify_prepared()
    assert app.backup.is_dir() and not app.backup.is_symlink() and app.backup.resolve() == app.backup
    entries = list(app.backup.iterdir())
    assert {p.name for p in entries} == {'before.json'}, 'PAST_STOP_BOUNDARY'
    assert all(p.is_file() and not p.is_symlink() for p in entries)
    assert json.loads(module.read_file(app.backup / 'before.json'))['migration'] == module.SOURCE_SCHEMA
    return module, app


def scratch_probe(image):
    name = 'journey-restore-probe-' + CANDIDATE[:12] + '-' + secrets.token_hex(4)
    password = secrets.token_hex(32)
    created = None
    try:
        result = command(['docker','run','-d','--name',name,'--network','none',
            '--label','journey.operation=restore-probe','-e','POSTGRES_PASSWORD='+password,
            '-e','POSTGRES_DB=restore',image], timeout=120)
        assert result.returncode == 0, 'SCRATCH_CREATE_FAILED'
        created = result.stdout.decode().strip()
        assert re.fullmatch('[0-9a-f]{64}', created)
        deadline = time.monotonic() + 120
        last = b''
        ready = False
        while time.monotonic() < deadline:
            probe = command(['docker','exec','-e','PGPASSWORD='+password,name,'psql',
                '-h','127.0.0.1','-U','postgres','-d','restore','-Atqc','SELECT 1'], timeout=10)
            if probe.returncode == 0 and probe.stdout.strip() == b'1':
                ready = True
                break
            last = probe.stderr
            state = json.loads(command(['docker','inspect',name]).stdout)[0]['State']
            if not state['Running']:
                break
            time.sleep(1)
        row = json.loads(command(['docker','inspect',name]).stdout)[0]
        logs = command(['docker','logs','--tail','60',name])
        raw = logs.stdout + logs.stderr
        report(scratch_ready=ready, running=row['State']['Running'],
            exit_code=row['State']['ExitCode'], oom_killed=row['State']['OOMKilled'],
            connection_category=classify(last), log_category=classify(raw),
            log_flags={token:token in raw.decode(errors='replace').lower() for token in [
                'database system is ready','fatal','initdb','error','could not create','could not open','lock file']})
        return ready
    finally:
        if created:
            row = json.loads(command(['docker','inspect',name]).stdout)[0]
            assert row['Id'] == created and row['Config']['Labels']['journey.operation'] == 'restore-probe'
            assert command(['docker','rm','-fv',name]).returncode == 0, 'SCRATCH_CLEANUP_FAILED'


def main():
    assert sys.platform == 'linux' and os.geteuid() == 0 and socket.gethostname() == 'journey-next-staging'
    module, app = load_release()
    usage = shutil.disk_usage(ROOT)
    stats = os.statvfs(ROOT)
    report(preconditions='PASS', production_switched=False, disk_free_bytes=usage.free,
        disk_total_bytes=usage.total, inodes_free=stats.f_favail)
    result = app.docker_api('secrets/migration.env','alembic','current',read_only=True)
    assert module.SOURCE_SCHEMA.encode() in result, 'SOURCE_SCHEMA_CHANGED'
    image = json.loads(command(['docker','image','inspect',app.images['dbrestore']]).stdout)[0]
    assert app.images['dbrestore'] in image['RepoDigests']
    report(restore_image=image['Id'], postgres_entrypoint=image['Config']['Entrypoint']==['docker-entrypoint.sh'],
        postgres_command=image['Config']['Cmd']==['postgres'])
    scratch_probe(app.images['dbrestore'])
    app.verify_base()
    report(diagnosis_complete=True, business_writes=0, services_switched=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        report(diagnosis='STOP', error_type=type(error).__name__,
            category=str(error) if re.fullmatch('[A-Z0-9_]+',str(error)) else None)
        raise SystemExit(1)
