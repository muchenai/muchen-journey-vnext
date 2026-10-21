import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
original_paths = list(sys.path)
try:
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT / 'deploy/exploration-release'))
    spec = importlib.util.spec_from_file_location("review_workspace_activation", ROOT / "deploy/review-workspace/activate.py")
    activate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(activate)
finally:
    # Multiprocessing children inherit sys.path. Never expose the operational
    # inspect.py as a replacement for Python's standard-library inspect module.
    sys.path[:] = original_paths


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        manifest = json.loads((ROOT / 'deploy/review-workspace/baseline.json').read_text())
        manifest['candidate'] = 'a' * 40
        manifest['images'].update(api='sha256:' + 'a' * 64, web='sha256:' + 'b' * 64)
        self.release = activate.Activation(manifest, self.root)
        self.release.new = self.root / 'new'
        self.release.backup = self.root / 'backup'
        self.release.new.mkdir()
        self.release.backup.mkdir()
        (self.release.backup / 'canary.dump.enc').write_bytes(b'backup')
        (self.release.backup / 'backup-receipt.json').write_text(json.dumps({
            'candidate': manifest['candidate'], 'restore': 'PASS', 'backup_sha256': activate.digest(b'backup')}))
        (self.release.backup / 'migration-rehearsal.json').write_text(json.dumps({'schema': activate.TARGET_SCHEMA}))

    def test_env_addition_preserves_existing_secrets_and_configuration(self):
        before = b'SECRET=private-token\nAPP_RELEASE=old\n'
        after = activate.add_env(before, {'APP_RELEASE': 'new', 'FEISHU_LEARNER_REGISTRATION_ENABLED': 'true'})
        self.assertEqual(activate.env_values(after), {'SECRET': 'private-token', 'APP_RELEASE': 'new', 'FEISHU_LEARNER_REGISTRATION_ENABLED': 'true'})
        with self.assertRaisesRegex(activate.UpgradeError, 'ENV_CHANGE_INVALID'):
            activate.add_env(before, {'EXTRA': 'true\nSECRET=replaced'})

    def test_api_probe_mounts_secrets_instead_of_passing_values_in_environment(self):
        with patch.object(activate, 'run', return_value=b'{}') as run:
            self.release.docker_api('secrets/api.env', 'python', '-c', 'pass')
        command = run.call_args.args[0]
        for key, path in activate.SECRET_FILES.items():
            self.assertIn(f'{self.release.new / path}:/run/secrets/{key}:ro', command)
        self.assertFalse(any('AI_API_KEY=' in value or 'AI_FEISHU_APP_SECRET=' in value for value in command))

    def test_development_waiver_cannot_allow_braces_in_runtime(self):
        with patch.object(activate, 'run', return_value=b'{"braces":0}'):
            self.release.verify_runtime_dependencies()
        with patch.object(activate, 'run', return_value=b'{"braces":1}'):
            with self.assertRaisesRegex(activate.UpgradeError, 'WAIVED_DEPENDENCY_IN_RUNTIME'):
                self.release.verify_runtime_dependencies()

    def test_image_requires_exact_config_digest_platform_and_revision(self):
        row = {'Id': self.release.images['api'], 'Os': 'linux', 'Architecture': 'amd64',
               'Config': {'Labels': {'org.opencontainers.image.revision': self.release.manifest['candidate']}}}
        with patch.object(activate, 'run', return_value=json.dumps([row]).encode()):
            self.release.image_check('api', self.release.images['api'], self.release.manifest['candidate'])
        row['Id'] = 'sha256:' + 'c' * 64
        with patch.object(activate, 'run', return_value=json.dumps([row]).encode()):
            with self.assertRaisesRegex(activate.UpgradeError, 'CONFIG_DIGEST_MISMATCH'):
                self.release.image_check('api', self.release.images['api'], self.release.manifest['candidate'])

    def test_rewrapped_archive_requires_the_original_config_including_layer_ids(self):
        path = self.root / 'saved.tar'
        config = b'{"rootfs":{"diff_ids":["sha256:original-layer"]}}'
        with tarfile.open(path, 'w') as archive:
            for name, content in [('manifest.json', b'[{"Config":"config.json","Layers":[]}]'), ('config.json', config)]:
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        activate.verify_exported_config(path, 'sha256:' + activate.digest(config))
        with self.assertRaisesRegex(activate.UpgradeError, 'EXPORTED_CONFIG_DIGEST'):
            activate.verify_exported_config(path, 'sha256:' + 'f' * 64)

    def exercise(self, *, business_write=False, switch_failure=False, migration_failure=False):
        release = self.release
        up_calls = []
        guards = [{'users': [42, 'same']}, {'users': [42, 'same']},
                  {'users': [43, 'changed']} if business_write else {'users': [42, 'same']}]

        def up(path):
            up_calls.append(path)
            if switch_failure and path == release.new:
                raise activate.UpgradeError('SIMULATED_SWITCH_FAILURE')

        migrated = [False]

        def api(*args, **kwargs):
            if migration_failure and 'upgrade' in args:
                raise activate.UpgradeError('SIMULATED_MIGRATION_FAILURE')
            if 'current' in args:
                return (activate.TARGET_SCHEMA if migrated[0] else activate.SOURCE_SCHEMA).encode()
            if 'upgrade' in args:
                migrated[0] = True
            return b''

        with patch.object(release, 'verify_base'), patch.object(release, 'verify_prepared'), \
             patch.object(release, 'guard', side_effect=guards), patch.object(release, 'docker_api', side_effect=api), \
             patch.object(release, 'probe_old_api'), patch.object(release, 'up', side_effect=up), \
             patch.object(release, 'healthy'), patch.object(release, 'pointer'), \
             patch.object(release, 'current', return_value=release.base), patch.object(activate, 'compose'), \
             patch.object(activate, 'run'):
            if switch_failure or migration_failure:
                with self.assertRaises(activate.UpgradeError) as error:
                    release.activate()
                return up_calls, str(error.exception)
            release.activate()
        return up_calls, None

    def test_healthy_upgrade_retains_old_assignments_and_records_receipt(self):
        calls, error = self.exercise()
        self.assertEqual(calls, [self.release.new])
        self.assertIsNone(error)
        self.assertTrue(json.loads((self.release.new / 'activation-receipt.json').read_text())['old_assignments_unchanged'])

    def test_switch_failure_restores_old_application_before_any_business_write(self):
        calls, error = self.exercise(switch_failure=True)
        self.assertEqual(calls, [self.release.new, self.release.base])
        self.assertEqual(error, 'SIMULATED_SWITCH_FAILURE')

    def test_new_business_write_prevents_unsafe_automatic_rollback(self):
        calls, error = self.exercise(switch_failure=True, business_write=True)
        self.assertEqual(calls, [self.release.new])
        self.assertEqual(error, 'BUSINESS_WRITES_DETECTED_FORWARD_FIX_REQUIRED')

    def test_failed_migration_recovers_the_old_application(self):
        calls, error = self.exercise(migration_failure=True)
        self.assertEqual(calls, [self.release.base])
        self.assertEqual(error, 'SIMULATED_MIGRATION_FAILURE')

    def test_tampered_backup_blocks_before_stopping_services(self):
        (self.release.backup / 'canary.dump.enc').write_bytes(b'tampered')
        with patch.object(self.release, 'verify_base'), patch.object(self.release, 'verify_prepared'), patch.object(activate, 'compose') as compose:
            with self.assertRaisesRegex(activate.UpgradeError, 'BACKUP_CHANGED'):
                self.release.activate()
            compose.assert_not_called()


if __name__ == '__main__':
    unittest.main()
