"""Resume the exact pre-migration stop using verified images already on the host."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sys
import traceback

CANDIDATE = '6fbc42e22e4df81aa32b3ccdbc00ff18b13f7313'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/40307327520-1-activate'
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
    assert original['package_run_id'] == '40306326918', 'PACKAGE_RUN_CHANGED'
    assert original['old_images'] == {}, 'ORIGINAL_BASE_OVERRIDE'
    assert original['migrations'] == {'from': '0044_task_author_review', 'to': '0047_learner_notification_reads'}, 'SCHEMA_CHANGED'
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
    assert {entry.name for entry in path.iterdir()} == {'before.json', 'restored.json'}, 'PAST_RESUME_BOUNDARY'
    before = json.loads(read_file(path / 'before.json'))
    restored = json.loads(read_file(path / 'restored.json'))
    assert before == restored and before['migration'] == '0044_task_author_review', 'RESTORE_NOT_PROVEN'


def resume_type(module, guard_source):
    class ResumeActivation(module.Activation):
        def guard(self):
            return json.loads(self.docker_api('secrets/migration.env', 'python', '-c',
                guard_source, read_only=True, timeout=600))

        def validate_restored_database(self, network, restore_env):
            prefix = ['docker', 'run', '--rm', '--network', network,
                      '--env-file', str(restore_env), self.images['api']]
            checkpoint('RESTORE_BUSINESS_FINGERPRINT_BEFORE')
            before = json.loads(module.run(prefix + ['python', '-c', guard_source], timeout=600))
            module.require(module.SOURCE_SCHEMA in module.run(prefix + ['alembic', 'current']).decode(), 'RESTORE_SOURCE_SCHEMA')
            checkpoint('REHEARSE_LEARNER_MIGRATION')
            module.run(prefix + ['alembic', 'upgrade', module.TARGET_SCHEMA], timeout=600)
            checkpoint('RESTORE_BUSINESS_FINGERPRINT_AFTER')
            after = json.loads(module.run(prefix + ['python', '-c', guard_source], timeout=600))
            module.require(after == before, 'RESTORE_MIGRATION_CHANGED_BUSINESS_FACTS')
            module.require(module.TARGET_SCHEMA in module.run(prefix + ['alembic', 'current']).decode(), 'RESTORE_TARGET_SCHEMA')
            module.write_new(self.backup / 'migration-rehearsal.json', json.dumps({
                'schema': module.TARGET_SCHEMA, 'business_facts_preserved': True}).encode())
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
    guard_source = module.read_file(Path(__file__).resolve().parent / 'facts_guard.py').decode()
    original = json.loads(module.read_file(SOURCE / 'manifest.json'))
    new = ROOT / 'releases' / (CANDIDATE + '-learner-project29')
    assert new.resolve() == new
    import fcntl
    fd = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(module.read_file(new / 'schema-upgrade-prepared.json'))
        release = resume_type(module, guard_source)(json.loads(json.dumps(original)), SOURCE)
        validate_state(state['manifest'], original, release.old_images, (new / 'activation-receipt.json').exists())
        release.manifest = state['manifest']
        release.verify_base()
        release.verify_prepared()
        verify_stopped_backup(release.backup, module.read_file)
        # Preserve the failed attempt's evidence. Create a fresh backup of current data.
        release.backup = ROOT / 'backups' / ('learner-project29-' + CANDIDATE + '-resume-' + payload['operations_commit'][:12])
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
        checkpoint('VERIFY_CORRECTED_READ_ONLY_GUARD')
        release.guard()
        checkpoint('FRESH_BACKUP_RESTORE_AND_MIGRATION_REHEARSAL')
        release.backup_migrate(payload['backup_key'])
        checkpoint('ACTIVATE_VERIFIED_LEARNER_RELEASE')
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
                          'resume_line': locations[-1] if locations else None,
                          'do_not_retry_blindly': True}), flush=True)
        raise SystemExit(1)
