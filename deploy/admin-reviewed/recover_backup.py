"""Resume the verified pre-switch backup stop without changing database schema."""
from __future__ import annotations
from restore_backup import install_safe_command_reporting

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sys
import traceback

CANDIDATE = '86c9cfd610f07c5ed3d0881339014f9ed1aec090'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/40330276649-1-activate'
SOURCE_FILES = frozenset({'activate.py', 'prepare.py', 'canary_schema_upgrade.py',
    'wp31_database_snapshot.py', 'db_facts.py', 'db_facts_control.py',
    'grant_runtime.py', 'facts_guard.py'})
CHECKPOINT = 'START'


def checkpoint(value):
    global CHECKPOINT
    CHECKPOINT = value
    print(json.dumps({'step': value}), flush=True)


def verify_source_files(root, hashes):
    assert set(hashes) == SOURCE_FILES, 'SOURCE_FILE_SET_CHANGED'
    for name, expected in hashes.items():
        path = root / name
        assert path.is_file() and not path.is_symlink() and path.resolve() == path, 'SOURCE_FILE_UNSAFE'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'SOURCE_CHANGED'


def validate_state(prepared, original, old_images, activated):
    assert original['candidate'] == CANDIDATE, 'CANDIDATE_CHANGED'
    assert original['package_run_id'] == '40328731784', 'PACKAGE_RUN_CHANGED'
    assert original['old_images'] == {}, 'ORIGINAL_BASE_OVERRIDE'
    assert original['migrations'] == {'from': '0047_learner_notification_reads', 'to': '0047_learner_notification_reads'}, 'SCHEMA_CHANGED'
    assert not activated, 'ALREADY_ACTIVATED'
    normalized = json.loads(json.dumps(prepared))
    for name in ('api', 'web'):
        assert re.fullmatch(r'sha256:[0-9a-f]{64}', prepared['images'][name]), 'IMAGE_ID'
        normalized['images'][name] = original['images'][name]
    assert prepared['old_images'] == old_images, 'BASE_IMAGES_CHANGED'
    normalized['old_images'] = {}
    assert normalized == original, 'PACKAGE_CHANGED'


def verify_stopped_backup(path, read_file):
    assert path.is_dir() and not path.is_symlink() and path.resolve() == path, 'BACKUP_PATH'
    assert {entry.name for entry in path.iterdir()} == {'before.json'}, 'PAST_RESUME_BOUNDARY'
    before = json.loads(read_file(path / 'before.json'))
    assert before['migration'] == '0047_learner_notification_reads', 'SOURCE_SCHEMA_CHANGED'


def resume_type(module):
    from restore_backup import restore_verified_backup
    class ResumeActivation(module.Activation):
        def restore_encrypt_migrate(self, before, dump, encrypted, verify, backup_key):
            return restore_verified_backup(self, before, dump, encrypted, verify, backup_key, module)
    return ResumeActivation


def main():
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert socket.gethostname() == 'journey-next-staging'
    assert ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE
    os.umask(0o077)
    payload = json.loads(sys.stdin.read(100_000))
    assert set(payload) == {'backup_key', 'source_hashes', 'operations_commit'}
    assert re.fullmatch('[0-9a-f]{40}', payload['operations_commit'])
    checkpoint('VERIFY_ORIGINAL_PACKAGE_SCRIPTS')
    verify_source_files(SOURCE, payload['source_hashes'])
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location('original_activation', SOURCE / 'activate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    install_safe_command_reporting(module)
    original = json.loads(module.read_file(SOURCE / 'manifest.json'))
    new = ROOT / 'releases' / (CANDIDATE + '-admin-reviewed')
    assert new.resolve() == new
    import fcntl
    fd = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(module.read_file(new / 'schema-upgrade-prepared.json'))
        release = resume_type(module)(json.loads(json.dumps(original)), SOURCE)
        validate_state(state['manifest'], original, release.old_images, (new / 'activation-receipt.json').exists())
        release.manifest = state['manifest']
        release.verify_base()
        release.verify_prepared()
        verify_stopped_backup(release.backup, module.read_file)
        # Preserve the failed attempt's evidence. Create a fresh backup of current data.
        release.backup = ROOT / 'backups' / ('admin-reviewed-' + CANDIDATE + '-recover-' + payload['operations_commit'][:12])
        assert not release.backup.exists() and not release.backup.is_symlink(), 'RESUME_BACKUP_EXISTS'
        checkpoint('VERIFY_SOURCE_SCHEMA_AND_PREPARED_IMAGES')
        module.require(module.SOURCE_SCHEMA in release.docker_api('secrets/migration.env',
            'alembic', 'current', read_only=True).decode(), 'SOURCE_SCHEMA')
        for name in ('api', 'web'):
            release.image_check(name, release.images[name], CANDIDATE)
            exported = Path(__file__).resolve().parent / (name + '-verification.tar')
            assert not exported.exists(), 'VERIFICATION_EXISTS'
            try:
                module.run(['docker', 'image', 'save', '--output', str(exported), release.images[name]], timeout=600)
                module.verify_exported_config(exported, original['archives'][name]['config_digest'])
            finally:
                if exported.is_file() and not exported.is_symlink():
                    exported.unlink()
        release.verify_runtime_dependencies()
        release.verify_login_configuration()
        checkpoint('VERIFY_READ_ONLY_BUSINESS_GUARD')
        release.guard()
        checkpoint('FRESH_BACKUP_WITH_TCP_READINESS')
        release.backup_migrate(payload['backup_key'])
        checkpoint('ACTIVATE_VERIFIED_ADMINISTRATOR_RELEASE')
        release.activate()
        checkpoint('RELEASE_COMPLETE')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        locations = [line for frame, line in traceback.walk_tb(exc.__traceback__)
                     if frame.f_code.co_filename == __file__]
        print(json.dumps({'result': 'STOP', 'checkpoint': CHECKPOINT,
                          'error_type': type(exc).__name__,
                          'category': str(exc) if re.fullmatch('[A-Z0-9_:]+',str(exc)) else None,
                          'resume_line': locations[-1] if locations else None,
                          'do_not_retry_blindly': True}), flush=True)
        raise SystemExit(1)
