"""Bind Docker/containerd image identities to the original runtime config."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('academy_image_identity', ROOT / 'deploy/academy-release/image_transport.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)

OCI_INDEX = 'application/vnd.oci.image.index.v1+json'
OCI_MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
OCI_CONFIG = 'application/vnd.oci.image.config.v1+json'


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def blob_path(identity):
    return 'blobs/sha256/' + identity[7:]


def archive(files, extra=()):
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode='w') as stream:
        for name, raw in [*files.items(), *extra]:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            stream.addfile(member, io.BytesIO(raw))
    result.seek(0)
    return result


def fixture(*, mode='index', duplicate=False, attestation=True, wrong_size=False,
            platform='amd64', docker_media=False, nesting=0):
    layer = b'fixture layer content'
    layer_digest = digest(layer)
    config = {'architecture': 'amd64', 'os': 'linux',
              'rootfs': {'type': 'layers', 'diff_ids': [layer_digest]},
              'config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40}}}
    config_raw = encode(config)
    config_digest = digest(config_raw)
    if mode == 'classic':
        config_name = config_digest[7:] + '.json'
        return {config_name: config_raw, 'layer/layer.tar': layer,
                'manifest.json': encode([{'Config': config_name, 'Layers': ['layer/layer.tar']}])}, config_digest, config_digest

    files = {blob_path(config_digest): config_raw, blob_path(layer_digest): layer}

    def blob(value, media_type):
        raw = encode(value)
        identity = digest(raw)
        files[blob_path(identity)] = raw
        return {'mediaType': media_type, 'digest': identity, 'size': len(raw)}

    manifest_type = 'application/vnd.docker.distribution.manifest.v2+json' if docker_media else OCI_MANIFEST
    index_type = 'application/vnd.docker.distribution.manifest.list.v2+json' if docker_media else OCI_INDEX
    config_type = 'application/vnd.docker.container.image.v1+json' if docker_media else OCI_CONFIG
    image = {'schemaVersion': 2, 'mediaType': manifest_type,
             'config': {'mediaType': config_type, 'digest': config_digest, 'size': len(config_raw) + int(wrong_size)},
             'layers': [{'mediaType': 'application/vnd.oci.image.layer.v1.tar',
                         'digest': layer_digest, 'size': len(layer)}]}
    descriptor = blob(image, manifest_type)
    descriptor['platform'] = {'os': 'linux', 'architecture': platform}
    selected = descriptor
    if mode == 'index':
        entries = [descriptor]
        if duplicate:
            entries.append(dict(descriptor))
        if attestation:
            proof = blob({'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                          'artifactType': 'application/vnd.docker.attestation.manifest.v1+json'}, OCI_MANIFEST)
            proof['platform'] = {'os': 'unknown', 'architecture': 'unknown'}
            proof['annotations'] = {'vnd.docker.reference.type': 'attestation-manifest'}
            entries.append(proof)
        selected = blob({'schemaVersion': 2, 'mediaType': index_type, 'manifests': entries}, index_type)
        for _ in range(nesting):
            selected = blob({'schemaVersion': 2, 'mediaType': index_type, 'manifests': [selected]}, index_type)
    files['index.json'] = encode({'schemaVersion': 2, 'mediaType': index_type, 'manifests': [selected]})
    files['manifest.json'] = encode([{'Config': blob_path(config_digest), 'Layers': [blob_path(layer_digest)]}])
    return files, selected['digest'], config_digest


@pytest.mark.parametrize('mode', ['classic', 'manifest', 'index'])
def test_source_identity_resolves_config_from_classic_manifest_and_index(mode):
    files, identity, config = fixture(mode=mode)
    assert transport.source_config_digest(archive(files), identity) == config
    # A post-load rewrap has a different image Id, but the config must stay exact.
    transport.verify_export(archive(files), config)
    if mode != 'classic':
        assert identity != config
        with pytest.raises(AssertionError, match='IMAGE_CONFIG_CHANGED'):
            transport.verify_export(archive(files), identity)


def test_docker_schema2_manifest_list_is_supported_without_relaxing_binding():
    files, identity, config = fixture(docker_media=True)
    assert transport.source_config_digest(archive(files), identity) == config


def test_nested_oci_index_remains_bound_to_original_identity():
    files, identity, config = fixture(nesting=2)
    assert transport.source_config_digest(archive(files), identity) == config


def test_unknown_image_id_never_falls_back_to_docker_manifest_config():
    files, _, _ = fixture()
    with pytest.raises(AssertionError, match='IMAGE_SOURCE_ID_UNBOUND'):
        transport.source_config_digest(archive(files), 'sha256:' + 'e' * 64)


def test_original_index_content_must_hash_to_the_approved_image_id():
    files, identity, _ = fixture()
    files[blob_path(identity)] += b' '
    with pytest.raises(AssertionError, match='IMAGE_SOURCE_ID_UNBOUND'):
        transport.source_config_digest(archive(files), identity)


def test_config_blob_tampering_is_rejected_even_if_docker_manifest_points_to_it():
    files, identity, config = fixture()
    files[blob_path(config)] = files[blob_path(config)].replace(b'a' * 40, b'b' * 40, 1)
    with pytest.raises(AssertionError, match='IMAGE_DESCRIPTOR_HASH'):
        transport.source_config_digest(archive(files), identity)


def test_config_descriptor_size_is_checked_against_real_member_size():
    files, identity, _ = fixture(wrong_size=True)
    with pytest.raises(AssertionError, match='IMAGE_DESCRIPTOR_SIZE'):
        transport.source_config_digest(archive(files), identity)


def test_direct_manifest_descriptor_hash_is_checked():
    files, identity, _ = fixture()
    index = json.loads(files[blob_path(identity)])
    child = blob_path(index['manifests'][0]['digest'])
    files[child] = files[child].replace(b'"schemaVersion":2', b'"schemaVersion":3')
    with pytest.raises(AssertionError, match='IMAGE_DESCRIPTOR_HASH'):
        transport.source_config_digest(archive(files), identity)


def test_attestation_cannot_hide_a_missing_or_changed_direct_descriptor():
    files, identity, _ = fixture()
    index = json.loads(files[blob_path(identity)])
    del files[blob_path(index['manifests'][1]['digest'])]
    with pytest.raises(AssertionError, match='IMAGE_DESCRIPTOR_MISSING'):
        transport.source_config_digest(archive(files), identity)


def test_duplicate_linux_amd64_runtime_is_ambiguous_even_with_identical_config():
    files, identity, _ = fixture(duplicate=True)
    with pytest.raises(AssertionError, match='IMAGE_RUNTIME_AMBIGUOUS'):
        transport.source_config_digest(archive(files), identity)


def test_index_platform_must_select_the_linux_amd64_runtime():
    files, identity, _ = fixture(platform='arm64')
    with pytest.raises(AssertionError, match='IMAGE_RUNTIME_AMBIGUOUS'):
        transport.source_config_digest(archive(files), identity)


def test_docker_runtime_config_must_match_the_identity_bound_config():
    files, identity, config = fixture()
    changed = json.loads(files[blob_path(config)])
    changed['config']['Labels']['org.opencontainers.image.revision'] = 'b' * 40
    raw = encode(changed)
    files[blob_path(digest(raw))] = raw
    docker = json.loads(files['manifest.json'])
    docker[0]['Config'] = blob_path(digest(raw))
    files['manifest.json'] = encode(docker)
    with pytest.raises(AssertionError, match='IMAGE_RUNTIME_BINDING'):
        transport.source_config_digest(archive(files), identity)


def test_layers_and_diff_ids_must_agree():
    files, identity, _ = fixture()
    docker = json.loads(files['manifest.json'])
    docker[0]['Layers'] = []
    files['manifest.json'] = encode(docker)
    with pytest.raises(AssertionError, match='IMAGE_LAYER_COUNT'):
        transport.source_config_digest(archive(files), identity)


def test_docker_layers_must_match_the_identity_bound_runtime_manifest():
    files, identity, _ = fixture()
    files['unrelated-layer.tar'] = b'unrelated'
    docker = json.loads(files['manifest.json'])
    docker[0]['Layers'] = ['unrelated-layer.tar']
    files['manifest.json'] = encode(docker)
    with pytest.raises(AssertionError, match='IMAGE_RUNTIME_BINDING'):
        transport.source_config_digest(archive(files), identity)


def test_classic_config_identity_also_requires_linux_amd64_and_valid_diff_ids():
    files, _, config = fixture(mode='classic')
    name = config[7:] + '.json'
    changed = json.loads(files[name])
    changed['architecture'] = 'arm64'
    files[name] = encode(changed)
    with pytest.raises(AssertionError, match='IMAGE_CONFIG_PLATFORM'):
        transport.source_config_digest(archive(files), digest(files[name]))
    changed['architecture'] = 'amd64'
    changed['rootfs']['diff_ids'] = ['not-a-digest']
    files[name] = encode(changed)
    with pytest.raises(AssertionError, match='IMAGE_CONFIG_ROOTFS'):
        transport.source_config_digest(archive(files), digest(files[name]))


def test_ambiguous_docker_export_cannot_select_an_unrelated_image():
    files, identity, _ = fixture()
    docker = json.loads(files['manifest.json'])
    files['manifest.json'] = encode(docker * 2)
    with pytest.raises(AssertionError, match='IMAGE_EXPORT_MANIFEST'):
        transport.source_config_digest(archive(files), identity)


def test_duplicate_archive_members_are_rejected():
    files, identity, _ = fixture()
    with pytest.raises(AssertionError, match='IMAGE_ARCHIVE_DUPLICATE'):
        transport.source_config_digest(archive(files, [('manifest.json', files['manifest.json'])]), identity)


def test_metadata_retention_is_bounded(monkeypatch):
    files, identity, _ = fixture()
    monkeypatch.setattr(transport, 'METADATA_TOTAL_LIMIT', 10)
    with pytest.raises(AssertionError, match='IMAGE_METADATA_LIMIT'):
        transport.source_config_digest(archive(files), identity)


def test_large_layer_bytes_are_not_retained_as_metadata(monkeypatch):
    files, identity, config = fixture()
    files['unused-layer.tar'] = b'x' * (transport.METADATA_FILE_LIMIT + 1)
    monkeypatch.setattr(transport, 'METADATA_TOTAL_LIMIT', 10_000)
    assert transport.source_config_digest(archive(files), identity) == config


def test_graph_depth_is_bounded():
    files, identity, _ = fixture(nesting=9)
    with pytest.raises(AssertionError, match='IMAGE_DESCRIPTOR_GRAPH'):
        transport.source_config_digest(archive(files), identity)
