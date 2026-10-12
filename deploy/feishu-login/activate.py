"""Pinned API/Web login update; no migrations, seed, reset or identity rewrite."""
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
import tarfile
import urllib.request

from canary_schema_upgrade import (
    ROOT, COPY_FILES, ENV_FILES, UpgradeError, changed_env, compose, env_values,
    read_file, require, run, write_new,
)

BASE_BACKEND = '9e24e64a6b35509da1f28a0dd0e4f8f2131c7399'
BASE_WEB = '50650ae883b14c3ec7485ebb20f518e47e0ac748'
APP_ID = 'cli_aaef896604b85bb4'
SERVICES = ('api', 'web')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_config(archive, expected):
    with tarfile.open(archive, 'r') as handle:
        manifest = json.load(handle.extractfile('manifest.json'))
        require(len(manifest) == 1, 'EXPORTED_IMAGE_COUNT')
        info = handle.getmember(manifest[0]['Config'])
        require(info.isfile() and info.size < 2_000_000, 'CONFIG_SIZE')
        require('sha256:' + hashlib.file_digest(handle.extractfile(info), 'sha256').hexdigest()
                == expected, 'EXPORTED_CONFIG_DIGEST')


def container(service):
    ids = run(['docker', 'ps', '-q', '--filter',
        'label=com.docker.compose.project=journey-next-greenfield-canary',
        '--filter', 'label=com.docker.compose.service=' + service]).split()
    require(len(ids) == 1, 'CONTAINER_COUNT')
    return json.loads(run(['docker', 'inspect', ids[0].decode()]))[0]


def other_containers():
    rows = run(['docker', 'ps', '-a', '--no-trunc', '--format',
        '{{.ID}} {{.Label "com.docker.compose.project"}} {{.Label "com.docker.compose.service"}}'])
    return sorted(line for line in rows.decode().splitlines()
        if not any(line.endswith(' journey-next-greenfield-canary ' + name) for name in SERVICES))


def normalized(config, new, base, previous):
    result = json.loads(json.dumps(config).replace(str(new), str(base)))
    for name in SERVICES:
        result['services'][name]['image'] = previous['services'][name]['image']
        result['services'][name]['environment']['APP_RELEASE'] = previous['services'][name]['environment']['APP_RELEASE']
    return result


def import_image(package, service, entry, candidate):
    archive = package / (service + '.tar.gz')
    with archive.open('xb') as dest:
        for part in entry['chunks']:
            require(re.fullmatch(service + r'\.part[0-9]{4}', part['file']), 'CHUNK_NAME')
            path = package / part['file']
            require(path.is_file() and not path.is_symlink() and sha(path) == part['sha256'], 'CHUNK_SHA')
            with path.open('rb') as src:
                shutil.copyfileobj(src, dest)
    require(sha(archive) == entry['gzip_sha256'], 'ARCHIVE_SHA')
    with gzip.open(archive, 'rb') as src:
        require(hashlib.file_digest(src, 'sha256').hexdigest() == entry['tar_sha256'], 'TAR_SHA')
    run(['docker', 'load', '--input', str(archive)], timeout=600)
    image = json.loads(run(['docker', 'image', 'inspect', entry['reference']]))[0]
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image['Id']), 'IMAGE_ID')
    require(image['Os'] == 'linux' and image['Architecture'] == 'amd64', 'IMAGE_PLATFORM')
    require(image['Config']['Labels']['org.opencontainers.image.revision'] == candidate, 'IMAGE_REVISION')
    exported = package / (service + '-verification.tar')
    run(['docker', 'image', 'save', '--output', str(exported), image['Id']], timeout=600)
    verify_config(exported, entry['config_digest'])
    exported.unlink()
    return image['Id']


