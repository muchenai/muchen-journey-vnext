"""Recovery requires the actual restore connection and unchanged release facts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy/admin-reviewed'/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
with patch.dict(sys.modules):
    sys.modules['diagnose_backup']=load('diagnose_backup')
    restore=load('restore_backup')
    sys.modules['restore_backup']=restore
    recovery=load('recover_backup')


def state():
    original={'candidate':recovery.CANDIDATE,'package_run_id':'40328731784',
        'migrations':{'from':'0047_learner_notification_reads','to':'0047_learner_notification_reads'},
        'images':{'api':'sha256:'+'a'*64,'web':'sha256:'+'b'*64},'old_images':{}}
    old={'api':'sha256:'+'c'*64,'web':'sha256:'+'d'*64}
    prepared=json.loads(json.dumps(original))
    prepared['old_images']=old
    prepared['images']['api']='sha256:'+'e'*64
    return prepared,original,old


def test_valid_prepared_state_is_accepted():
    recovery.validate_state(*state(),False)


@pytest.mark.parametrize('change',['activated','extra','base','schema','image','candidate','run'])
def test_changed_or_activated_release_is_rejected(change):
    prepared,original,old=state()
    if change=='extra': prepared['unexpected']='changed'
    if change=='base': prepared['old_images']={}
    if change=='schema': prepared['migrations']['to']='other'
    if change=='image': prepared['images']['web']='latest'
    if change=='candidate': original['candidate']='f'*40
    if change=='run': original['package_run_id']='1'
    with pytest.raises(AssertionError): recovery.validate_state(prepared,original,old,change=='activated')


def test_existing_failure_evidence_is_preserved_and_later_steps_rejected(tmp_path):
    before=tmp_path/'before.json'
    before.write_text(json.dumps({'migration':'0047_learner_notification_reads'}))
    raw=before.read_bytes()
    recovery.verify_stopped_backup(tmp_path,lambda path:path.read_bytes())
    assert before.read_bytes()==raw
    (tmp_path/'backup-receipt.json').write_text('{}')
    with pytest.raises(AssertionError): recovery.verify_stopped_backup(tmp_path,lambda path:path.read_bytes())


def test_source_script_changes_are_rejected(tmp_path):
    hashes={}
    for name in recovery.SOURCE_FILES:
        (tmp_path/name).write_bytes(name.encode())
        hashes[name]=hashlib.sha256(name.encode()).hexdigest()
    recovery.verify_source_files(tmp_path,hashes)
    (tmp_path/'activate.py').write_bytes(b'changed')
    with pytest.raises(AssertionError): recovery.verify_source_files(tmp_path,hashes)


def test_bootstrap_socket_does_not_count_as_restore_ready():
    results=[subprocess.CompletedProcess([],2,b'',b'connection refused'),
             subprocess.CompletedProcess([],0,b'',b''),subprocess.CompletedProcess([],0,b'1\n',b'')]
    with patch.object(restore.subprocess,'run',side_effect=results) as run,patch.object(restore.time,'sleep'):
        restore.wait_restore_ready('scratch','private')
    assert run.call_count==3
    for call in run.call_args_list:
        args=call.args[0]
        assert args[args.index('-h')+1]=='127.0.0.1'
        assert args[args.index('-d')+1]=='restore'
        assert 'PGPASSWORD=private' in args and 'SELECT 1' in args and 'pg_isready' not in args


def test_readiness_timeout_is_bounded():
    with patch.object(restore.time,'monotonic',side_effect=[0,0,121]),patch.object(restore.time,'sleep'),\
         patch.object(restore.subprocess,'run',return_value=subprocess.CompletedProcess([],2,b'',b'')):
        with pytest.raises(RuntimeError,match='RESTORE_AUTHENTICATED_TCP_NOT_READY'):
            restore.wait_restore_ready('scratch','private')


def test_readiness_command_timeout_can_recover():
    with patch.object(restore.subprocess,'run',side_effect=[subprocess.TimeoutExpired(['private'],10),
         subprocess.CompletedProcess([],0,b'1',b'')]),patch.object(restore.time,'sleep'):
        restore.wait_restore_ready('scratch','private')


@pytest.mark.parametrize('matching',[True,False])
def test_restore_requires_matching_facts_before_encryption_or_receipt(tmp_path,matching):
    def require(value,code):
        if not value: raise AssertionError(code)
    module=Mock()
    module.require=require
    module.UpgradeError=RuntimeError
    module.read_file.side_effect=lambda path,**kwargs: b'DATABASE_URL=unused' if path.name=='migration.env' else path.read_bytes()
    module.changed_env.return_value=b'DATABASE_URL=isolated'
    module.write_new.side_effect=lambda path,raw: path.write_bytes(raw)
    module.digest.side_effect=lambda raw:hashlib.sha256(raw).hexdigest()
    app=SimpleNamespace(manifest={'candidate':'a'*40},backup=tmp_path,new=tmp_path,package=tmp_path,
        images={'api':'pinned-api','dbrestore':'pinned-db'},validate_restored_database=Mock())
    dump=tmp_path/'dump'; dump.write_bytes(b'complete backup')
    encrypted=tmp_path/'encrypted'; verify=tmp_path/'verify'
    before={'migration':'0047_learner_notification_reads','facts':'original'}
    def run(args,**kwargs):
        if args[-1]=='/tmp/db_facts.py':
            return json.dumps(before if matching else {**before,'facts':'changed'}).encode()
        if args[0]=='openssl':
            Path(args[args.index('-out')+1]).write_bytes(b'complete backup')
        return b''
    module.run.side_effect=run
    with patch.object(restore.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'')) as cleanup,\
         patch.object(restore,'wait_restore_ready') as ready:
        if matching:
            restore.restore_verified_backup(app,before,dump,encrypted,verify,'k'*32,module)
            assert json.loads((tmp_path/'backup-receipt.json').read_text())['restore']=='PASS'
            app.validate_restored_database.assert_called_once()
        else:
            with pytest.raises(AssertionError,match='RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT'):
                restore.restore_verified_backup(app,before,dump,encrypted,verify,'k'*32,module)
            assert not encrypted.exists() and not (tmp_path/'backup-receipt.json').exists()
            app.validate_restored_database.assert_not_called()
        ready.assert_called_once()
        assert any(c.args[0][:3]==['docker','rm','-f'] for c in cleanup.call_args_list)
        assert any(c.args[0][:3]==['docker','network','rm'] for c in cleanup.call_args_list)


def test_failure_reporting_never_discloses_command_or_raw_stderr(capsys):
    module=SimpleNamespace(UpgradeError=RuntimeError)
    with patch.dict(sys.modules,{'prepare':SimpleNamespace(),'canary_schema_upgrade':SimpleNamespace()}):
        restore.install_safe_command_reporting(module)
        with patch.object(restore.subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'permission denied password private')):
            with pytest.raises(RuntimeError,match='COMMAND_FAILED:PERMISSION_DENIED'):
                module.run(['docker','pg_restore','private'])
    assert 'private' not in capsys.readouterr().out


def test_recovery_is_pinned_protected_and_applies_no_schema_migration():
    source=(ROOT/'deploy/admin-reviewed/recover_backup.py').read_text()
    workflow=(ROOT/'.github/workflows/admin-backup-recover.yml').read_text()
    assert "'alembic', 'upgrade'" not in source
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert 'restore_backup.py' in workflow and 'diagnose_backup.py' in workflow
    assert '86c9cfd610f07c5ed3d0881339014f9ed1aec090' in workflow
