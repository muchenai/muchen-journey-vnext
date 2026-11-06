import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('login_layout_recovery', ROOT / 'deploy/exploration-web/recover.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class LoginLayoutRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.package = self.root / 'source'
        self.package.mkdir()
        self.tar_bytes = b'verified original Web image archive'
        self.zipped = gzip.compress(self.tar_bytes, mtime=0)
        digest = lambda data: hashlib.sha256(data).hexdigest()
        self.manifest = {
            'candidate': recovery.CANDIDATE, 'package_run_id': recovery.PACKAGE_RUN,
            'base_candidate': recovery.BASE, 'base_release': recovery.BASE + '-academy',
            'schema': recovery.SCHEMA, 'disk_budget': {'import': 1024},
            'archive': {'reference': f'ghcr.io/muchenai/muchen-journey-vnext-web:{recovery.CANDIDATE}',
                        'config_digest': 'sha256:' + '1' * 64,
                        'tar_sha256': digest(self.tar_bytes), 'tar_bytes': len(self.tar_bytes),
                        'gzip_sha256': digest(self.zipped), 'gzip_bytes': len(self.zipped),
                        'chunks': [{'file': 'web.part0000', 'sha256': digest(self.zipped)}]},
        }
        for name in recovery.SOURCE_FILES:
            (self.package / name).write_text('original verified executable evidence\n')
        (self.package / 'web.part0000').write_bytes(self.zipped)
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest))
        sums = ''.join(recovery.file_info(path)['sha256'] + '  ' + path.name + '\n'
                       for path in sorted(self.package.iterdir()))
        (self.package / 'SHA256SUMS').write_text(sums)
        self.enterContext(patch.object(recovery, 'FILE_COUNT', 7))
        self.enterContext(patch.object(recovery, 'ORIGINAL_BYTES', sum(path.stat().st_size for path in self.package.iterdir())))
        self.controls = self.root / 'controls'
        recovery.prepare_proof(self.package, self.controls, '2' * 40)
        self.proof = json.loads((self.controls / 'original-package-proof.json').read_text())

    def test_original_package_and_proof_round_trip(self):
        recovery.verify_original_package(self.package, self.proof)
        self.assertEqual(self.proof['controls'].keys(), recovery.CONTROL_FILES)
        self.assertEqual({path.name for path in self.controls.iterdir()},
                         recovery.CONTROL_FILES | {'original-package-proof.json', 'SHA256SUMS'})
        self.assertFalse(any(path.name.startswith('web.part') for path in self.controls.iterdir()))

    def test_verified_assembled_archive_can_be_reused(self):
        archive = self.package / 'web.tar.gz'
        archive.write_bytes(self.zipped)
        recovery.verify_original_package(self.package, self.proof)
        self.assertEqual(archive.read_bytes(), self.zipped)

    def test_corrupt_assembled_archive_stops_without_overwriting(self):
        archive = self.package / 'web.tar.gz'
        archive.write_bytes(b'corrupt')
        with self.assertRaisesRegex(recovery.RecoveryError, 'ASSEMBLED_ARCHIVE_CHANGED'):
            recovery.verify_original_package(self.package, self.proof)
        self.assertEqual(archive.read_bytes(), b'corrupt')

    def test_original_script_tampering_is_detected(self):
        (self.package / 'activate.py').write_text('different executable')
        with self.assertRaisesRegex(recovery.RecoveryError, 'ORIGINAL_FILE_CHANGED'):
            recovery.verify_original_package(self.package, self.proof)

    def test_original_chunk_tampering_is_detected(self):
        (self.package / 'web.part0000').write_bytes(b'different archive')
        with self.assertRaisesRegex(recovery.RecoveryError, 'ORIGINAL_FILE_CHANGED'):
            recovery.verify_original_package(self.package, self.proof)

    def test_injected_source_file_is_rejected(self):
        (self.package / 'sitecustomize.py').write_text('untrusted')
        with self.assertRaisesRegex(recovery.RecoveryError, 'SOURCE_FILE_SET'):
            recovery.verify_original_package(self.package, self.proof)

    def test_known_cache_is_preserved_as_unexecuted_evidence(self):
        cache = self.package / '__pycache__'
        cache.mkdir()
        (cache / 'activate.cpython-312.pyc').write_bytes(b'original cache')
        recovery.verify_original_package(self.package, self.proof)
        self.assertTrue((cache / 'activate.cpython-312.pyc').exists())

    def test_unexpected_cache_module_is_rejected(self):
        cache = self.package / '__pycache__'
        cache.mkdir()
        (cache / 'unexpected.cpython-312.pyc').write_bytes(b'untrusted')
        with self.assertRaisesRegex(recovery.RecoveryError, 'SOURCE_CACHE_ENTRY'):
            recovery.verify_original_package(self.package, self.proof)

    def test_candidate_and_source_run_are_pinned(self):
        for field, value, message in [('source_run_id', '9', 'SOURCE_RUN_PIN'),
                                      ('source_package', '/other', 'SOURCE_PACKAGE_PIN')]:
            proof = copy.deepcopy(self.proof)
            proof[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(recovery.RecoveryError, message):
                recovery.validate_proof(proof)
        proof = copy.deepcopy(self.proof)
        proof['manifest']['candidate'] = 'a' * 40
        with self.assertRaisesRegex(recovery.RecoveryError, 'APPLICATION_PIN'):
            recovery.validate_proof(proof)

    def test_control_hash_proof_rejects_incomplete_control_set(self):
        self.proof['controls'].pop('activate.py')
        with self.assertRaisesRegex(recovery.RecoveryError, 'PROOF_FILE_SET'):
            recovery.validate_proof(self.proof)

    def test_preparation_requires_exact_original_file_set(self):
        (self.package / 'web.tar.gz').write_bytes(self.zipped)
        with self.assertRaisesRegex(recovery.RecoveryError, 'RECONSTRUCTED_FILE_SET'):
            recovery.prepare_proof(self.package, self.root / 'another', '2' * 40)

    def test_workflow_and_remote_control_contract(self):
        workflow = (ROOT / '.github/workflows/login-layout-recovery.yml').read_text()
        script = (ROOT / 'deploy/exploration-web/recover.py').read_text()
        self.assertIn('inputs.expected_commit == github.sha', workflow)
        self.assertIn('environment: production-canary-uat', workflow)
        self.assertIn('group: wp08-volcengine-staging', workflow)
        self.assertIn('artifact-ids: ${{ needs.prepare.outputs.artifact_id }}', workflow)
        self.assertIn("source['run_attempt']==1", workflow)
        self.assertIn("build['name']=='Mainline Candidate Gate'", workflow)
        self.assertIn('original-candidate/deploy/exploration-web/package.py', workflow)
        self.assertIn('sha256sum -c SHA256SUMS', workflow)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1 python3 recover.py', workflow)
        self.assertIn("len(proof['files'])==96", workflow)
        self.assertIn('187423441', workflow)
        self.assertNotIn('MIGRATION_PASSWORD', workflow)
        self.assertNotIn('BACKUP_KEY', workflow)
        self.assertNotIn('docker build', workflow)
        self.assertNotIn('transfer_package.py', workflow)
        self.assertIn("fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)", script)
        self.assertIn("control / 'activate.py'", script)
        self.assertNotIn("sys.path.insert(0, str(SOURCE))", script)
        self.assertIn("module.activate(SOURCE, recovery_id=payload['recovery_id'])", script)


if __name__ == '__main__':
    unittest.main()
