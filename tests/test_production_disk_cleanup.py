"""Deletion requires exact scope, provenance and current runtime/rollback exclusions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name,ROOT/'deploy/production'/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

with patch.dict(sys.modules):
    sys.modules['disk_audit'] = load('disk_audit')
    cleanup = load('disk_cleanup')


def image():
    return {'id':'sha256:'+'a'*64,'revision':'b'*40,'source':'https://github.com/muchenai/muchen-journey-vnext',
        'refs':['ghcr.io/muchenai/muchen-journey-vnext-api@sha256:'+'c'*64],
        'created':'2026-01-01T00:00:00Z'}


def eligible(value,protected=(),revisions=(),referenced=()):
    return cleanup.image_eligible(value,protected,revisions,1800000000,referenced)


def test_retired_project_image_is_eligible():
    assert eligible(image())


@pytest.mark.parametrize('change',['runtime','protected','revision','source','unknown_alias','mutable_tag','tool','new','no_revision'])
def test_runtime_rollback_tools_recent_or_unproven_images_are_preserved(change):
    value = image(); protected=[]; revisions=[]; referenced=[]
    if change=='runtime': referenced=[value['id']]
    if change=='protected': protected=[value['id']]
    if change=='revision': revisions=[value['revision']]
    if change=='source': value['source']='https://example.test/unknown'
    if change=='unknown_alias': value['refs'].append('ghcr.io/other/project:latest')
    if change=='mutable_tag': value['refs'].append('ghcr.io/muchenai/muchen-journey-vnext-api:latest')
    if change=='tool': value['refs']=['ghcr.io/muchenai/muchen-journey-vnext-dbrestore:tool']
    if change=='new': value['created']='2030-01-01T00:00:00Z'
    if change=='no_revision': value['revision']='local'
    assert not eligible(value,protected,revisions,referenced)


def volume():
    return {'Name':'a'*64,'Driver':'local','Options':{},
        'Labels':{'journey.operation':'backup-restore','journey.candidate':'b'*40}}


def test_unreferenced_is_not_sufficient_volume_provenance():
    value=volume()
    assert cleanup.volume_eligible(value,{'b'*40},[])
    value['Labels']={'com.docker.volume.anonymous':''}
    assert not cleanup.volume_eligible(value,{'b'*40},[])


@pytest.mark.parametrize('change',['referenced','named','driver','options','unknown_candidate'])
def test_persistent_or_unknown_volumes_are_preserved(change):
    value=volume(); refs=[]
    if change=='referenced': refs=['container']
    if change=='named': value['Name']='business_attachments'
    if change=='driver': value['Driver']='nfs'
    if change=='options': value['Options']={'device':'external'}
    if change=='unknown_candidate': value['Labels']['journey.candidate']='c'*40
    assert not cleanup.volume_eligible(value,{'b'*40},refs)


def package(tmp_path,monkeypatch):
    monkeypatch.setattr(cleanup,'ROOT',tmp_path)
    path=tmp_path/'exploration-runs'/'123-1-activate'; path.mkdir(parents=True)
    archives={}
    for name in ['api','web']:
        raw=(name+'verified').encode(); digest=hashlib.sha256(raw).hexdigest()
        (path/(name+'.part0000')).write_bytes(raw)
        (path/(name+'.tar.gz')).write_bytes(raw)
        archives[name]={'gzip_sha256':digest,'chunks':[{'file':name+'.part0000','sha256':digest}]}
    (path/'manifest.json').write_text(json.dumps({'candidate':'a'*40,'archives':archives}))
    return path


def test_only_hash_bound_published_transports_are_planned_and_deleted(tmp_path,monkeypatch):
    path=package(tmp_path,monkeypatch)
    important=path/'business.dump.enc'; important.write_bytes(b'preserve')
    plan,preserved=cleanup.transport_plan({'a'*40:Path('/release')})
    assert len(plan)==4 and not preserved
    for row in plan: cleanup.remove_transport(row)
    assert important.read_bytes()==b'preserve' and (path/'manifest.json').exists()


def test_failed_publication_and_changed_copies_are_preserved(tmp_path,monkeypatch):
    path=package(tmp_path,monkeypatch)
    assert cleanup.transport_plan({})==([],[])
    (path/'api.tar.gz').write_bytes(b'unknown historical contents')
    plan,preserved=cleanup.transport_plan({'a'*40:Path('/release')})
    assert len(plan)==3 and preserved[0]['reason']=='HASH_MISMATCH'
    assert (path/'api.tar.gz').read_bytes()==b'unknown historical contents'


def test_changed_file_after_planning_is_not_deleted(tmp_path,monkeypatch):
    path=package(tmp_path,monkeypatch)
    plan,_=cleanup.transport_plan({'a'*40:Path('/release')})
    chosen=tmp_path/plan[0]['file']; chosen.write_bytes(b'replaced')
    with pytest.raises(AssertionError,match='TRANSPORT_CHANGED'):
        cleanup.remove_transport(plan[0])
    assert chosen.exists()


def test_transport_deletion_cannot_escape_to_backup_directories(tmp_path,monkeypatch):
    monkeypatch.setattr(cleanup,'ROOT',tmp_path)
    with pytest.raises(AssertionError): cleanup.remove_transport({'file':'../backups/canary.dump.enc'})


def test_protected_inventory_detects_deleted_or_changed_backup(tmp_path):
    path=tmp_path/'backup.dump.enc'; path.write_bytes(b'keep backup')
    before=cleanup.metadata_inventory(tmp_path)
    cleanup.unchanged(before,tmp_path)
    path.write_bytes(b'changed backup')
    with pytest.raises(AssertionError,match='PROTECTED_FILES_CHANGED'):
        cleanup.unchanged(before,tmp_path)


def test_cleanup_scope_is_exact_and_workflow_keeps_production_gate():
    scope=json.loads((ROOT/'deploy/production/disk-cleanup-scope-20261103.json').read_text())
    cleanup.scope_check(scope)
    assert len(scope['candidate_images'])==186
    scope['keep_release_chain'].pop()
    with pytest.raises(AssertionError,match='ROLLBACK_CHAIN_CHANGED'):
        cleanup.scope_check(scope)
    source=(ROOT/'deploy/production/disk_cleanup.py').read_text()
    assert "['docker','image','rm','--no-prune',reference]" in source
    assert "['docker','volume','rm',row['name']]" in source
    assert 'system prune' not in source and "'--force'" not in source
    workflow=(ROOT/'.github/workflows/production-disk-cleanup.yml').read_text()
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
