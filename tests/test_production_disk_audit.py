"""Production disk accounting reports physical and logical usage without changing files."""
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('disk_audit',ROOT/'deploy/production/disk_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_mounts_exclude_virtual_network_and_duplicate_bind_mounts():
    raw = '\n'.join([
        '1 0 8:1 / / rw - ext4 /dev/vda1 rw',
        '2 1 8:1 / /duplicate rw - ext4 /dev/vda1 rw',
        '3 1 0:3 / /proc rw - proc proc rw',
        '4 1 0:4 / /run rw - tmpfs tmpfs rw',
        '5 1 8:2 / /data\\040disk rw - xfs /dev/vdb rw',
        '6 1 0:6 / /mnt/network rw - nfs server:/data rw',
        '7 1 8:1 /private /bind rw - ext4 /dev/vda1 rw',
    ])
    rows = audit.local_mounts(raw)
    assert [row['mount'] for row in rows] == ['/','/data disk']


def test_du_records_use_allocated_bytes_and_preserve_null_delimited_paths():
    assert audit.parse_du(b'4096\t/\x001024\t/folder with space\x00') == {'/':4096,'/folder with space':1024}


def test_file_categories_do_not_read_contents_or_follow_symlinks_and_deduplicate_hardlinks(tmp_path):
    root = tmp_path/'operations'; root.mkdir()
    original = root/'api.part0000'; original.write_bytes(b'private fixture contents')
    os.link(original,root/'api.part0001')
    (root/'api.tar.gz').write_bytes(b'compressed transport')
    (root/'credentials.env').write_bytes(b'private fixture contents')
    outside = tmp_path/'outside'; outside.write_bytes(b'must not count')
    (root/'outside-link').symlink_to(outside)
    with patch('builtins.open',side_effect=AssertionError('FILE_CONTENT_READ')):
        result = audit.file_accounting(root,'transport')
    assert result['metadata_errors'] == 0
    assert result['groups']['image_chunks']['files'] == 1
    assert result['groups']['compressed_image_archives']['files'] == 1
    assert result['groups']['other_operation_files']['files'] == 1
    assert 'private fixture' not in str(result)


def test_database_backups_are_reported_separately_from_temporary_plain_dumps(tmp_path):
    for name in ['canary.dump.enc','verify.dump','backup-receipt.json']:
        (tmp_path/name).write_bytes(b'data')
    assert set(audit.file_accounting(tmp_path,'backup')['groups']) == {
        'encrypted_database_dumps','temporary_plain_dumps','backup_metadata'}


def test_root_file_categories_count_swap_without_following_links_or_reading_contents(tmp_path):
    (tmp_path/'swapfile').write_bytes(b'allocated swap fixture')
    (tmp_path/'other-file').write_bytes(b'private fixture')
    (tmp_path/'subdirectory').mkdir()
    (tmp_path/'link').symlink_to(tmp_path/'swapfile')
    with patch('builtins.open',side_effect=AssertionError('FILE_CONTENT_READ')):
        result = audit.root_file_accounting(tmp_path)
    assert result['swap_files']['files'] == 1
    assert result['other_root_files']['files'] == 1
    assert 'private fixture' not in str(result)


def test_docker_logical_sizes_do_not_replace_unique_layer_total_or_include_labels():
    result = audit.docker_summary({'LayersSize':120,
        'Images':[{'Id':'a','Size':100,'SharedSize':80,'Containers':1,'Labels':{'private':'hidden'}},
                  {'Id':'b','Size':100,'SharedSize':80,'Containers':0}],
        'Containers':[{'Id':'c','ImageID':'a','State':'running','Labels':{'private':'hidden'}}],
        'Volumes':[{'Name':'volume','UsageData':{'Size':-1,'RefCount':0}}],
        'BuildCache':[{'Size':20,'Shared':True,'InUse':False}]})
    assert result['layer_bytes_reported_by_engine'] == 120
    assert result['unreferenced_image_count'] == 1
    assert result['volumes'][0]['size_bytes'] is None
    assert 'hidden' not in str(result) and 'Labels' not in str(result)
    assert 'must not be added' in result['note']


@pytest.mark.parametrize('endpoint',['/containers/create','/images/prune','/volumes/prune'])
def test_docker_read_transport_rejects_mutation_endpoints(endpoint):
    with pytest.raises(AssertionError,match='DOCKER_READ_ENDPOINT'):
        audit.docker_get(endpoint)


def test_workflow_preserves_production_gate_and_does_not_take_database_credentials():
    workflow = (ROOT/'.github/workflows/production-disk-audit.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert 'disk_audit.py' in workflow
    assert 'BACKUP_KEY' not in workflow and 'MIGRATION_PASSWORD' not in workflow
    source = (ROOT/'deploy/production/disk_audit.py').read_text()
    assert 'unlink(' not in source and 'rmtree(' not in source and 'write_text(' not in source
    assert "connection.request('GET',path)" in source
