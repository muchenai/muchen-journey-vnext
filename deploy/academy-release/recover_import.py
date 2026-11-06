"""Resume one verified pre-stage Academy import, keeping its original release code."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import traceback

CANDIDATE = '29f00234e5f2de1321792ac57ba810fc23c8bdaa'
BASE = '2bab0cefe55447c9d64af81dd5c52f5db67db09c'
PACKAGE_RUN = '42035425027'
SOURCE_RUN = '42037456146'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/42037456146-1-activate'
MIGRATIONS = {'from': '0052_knowledge_publication', 'to': '0054_academy_covers'}
DBRESTORE = 'ghcr.io/muchenai/muchen-journey-vnext-dbrestore@sha256:1517ffbd8fdf7c4946535604bfa8df5299456b7749e5396c0edcbb345fe76d6a'
SOURCE_FILES = frozenset({'activate.py', 'prepare.py', 'canary_schema_upgrade.py',
    'wp31_database_snapshot.py', 'db_facts.py', 'db_facts_control.py', 'grant_runtime.py',
    'facts_guard.py', 'restore_backup.py', 'diagnose_backup.py', 'disk_space.py',
    'image_transport.py'})
CONTROL_FILES = frozenset({'recover_import.py', 'image_transport.py'})
FILE_COUNT = 155
CHECKPOINT = 'START'


class RecoveryError(RuntimeError):
    pass


def require(value, category):
    if not value:
        raise RecoveryError(category)


def checkpoint(value):
    global CHECKPOINT
    CHECKPOINT = value
    print(json.dumps({'step': value}), flush=True)


def file_info(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'UNSAFE_FILE')
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': value, 'bytes': path.stat().st_size}


def validate_manifest(manifest):
    require(manifest['candidate'] == CANDIDATE and manifest['package_run_id'] == PACKAGE_RUN, 'APPLICATION_PIN')
    require(manifest['base_candidate'] == BASE and manifest['base_release'] == str(ROOT / 'releases' / (BASE + '-badges-knowledge')), 'BASE_PIN')
    require(manifest['schema_version'] == 3 and manifest['migrations'] == MIGRATIONS, 'MIGRATION_CONTRACT')
    require(manifest['database'] == 'journey_next_canary_20260901_c72fea5', 'DATABASE_PIN')
    require(manifest['old_images'] == {} and set(manifest['images']) == {'api', 'web', 'dbrestore'}, 'ORIGINAL_IMAGES')
    require(manifest['images']['dbrestore'] == DBRESTORE, 'RESTORE_IMAGE_PIN')
    require(set(manifest['archives']) == {'api', 'web'}, 'ARCHIVE_SET')
    names = set(SOURCE_FILES) | {'manifest.json', 'SHA256SUMS'}
    for name, entry in manifest['archives'].items():
        require(entry['source_reference'] == f'ghcr.io/muchenai/muchen-journey-vnext-{name}:{CANDIDATE}', 'SOURCE_REFERENCE')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', entry['config_digest']) and entry['config_digest'] == manifest['images'][name], 'SOURCE_IMAGE_ID')
        for field in ('gzip_sha256', 'source_tar_sha256'):
            require(re.fullmatch(r'[0-9a-f]{64}', entry[field]), 'ARCHIVE_DIGEST')
        for field in ('gzip_bytes', 'source_tar_bytes'):
            require(type(entry[field]) is int and 0 < entry[field] <= 4 * 1024**3, 'ARCHIVE_SIZE')
        require(0 < len(entry['chunks']) <= 1000, 'CHUNK_COUNT')
        for index, part in enumerate(entry['chunks']):
            require(part['file'] == f'{name}.part{index:04}' and re.fullmatch(r'[0-9a-f]{64}', part['sha256']), 'CHUNK_IDENTITY')
            names.add(part['file'])
    require(len(names) == FILE_COUNT, 'ORIGINAL_FILE_COUNT')
    return names


def validate_proof(proof):
    require(proof['schema_version'] == 1 and proof['source_run_id'] == SOURCE_RUN and proof['source_attempt'] == 1, 'SOURCE_RUN_PIN')
    require(proof['source_package'] == str(SOURCE), 'SOURCE_PACKAGE_PIN')
    require(re.fullmatch(r'[0-9a-f]{40}', proof['operations_commit']), 'OPERATIONS_PIN')
    names = validate_manifest(proof['manifest'])
    require(set(proof['files']) == names and set(proof['controls']) == CONTROL_FILES, 'PROOF_FILE_SET')
    for info in list(proof['files'].values()) + list(proof['controls'].values()):
        require(set(info) == {'sha256', 'bytes'} and re.fullmatch(r'[0-9a-f]{64}', info['sha256']), 'PROOF_DIGEST')
        require(type(info['bytes']) is int and 0 < info['bytes'] <= 2 * 1024**2, 'PROOF_FILE_SIZE')
    for entry in proof['manifest']['archives'].values():
        require(sum(proof['files'][part['file']]['bytes'] for part in entry['chunks']) == entry['gzip_bytes'], 'CHUNK_TOTAL')
        for part in entry['chunks']:
            require(proof['files'][part['file']]['sha256'] == part['sha256'], 'CHUNK_PROOF')


def verify_archive(path, entry):
    require(file_info(path) == {'sha256': entry['gzip_sha256'], 'bytes': entry['gzip_bytes']}, 'ASSEMBLED_ARCHIVE_CHANGED')
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            size += len(block)
            require(size <= entry['source_tar_bytes'], 'SOURCE_TAR_SIZE')
            digest.update(block)
    require(size == entry['source_tar_bytes'] and digest.hexdigest() == entry['source_tar_sha256'], 'SOURCE_TAR_CHANGED')


def verify_original_package(package, proof):
    """Hash every original entry before importing any of its executable code."""
    validate_proof(proof)
    require(package.is_dir() and not package.is_symlink() and package.resolve() == package, 'SOURCE_PACKAGE_PATH')
    expected = set(proof['files'])
    actual = {path.name for path in package.iterdir()}
    require(expected <= actual and actual <= expected | {'api.tar.gz', 'web.tar.gz', '__pycache__'}, 'SOURCE_FILE_SET')
    # Original failed imports can leave caches. Never trust or execute them.
    cache = package / '__pycache__'
    if os.path.lexists(cache):
        require(cache.is_dir() and not cache.is_symlink() and cache.resolve() == cache, 'SOURCE_CACHE_PATH')
        modules = {Path(name).stem for name in SOURCE_FILES}
        for path in cache.iterdir():
            match = re.fullmatch(r'([a-z_0-9]+)\.cpython-[0-9]{2,3}(?:\.opt-[12])?\.pyc', path.name)
            require(match and match.group(1) in modules and path.is_file() and not path.is_symlink(), 'SOURCE_CACHE_ENTRY')
    for name, expected_info in proof['files'].items():
        require(file_info(package / name) == expected_info, 'ORIGINAL_FILE_CHANGED')
    require(json.loads((package / 'manifest.json').read_text()) == proof['manifest'], 'ORIGINAL_MANIFEST_CHANGED')
    # This also binds the original source-code checksums to the runner's exact
    # candidate checkout, rather than trusting a server-local checksum list.
    sums = ''.join(proof['files'][name]['sha256'] + '  ' + name + '\n'
                   for name in sorted(expected - {'SHA256SUMS'}))
    require((package / 'SHA256SUMS').read_text() == sums, 'ORIGINAL_CHECKSUM_LIST')
    for name, entry in proof['manifest']['archives'].items():
        archive = package / (name + '.tar.gz')
        if os.path.lexists(archive):
            verify_archive(archive, entry)


def prepare_proof(package, destination, operations_commit):
    """Runner only: input comes from the pinned candidate's original package.py."""
    package, destination = package.resolve(), destination.resolve()
    manifest = json.loads((package / 'manifest.json').read_text())
    names = validate_manifest(manifest)
    require({p.name for p in package.iterdir()} == names, 'RECONSTRUCTED_FILE_SET')
    controls = Path(__file__).resolve().parent
    proof = {'schema_version': 1, 'source_run_id': SOURCE_RUN, 'source_attempt': 1,
        'source_package': str(SOURCE), 'operations_commit': operations_commit,
        'manifest': manifest, 'files': {name: file_info(package / name) for name in sorted(names)},
        'controls': {name: file_info(controls / name) for name in sorted(CONTROL_FILES)}}
    verify_original_package(package, proof)
    destination.mkdir(mode=0o700, exist_ok=False)
    for name in CONTROL_FILES:
        shutil.copyfile(controls / name, destination / name)
    (destination / 'original-package-proof.json').write_text(json.dumps(proof, sort_keys=True), encoding='utf-8')
    sums = ''.join(file_info(path)['sha256'] + '  ' + path.name + '\n' for path in sorted(destination.iterdir()))
    (destination / 'SHA256SUMS').write_text(sums, encoding='utf-8')
    print(json.dumps({'proof': 'PASS', 'application_candidate': CANDIDATE,
        'source_files': len(names), 'control_bytes': sum(p.stat().st_size for p in destination.iterdir())}), flush=True)


