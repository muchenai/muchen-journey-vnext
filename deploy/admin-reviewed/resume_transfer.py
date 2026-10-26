"""Resume the exact approved package before activation, retaining verified chunks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = '86c9cfd610f07c5ed3d0881339014f9ed1aec090'
SOURCE_RUN = '40330276649'
REMOTE = '/srv/journey-next-production/canary/exploration-runs/' + SOURCE_RUN + '-1-activate'


def files_to_send(files, inventory):
    if not isinstance(inventory, dict):
        raise ValueError('INVALID_INVENTORY')
    names = {path.name for path in files}
    if set(inventory) - names:
        raise ValueError('UNKNOWN_REMOTE_FILE')
    for name, digest in inventory.items():
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('INVALID_REMOTE_DIGEST')
    pending = []
    for path in files:
        if path.is_symlink() or not path.is_file() or not re.fullmatch('[A-Za-z0-9_.-]+', path.name):
            raise ValueError('INVALID_PACKAGE_FILE')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if inventory.get(path.name) != digest:
            pending.append(path)
    return pending


def remote_probe(names):
    if any(not re.fullmatch('[A-Za-z0-9_.-]+', name) for name in names):
        raise ValueError('INVALID_PACKAGE_FILE')
    # Read only. An existing release/backup means activation already began and
    # requires a separate recovery analysis, never this upload-only continuation.
    return '''import hashlib,json,os,pathlib,socket
assert socket.gethostname() == 'journey-next-staging', 'HOST'
root=pathlib.Path('/srv/journey-next-production/canary')
assert root.resolve() == root, 'ROOT_SYMLINK'
folder=pathlib.Path(REMOTE)
assert folder.is_dir() and folder.resolve() == folder, 'PACKAGE_PATH'
assert folder.stat().st_uid == 0, 'PACKAGE_OWNER'
for target in (root/'releases'/(CANDIDATE+'-admin-reviewed'), root/'backups'/('admin-reviewed-'+CANDIDATE)):
    assert not os.path.lexists(target), 'ACTIVATION_ALREADY_STARTED'
result={}
allowed=set(NAMES)
for path in folder.iterdir():
    assert path.name in allowed and not path.is_symlink() and path.is_file(), 'UNEXPECTED_PACKAGE_ENTRY'
    with path.open('rb') as stream:
        result[path.name]=hashlib.file_digest(stream,'sha256').hexdigest()
print(json.dumps(result))
'''.replace('REMOTE', repr(REMOTE)).replace('CANDIDATE', repr(CANDIDATE)).replace('NAMES', repr(names))


def main():
    if os.environ['REMOTE_PACKAGE'] != REMOTE or os.environ['CANDIDATE'] != CANDIDATE:
        raise ValueError('RELEASE_PIN')
    package = Path(os.environ['PACKAGE_DIR'])
    files = sorted(package.iterdir())
    manifest = json.loads((package/'manifest.json').read_text())
    if manifest['candidate'] != CANDIDATE or str(manifest['package_run_id']) != '40328731784':
        raise ValueError('PACKAGE_PIN')
    options = ['-i', os.environ['SSH_KEY'], '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
               '-o', 'StrictHostKeyChecking=accept-new', '-o', 'UserKnownHostsFile='+os.environ['SSH_KNOWN']]
    probe = subprocess.run(['ssh', *options, 'root@'+os.environ['JOURNEY_HOST'], 'python3 -'],
                           input=remote_probe([path.name for path in files]), text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if probe.returncode:
        raise ValueError('REMOTE_RESUME_PRECONDITION')
    pending = files_to_send(files, json.loads(probe.stdout))
    print(json.dumps({'step':'VERIFIED_UPLOAD_RESUME', 'verified_files':len(files)-len(pending),
                      'remaining_files':len(pending), 'remaining_bytes':sum(p.stat().st_size for p in pending)}), flush=True)
    spec = importlib.util.spec_from_file_location('transfer', ROOT/'deploy/exploration-release/transfer_package.py')
    transfer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transfer)
    transfer.transfer_files(pending, os.environ['JOURNEY_HOST'], REMOTE, options)


if __name__ == '__main__':
    main()
