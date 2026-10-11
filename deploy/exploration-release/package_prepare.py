"""Verify the pinned Actions handoff and package only reviewed operations files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.wp31_candidate_binding import build_binding

def main():
    binding_dir = Path(os.environ['BINDING_DIR'])
    expected = json.loads((binding_dir / 'candidate-binding.json').read_text())
    actual = build_binding(binding_dir / 'release-manifest.json', '38117619977')
    assert actual == expected, 'CANDIDATE_BINDING_CHANGED'
    assert actual['application_candidate_sha'] == '05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292'
    source = ROOT / 'deploy/exploration-release'
    manifest = json.loads((source / 'manifest.json').read_text())
    for service in ('api','web'):
        image = actual['images'][service]
        reference = image['registry_reference'].split(':')[0] + '@' + image['registry_digest']
        assert manifest['images'][service] == reference, 'IMAGE_CHANGED'
    package = Path(os.environ['PACKAGE_DIR'])
    package.mkdir(mode=0o700, exist_ok=False)
    files = {
        'prepare.py': source / 'prepare.py',
        'manifest.json': source / 'manifest.json',
        'content_inventory.py': source / 'content_inventory.py',
        'canary_schema_upgrade.py': ROOT / 'scripts/canary_schema_upgrade.py',
        'wp31_database_snapshot.py': ROOT / 'scripts/wp31_database_snapshot.py',
        'db_facts.py': ROOT / 'deploy/production/db_facts.py',
        'db_facts_control.py': ROOT / 'deploy/production/db_facts.py',
        'grant_runtime.py': ROOT / 'deploy/production/greenfield_canary_grant_runtime.py',
    }
    checksums = []
    for name, path in files.items():
        shutil.copyfile(path, package / name)
        checksums.append(hashlib.sha256((package / name).read_bytes()).hexdigest() + '  ' + name)
    (package / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
    print('PINNED_PREPARATION_PACKAGE=PASS')

if __name__ == '__main__':
    main()
