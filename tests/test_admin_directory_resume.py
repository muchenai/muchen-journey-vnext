import contextlib
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('admin_resume', Path(__file__).resolve().parents[1] / 'deploy/admin-directory/resume.py')
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)


class ResumeTests(unittest.TestCase):
    def test_real_package_file_set_including_wp31_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hashes = {}
            for name in resume.SOURCE_FILES:
                raw = ('original ' + name).encode()
                (root / name).write_bytes(raw)
                hashes[name] = hashlib.sha256(raw).hexdigest()
            self.assertIn('wp31_database_snapshot.py', hashes)
            resume.verify_source_files(root, hashes)
            (root / 'wp31_database_snapshot.py').write_bytes(b'modified')
            with self.assertRaisesRegex(AssertionError, 'SOURCE_CHANGED'):
                resume.verify_source_files(root, hashes)

    def test_missing_extra_and_traversal_source_names_are_rejected(self):
        hashes = dict.fromkeys(resume.SOURCE_FILES, 'a' * 64)
        invalid = [{k:v for k,v in hashes.items() if k != 'activate.py'},
                   {**hashes, 'unexpected.py':'a'*64},
                   {**hashes, '../activate.py':'a'*64}]
        for values in invalid:
            with self.assertRaisesRegex(AssertionError, 'SOURCE_FILE_SET_CHANGED'):
                resume.verify_source_files(Path('nonexistent'), values)

    def probe(self, source):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch('sys.argv', []):
            exec(resume.probe_program(source, '--check'), {})
        self.assertNotIn('sensitive-token', output.getvalue())
        return json.loads(output.getvalue())

    def test_assertion_diagnostic_does_not_leak_private_message(self):
        result = self.probe("CHECKPOINT='DATABASE_OWNER_1'\ndef main():\n print('sensitive-token')\n raise AssertionError('sensitive-token')")
        self.assertEqual(result['checkpoint'], 'DATABASE_OWNER_1')
        self.assertEqual(result['code'], 'ASSERTION_FAILED')

    def test_known_assertion_retains_actionable_code(self):
        result = self.probe("CHECKPOINT='DIRECTORY_OWNER_2'\ndef main():\n raise AssertionError('OWNER_DIRECTORY_MISMATCH')")
        self.assertEqual(result['code'], 'OWNER_DIRECTORY_MISMATCH')

    def test_provider_diagnostic_exports_only_numeric_safe_details(self):
        result = self.probe("""CHECKPOINT='DIRECTORY_READ'
class ProviderError(Exception):
 code='DIRECTORY_BUSY'
 retryable=True
 details={'provider_code':99991400, 'http_status':429, 'message':'sensitive-token'}
def main():
 raise ProviderError('sensitive-token')
""")
        self.assertEqual(result['provider_code'], 99991400)
        self.assertTrue(result['retryable'])
        self.assertNotIn('message', result)

    def test_identity_conflict_never_retried_or_ignored(self):
        release = Mock()
        release.docker_api.return_value = json.dumps({'result':'STOP','code':'OWNER_IDENTITY_CONFLICT'})
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'OWNER_CHECK_STOPPED'):
                resume.owner_probe(release, '', '--check')
        self.assertEqual(release.docker_api.call_count, 1)
        self.assertTrue(release.docker_api.call_args.kwargs['read_only'])

    def test_only_transient_read_check_has_one_retry(self):
        release = Mock()
        release.docker_api.side_effect = [json.dumps({'result':'STOP','code':'DIRECTORY_BUSY','retryable':True}), json.dumps({'result':'PASS'})]
        with contextlib.redirect_stdout(io.StringIO()), patch.object(resume.time, 'sleep'):
            resume.owner_probe(release, '', '--check')
        self.assertEqual(release.docker_api.call_count, 2)
        release.docker_api.reset_mock(side_effect=True)
        release.docker_api.return_value = json.dumps({'result':'STOP','code':'DIRECTORY_BUSY','retryable':True})
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                resume.owner_probe(release, '', '--apply')
        self.assertEqual(release.docker_api.call_count, 1)

    def test_resumption_refuses_any_post_backup_or_activated_state(self):
        original = {'candidate':resume.CANDIDATE,'package_run_id':'39925261076',
            'migrations':{'from':'0038_review_admin_workspace','to':'0044_task_author_review'},
            'images':{'api':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}}
        resume.validate_state(original, original, backup_exists=False, activated=False)
        for backup, activated in [(True,False),(False,True)]:
            with self.assertRaisesRegex(AssertionError, 'PAST_RESUME_BOUNDARY'):
                resume.validate_state(original, original, backup_exists=backup, activated=activated)
        modified = {**original,'package_run_id':'1'}
        with self.assertRaisesRegex(AssertionError, 'PACKAGE_RUN_CHANGED'):
            resume.validate_state(modified, original, backup_exists=False, activated=False)

    def test_only_image_rewrapping_is_permitted(self):
        original = {'candidate':resume.CANDIDATE,'package_run_id':'39925261076',
            'migrations':{'from':'0038_review_admin_workspace','to':'0044_task_author_review'},
            'images':{'api':'sha256:'+'a'*64,'web':'sha256:'+'b'*64}, 'database':'production'}
        modified = {**original,'images':{**original['images'],'api':'sha256:'+'c'*64}}
        resume.validate_state(modified, original, backup_exists=False, activated=False)
        modified['database']='other'
        with self.assertRaisesRegex(AssertionError, 'PACKAGE_CHANGED'):
            resume.validate_state(modified, original, backup_exists=False, activated=False)
