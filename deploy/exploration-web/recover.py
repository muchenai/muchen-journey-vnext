"""Recover the verified login Web package using separately reviewed controls."""
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


CANDIDATE = 'f01385df0921e3773bb530391ccf5fbf6c96b027'
BASE = '29f00234e5f2de1321792ac57ba810fc23c8bdaa'
PACKAGE_RUN = '42162769489'
SOURCE_RUN = '42164220807'
SCHEMA = '0054_academy_covers'
ROOT = Path('/srv/journey-next-production/canary')
SOURCE = ROOT / 'exploration-runs/42164220807-1-activate'
SOURCE_FILES = frozenset({'activate.py', 'canary_schema_upgrade.py', 'image_transport.py', 'disk_space.py'})
CONTROL_FILES = SOURCE_FILES | {'recover.py'}
FILE_COUNT = 96
ORIGINAL_BYTES = 187423441
CHECKPOINT = 'START'


class RecoveryError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise RecoveryError(reason)


def checkpoint(name):
    global CHECKPOINT
    CHECKPOINT = name
    print(json.dumps({'step': name}), flush=True)


def file_info(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, 'UNSAFE_FILE')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'bytes': path.stat().st_size}


def validate_manifest(manifest):
    require(manifest['candidate'] == CANDIDATE and manifest['package_run_id'] == PACKAGE_RUN, 'APPLICATION_PIN')
    require(manifest['base_candidate'] == BASE and manifest['base_release'] == BASE + '-academy', 'BASE_PIN')
    require(manifest['schema'] == SCHEMA, 'SCHEMA_PIN')
    entry = manifest['archive']
    require(entry['reference'] == f'ghcr.io/muchenai/muchen-journey-vnext-web:{CANDIDATE}', 'IMAGE_REFERENCE')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', entry['config_digest']), 'IMAGE_DIGEST')
    for name in ('gzip_sha256', 'tar_sha256'):
        require(re.fullmatch(r'[0-9a-f]{64}', entry[name]), 'ARCHIVE_DIGEST')
    for name in ('gzip_bytes', 'tar_bytes'):
        require(type(entry[name]) is int and 0 < entry[name] <= 4 * 1024**3, 'ARCHIVE_SIZE')
    require(0 < len(entry['chunks']) <= 1000, 'CHUNK_COUNT')
    names = set(SOURCE_FILES) | {'manifest.json', 'SHA256SUMS'}
    for index, part in enumerate(entry['chunks']):
        require(part['file'] == f'web.part{index:04}' and re.fullmatch(r'[0-9a-f]{64}', part['sha256']), 'CHUNK_IDENTITY')
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
    require(sum(info['bytes'] for info in proof['files'].values()) == ORIGINAL_BYTES, 'ORIGINAL_PACKAGE_BYTES')
    entry = proof['manifest']['archive']
    require(sum(proof['files'][part['file']]['bytes'] for part in entry['chunks']) == entry['gzip_bytes'], 'CHUNK_TOTAL')
    for part in entry['chunks']:
        require(proof['files'][part['file']]['sha256'] == part['sha256'], 'CHUNK_PROOF')


def verify_archive(path, entry):
    require(file_info(path) == {'sha256': entry['gzip_sha256'], 'bytes': entry['gzip_bytes']}, 'ASSEMBLED_ARCHIVE_CHANGED')
    size, digest = 0, hashlib.sha256()
    with gzip.open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(block)
            require(size <= entry['tar_bytes'], 'SOURCE_TAR_SIZE')
            digest.update(block)
    require(size == entry['tar_bytes'] and digest.hexdigest() == entry['tar_sha256'], 'SOURCE_TAR_CHANGED')


def verify_original_package(package, proof):
    validate_proof(proof)
    require(package.is_dir() and not package.is_symlink() and package.resolve() == package, 'SOURCE_PACKAGE_PATH')
    expected = set(proof['files'])
    actual = {path.name for path in package.iterdir()}
    require(expected <= actual and actual <= expected | {'web.tar.gz', '__pycache__'}, 'SOURCE_FILE_SET')
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
    checksums = ''.join(proof['files'][name]['sha256'] + '  ' + name + '\n'
                        for name in sorted(expected - {'SHA256SUMS'}))
    require((package / 'SHA256SUMS').read_text() == checksums, 'ORIGINAL_CHECKSUM_LIST')
    archive = package / 'web.tar.gz'
    if os.path.lexists(archive):
        verify_archive(archive, proof['manifest']['archive'])


