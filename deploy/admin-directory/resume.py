"""Resume only the known pre-migration stop; reuse verified uploaded images.

No failed command's raw output, exception message or connection details are
logged. Owner diagnostics expose fixed checkpoints, codes and numeric status.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sys
import time

CANDIDATE = 'f8afcb5c865c3a6a44b68af49ed347c6e593a3ad'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/39926387464-1-activate'


def probe_program(source, mode):
    assert mode in ('--check', '--apply')
    # Catch inside the isolated container so the transport can return a safe
    # structured result even when its underlying program raises an exception.
    return '''import contextlib, io, json, re, sys
scope = {'__name__': 'owner_probe'}
sys.argv = ['bootstrap_owners.py', MODE]
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        exec(compile(SOURCE, 'bootstrap_owners.py', 'exec'), scope)
        scope['main']()
    result = {'result':'PASS', 'approved_owners':2, 'mode':MODE}
except Exception as exc:
    checkpoint = scope.get('CHECKPOINT', 'IMPORTS')
    result = {'result':'STOP', 'checkpoint':checkpoint if re.fullmatch('[A-Z_0-9]{1,60}', checkpoint) else 'UNKNOWN',
              'error_type':type(exc).__name__}
    if isinstance(exc, AssertionError):
        code = str(exc)
        result['code'] = code if re.fullmatch('[A-Z_]{1,80}', code) else 'ASSERTION_FAILED'
    elif hasattr(exc, 'code'):
        code = getattr(exc, 'code', '')
        result['code'] = code if isinstance(code, str) and re.fullmatch('[A-Z_]{1,80}', code) else 'PROBE_ERROR'
        result['retryable'] = getattr(exc, 'retryable', False) is True
        details = getattr(exc, 'details', {})
        for key in ('provider_code', 'http_status'):
            value = details.get(key) if isinstance(details, dict) else None
            if type(value) is int:
                result[key] = value
    else:
        state = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
        if isinstance(state, str) and re.fullmatch('[A-Z0-9]{5}', state):
            result['sqlstate'] = state
print(json.dumps(result))
'''.replace('MODE', repr(mode)).replace('SOURCE', repr(source))


def owner_probe(release, source, mode):
    for attempt in range(2):
        value = json.loads(release.docker_api('secrets/api.env', 'python', '-c',
                          probe_program(source, mode), read_only=mode == '--check', timeout=300))
        print(json.dumps({'owner_probe': value}), flush=True)
        if value.get('result') == 'PASS':
            return
        transient = (mode == '--check' and value.get('retryable') is True
                     and value.get('code') in {'DIRECTORY_BUSY', 'DIRECTORY_UNAVAILABLE', 'DIRECTORY_TOKEN_INVALID'})
        if not transient or attempt:
            raise RuntimeError('OWNER_CHECK_STOPPED')
        time.sleep(3)


def validate_state(manifest, original, *, backup_exists, activated):
    assert manifest['candidate'] == CANDIDATE, 'CANDIDATE_CHANGED'
    assert manifest['package_run_id'] == '39925261076', 'PACKAGE_RUN_CHANGED'
    assert manifest['migrations'] == {'from':'0038_review_admin_workspace', 'to':'0044_task_author_review'}, 'SCHEMA_CHANGED'
    assert not backup_exists and not activated, 'PAST_RESUME_BOUNDARY'
    # docker load can rewrap manifests; only the two imported immutable IDs
    # may differ from the original package, and their config is reproved below.
    normalized = json.loads(json.dumps(manifest))
    for name in ('api', 'web'):
        assert re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['images'][name]), 'IMAGE_ID'
        normalized['images'][name] = original['images'][name]
    assert normalized == original, 'PACKAGE_CHANGED'


def main():
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert socket.gethostname() == 'journey-next-staging'
    assert ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
    payload = json.loads(sys.stdin.read(100_000))
    assert set(payload) == {'backup_key', 'bootstrap_source', 'source_hashes'}
    # The workflow computes these from the exact original released commit.
    for name, expected in payload['source_hashes'].items():
        assert re.fullmatch(r'[a-z_]+\.py', name)
        path = SOURCE / name
        assert path.is_file() and not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'SOURCE_CHANGED'
    assert set(payload['source_hashes']) == {'activate.py','prepare.py','canary_schema_upgrade.py',
        'wp31_database_snapshot.py','db_facts.py','db_facts_control.py','grant_runtime.py','facts_guard.py','verify_ready.py','bootstrap_owners.py'}
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('original_activation', SOURCE / 'activate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    new = ROOT / 'releases' / (CANDIDATE + '-admin-directory')
    assert new.resolve() == new
    state = json.loads(module.read_file(new / 'schema-upgrade-prepared.json'))
    original = json.loads(module.read_file(SOURCE / 'manifest.json'))
    release = module.Activation(state['manifest'], SOURCE)
    import fcntl
    fd = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate_state(release.manifest, original, backup_exists=release.backup.exists(),
                       activated=(new / 'activation-receipt.json').exists())
        release.verify_base()
        release.verify_prepared()
        module.require(module.SOURCE_SCHEMA in release.docker_api('secrets/migration.env',
            'alembic', 'current', read_only=True).decode(), 'SOURCE_SCHEMA')
        for name in ('api', 'web'):
            release.image_check(name, release.images[name], CANDIDATE)
            exported = SOURCE / (name + '-resume-verification.tar')
            module.require(not exported.exists(), 'VERIFICATION_EXISTS')
            try:
                module.run(['docker','image','save','--output',str(exported),release.images[name]], timeout=600)
                module.verify_exported_config(exported, original['archives'][name]['config_digest'])
            finally:
                if exported.is_file() and not exported.is_symlink():
                    exported.unlink()
        release.verify_runtime_dependencies()
        release.verify_login_configuration()
        module.event('CHECK_APPROVED_OWNERS_BEFORE_ANY_DATABASE_CHANGE')
        owner_probe(release, payload['bootstrap_source'], '--check')
        module.event('BACKUP_AND_PROVE_RESTORE')
        release.backup_migrate(payload['backup_key'])
        release.activate()
        module.event('CONFIGURE_APPROVED_OWNERS_AND_PREPARE_DIRECTORY')
        owner_probe(release, payload['bootstrap_source'], '--apply')
        print(release.docker_api('secrets/api.env', 'python', '-c',
            module.read_file(SOURCE / 'verify_ready.py').decode(), timeout=600).decode(), flush=True)
        module.event('RELEASE_COMPLETE')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({'result':'STOP','error_type':type(exc).__name__,
                          'do_not_retry_blindly':True}), flush=True)
        raise SystemExit(1)