def ensure_archive(package, name, entry):
    archive = package / (name + '.tar.gz')
    if os.path.lexists(archive):
        verify_archive(archive, entry)
        checkpoint('REUSE_VERIFIED_' + name.upper() + '_ARCHIVE')
        return archive
    # All source parts were proved before import, and are checked again before
    # assembly. Never overwrite a partial/corrupt archive or append to it.
    for part in entry['chunks']:
        require(file_info(package / part['file'])['sha256'] == part['sha256'], 'CHUNK_CHANGED')
    with archive.open('xb') as target:
        for part in entry['chunks']:
            with (package / part['file']).open('rb') as source:
                shutil.copyfileobj(source, target)
    verify_archive(archive, entry)
    return archive


def require_pre_stage_boundary(root):
    require(root.is_dir() and root.resolve() == root and not root.is_symlink(), 'ROOT_PATH')
    for parent, prefix in ((root / 'releases', CANDIDATE), (root / 'backups', 'academy-' + CANDIDATE)):
        require(parent.is_dir() and parent.resolve() == parent, 'STATE_PARENT_PATH')
        require(not any(parent.glob(prefix + '*')), 'PAST_IMPORT_RECOVERY_BOUNDARY')


def verify_original_live_state(module, release):
    require_pre_stage_boundary(module.ROOT)
    release.verify_base()
    # No new release directory or migration credentials are needed for this
    # read-only check of the still-running original API's database.
    probe = "from sqlalchemy import text; from journey_api.db import SessionLocal; import json; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); print(json.dumps(list(s.execute(text('SELECT version_num FROM alembic_version')).scalars()))); s.rollback(); s.close()"
    versions = json.loads(module.compose(release.base, 'exec', '-T', 'api', 'python', '-c', probe))
    require(versions == [MIGRATIONS['from']], 'LIVE_SCHEMA_CHANGED')


