"""An upload continuation must not reuse corrupted chunks or repeat activation."""
import hashlib
import importlib.util
import io
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('admin_resume', ROOT/'deploy/admin-reviewed/resume_transfer.py')
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


def test_skips_only_complete_matching_files(tmp_path):
    paths = [tmp_path/name for name in ('api.part0000','api.part0001','manifest.json')]
    for path in paths:
        path.write_bytes(b'complete')
    good = hashlib.sha256(b'complete').hexdigest()
    bad = hashlib.sha256(b'partial').hexdigest()
    assert resume.files_to_send(paths, {'api.part0000':good,'api.part0001':bad}) == paths[1:]
    assert resume.files_to_send(paths, {p.name:good for p in paths}) == []


@pytest.mark.parametrize('inventory', [[], {'other':'a'*64}, {'api.part0000':'invalid'}, {'api.part0000':None}])
def test_rejects_untrusted_inventory(tmp_path, inventory):
    path=tmp_path/'api.part0000'
    path.write_bytes(b'x')
    with pytest.raises(ValueError):
        resume.files_to_send([path], inventory)


@pytest.mark.parametrize('state', ['clean','release','backup','unknown','symlink','owner'])
def test_remote_probe_fails_before_transfer_when_activation_started_or_path_unsafe(tmp_path, state):
    root=tmp_path/'canary'
    folder=root/'exploration-runs'/'40330276649-1-activate'
    folder.mkdir(parents=True)
    (folder/'api.part0000').write_bytes(b'chunk')
    if state == 'release':
        (root/'releases'/(resume.CANDIDATE+'-admin-reviewed')).mkdir(parents=True)
    elif state == 'backup':
        (root/'backups'/('admin-reviewed-'+resume.CANDIDATE)).mkdir(parents=True)
    elif state == 'unknown':
        (folder/'unexpected').write_bytes(b'x')
    elif state == 'symlink':
        (folder/'api.part0000').unlink()
        (folder/'api.part0000').symlink_to(tmp_path/'outside')
    source=resume.remote_probe(['api.part0000']).replace('/srv/journey-next-production/canary', str(root))
    source=source.replace('.st_uid == 0', '.st_uid == -1' if state == 'owner' else '.st_uid == os.getuid()')
    with patch('socket.gethostname', return_value='journey-next-staging'), patch('sys.stdout', new_callable=io.StringIO) as out:
        if state == 'clean':
            exec(source, {})
            assert hashlib.sha256(b'chunk').hexdigest() in out.getvalue()
        else:
            reason = 'ACTIVATION_ALREADY_STARTED' if state in ('release','backup') else ('PACKAGE_OWNER' if state == 'owner' else 'UNEXPECTED_PACKAGE_ENTRY')
            with pytest.raises(AssertionError, match=reason):
                exec(source, {})


def test_continuation_retains_approval_pins_and_complete_checksum_gate():
    text=(ROOT/'.github/workflows/admin-reviewed-resume.yml').read_text()
    assert 'environment: production-canary-uat' in text
    assert 'cancel-in-progress: false' in text
    assert 'timeout-minutes: 180' in text
    assert "source['status']=='completed'" in text
    assert "source['run_attempt']==1" in text
    assert "source['head_sha']==p['candidate']" in text
    assert 'sha256sum -c SHA256SUMS && python3 activate.py' in text
    assert resume.REMOTE in text
    assert "PACKAGE_RUN: '40328731784'" in text