def prepare_proof(package, destination, operations_commit):
    package, destination = package.resolve(), destination.resolve()
    manifest = json.loads((package / 'manifest.json').read_text())
    names = validate_manifest(manifest)
    require({path.name for path in package.iterdir()} == names, 'RECONSTRUCTED_FILE_SET')
    repository = Path(__file__).resolve().parents[2]
    controls = {
        'recover.py': Path(__file__).resolve(),
        'activate.py': repository / 'deploy/exploration-web/activate.py',
        'canary_schema_upgrade.py': repository / 'scripts/canary_schema_upgrade.py',
        'image_transport.py': repository / 'deploy/academy-release/image_transport.py',
        'disk_space.py': repository / 'deploy/academy-release/disk_space.py',
    }
    proof = {'schema_version': 1, 'source_run_id': SOURCE_RUN, 'source_attempt': 1,
             'source_package': str(SOURCE), 'operations_commit': operations_commit,
             'manifest': manifest, 'files': {name: file_info(package / name) for name in sorted(names)},
             'controls': {name: file_info(path) for name, path in controls.items()}}
    verify_original_package(package, proof)
    destination.mkdir(mode=0o700, exist_ok=False)
    for name, path in controls.items():
        shutil.copyfile(path, destination / name)
    (destination / 'original-package-proof.json').write_text(json.dumps(proof, sort_keys=True), encoding='utf-8')
    checksums = ''.join(file_info(path)['sha256'] + '  ' + path.name + '\n' for path in sorted(destination.iterdir()))
    (destination / 'SHA256SUMS').write_text(checksums, encoding='utf-8')
    print(json.dumps({'proof': 'PASS', 'candidate': CANDIDATE, 'source_files': len(names),
                     'source_bytes': ORIGINAL_BYTES, 'control_bytes': sum(path.stat().st_size for path in destination.iterdir())}), flush=True)


def main():
    require(sys.platform == 'linux' and os.geteuid() == 0, 'LINUX_ROOT_REQUIRED')
    require(socket.gethostname() == 'journey-next-staging' and ROOT.resolve() == ROOT, 'HOST_ROOT')
    require(SOURCE.resolve() == SOURCE and SOURCE.stat().st_uid == 0, 'SOURCE_ROOT')
    os.umask(0o077)
    control = Path(__file__).resolve().parent
    match = re.fullmatch(r'([0-9]+-[0-9]+)-web-recover', control.name)
    require(control.parent == ROOT / 'exploration-runs' and control.resolve() == control and match, 'CONTROL_PACKAGE_PATH')
    require({path.name for path in control.iterdir()} == CONTROL_FILES | {'original-package-proof.json', 'SHA256SUMS'}, 'CONTROL_FILE_SET')
    payload = json.loads(sys.stdin.read(4096))
    require(set(payload) == {'operations_commit', 'recovery_id'} and payload['recovery_id'] == match.group(1), 'PAYLOAD_FIELDS')
    proof = json.loads((control / 'original-package-proof.json').read_text())
    validate_proof(proof)
    require(payload['operations_commit'] == proof['operations_commit'], 'OPERATIONS_COMMIT_CHANGED')
    for name, expected in proof['controls'].items():
        require(file_info(control / name) == expected, 'CONTROL_SCRIPT_CHANGED')
    # Only reviewed controls are imported. Original executable files and caches
    # are verified as evidence, never added to the module search path.
    sys.pycache_prefix = str(control / 'unused-python-cache')
    require(not os.path.lexists(sys.pycache_prefix), 'CACHE_PREFIX_EXISTS')
    sys.dont_write_bytecode = True
    import fcntl
    descriptor = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checkpoint('VERIFY_ORIGINAL_96_FILES_AND_ARCHIVE')
        verify_original_package(SOURCE, proof)
        spec = importlib.util.spec_from_file_location('login_web_recovery_activation', control / 'activate.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        require(module.ROOT == ROOT and module.BASE == BASE and module.SCHEMA == SCHEMA, 'ACTIVATION_CONTRACT')
        checkpoint('RECOVER_VERIFIED_WEB_PACKAGE')
        module.activate(SOURCE, recovery_id=payload['recovery_id'])


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
