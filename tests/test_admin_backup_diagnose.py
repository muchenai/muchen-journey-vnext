"""Backup diagnostics disclose fixed categories, never raw database errors."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('backup_diagnose',ROOT/'deploy/admin-reviewed/diagnose_backup.py')
diagnose=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose)


@pytest.mark.parametrize('message,expected',[
 ('no space left on device','DISK_FULL'),('Permission denied: secret','PERMISSION_DENIED'),
 ('password authentication failed for user secret','DATABASE_AUTHENTICATION'),
 ('syntax error at or near secret','SQL_SYNTAX'),('sensitive unknown error','UNCLASSIFIED_COMMAND_FAILURE'),
])
def test_errors_are_reduced_to_fixed_categories(message,expected,capsys):
    result=subprocess.CompletedProcess([],1,stdout=b'private rows',stderr=message.encode())
    with patch.object(diagnose.subprocess,'run',return_value=result):
        assert diagnose.probe('FACTS',['fixed']) is None
    printed=capsys.readouterr().out
    assert json.loads(printed)['category'] == expected
    assert message not in printed and 'private' not in printed and 'secret' not in printed


def test_success_does_not_echo_facts_or_credentials(capsys):
    result=subprocess.CompletedProcess([],0,stdout=b'private payload',stderr=b'secret')
    with patch.object(diagnose.subprocess,'run',return_value=result):
        assert diagnose.probe('FACTS',['fixed']) == b'private payload'
    assert json.loads(capsys.readouterr().out) == {'probe':'FACTS','status':'PASS'}


def test_timeout_does_not_echo_command_or_credentials(capsys):
    with patch.object(diagnose.subprocess,'run',side_effect=subprocess.TimeoutExpired(['secret'],1)):
        assert diagnose.probe('FACTS',['secret']) is None
    assert 'secret' not in capsys.readouterr().out


@pytest.mark.parametrize('state',['valid','changed','symlink'])
def test_remote_code_is_verified_before_loading(tmp_path,monkeypatch,state):
    path=tmp_path/'activate.py'
    path.write_bytes(b'fixed')
    monkeypatch.setattr(diagnose,'SOURCE',tmp_path)
    monkeypatch.setattr(diagnose,'EXPECTED',{'activate.py':hashlib.sha256(b'fixed').hexdigest()})
    if state == 'changed': path.write_bytes(b'changed')
    elif state == 'symlink':
        path.unlink()
        path.symlink_to(tmp_path/'outside')
    if state == 'valid': diagnose.verify_sources()
    else:
        with pytest.raises(AssertionError): diagnose.verify_sources()


def test_diagnosis_stays_read_only_and_protected():
    source=(ROOT/'deploy/admin-reviewed/diagnose_backup.py').read_text()
    workflow=(ROOT/'.github/workflows/admin-backup-diagnose.yml').read_text()
    assert 'default_transaction_read_only=on' in source
    assert '--file=/dev/null' in source
    assert '.activate(' not in source and '.backup_migrate(' not in source and '.stage(' not in source
    assert 'alembic upgrade' not in source
    assert 'environment: production-canary-uat' in workflow
    assert 'inputs.expected_commit == github.sha' in workflow
    assert len(diagnose.EXPECTED)==8