def recovery_type(module, transport):
    class ImportRecovery(module.Activation):
        def import_images(self):
            verify_original_live_state(module, self)
            module.check_space('IMPORT', self.manifest['disk_budget']['import'])
            for name in ('api', 'web'):
                entry = self.manifest['archives'][name]
                archive = ensure_archive(self.package, name, entry)
                # The original build recorded a Docker image Id, which can be
                # an OCI index. Bind the real config through the VERIFIED tar.
                with gzip.open(archive, 'rb') as source:
                    config_digest = transport.source_config_digest(source, entry['config_digest'])
                checkpoint('IMPORT_' + name.upper())
                module.run(['docker', 'load', '--input', str(archive)], timeout=600)
                loaded = json.loads(module.run(['docker', 'image', 'inspect', entry['source_reference']]))[0]
                require(re.fullmatch(r'sha256:[0-9a-f]{64}', loaded['Id']), 'LOADED_IMAGE_ID')
                transport.verify_loaded_image(loaded['Id'], config_digest)
                self.manifest['images'][name] = loaded['Id']
                self.image_check(name, self.images[name], CANDIDATE)
                print(json.dumps({'step': 'VERIFIED_IMAGE_CONFIG', 'image': name,
                    'source_image_id': entry['config_digest'], 'config_digest': config_digest,
                    'loaded_image_id': loaded['Id']}), flush=True)
            for name, reference in self.old_images.items():
                self.image_check(name, reference, BASE)
            module.Upgrade.image_check(self, 'dbrestore', self.images['dbrestore'])
            self.verify_runtime_dependencies()
            # Same narrowly bounded cleanup as the original release, only
            # after both imports and their immutable content have been proved.
            transport.cleanup_verified_transports(self.package, self.manifest)
    return ImportRecovery


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    require(sys.platform == 'linux' and os.geteuid() == 0, 'LINUX_ROOT_REQUIRED')
    require(socket.gethostname() == 'journey-next-staging', 'UNEXPECTED_HOST')
    require(ROOT.resolve() == ROOT and SOURCE.resolve() == SOURCE and SOURCE.stat().st_uid == 0, 'SOURCE_ROOT')
    os.umask(0o077)
    control = Path(__file__).resolve().parent
    require(control.parent == ROOT / 'exploration-runs' and re.fullmatch(r'[0-9]+-[0-9]+-import-recover', control.name), 'CONTROL_PACKAGE_PATH')
    payload = json.loads(sys.stdin.read(16384))
    require(set(payload) == {'migration_password', 'backup_key', 'operations_commit'}, 'PAYLOAD_FIELDS')
    proof = json.loads((control / 'original-package-proof.json').read_text())
    validate_proof(proof)
    require(payload['operations_commit'] == proof['operations_commit'], 'OPERATIONS_COMMIT_CHANGED')
    for name, expected in proof['controls'].items():
        require(file_info(control / name) == expected, 'CONTROL_SCRIPT_CHANGED')
    # The server can contain .pyc files from the original failed import. Use an
    # absent cache prefix and disable writes so none can shadow verified source.
    sys.pycache_prefix = str(control / 'unused-python-cache')
    require(not os.path.lexists(sys.pycache_prefix), 'CACHE_PREFIX_EXISTS')
    sys.dont_write_bytecode = True
    import fcntl
    fd = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_pre_stage_boundary(ROOT)
        checkpoint('VERIFY_ORIGINAL_155_FILES_AND_ASSEMBLED_ARCHIVES')
        verify_original_package(SOURCE, proof)
        transport = load_module('academy_recovery_transport', control / 'image_transport.py')
        sys.path.insert(0, str(SOURCE))
        module = load_module('academy_original_activation', SOURCE / 'activate.py')
        from restore_backup import install_safe_command_reporting
        install_safe_command_reporting(module)
        release = recovery_type(module, transport)(json.loads(json.dumps(proof['manifest'])), SOURCE)
        release.import_images()
        verify_original_live_state(module, release)
        checkpoint('STAGE_EXISTING_PRODUCTION_CONFIGURATION')
        release.stage(payload['migration_password'])
        release.verify_login_configuration()
        release.verify_restore_space()
        checkpoint('BACKUP_AND_PROVE_RESTORE')
        release.backup_migrate(payload['backup_key'])
        release.activate()
        receipt = {'status': 'PASS', 'candidate': CANDIDATE, 'schema': MIGRATIONS['to'],
            'operations_commit': proof['operations_commit'], 'source_run_id': SOURCE_RUN,
            'package_run_id': PACKAGE_RUN, 'original_manifest_sha256': proof['files']['manifest.json']['sha256'],
            'control_hashes': proof['controls']}
        with (control / 'import-recovery-receipt.json').open('x') as output:
            json.dump(receipt, output, sort_keys=True)
        checkpoint('RELEASE_COMPLETE')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 5 and sys.argv[1] == '--prepare-proof':
            prepare_proof(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        else:
            require(len(sys.argv) == 1, 'ARGUMENTS')
            main()
    except (Exception, KeyboardInterrupt) as error:
        locations = [{'file': Path(frame.f_code.co_filename).name, 'line': line}
                     for frame, line in traceback.walk_tb(error.__traceback__)]
        print(json.dumps({'result': 'STOP', 'checkpoint': CHECKPOINT,
            'category': str(error) if re.fullmatch(r'[A-Z0-9_:]+', str(error)) else type(error).__name__,
            'location': locations[-1] if locations else None, 'do_not_retry_blindly': True}), flush=True)
        raise SystemExit(1)
