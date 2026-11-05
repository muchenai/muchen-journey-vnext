"""Verify loaded immutable images without another on-disk tar; retire own chunks."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import threading


def sha(path):
    assert path.is_file() and not path.is_symlink()
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_export(stream, expected):
    assert re.fullmatch('sha256:[0-9a-f]{64}', expected)
    hashes, manifest = {}, None
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for index, member in enumerate(archive):
            assert index < 20000, 'IMAGE_EXPORT_MEMBER_LIMIT'
            if member.isfile() and member.size <= 2_000_000:
                with archive.extractfile(member) as handle:
                    raw = handle.read()
                hashes[member.name] = hashlib.sha256(raw).hexdigest()
                if member.name == 'manifest.json':
                    assert manifest is None, 'DUPLICATE_IMAGE_MANIFEST'
                    manifest = json.loads(raw)
    assert manifest and len(manifest) == 1, 'IMAGE_EXPORT_MANIFEST'
    assert 'sha256:' + hashes.get(manifest[0]['Config'], '') == expected, 'IMAGE_CONFIG_CHANGED'


def verify_loaded_image(image, expected):
    assert re.fullmatch('sha256:[0-9a-f]{64}', image)
    process = subprocess.Popen(['docker', 'image', 'save', image], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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


def transport_plan(package, manifest):
    package = Path(package)
    assert package.is_dir() and not package.is_symlink() and package.resolve() == package
    assert set(manifest['archives']) == {'api', 'web'}
    planned = []
    for name in ('api', 'web'):
        entry = manifest['archives'][name]
        assert 0 < len(entry['chunks']) <= 1000
        rows = [(part['file'], part['sha256'], 2*1024**2) for part in entry['chunks']]
        assert len({row[0] for row in rows}) == len(rows)
        assert all(re.fullmatch(name+r'\.part[0-9]{4}', row[0]) for row in rows)
        rows.append((name+'.tar.gz', entry['gzip_sha256'], 4*1024**3))
        for filename, expected, limit in rows:
            assert re.fullmatch('[0-9a-f]{64}', expected)
            path = package / filename
            assert path.is_file() and not path.is_symlink() and path.resolve().parent == package
            assert 0 < path.stat().st_size <= limit and sha(path) == expected, 'TRANSPORT_CHANGED'
            planned.append((path, expected, path.stat().st_size))
    return planned


def cleanup_verified_transports(package, manifest):
    package = Path(package)
    assert package.parent == Path('/srv/journey-next-production/canary/exploration-runs')
    assert re.fullmatch('[0-9]+-[0-9]+-activate', package.name)
    # This function is called only after both candidate images and the previous
    # runtime images have passed verification. Validate the entire plan before
    # removing any file; all scripts/manifests/backups remain intact.
    plan = transport_plan(package, manifest)
    for path, expected, _ in plan:
        assert sha(path) == expected, 'TRANSPORT_CHANGED'
        path.unlink()
    print(json.dumps({'step': 'CURRENT_PACKAGE_TRANSPORTS_RETIRED', 'files': len(plan),
                      'reclaimed_bytes': sum(row[2] for row in plan)}), flush=True)
