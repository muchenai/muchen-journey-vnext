"""Update only Canary Web; preserve API container, configuration and all DB data."""
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
    ROOT, COPY_FILES, ENV_FILES, UpgradeError, changed_env, compose,
    read_file, require, run, write_new,
)


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


def normalized(config, new, base, previous_web):
    result = json.loads(json.dumps(config).replace(str(new), str(base)))
    result['services']['web']['image'] = previous_web['image']
    result['services']['web']['environment']['APP_RELEASE'] = previous_web['environment']['APP_RELEASE']
    return result


def activate(package):
    require(socket.gethostname() == 'journey-next-staging', 'HOST')
    require(package.parent == ROOT / 'exploration-runs' and
            re.fullmatch(r'[0-9]+-[0-9]+-activate', package.name), 'PACKAGE_PATH')
    pin = json.loads(read_file(package / 'manifest.json'))
    candidate = pin['candidate']
    require(re.fullmatch('[0-9a-f]{40}', candidate), 'CANDIDATE')
    baseline = 'fc591682249c34d7737144e7753ddef5da7aa554'
    web_baseline = 'b685ee68f249a66b2b03f9c5c4edac1a388206c6'
    require(pin['base_candidate'] == web_baseline, 'BASE_PIN')
    base = ROOT / 'releases' / (web_baseline + '-feishu-inline-login')
    new = ROOT / 'releases' / (candidate + '-feishu-inline-login')
    require((ROOT / 'current').resolve(strict=True) == base and not new.exists(), 'BASE_RELEASE')
    api_before = container('api')
    require('APP_RELEASE=' + baseline in api_before['Config']['Env'], 'API_BASELINE')
    require('APP_RELEASE=' + web_baseline in container('web')['Config']['Env'], 'WEB_BASELINE')
    before = json.loads(compose(base, 'config', '--format', 'json'))
    entry = pin['archive']
    archive = package / 'web.tar.gz'
    with archive.open('xb') as dest:
        for part in entry['chunks']:
            require(re.fullmatch(r'web\.part[0-9]{4}', part['file']), 'CHUNK_NAME')
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
    exported = package / 'web-verification.tar'
    run(['docker', 'image', 'save', '--output', str(exported), image['Id']], timeout=600)
    verify_config(exported, entry['config_digest'])
    exported.unlink()
    new.mkdir(mode=0o700)
    (new / 'secrets').mkdir(mode=0o700)
    for name in COPY_FILES + ENV_FILES:
        raw = read_file(base / name)
        if name == '.deployment.env':
            raw = changed_env(raw, {'WEB_IMAGE': image['Id'], 'CANDIDATE_COMMIT': candidate})
        elif name == 'secrets/web.env':
            raw = changed_env(raw, {'APP_RELEASE': candidate})
        write_new(new / name, raw, stat.S_IMODE((base / name).stat().st_mode))
    after = json.loads(compose(new, 'config', '--format', 'json'))
    require(normalized(after, new, base, before['services']['web']) == before, 'COMPOSE_EXTRA_CHANGE')
    require(read_file(new / 'secrets/api.env') == read_file(base / 'secrets/api.env'), 'API_CONFIG_CHANGED')
    switched = False
    try:
        print('SWITCH_WEB_ONLY', flush=True)
        compose(new, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', 'web', timeout=240)
        require(container('api')['Id'] == api_before['Id'], 'API_CONTAINER_CHANGED')
        require(container('web')['Image'] == image['Id'], 'WEB_IMAGE_CHANGED')
        with urllib.request.urlopen('https://journey.muchenai.com/health/ready', timeout=30) as response:
            require(json.load(response) == {'status': 'ready', 'release': candidate}, 'PUBLIC_READINESS')
        for path in ('/join', '/review/login', '/ops/login'):
            with urllib.request.urlopen('https://journey.muchenai.com' + path, timeout=30) as response:
                require(response.status == 200, 'ENTRY_UNAVAILABLE')
        temporary = ROOT / ('current-' + candidate)
        temporary.symlink_to(new)
        os.replace(temporary, ROOT / 'current')
        switched = True
    except Exception:
        compose(base, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                '--force-recreate', '--wait', '--wait-timeout', '180', 'web', timeout=240)
        require(container('api')['Id'] == api_before['Id'], 'ROLLBACK_API_CHANGED')
        print('WEB_ROLLBACK_COMPLETE', flush=True)
        raise
    require(switched, 'SWITCH_INCOMPLETE')
    receipt = {'result': 'PASS', 'web_candidate': candidate, 'api_candidate': baseline,
        'api_container_unchanged': True, 'database_operations': 0, 'previous_release': str(base)}
    write_new(new / 'web-release-receipt.json', json.dumps(receipt).encode())
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    try:
        activate(Path(sys.argv[1]).resolve(strict=True))
    except Exception as error:
        # Never dump subprocess output/configuration into public workflow logs.
        print(json.dumps({'result': 'STOP', 'category': type(error).__name__,
            'reason': str(error) if type(error).__name__ == 'UpgradeError' else 'WEB_RELEASE_FAILED'}))
        raise SystemExit(1)
