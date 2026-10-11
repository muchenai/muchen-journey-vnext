#!/usr/bin/env python3
"""Bounded, independently invocable stages for the synthetic Talent demo."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import urllib.error

ROOT = Path('/opt/talent-cloud')
STATE = Path('/var/lib/talent-cloud')
CONFIG = Path('/etc/talent-cloud')
EDGE = 'journey-next-staging-edge-1'
NETWORK = 'journey-next-staging_default'
DOMAIN = 'talent.muchenai.com'
JOURNEY_RELEASE = '9a35f45053e903aa8e4d113aadbf7168d9ae9d0d'
PROXY_SHA = 'd61d3004076110c9d29cf132b21cac9ff81129bc9981b7bcf753e24b6a20c840'
NODE_VERSION = '24.21.0'
NODE_SHA = 'fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def capture(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.load(r)


def journey_ready():
    assert fetch('https://journey.muchenai.com/health/ready') == {
        'status': 'ready', 'release': JOURNEY_RELEASE}, 'Journey revision drift'


def gateway():
    info = json.loads(capture('docker', 'network', 'inspect', NETWORK))[0]
    value = info['IPAM']['Config'][0]['Gateway']
    ip = ipaddress.IPv4Address(value)
    assert any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    return value


def unpack_payload(archive, destination):
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            p = Path(member.name)
            assert p.parts[0] == 'dist-standalone' and '..' not in p.parts and not p.is_absolute()
            assert member.isdir() or member.isfile(), 'Only regular release files are accepted'
            target = destination.joinpath(*p.parts[1:])
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as src, target.open('wb') as out:
                    shutil.copyfileobj(src, out)
                target.chmod(0o644)


def prepare(stage, manifest):
    journey_ready()
    assert os.uname().machine == 'x86_64'
    assert digest(stage/'payload.tar.gz') == manifest['payload_sha256']
    release = ROOT/'releases'/manifest['revision']
    if release.exists():
        assert (release/'payload.sha256').read_text().strip() == manifest['payload_sha256'], 'Reconcile partial release before retry'
    else:
        release.mkdir(parents=True)
        unpack_payload(stage/'payload.tar.gz', release)
        assert json.loads((release/'release.json').read_text())['revision'] == manifest['revision']
        (release/'payload.sha256').write_text(manifest['payload_sha256'])
    node = ROOT/'node/bin/node'
    if not node.exists():
        archive = stage/'node.tar.xz'
        url = f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz'
        if not archive.exists():
            run('curl', '--fail', '--silent', '--show-error', '--location', '--retry', '2', '--connect-timeout', '10', '--max-time', '240', url, '-o', str(archive)+'.partial')
            assert digest(Path(str(archive)+'.partial')) == NODE_SHA
            Path(str(archive)+'.partial').rename(archive)
        assert digest(archive) == NODE_SHA
        node.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tf:
            prefix = f'node-v{NODE_VERSION}-linux-x64/'
            node.write_bytes(tf.extractfile(prefix+'bin/node').read())
            (ROOT/'node/LICENSE').write_bytes(tf.extractfile(prefix+'LICENSE').read())
        node.chmod(0o755)
    assert capture(str(node), '--version') == 'v'+NODE_VERSION
    try:
        account = pwd.getpwnam('talent-cloud')
    except KeyError:
        run('useradd', '--system', '--user-group', '--home-dir', str(STATE), '--shell', '/usr/sbin/nologin', 'talent-cloud')
        account = pwd.getpwnam('talent-cloud')
    assert account.pw_uid != 0 and account.pw_shell.endswith('/nologin')
    for path in (STATE, STATE/'backups'):
        path.mkdir(exist_ok=True); path.chmod(0o700); os.chown(path, account.pw_uid, account.pw_gid)
    CONFIG.mkdir(exist_ok=True); CONFIG.chmod(0o750); os.chown(CONFIG, 0, account.pw_gid)
    users = CONFIG/'users.json'
    if users.exists():
        assert json.loads(users.read_text()) == json.loads((stage/'users.json').read_text()), 'Existing accounts differ; no automatic rotation'
    else:
        shutil.copyfile(stage/'users.json', users)
    users.chmod(0o640); os.chown(users, 0, account.pw_gid)
    assert len(json.loads(users.read_text())) == 5
    env = f'TALENT_PUBLIC_ORIGIN=https://{DOMAIN}\nTALENT_BIND_ADDRESS={gateway()}\nTALENT_PORT=3187\nTALENT_DATABASE={STATE}/data.sqlite\nTALENT_USERS_FILE={users}\n'
    (CONFIG/'runtime.env').write_text(env); (CONFIG/'runtime.env').chmod(0o640); os.chown(CONFIG/'runtime.env', 0, account.pw_gid)
    shutil.copyfile(stage/'talent-cloud.service', '/etc/systemd/system/talent-cloud.service')
    Path('/etc/systemd/system/talent-cloud.service').chmod(0o644)
    print('PREPARE=PASS')


def migrate(stage, manifest):
    journey_ready()
    release = ROOT/'releases'/manifest['revision']
    assert (release/'payload.sha256').read_text() == manifest['payload_sha256']
    node = str(ROOT/'node/bin/node')
    db = STATE/'data.sqlite'
    if db.exists():
        backup = STATE/'backups'/f'before-{manifest["revision"][:12]}-{time.time_ns()}.sqlite'
        run('runuser', '-u', 'talent-cloud', '--', node, str(release/'tools/backup.mjs'), str(db), str(backup))
    run('runuser', '-u', 'talent-cloud', '--', node, str(release/'tools/migrate.mjs'), str(db), str(release/'drizzle'))
    print('MIGRATE=PASS')


def internal_ready(revision):
    data = fetch(f'http://{gateway()}:3187/health/ready')
    assert data['status'] == 'ready' and data['release'] == revision
    try:
        urllib.request.urlopen(f'http://{gateway()}:3187/api/workspace', timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError('Anonymous workspace access was allowed')


def start(stage, manifest):
    journey_ready()
    release = ROOT/'releases'/manifest['revision']
    assert (release/'payload.sha256').read_text() == manifest['payload_sha256']
    current = ROOT/'current'
    prior = current.resolve() if current.is_symlink() else None
    assert not current.exists() or current.is_symlink()
    tmp = ROOT/'current.next'
    tmp.unlink(missing_ok=True); tmp.symlink_to(release); tmp.replace(current)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', 'talent-cloud')
    try:
        run('systemctl', 'restart', 'talent-cloud')
        for attempt in range(20):
            try:
                internal_ready(manifest['revision']); break
            except Exception:
                if attempt == 19: raise
                time.sleep(1)
        journey_ready()
    except Exception:
        if prior is not None and prior != release:
            tmp.symlink_to(prior); tmp.replace(current); run('systemctl', 'restart', 'talent-cloud')
        else:
            run('systemctl', 'stop', 'talent-cloud')
        raise
    print('START=PASS')


def route(stage, manifest):
    journey_ready(); internal_ready(manifest['revision'])
    edge = json.loads(capture('docker', 'inspect', EDGE))[0]
    mount = [m for m in edge['Mounts'] if m['Destination'] == '/etc/caddy/Caddyfile' and m['Type']=='bind']
    assert len(mount) == 1
    config = Path(mount[0]['Source'])
    backup = ROOT/'backups'/('Caddyfile-'+PROXY_SHA)
    original = config.read_bytes()
    if digest(config) == PROXY_SHA:
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists(): backup.write_bytes(original); backup.chmod(0o600)
    else:
        assert backup.exists() and digest(backup) == PROXY_SHA, 'Proxy configuration drift; inspect before retry'
        original = backup.read_bytes()
    assert b'talent.muchenai.com' not in original
    added = f'\n# BEGIN TALENT DEMO\n{DOMAIN} {{\n    encode zstd gzip\n    reverse_proxy {gateway()}:3187\n}}\n# END TALENT DEMO\n'.encode()
    candidate = original+added
    assert config.read_bytes() in (original, candidate), 'Do not overwrite unrelated proxy changes'
    if config.read_bytes() != candidate:
        pending = stage/'Caddyfile.talent'
        pending.write_bytes(candidate)
        run('docker','cp',str(pending),EDGE+':/tmp/Caddyfile.talent')
        run('docker','exec',EDGE,'caddy','validate','--config','/tmp/Caddyfile.talent','--adapter','caddyfile')
        # Preserve the inode of the existing bind-mounted file.
        with config.open('wb') as f: f.write(candidate); f.flush(); os.fsync(f.fileno())
        try:
            run('docker','restart',EDGE)
            for attempt in range(30):
                try: journey_ready(); break
                except Exception:
                    if attempt == 29: raise
                    time.sleep(1)
        except Exception:
            with config.open('wb') as f: f.write(original); f.flush(); os.fsync(f.fileno())
            run('docker','restart',EDGE)
            for attempt in range(30):
                try: journey_ready(); break
                except Exception:
                    if attempt == 29: raise
                    time.sleep(1)
            print('PROXY_ROLLBACK=PASS')
            raise
    print('ROUTE=PASS; verify external TLS separately')


def verify(stage, manifest):
    journey_ready(); internal_ready(manifest['revision'])
    print('VERIFY_INTERNAL=PASS')


if __name__ == '__main__':
    phase, directory = sys.argv[1:]
    assert phase in ('prepare','migrate','start','route','verify')
    assert capture('hostname') == 'journey-next-staging'
    stage = Path(directory)
    assert stage.parent == ROOT/'staging' and stage.is_dir() and not stage.is_symlink()
    manifest = json.loads((stage/'manifest.json').read_text())
    assert len(manifest['revision']) == 40 and all(c in '0123456789abcdef' for c in manifest['revision'])
    globals()[phase](stage, manifest)