def public_checks(candidate, sdk_sha):
    with urllib.request.urlopen('https://journey.muchenai.com/health/ready', timeout=30) as response:
        require(json.load(response) == {'status': 'ready', 'release': candidate}, 'PUBLIC_READINESS')
    for path in ('/join', '/review/login', '/ops/login'):
        with urllib.request.urlopen('https://journey.muchenai.com' + path, timeout=30) as response:
            require(response.status == 200, 'ENTRY_UNAVAILABLE')
    with urllib.request.urlopen('https://journey.muchenai.com/vendor/feishu/h5-js-sdk-1.5.26.csp.js', timeout=30) as response:
        require(hashlib.sha256(response.read()).hexdigest() == sdk_sha, 'PUBLIC_SDK_MISMATCH')
    request = urllib.request.Request('https://journey.muchenai.com/auth/feishu/client',
        data=b'{"step":"start"}', headers={'Content-Type': 'application/json',
            'Origin': 'https://journey.muchenai.com', 'X-Journey-Client-Login': '1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
        require(response.status == 200 and data.get('appId') == APP_ID
                and isinstance(data.get('state'), str) and len(data['state']) >= 32, 'CLIENT_START_FAILED')
        require(any('HttpOnly' in value and 'Secure' in value for value in response.headers.get_all('Set-Cookie', [])), 'OAUTH_COOKIE_MISSING')


def activate(package):
    require(socket.gethostname() == 'journey-next-staging', 'HOST')
    require(package.parent == ROOT / 'exploration-runs' and
            re.fullmatch(r'[0-9]+-[0-9]+-activate', package.name), 'PACKAGE_PATH')
    pin = json.loads(read_file(package / 'manifest.json'))
    candidate = pin['candidate']
    require(re.fullmatch('[0-9a-f]{40}', candidate), 'CANDIDATE')
    require(pin['base_backend'] == BASE_BACKEND and pin['base_web'] == BASE_WEB, 'BASE_PIN')
    require(set(pin['archives']) == set(SERVICES), 'IMAGE_SET')
    base = ROOT / 'releases' / (BASE_WEB + '-web-labels')
    new = ROOT / 'releases' / (candidate + '-feishu-login')
    require((ROOT / 'current').resolve(strict=True) == base and not new.exists(), 'BASE_RELEASE')
    old = {name: container(name) for name in SERVICES}
    for name, revision in [('api', BASE_BACKEND), ('web', BASE_WEB)]:
        require('APP_RELEASE=' + revision in old[name]['Config']['Env'], 'RUNTIME_BASELINE')
    untouched = other_containers()
    before = json.loads(compose(base, 'config', '--format', 'json'))
    images = {name: import_image(package, name, pin['archives'][name], candidate) for name in SERVICES}
    new.mkdir(mode=0o700)
    (new / 'secrets').mkdir(mode=0o700)
    for name in COPY_FILES + ENV_FILES:
        raw = read_file(base / name)
        if name == '.deployment.env':
            raw = changed_env(raw, {'API_IMAGE': images['api'], 'WEB_IMAGE': images['web'], 'CANDIDATE_COMMIT': candidate})
        elif name in ('secrets/api.env', 'secrets/web.env'):
            raw = changed_env(raw, {'APP_RELEASE': candidate})
        write_new(new / name, raw, stat.S_IMODE((base / name).stat().st_mode))
    after = json.loads(compose(new, 'config', '--format', 'json'))
    require(normalized(after, new, base, before) == before, 'COMPOSE_EXTRA_CHANGE')
    for name in ('secrets/api.env', 'secrets/web.env'):
        require(env_values(read_file(new / name)) == {**env_values(read_file(base / name)), 'APP_RELEASE': candidate}, 'CONFIG_EXTRA_CHANGE')
    # Recheck after image import, before touching the running services.
    require((ROOT / 'current').resolve(strict=True) == base, 'BASE_CHANGED')
    require(all(container(name)['Id'] == old[name]['Id'] for name in SERVICES), 'CONTAINER_CHANGED')
    try:
        print('SWITCH_API_WEB_NO_MIGRATION', flush=True)
        compose(new, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', *SERVICES, timeout=300)
        for name in SERVICES:
            current = container(name)
            require(current['Image'] == images[name] and current['State']['Health']['Status'] == 'healthy', 'SERVICE_UNHEALTHY')
            require('APP_RELEASE=' + candidate in current['Config']['Env'], 'RELEASE_MISMATCH')
        require(other_containers() == untouched, 'OTHER_CONTAINER_CHANGED')
        public_checks(candidate, pin['sdk_sha256'])
        receipt = {'result': 'PASS', 'candidate': candidate, 'previous_api': BASE_BACKEND,
            'previous_web': BASE_WEB, 'migrations': 0, 'data_reset': False,
            'other_containers_unchanged': True, 'previous_release': str(base)}
        write_new(new / 'login-release-receipt.json', json.dumps(receipt).encode())
        temporary = ROOT / ('current-' + candidate)
        temporary.symlink_to(new)
        os.replace(temporary, ROOT / 'current')
    except Exception:
        compose(base, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', *SERVICES, timeout=300)
        require(all(container(name)['Image'] == old[name]['Image'] for name in SERVICES), 'ROLLBACK_IMAGE')
        require(other_containers() == untouched, 'ROLLBACK_OTHER_CONTAINER')
        print('API_WEB_ROLLBACK_COMPLETE', flush=True)
        raise
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    try:
        activate(Path(sys.argv[1]).resolve(strict=True))
    except Exception as error:
        print(json.dumps({'result': 'STOP', 'category': type(error).__name__,
            'reason': str(error) if type(error).__name__ == 'UpgradeError' else 'LOGIN_RELEASE_FAILED'}))
        raise SystemExit(1)
