"""Reclaim verified transport copies, then resume the exact pre-migration release."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import threading

from diagnose_restore import CANDIDATE, ROOT, SOURCE, load_release, report, scratch_probe

TARGET_FREE = 2 * 1024**3
MINIMUM_FREE = 1024**3
MAXIMUM_RECLAIM = 8 * 1024**3


def sha(path):
    assert path.is_file() and not path.is_symlink() and path.resolve() == path
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_export(stream, expected):
    """Verify the saved image config without writing another image tar to disk."""
    hashes = {}
    manifest = None
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for index, member in enumerate(archive):
            assert index < 20000, 'IMAGE_EXPORT_MEMBER_LIMIT'
            if member.isfile() and member.size <= 2_000_000:
                handle = archive.extractfile(member)
                raw = handle.read()
                hashes[member.name] = hashlib.sha256(raw).hexdigest()
                if member.name == 'manifest.json':
                    assert manifest is None, 'DUPLICATE_IMAGE_MANIFEST'
                    manifest = json.loads(raw)
    assert manifest and len(manifest) == 1, 'IMAGE_EXPORT_MANIFEST'
    assert 'sha256:' + hashes.get(manifest[0]['Config'], '') == expected, 'IMAGE_CONFIG_CHANGED'


def verify_image(image, expected):
    process = subprocess.Popen(['docker','image','save',image], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    timer = threading.Timer(600, process.kill)
    timer.start()
    try:
        verify_export(process.stdout, expected)
        process.stdout.read()
        assert process.wait(timeout=30) == 0, 'IMAGE_EXPORT_FAILED'
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()


def transport_files(package, manifest):
    """Only exact manifest-bound image chunks and their assembled gzip copies."""
    assert package.is_dir() and not package.is_symlink() and package.resolve() == package
    result = []
    assert set(manifest['archives']) == {'api','web'}, 'ARCHIVE_SET_CHANGED'
    for name in ('api','web'):
        entry = manifest['archives'][name]
        assert re.fullmatch('[0-9a-f]{64}', entry['gzip_sha256'])
        assert 0 < len(entry['chunks']) <= 1000, 'CHUNK_COUNT'
        candidates = [(part['file'], part['sha256'], 64 * 1024**2) for part in entry['chunks']]
        assert len({row[0] for row in candidates}) == len(candidates), 'DUPLICATE_CHUNK'
        assert all(re.fullmatch(name+r'\.part[0-9]{4}', row[0]) for row in candidates), 'UNSAFE_CHUNK'
        candidates.append((name+'.tar.gz', entry['gzip_sha256'], 2 * 1024**3))
        for filename, expected, limit in candidates:
            assert re.fullmatch('[0-9a-f]{64}', expected)
            path = package / filename
            assert not path.is_symlink(), 'UNSAFE_TRANSPORT_FILE'
            if path.exists():
                assert path.is_file() and path.resolve().parent == package, 'UNSAFE_TRANSPORT_FILE'
                assert 0 < path.stat().st_size <= limit, 'TRANSPORT_SIZE'
                assert sha(path) == expected, 'TRANSPORT_CHANGED'
                result.append((path, expected, path.stat().st_size))
    return result


def cleanup_transports(module):
    runs = ROOT / 'exploration-runs'
    assert runs.is_dir() and not runs.is_symlink() and runs.resolve() == runs
    successful = set()
    for release in (ROOT / 'releases').iterdir():
        if release.is_symlink() or not release.is_dir() or release.resolve() != release:
            continue
        receipt = release / 'activation-receipt.json'
        if receipt.is_file() and not receipt.is_symlink():
            data = json.loads(module.read_file(receipt))
            if data.get('status') == 'PASS' and re.fullmatch('[0-9a-f]{40}', data.get('release','')):
                successful.add(data['release'])
    packages = [SOURCE] + sorted(path for path in runs.iterdir() if path != SOURCE)
    removed = 0
    count = 0
    for package in packages:
        if shutil.disk_usage(ROOT).free >= TARGET_FREE:
            break
        if package.is_symlink() or not package.is_dir() or package.resolve() != package:
            continue
        if not re.fullmatch('[0-9]+-[0-9]+-activate', package.name):
            continue
        path = package / 'manifest.json'
        if not path.is_file() or path.is_symlink():
            continue
        manifest = json.loads(module.read_file(path))
        if package != SOURCE and manifest.get('candidate') not in successful:
            continue
        if 'archives' not in manifest:
            continue
        plan = transport_files(package, manifest)
        assert removed + sum(row[2] for row in plan) <= MAXIMUM_RECLAIM, 'RECLAIM_BOUND'
        for path, expected, size in plan:
            assert sha(path) == expected, 'TRANSPORT_CHANGED'
            path.unlink()
            removed += size
            count += 1
        report(cleanup_package=package.name, transport_files=len(plan), reclaimed_bytes=sum(row[2] for row in plan))
    free = shutil.disk_usage(ROOT).free
    report(cleanup_complete=True, transport_files=count, reclaimed_bytes=removed, disk_free_bytes=free)
    assert free >= MINIMUM_FREE, 'INSUFFICIENT_SPACE_AFTER_BOUNDED_CLEANUP'


def main():
    assert sys.platform == 'linux' and os.geteuid() == 0
    import socket
    assert socket.gethostname() == 'journey-next-staging'
    payload = json.loads(sys.stdin.read(16384))
    assert set(payload) == {'backup_key','operations_commit'}
    assert re.fullmatch('[0-9a-f]{40}', payload['operations_commit'])
    import fcntl
    descriptor = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor,'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        module, app = load_release()
        from restore_backup import install_safe_command_reporting, restore_verified_backup
        install_safe_command_reporting(module)
        original = json.loads(module.read_file(SOURCE / 'manifest.json'))
        for name in ('api','web'):
            app.image_check(name, app.images[name], CANDIDATE)
            verify_image(app.images[name], original['archives'][name]['config_digest'])
        report(prepared_images='PASS', candidate=CANDIDATE)
        cleanup_transports(module)
        assert scratch_probe(app.images['dbrestore']), 'RESTORE_STILL_NOT_READY'
        app.verify_base()
        app.verify_prepared()
        app.verify_runtime_dependencies()
        app.verify_login_configuration()
        assert module.SOURCE_SCHEMA.encode() in app.docker_api('secrets/migration.env','alembic','current',read_only=True)
        app.guard()

        class ResumeActivation(module.Activation):
            def restore_encrypt_migrate(self, before, dump, encrypted, verify, backup_key):
                return restore_verified_backup(self,before,dump,encrypted,verify,backup_key,module)

        release = ResumeActivation(original, SOURCE)
        release.manifest = app.manifest
        release.backup = ROOT / 'backups' / ('badges-knowledge-' + CANDIDATE + '-recover-' + payload['operations_commit'][:12])
        assert not release.backup.exists() and not release.backup.is_symlink(), 'RECOVERY_BACKUP_EXISTS'
        report(step='FRESH_BACKUP_AND_RESTORE_AFTER_SPACE_RECOVERY')
        release.backup_migrate(payload['backup_key'])
        release.activate()
        report(step='RELEASE_COMPLETE', candidate=CANDIDATE, disk_free_bytes=shutil.disk_usage(ROOT).free)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        report(result='STOP', error_type=type(error).__name__,
            category=str(error) if re.fullmatch('[A-Z0-9_:]+',str(error)) else None,
            do_not_retry_blindly=True)
        raise SystemExit(1)
