import copy
from contextlib import ExitStack, redirect_stdout
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'deploy/academy-release'))
spec = importlib.util.spec_from_file_location('web_release', ROOT / 'deploy/exploration-web/activate.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class WebReleaseTests(unittest.TestCase):
    def test_normalization_does_not_hide_api_changes(self):
        before = {'services': {'api': {'image': 'api-old'}, 'web': {'image': 'web-old', 'environment': {'APP_RELEASE': 'old'}}}}
        after = copy.deepcopy(before)
        after['services']['web'] = {'image': 'web-new', 'environment': {'APP_RELEASE': 'new'}}
        self.assertEqual(release.normalized(after, Path('/new'), Path('/old'), before['services']['web']), before)
        after['services']['api']['image'] = 'api-new'
        self.assertNotEqual(release.normalized(after, Path('/new'), Path('/old'), before['services']['web']), before)

    def exercise(self, failure=None, recovery=False):
        candidate = '1' * 40
        image_id = 'sha256:' + '2' * 64
        old_web = 'sha256:' + '3' * 64
        old_api = 'sha256:' + '4' * 64
        config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
        config_digest = 'sha256:' + hashlib.sha256(config).hexdigest()
        config_name = config_digest[7:] + '.json'
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as tar:
            for name, data in [('manifest.json', json.dumps([{'Config': config_name, 'Layers': []}]).encode()), (config_name, config)]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        tar_bytes = buffer.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            base = root / 'releases' / (release.BASE + '-academy')
            (base / 'secrets').mkdir(parents=True)
            for name in release.COPY_FILES:
                (base / name).write_bytes(b'preserve file')
            (base / '.deployment.env').write_text('WEB_IMAGE='+old_web+'\nCANDIDATE_COMMIT='+release.BASE+'\nAPI_IMAGE='+old_api+'\n')
            (base / 'secrets/web.env').write_text('APP_RELEASE='+release.BASE+'\n')
            (base / 'secrets/api.env').write_text('APP_RELEASE='+release.BASE+'\nDATABASE_URL=private\n')
            for name in (*release.AI_SECRETS, 'secrets/migration.env', 'secrets/future-secret'):
                (base / name).write_bytes(b'private configuration')
                (base / name).chmod(0o600)
            for name in release.AI_SECRETS:
                owner = (10001, 10001) if os.geteuid() == 0 else (os.geteuid(), os.getegid())
                os.chown(base / name, *owner)
            (base / 'activation-receipt.json').write_text(json.dumps({'status': 'PASS', 'release': release.BASE, 'schema': release.SCHEMA}))
            (base / 'schema-upgrade-prepared.json').write_text(json.dumps({'manifest': {
                'candidate': release.BASE, 'images': {'api': old_api, 'web': old_web}}}))
            (root / 'current').symlink_to(base)
            package = root / 'exploration-runs/1-1-activate'
            package.mkdir(parents=True)
            zipped = gzip.compress(tar_bytes)
            (package / 'web.part0000').write_bytes(zipped)
            (package / 'unrelated.keep').write_bytes(b'keep')
            if recovery:
                (package / 'web.tar.gz').write_bytes(b'tampered' if failure == 'archive' else zipped)
                original_stage = root / 'releases' / (candidate + '-login-layout')
                original_stage.mkdir()
                (original_stage / 'diagnostic.keep').write_bytes(b'original staged files')
            manifest = {'candidate': candidate, 'package_run_id': '12345678',
                'base_candidate': release.BASE, 'base_release': release.BASE + '-academy', 'schema': release.SCHEMA,
                'disk_budget': {'import': 1024}, 'archive': {
                'chunks': [{'file': 'web.part0000', 'sha256': hashlib.sha256(zipped).hexdigest()}],
                'gzip_sha256': hashlib.sha256(zipped).hexdigest(), 'gzip_bytes': len(zipped),
                'tar_sha256': hashlib.sha256(tar_bytes).hexdigest(), 'tar_bytes': len(tar_bytes),
                'config_digest': config_digest, 'reference': 'ghcr.io/muchenai/muchen-journey-vnext-web:'+candidate}}
            if failure == 'chunk':
                manifest['archive']['chunks'][0]['sha256'] = 'f' * 64
            (package / 'manifest.json').write_text(json.dumps(manifest))
            before = {'services': {'api': {'image': old_api},
                'web': {'image': old_web, 'environment': {'APP_RELEASE': release.BASE}}}}
            operations, runtime = [], {'release': release.BASE}
            def compose(path, *args, **kwargs):
                if args[0] == 'config':
                    result = copy.deepcopy(before)
                    if path != base:
                        result['services']['web'] = {'image': image_id, 'environment': {'APP_RELEASE': candidate}}
                    return json.dumps(result).encode()
                if args[0] == 'exec':
                    self.assertEqual(args[1:5], ('-T', 'api', 'python', '-c'))
                    self.assertIn('SET TRANSACTION READ ONLY', args[5])
                    return json.dumps(['wrong' if failure == 'schema' else release.SCHEMA]).encode()
                operations.append((path, args))
                runtime['release'] = release.BASE if path == base else candidate
                if failure == 'up' and path != base:
                    raise release.UpgradeError('SIMULATED_UNHEALTHY_WEB')
                return b''
            commands = []
            def run(args, **kwargs):
                commands.append(args)
                if args[1:3] == ['image', 'inspect']:
                    return json.dumps([{'Id': image_id, 'Os': 'linux', 'Architecture': 'amd64',
                        'Config': {'Labels': {'org.opencontainers.image.revision': candidate}}}]).encode()
                return b''
            def container(service):
                current = release.BASE if service == 'api' else runtime['release']
                requested = old_api if service == 'api' else old_web if current == release.BASE else image_id
                actual = requested if current == release.BASE else config_digest
                if failure == 'drift' and service == 'api':
                    requested = 'sha256:' + 'f' * 64
                return {'Id': service+'-stable', 'Image': actual,
                    'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                    'Config': {'Image': requested, 'Env': ['APP_RELEASE='+current],
                        'Labels': {'org.opencontainers.image.revision': current}}}
            def urlopen(*args, **kwargs):
                stream = io.BytesIO(json.dumps({'status': 'ready', 'release': runtime['release']}).encode())
                stream.status = 200
                return stream
            original_replace = os.replace
            def replace(src, dest):
                original_replace(src, dest)
                if failure == 'pointer' and src.name == 'current-'+candidate:
                    raise KeyboardInterrupt()
            original_write = release.write_new
            def write_new(path, data, *args):
                original_write(path, data, *args)
                if failure == 'receipt' and path.name == 'web-release-receipt.json':
                    raise OSError('simulated receipt interruption')
            with ExitStack() as stack:
                stack.enter_context(patch.object(release, 'ROOT', root))
                stack.enter_context(patch.object(release.socket, 'gethostname', return_value='journey-next-staging'))
                stack.enter_context(patch.object(release, 'compose', side_effect=compose))
                stack.enter_context(patch.object(release, 'run', side_effect=run))
                stack.enter_context(patch.object(release, 'container', side_effect=container))
                stack.enter_context(patch.object(release, 'protected_containers', return_value={'api': 'stable', 'worker': 'stable', 'db': 'stable'}))
                stack.enter_context(patch.object(release, 'check_space'))
                loaded = stack.enter_context(patch.object(release, 'verify_loaded_image'))
                stack.enter_context(patch.object(release.urllib.request, 'urlopen', side_effect=urlopen))
                stack.enter_context(patch.object(release.os, 'replace', side_effect=replace))
                stack.enter_context(patch.object(release, 'write_new', side_effect=write_new))
                if failure:
                    expected = KeyboardInterrupt if failure == 'pointer' else OSError if failure == 'receipt' else release.UpgradeError
                    with self.assertRaises(expected):
                        release.activate(package, recovery_id='20-1' if recovery else None)
                    self.assertEqual((root/'current').resolve(), base)
                    if failure in ('up', 'pointer', 'receipt'):
                        self.assertEqual(operations[-1][0], base)
                        new = root/'releases'/(candidate+'-login-layout')
                        self.assertFalse((new/'web-release-receipt.json').exists())
                        self.assertEqual(json.loads((new/'web-rollback-receipt.json').read_text())['result'], 'ROLLED_BACK')
                    else:
                        self.assertFalse(operations)
                        self.assertFalse(commands)
                else:
                    release.activate(package, recovery_id='20-1' if recovery else None)
                    new = (root/'current').resolve()
                    self.assertNotEqual(new, base)
                    for source in (base/'secrets').iterdir():
                        if source.name != 'web.env':
                            copied = new/'secrets'/source.name
                            self.assertEqual(copied.read_bytes(), source.read_bytes())
                            self.assertEqual((copied.stat().st_uid, copied.stat().st_gid, copied.stat().st_mode),
                                             (source.stat().st_uid, source.stat().st_gid, source.stat().st_mode))
                    loaded.assert_called_once_with(image_id, config_digest)
                    self.assertTrue(json.loads((new/'web-release-receipt.json').read_text())['other_containers_unchanged'])
                    self.assertFalse((package/'web.part0000').exists())
                    self.assertFalse((package/'web.tar.gz').exists())
                if recovery:
                    self.assertEqual((original_stage / 'diagnostic.keep').read_bytes(), b'original staged files')
                    if not failure:
                        self.assertEqual((root/'current').resolve().name, candidate+'-login-layout-recovery-20-1')
                self.assertEqual((package/'unrelated.keep').read_bytes(), b'keep')
                for _, args in operations:
                    self.assertEqual(args[-1], 'web')
                    self.assertIn('--no-deps', args)
                    self.assertIn('--no-build', args)

    def test_success_switches_only_web_and_preserves_all_secrets(self):
        self.exercise()

    def test_failed_web_health_rolls_back_only_web(self):
        self.exercise('up')

    def test_interrupt_after_pointer_replace_restores_base(self):
        self.exercise('pointer')

    def test_receipt_failure_rolls_back_and_removes_success_claim(self):
        self.exercise('receipt')

    def test_schema_mismatch_stops_before_import(self):
        self.exercise('schema')

    def test_baseline_image_drift_stops_before_import(self):
        self.exercise('drift')

    def test_changed_chunk_stops_before_import(self):
        self.exercise('chunk')

    def test_recovery_reuses_verified_archive_and_preserves_original_stage(self):
        self.exercise(recovery=True)

    def test_recovery_rejects_changed_existing_archive_before_import(self):
        self.exercise('archive', recovery=True)

    def test_mount_order_does_not_change_protected_snapshot(self):
        item = {'Name': '/api', 'Id': 'api-id', 'Image': 'image-id',
                'Config': {'Labels': {}, 'Env': ['SECRET=value']}, 'HostConfig': {},
                'Mounts': [{'Destination': '/a', 'Source': '/source-a', 'RW': False},
                           {'Destination': '/b', 'Source': '/source-b', 'RW': True}]}
        reordered = copy.deepcopy(item)
        reordered['Mounts'].reverse()
        outputs = [b'api-id', json.dumps([item]).encode(), b'api-id', json.dumps([reordered]).encode()]
        with patch.object(release, 'run', side_effect=outputs):
            self.assertEqual(release.protected_containers(), release.protected_containers())

    def test_runtime_differences_stop_without_exposing_configuration(self):
        item = {'Id': 'api-id', 'Image': 'image-id',
                'Config': {'Env': ['SECRET=old-private']}, 'HostConfig': {},
                'Mounts': [{'Destination': '/a', 'Source': '/private', 'RW': False}]}
        for field, value in [('Id', 'replaced-id'), ('Image', 'new-image'),
                             ('Config', {'Env': ['SECRET=new-private']}),
                             ('HostConfig', {'Privileged': True}),
                             ('Mounts', [{'Destination': '/a', 'Source': '/different-private', 'RW': False}])]:
            after = copy.deepcopy(item)
            after[field] = value
            output = io.StringIO()
            with self.subTest(field=field), patch.object(release, 'protected_containers', return_value={'/api': after}):
                with redirect_stdout(output), self.assertRaisesRegex(release.UpgradeError, 'BASE_RUNTIME_CHANGED'):
                    release.verify_protected_containers({'/api': item}, 'BASE_RUNTIME_CHANGED')
            message = json.loads(output.getvalue())
            self.assertEqual(message['changes'][0]['fields'], [field])
            self.assertNotIn('private', output.getvalue())
            self.assertNotIn('SECRET', output.getvalue())

    def test_added_or_removed_protected_container_is_detected(self):
        item = {'Id': 'api-id'}
        for before, after in [({}, {'/api': item}), ({'/api': item}, {})]:
            with patch.object(release, 'protected_containers', return_value=after):
                with redirect_stdout(io.StringIO()), self.assertRaisesRegex(release.UpgradeError, 'RUNTIME_CHANGED'):
                    release.verify_protected_containers(before, 'RUNTIME_CHANGED')

    def test_cleanup_checks_all_transports_before_any_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            package = root/'exploration-runs/1-1-activate'
            package.mkdir(parents=True)
            (package/'web.part0000').write_bytes(b'valid')
            (package/'web.tar.gz').write_bytes(b'tampered')
            entry = {'chunks': [{'file': 'web.part0000', 'sha256': hashlib.sha256(b'valid').hexdigest()}],
                     'gzip_sha256': hashlib.sha256(b'expected').hexdigest()}
            with patch.object(release, 'ROOT', root), self.assertRaisesRegex(release.UpgradeError, 'TRANSPORT_CHANGED'):
                release.cleanup_web_transports(package, entry)
            self.assertTrue((package/'web.part0000').exists())

    def test_release_contract_pins_main_build_and_shared_production_lock(self):
        workflow = (ROOT/'.github/workflows/exploration-web-release.yml').read_text()
        script = (ROOT/'deploy/exploration-web/activate.py').read_text()
        package = (ROOT/'deploy/exploration-web/package.py').read_text()
        self.assertIn('inputs.expected_commit == github.sha', workflow)
        self.assertIn('PACKAGE_RUN: ${{ inputs.package_run }}', workflow)
        self.assertIn("run['head_sha']==p['candidate']", workflow)
        self.assertIn("run['name']=='Mainline Candidate Gate'", workflow)
        self.assertIn('environment: production-canary-uat', workflow)
        self.assertIn('group: wp08-volcengine-staging', workflow)
        self.assertIn('timeout-minutes: 180', workflow)
        self.assertIn('disk_space.py', workflow)
        self.assertIn('.schema-upgrade.lock', script)
        self.assertIn('fcntl.LOCK_EX | fcntl.LOCK_NB', script)
        self.assertIn('source_config_digest(src', script)
        self.assertIn('verify_loaded_image(image', script)
        self.assertIn("pin['candidate'] = os.environ['CANDIDATE']", package)
        self.assertIn("['images']['web']", package)
        self.assertNotIn('docker build', workflow)
        self.assertNotIn('alembic upgrade', script)


if __name__ == '__main__':
    unittest.main()
