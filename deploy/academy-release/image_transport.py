"""Verify loaded immutable images without another on-disk tar; retire own chunks."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import threading


DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
INDEX_TYPES = {'application/vnd.oci.image.index.v1+json',
               'application/vnd.docker.distribution.manifest.list.v2+json'}
MANIFEST_TYPES = {'application/vnd.oci.image.manifest.v1+json',
                  'application/vnd.docker.distribution.manifest.v2+json'}
CONFIG_TYPES = {'application/vnd.oci.image.config.v1+json',
                'application/vnd.docker.container.image.v1+json'}
METADATA_FILE_LIMIT = 2_000_000
METADATA_TOTAL_LIMIT = 16_000_000


def _safe_member(name):
    return (isinstance(name, str) and bool(name) and not name.startswith('/')
            and '\\' not in name and all(part not in ('', '.', '..') for part in name.split('/')))


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _source_metadata(stream):
    """Retain bounded JSON metadata, never layer bytes or filesystem extractions."""
    files, metadata, retained = {}, {}, 0
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for index, member in enumerate(archive):
            assert index < 20_000, 'IMAGE_EXPORT_MEMBER_LIMIT'
            if member.isdir():
                continue
            assert _safe_member(member.name), 'IMAGE_ARCHIVE_PATH'
            assert member.name not in files, 'IMAGE_ARCHIVE_DUPLICATE'
            assert member.isfile(), 'IMAGE_ARCHIVE_MEMBER_TYPE'
            files[member.name] = member.size
            if member.size > METADATA_FILE_LIMIT:
                continue
            with archive.extractfile(member) as handle:
                raw = handle.read()
            try:
                value = json.loads(raw, object_pairs_hook=_unique_json)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(value, (dict, list)):
                continue
            retained += len(raw)
            assert retained <= METADATA_TOTAL_LIMIT, 'IMAGE_METADATA_LIMIT'
            metadata[member.name] = (value, 'sha256:' + hashlib.sha256(raw).hexdigest())
    return files, metadata


def source_config_digest(stream, expected_id):
    """Resolve config identity from an already SHA-verified ORIGINAL image tar.

    The caller must verify the complete original archive against the immutable
    build receipt first. Docker's image Id may identify a config, OCI manifest,
    or OCI index. Only a descriptor chain rooted at that exact Id can authorize
    a config; the archive's Docker manifest must select that same runtime image.
    Layer content is covered by the original tar hash and the config's diff_ids;
    reading it again into memory is neither necessary nor permitted here.
    """
    assert isinstance(expected_id, str) and DIGEST.fullmatch(expected_id), 'IMAGE_SOURCE_ID'
    files, metadata = _source_metadata(stream)
    docker = metadata.get('manifest.json', (None,))[0]
    assert isinstance(docker, list) and len(docker) == 1 and isinstance(docker[0], dict), 'IMAGE_EXPORT_MANIFEST'
    docker = docker[0]
    config_path = docker.get('Config')
    assert _safe_member(config_path) and config_path in metadata, 'IMAGE_CONFIG_MISSING'
    config, config_digest = metadata[config_path]
    assert isinstance(config, dict), 'IMAGE_CONFIG_INVALID'
    assert config.get('os') == 'linux' and config.get('architecture') == 'amd64', 'IMAGE_CONFIG_PLATFORM'
    rootfs = config.get('rootfs')
    assert isinstance(rootfs, dict) and rootfs.get('type') == 'layers', 'IMAGE_CONFIG_ROOTFS'
    diff_ids = rootfs.get('diff_ids')
    assert isinstance(diff_ids, list) and all(isinstance(value, str) and DIGEST.fullmatch(value) for value in diff_ids), 'IMAGE_CONFIG_ROOTFS'
    docker_layers = docker.get('Layers')
    assert isinstance(docker_layers, list) and len(docker_layers) == len(diff_ids), 'IMAGE_LAYER_COUNT'
    assert all(_safe_member(path) and path in files for path in docker_layers), 'IMAGE_LAYER_MISSING'
    if expected_id == config_digest:
        return config_digest

    def descriptor(value, allowed_types):
        assert isinstance(value, dict), 'IMAGE_DESCRIPTOR_INVALID'
        digest, size = value.get('digest'), value.get('size')
        assert isinstance(digest, str) and DIGEST.fullmatch(digest), 'IMAGE_DESCRIPTOR_DIGEST'
        assert type(size) is int and size >= 0, 'IMAGE_DESCRIPTOR_SIZE'
        assert value.get('mediaType') in allowed_types, 'IMAGE_DESCRIPTOR_TYPE'
        path = 'blobs/sha256/' + digest[7:]
        assert path in metadata, 'IMAGE_DESCRIPTOR_MISSING'
        assert files[path] == size, 'IMAGE_DESCRIPTOR_SIZE'
        document, actual = metadata[path]
        assert actual == digest, 'IMAGE_DESCRIPTOR_HASH'
        assert isinstance(document, dict), 'IMAGE_DESCRIPTOR_INVALID'
        return document, digest

    candidates, visited = [], 0

    def walk(document, identity, ancestry=(), inherited_platform=None):
        nonlocal visited
        visited += 1
        assert visited <= 512, 'IMAGE_DESCRIPTOR_GRAPH'
        assert identity not in ancestry and len(ancestry) < 8, 'IMAGE_DESCRIPTOR_GRAPH'
        assert document.get('schemaVersion') == 2, 'IMAGE_DESCRIPTOR_SCHEMA'
        media_type = document.get('mediaType')
        if media_type in INDEX_TYPES:
            entries = document.get('manifests')
            assert isinstance(entries, list) and 0 < len(entries) <= 128, 'IMAGE_INDEX_MANIFESTS'
            for entry in entries:
                child, digest = descriptor(entry, INDEX_TYPES | MANIFEST_TYPES)
                assert child.get('mediaType') == entry['mediaType'], 'IMAGE_DESCRIPTOR_TYPE'
                platform = entry.get('platform', inherited_platform)
                assert platform is None or isinstance(platform, dict), 'IMAGE_DESCRIPTOR_PLATFORM'
                # Attestations and other architectures cannot authorize the
                # linux/amd64 runtime. Their direct descriptor is still verified.
                if platform is not None and (platform.get('os'), platform.get('architecture')) != ('linux', 'amd64'):
                    continue
                walk(child, digest, ancestry + (identity,), platform)
            return
        assert media_type in MANIFEST_TYPES, 'IMAGE_DESCRIPTOR_TYPE'
        assert not document.get('artifactType'), 'IMAGE_RUNTIME_ARTIFACT'
        selected, selected_digest = descriptor(document.get('config'), CONFIG_TYPES)
        assert selected.get('os') == 'linux' and selected.get('architecture') == 'amd64', 'IMAGE_CONFIG_PLATFORM'
        layers = document.get('layers')
        assert isinstance(layers, list), 'IMAGE_MANIFEST_LAYERS'
        paths = []
        for layer in layers:
            assert isinstance(layer, dict), 'IMAGE_LAYER_DESCRIPTOR'
            digest, size = layer.get('digest'), layer.get('size')
            assert isinstance(digest, str) and DIGEST.fullmatch(digest), 'IMAGE_LAYER_DESCRIPTOR'
            assert type(size) is int and size >= 0, 'IMAGE_LAYER_DESCRIPTOR'
            path = 'blobs/sha256/' + digest[7:]
            assert path in files and files[path] == size, 'IMAGE_LAYER_SIZE'
            paths.append(path)
        candidates.append((selected_digest, paths))
        assert len(candidates) <= 1, 'IMAGE_RUNTIME_AMBIGUOUS'

    source_path = 'blobs/sha256/' + expected_id[7:]
    source = metadata.get(source_path)
    if source is None:
        source = metadata.get('index.json')
    assert source is not None and source[1] == expected_id, 'IMAGE_SOURCE_ID_UNBOUND'
    assert isinstance(source[0], dict), 'IMAGE_SOURCE_ID_UNBOUND'
    walk(source[0], expected_id)
    assert len(candidates) == 1, 'IMAGE_RUNTIME_AMBIGUOUS'
    assert candidates[0] == (config_digest, docker_layers), 'IMAGE_RUNTIME_BINDING'
    return config_digest


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
