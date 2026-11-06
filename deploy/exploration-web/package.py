"""Package only the Web image from an already verified mainline build."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.wp07_image_archive import verify_files
from scripts.wp31_candidate_binding import build_binding
sys.path.insert(0, str(ROOT / 'deploy/academy-release'))
from disk_space import disk_budget


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(build, output):
    pin = json.loads((ROOT / 'deploy/exploration-web/manifest.json').read_text())
    pin['candidate'] = os.environ['CANDIDATE']
    pin['package_run_id'] = os.environ['PACKAGE_RUN']
    assert re.fullmatch('[0-9a-f]{40}', pin['candidate'])
    assert re.fullmatch('[0-9]+', pin['package_run_id'])
    for line in (build / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        path = (build / name).resolve()
        assert path.parent == build.resolve() and sha(path) == expected
    binding = build_binding(build / 'release-manifest.json', pin['package_run_id'])
    assert binding == json.loads((build / 'candidate-binding.json').read_text())
    assert binding['application_candidate_sha'] == pin['candidate']
    verify_files(build / 'release-manifest.json', build / 'image-archives.json', build / 'images')
    entry = json.loads((build / 'image-archives.json').read_text())['images']['web']
    output.mkdir(mode=0o700, exist_ok=False)
    archive = output / 'web.tar.gz'
    with (build / 'images' / entry['file']).open('rb') as src, archive.open('xb') as dest:
        with gzip.GzipFile(fileobj=dest, mode='wb', compresslevel=3, mtime=0) as zipped:
            shutil.copyfileobj(src, zipped)
    parts = []
    with archive.open('rb') as stream:
        while chunk := stream.read(2 * 1024 * 1024):
            part = output / f'web.part{len(parts):04}'
            part.write_bytes(chunk)
            parts.append({'file': part.name, 'sha256': sha(part)})
    pin['archive'] = {'chunks': parts, 'gzip_sha256': sha(archive), 'gzip_bytes': archive.stat().st_size,
        'tar_sha256': entry['sha256'], 'tar_bytes': entry['size_bytes'], 'config_digest': entry['local_image_digest'],
        'reference': entry['runtime_reference']}
    archive.unlink()
    shutil.copyfile(ROOT / 'deploy/exploration-web/activate.py', output / 'activate.py')
    shutil.copyfile(ROOT / 'scripts/canary_schema_upgrade.py', output / 'canary_schema_upgrade.py')
    for name in ('image_transport.py', 'disk_space.py'):
        shutil.copyfile(ROOT / 'deploy/academy-release' / name, output / name)
    pin['disk_budget'] = disk_budget(sum(p.stat().st_size for p in output.iterdir()) + 1024**2,
        entry['size_bytes'], pin['archive']['gzip_bytes'])
    (output / 'manifest.json').write_text(json.dumps(pin))
    (output / 'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir())))
    print(json.dumps({'web_package': 'PASS', 'candidate': pin['candidate'], 'chunks': len(parts)}))


if __name__ == '__main__':
    package(Path(os.environ['BUILD_DIR']), Path(os.environ['PACKAGE_DIR']))
