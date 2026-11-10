"""Publish learner profile growth on the verified Guild baseline, replacing only Web."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
import urllib.request

from canary_schema_upgrade import (
    ROOT, COPY_FILES, ENV_FILES, UpgradeError, changed_env, compose,
    read_file, require, run, write_new,
)
from disk_space import DiskSpaceError, check_space
from image_transport import source_config_digest, verify_loaded_image

BASE = 'b1be86fb9dfb81e67fc58965417a0d86061a61d4'
BASE_RELEASE = BASE + '-guild-growth'
SCHEMA = '0056_guild_halls'
PROJECT = 'journey-next-greenfield-canary'
AI_SECRETS = {'secrets/ai_api_key', 'secrets/ai_feishu_app_secret'}


def sha(path):
    require(path.is_file() and not path.is_symlink(), 'FILE_PATH')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def container(service):
    ids = run(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=' + PROJECT,
               '--filter', 'label=com.docker.compose.service=' + service]).split()
    require(len(ids) == 1, 'CONTAINER_COUNT')
    return json.loads(run(['docker', 'inspect', ids[0].decode()]))[0]


def protected_containers():
    """Compare every existing non-Web container without logging its configuration."""
    ids = run(['docker', 'ps', '-aq']).decode().split()
    require(ids, 'CONTAINERS_MISSING')
    result = {}
    for item in json.loads(run(['docker', 'inspect', *ids])):
        labels = item['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project') == PROJECT and labels.get('com.docker.compose.service') == 'web':
            continue
        result[item['Name']] = {key: item[key] for key in ('Id', 'Image', 'Config', 'HostConfig', 'Mounts')}
        # Docker can return mount entries in a different order on each inspect.
        # Keep every mount attribute while comparing this unordered collection.
        result[item['Name']]['Mounts'] = sorted(item['Mounts'], key=lambda mount: json.dumps(mount, sort_keys=True))
    return result


def verify_protected_containers(expected, category):
    actual = protected_containers()
    changes = []
    for name in sorted(set(expected) | set(actual)):
        before, after = expected.get(name), actual.get(name)
        if before == after:
            continue
        fields = ['container_presence'] if before is None or after is None else [
            field for field in before if before[field] != after[field]]
        changes.append({'container_id': (after or before)['Id'], 'fields': fields})
    if changes:
        # Values can contain credentials, so report field names and IDs only.
        print(json.dumps({'step': 'PROTECTED_RUNTIME_DIFFERENCE', 'changes': changes}), flush=True)
    require(not changes, category)


def healthy_web(candidate, requested_image, actual_images):
    item = container('web')
    require(item['Config']['Image'] == requested_image and item['Image'] in actual_images, 'WEB_IMAGE_CHANGED')
    require('APP_RELEASE=' + candidate in item['Config']['Env'], 'WEB_RELEASE')
    require(item['State']['Running'] and item['State'].get('Health', {}).get('Status') == 'healthy', 'WEB_UNHEALTHY')
    require(item['Config']['Labels'].get('org.opencontainers.image.revision') == candidate, 'WEB_REVISION')
    with urllib.request.urlopen('https://journey.muchenai.com/health/ready', timeout=30) as response:
        require(json.load(response) == {'status': 'ready', 'release': candidate}, 'PUBLIC_READINESS')
    for path in ('/join', '/review/login', '/ops/login'):
        with urllib.request.urlopen('https://journey.muchenai.com' + path, timeout=30) as response:
            require(response.status == 200, 'ENTRY_UNAVAILABLE')


def verify_schema(base):
    probe = "from sqlalchemy import text; from journey_api.db import SessionLocal; import json; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); print(json.dumps(list(s.execute(text('SELECT version_num FROM alembic_version')).scalars()))); s.rollback(); s.close()"
    versions = json.loads(compose(base, 'exec', '-T', 'api', 'python', '-c', probe))
    require(versions == [SCHEMA], 'BASE_SCHEMA')


def normalized(config, new, base, previous_web):
    result = json.loads(json.dumps(config).replace(str(new), str(base)))
    result['services']['web']['image'] = previous_web['image']
    result['services']['web']['environment']['APP_RELEASE'] = previous_web['environment']['APP_RELEASE']
    return result


def stage_configuration(base, new, before, candidate, image_id):
    secret_dir = base / 'secrets'
    require(secret_dir.is_dir() and not secret_dir.is_symlink() and secret_dir.resolve() == secret_dir, 'SECRETS_PATH')
    names = set(COPY_FILES + ENV_FILES)
    for path in secret_dir.iterdir():
        require(path.is_file() and not path.is_symlink(), 'SECRET_FILE_TYPE')
        names.add('secrets/' + path.name)
    require(AI_SECRETS <= names, 'AI_SECRET_FILES_MISSING')
    for service in before['services'].values():
        for mount in service.get('volumes', []):
            if mount.get('type') == 'bind' and Path(mount['source']).is_relative_to(base):
                relative = Path(mount['source']).relative_to(base)
                require(len(relative.parts) <= 2 and relative.parts[0] != '..', 'LOCAL_MOUNT_PATH')
                names.add(relative.as_posix())
    originals = {name: read_file(base / name) for name in names}
    metadata = {name: (base / name).stat() for name in names}
    new.mkdir(mode=0o700)
    (new / 'secrets').mkdir(mode=stat.S_IMODE(secret_dir.stat().st_mode))
    os.chown(new / 'secrets', secret_dir.stat().st_uid, secret_dir.stat().st_gid)
    for name in sorted(names):
        raw = originals[name]
        if name == '.deployment.env':
            raw = changed_env(raw, {'WEB_IMAGE': image_id, 'CANDIDATE_COMMIT': candidate})
        elif name == 'secrets/web.env':
            raw = changed_env(raw, {'APP_RELEASE': candidate})
        require((new / name).parent in {new, new / 'secrets'}, 'CONFIGURATION_PATH')
        info = metadata[name]
        write_new(new / name, raw, stat.S_IMODE(info.st_mode))
        os.chown(new / name, info.st_uid, info.st_gid)
        require(read_file(new / name) == raw, 'CONFIGURATION_COPY')
        copied = (new / name).stat()
        require((stat.S_IMODE(copied.st_mode), copied.st_uid, copied.st_gid) ==
                (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid), 'CONFIGURATION_PERMISSIONS')
        require(read_file(base / name) == originals[name], 'BASE_CONFIGURATION_CHANGED')
    after = json.loads(compose(new, 'config', '--format', 'json'))
    require(normalized(after, new, base, before['services']['web']) == before, 'COMPOSE_EXTRA_CHANGE')
    return {name: hashlib.sha256(read_file(new / name)).hexdigest() for name in sorted(names)}


def cleanup_web_transports(package, entry):
    require(package.resolve() == package and package.parent == ROOT / 'exploration-runs', 'CLEANUP_PATH')
    require(re.fullmatch(r'[0-9]+-[0-9]+-activate', package.name), 'CLEANUP_PACKAGE')
    rows = [(part['file'], part['sha256'], 2 * 1024**2) for part in entry['chunks']]
    require(0 < len(rows) <= 1000 and len({row[0] for row in rows}) == len(rows), 'CLEANUP_CHUNKS')
    require(all(re.fullmatch(r'web\.part[0-9]{4}', row[0]) for row in rows), 'CLEANUP_CHUNK_NAME')
    rows.append(('web.tar.gz', entry['gzip_sha256'], 4 * 1024**3))
    # Validate the entire deletion set before removing a verified transport.
    for name, expected, limit in rows:
        path = package / name
        require(path.resolve().parent == package and 0 < path.stat().st_size <= limit and sha(path) == expected, 'TRANSPORT_CHANGED')
    reclaimed = sum((package / name).stat().st_size for name, _, _ in rows)
    for name, expected, _ in rows:
        require(sha(package / name) == expected, 'TRANSPORT_CHANGED')
        (package / name).unlink()
    print(json.dumps({'step': 'CURRENT_WEB_TRANSPORTS_RETIRED', 'files': len(rows), 'reclaimed_bytes': reclaimed}), flush=True)


def activate(package, recovery_id=None):
    require(socket.gethostname() == 'journey-next-staging' and ROOT.resolve() == ROOT, 'HOST')
    require(package.resolve() == package and package.parent == ROOT / 'exploration-runs' and
            re.fullmatch(r'[0-9]+-[0-9]+-activate', package.name), 'PACKAGE_PATH')
    pin = json.loads(read_file(package / 'manifest.json'))
    candidate = pin['candidate']
    require(re.fullmatch('[0-9a-f]{40}', candidate) and candidate != BASE, 'CANDIDATE')
    require(re.fullmatch('[0-9]+', pin['package_run_id']), 'PACKAGE_RUN')
    require(pin['base_candidate'] == BASE and pin['base_release'] == BASE_RELEASE and pin['schema'] == SCHEMA, 'BASE_PIN')
    base = ROOT / 'releases' / pin['base_release']
    suffix = '-profile-growth'
    if recovery_id is not None:
        require(re.fullmatch(r'[0-9]+-[0-9]+', recovery_id), 'RECOVERY_ID')
        suffix += '-recovery-' + recovery_id
    new = ROOT / 'releases' / (candidate + suffix)
    require((ROOT / 'current').is_symlink() and (ROOT / 'current').resolve(strict=True) == base and
            base.resolve() == base and not os.path.lexists(new), 'BASE_RELEASE')
    receipt = json.loads(read_file(base / 'activation-receipt.json'))
    require(receipt['status'] == 'PASS' and receipt['release'] == BASE and receipt['schema'] == SCHEMA, 'BASE_RECEIPT')
    api_before, web_before = container('api'), container('web')
    require('APP_RELEASE=' + BASE in api_before['Config']['Env'] and api_before['State']['Running'] and
            api_before['State'].get('Health', {}).get('Status') == 'healthy', 'API_BASELINE')
    require(api_before['Config']['Labels'].get('org.opencontainers.image.revision') == BASE, 'API_REVISION')
    before = json.loads(compose(base, 'config', '--format', 'json'))
    previous = json.loads(read_file(base / 'schema-upgrade-prepared.json'))['manifest']
    require(previous['candidate'] == BASE, 'BASE_PREPARED_CANDIDATE')
    for service, item in (('api', api_before), ('web', web_before)):
        require(item['Config']['Image'] == before['services'][service]['image'] ==
                previous['images'][service], 'BASE_IMAGE_DRIFT')
    healthy_web(BASE, web_before['Config']['Image'], {web_before['Image']})
    verify_schema(base)
    protected = protected_containers()
    entry = pin['archive']
    require(entry['reference'] == f'ghcr.io/muchenai/muchen-journey-vnext-web:{candidate}', 'WEB_SOURCE_REFERENCE')
    check_space('IMPORT', pin['disk_budget']['import'])
    archive = package / 'web.tar.gz'
    require(0 < len(entry['chunks']) <= 1000, 'CHUNK_COUNT')
    for index, part in enumerate(entry['chunks']):
        require(part['file'] == f'web.part{index:04}', 'CHUNK_NAME')
        path = package / part['file']
        require(0 < path.stat().st_size <= 2 * 1024**2 and sha(path) == part['sha256'], 'CHUNK_SHA')
    if not os.path.lexists(archive):
        with archive.open('xb') as dest:
            for part in entry['chunks']:
                with (package / part['file']).open('rb') as src:
                    shutil.copyfileobj(src, dest)
    require(archive.stat().st_size == entry['gzip_bytes'] and sha(archive) == entry['gzip_sha256'], 'ARCHIVE_SHA')
    with gzip.open(archive, 'rb') as src:
        require(hashlib.file_digest(src, 'sha256').hexdigest() == entry['tar_sha256'], 'TAR_SHA')
    with gzip.open(archive, 'rb') as src:
        config_digest = source_config_digest(src, entry['config_digest'])
    run(['docker', 'load', '--input', str(archive)], timeout=600)
    image = json.loads(run(['docker', 'image', 'inspect', entry['reference']]))[0]
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image['Id']), 'IMAGE_ID')
    require(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'IMAGE_PLATFORM')
    require(image['Config']['Labels']['org.opencontainers.image.revision'] == candidate, 'IMAGE_REVISION')
    verify_loaded_image(image['Id'], config_digest)
    hashes = stage_configuration(base, new, before, candidate, image['Id'])
    verify_protected_containers(protected, 'BASE_RUNTIME_CHANGED')
    require((ROOT / 'current').resolve() == base, 'BASE_POINTER_CHANGED')
    cleanup_web_transports(package, entry)
    try:
        print('SWITCH_WEB_ONLY', flush=True)
        compose(new, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', 'web', timeout=240)
        verify_protected_containers(protected, 'PROTECTED_CONTAINER_CHANGED')
        healthy_web(candidate, image['Id'], {image['Id'], config_digest})
        verify_schema(base)
        receipt = {'result': 'PASS', 'web_candidate': candidate, 'api_candidate': BASE, 'schema': SCHEMA,
            'api_container_unchanged': True, 'other_containers_unchanged': True, 'database_writes': 0,
            'previous_release': str(base), 'package_run_id': pin['package_run_id'],
            'web_image_id': image['Id'], 'web_config_digest': config_digest, 'configuration_hashes': hashes}
        temporary = ROOT / ('current-' + candidate)
        temporary.symlink_to(new)
        os.replace(temporary, ROOT / 'current')
        write_new(new / 'web-release-receipt.json', json.dumps(receipt).encode())
    except (Exception, KeyboardInterrupt):
        compose(base, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', 'web', timeout=240)
        verify_protected_containers(protected, 'ROLLBACK_PROTECTED_CONTAINER_CHANGED')
        healthy_web(BASE, web_before['Config']['Image'], {web_before['Image']})
        if (ROOT / 'current').resolve() == new:
            rollback_pointer = ROOT / ('current-rollback-' + candidate)
            rollback_pointer.symlink_to(base)
            os.replace(rollback_pointer, ROOT / 'current')
        require((ROOT / 'current').resolve() == base, 'ROLLBACK_POINTER')
        success_receipt = new / 'web-release-receipt.json'
        if success_receipt.exists():
            require(not success_receipt.is_symlink(), 'ROLLBACK_RECEIPT_PATH')
            success_receipt.unlink()
        write_new(new / 'web-rollback-receipt.json', json.dumps({'result': 'ROLLED_BACK',
            'current_release': str(base), 'web_candidate': BASE,
            'other_containers_unchanged': True}).encode())
        print('WEB_ROLLBACK_COMPLETE', flush=True)
        raise
    print(json.dumps(receipt), flush=True)
    print('RELEASE_COMPLETE', flush=True)


def main():
    require(sys.platform == 'linux' and os.geteuid() == 0 and ROOT.resolve() == ROOT, 'LINUX_ROOT_REQUIRED')
    os.umask(0o077)
    import fcntl
    descriptor = os.open(ROOT / '.schema-upgrade.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        activate(Path(sys.argv[1]).resolve(strict=True))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({'result': 'STOP', 'category': type(error).__name__,
            'reason': str(error) if isinstance(error, (UpgradeError, DiskSpaceError)) or
            re.fullmatch(r'[A-Z0-9_]+', str(error)) else 'WEB_RELEASE_FAILED'}), flush=True)
        raise SystemExit(1)
