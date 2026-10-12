import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('login_release', ROOT / 'deploy/feishu-login/activate.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class LoginReleaseTests(unittest.TestCase):
    def test_corrupted_chunk_stops_before_docker_load(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / 'api.part0000').write_bytes(b'corrupted')
            with patch.object(release, 'run') as run:
                with self.assertRaisesRegex(release.UpgradeError, 'CHUNK_SHA'):
                    release.import_image(package, 'api', {'chunks': [
                        {'file': 'api.part0000', 'sha256': '0' * 64}]}, '1' * 40)
                run.assert_not_called()

    def test_normalization_preserves_database_credentials_and_other_services(self):
        before = {'services': {name: {'image': name + '-old', 'environment': {
            'APP_RELEASE': 'old', 'DATABASE_URL': 'unchanged'}} for name in ('api', 'web', 'worker')}}
        after = copy.deepcopy(before)
        for name in release.SERVICES:
            after['services'][name]['image'] = name + '-new'
            after['services'][name]['environment']['APP_RELEASE'] = 'new'
        self.assertEqual(release.normalized(after, Path('/new'), Path('/old'), before), before)
        for name, key in [('api', 'DATABASE_URL'), ('worker', 'APP_RELEASE')]:
            invalid = copy.deepcopy(after)
            invalid['services'][name]['environment'][key] = 'changed'
            self.assertNotEqual(release.normalized(invalid, Path('/new'), Path('/old'), before), before)

    def exercise(self, failure=None):
        candidate = '1' * 40
        images = {'api': 'sha256:' + '2' * 64, 'web': 'sha256:' + '3' * 64}
        baseline = {'api': release.BASE_BACKEND, 'web': release.BASE_WEB}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            base = root / 'releases' / (release.BASE_WEB + '-web-labels')
            (base / 'secrets').mkdir(parents=True)
            for name in release.COPY_FILES:
                (base / name).write_bytes(b'preserve file')
            (base / '.deployment.env').write_text('API_IMAGE=api-old\nWEB_IMAGE=web-old\nCANDIDATE_COMMIT='+release.BASE_WEB+'\n')
            for name in release.SERVICES:
                (base / ('secrets/'+name+'.env')).write_text('APP_RELEASE='+baseline[name]+'\nDATABASE_URL=unchanged\n')
            (root / 'current').symlink_to(base)
            package = root / 'exploration-runs/1-1-activate'
            package.mkdir(parents=True)
            (package / 'manifest.json').write_text(json.dumps({'candidate': candidate,
                'base_backend': release.BASE_BACKEND, 'base_web': 'wrong' if failure == 'baseline' else release.BASE_WEB,
                'archives': {name: {} for name in release.SERVICES}, 'sdk_sha256': '4' * 64}))
            before = {'services': {name: {'image': name+'-old', 'environment': {
                'APP_RELEASE': baseline[name], 'DATABASE_URL': 'unchanged'}} for name in release.SERVICES}}
            operations = []
            active = [False]

            def compose(path, *args, **kwargs):
                if args[0] == 'config':
                    result = copy.deepcopy(before)
                    if path != base:
                        for name in release.SERVICES:
                            result['services'][name]['image'] = images[name]
                            result['services'][name]['environment']['APP_RELEASE'] = candidate
                    return json.dumps(result).encode()
                operations.append((path, args))
                active[0] = path != base
                if failure == 'startup' and active[0]:
                    raise release.UpgradeError('SIMULATED_STARTUP_FAILURE')
                return b''

            def container(name):
                return {'Id': name+('-new' if active[0] else '-old'),
                    'Image': images[name] if active[0] else name+'-old',
                    'Config': {'Env': ['APP_RELEASE='+(candidate if active[0] else baseline[name])]},
                    'State': {'Health': {'Status': 'healthy'}}}

            with patch.object(release, 'ROOT', root), patch.object(release.socket, 'gethostname', return_value='journey-next-staging'), \
                 patch.object(release, 'compose', side_effect=compose), patch.object(release, 'container', side_effect=container), \
                 patch.object(release, 'other_containers', return_value=['untouched-worker']), \
                 patch.object(release, 'import_image', side_effect=lambda package, name, entry, candidate: images[name]) as imported, \
                 patch.object(release, 'public_checks', side_effect=release.UpgradeError('SIMULATED_PUBLIC_FAILURE') if failure == 'public' else None):
                if failure:
                    with self.assertRaises(release.UpgradeError):
                        release.activate(package)
                    self.assertEqual((root/'current').resolve(), base)
                    if failure == 'baseline':
                        imported.assert_not_called()
                        self.assertEqual(operations, [])
                    else:
                        self.assertEqual(operations[-1][0], base)
                        self.assertFalse(active[0])
                else:
                    release.activate(package)
                    new = (root/'current').resolve()
                    self.assertNotEqual(new, base)
                    for name in release.SERVICES:
                        values = release.env_values((new/('secrets/'+name+'.env')).read_bytes())
                        self.assertEqual(values, {'APP_RELEASE': candidate, 'DATABASE_URL': 'unchanged'})
                    self.assertEqual(json.loads((new/'login-release-receipt.json').read_text())['migrations'], 0)
                for _, args in operations:
                    self.assertEqual(args[-2:], ('api', 'web'))
                    self.assertIn('--no-deps', args)
                    self.assertIn('--pull', args)
                    self.assertIn('never', args)

    def test_success_switches_both_services_without_migrations(self):
        self.exercise()

    def test_failed_startup_rolls_back_both_services(self):
        self.exercise('startup')

    def test_failed_public_login_checks_roll_back_both_services(self):
        self.exercise('public')

    def test_wrong_baseline_stops_before_loading_or_switching(self):
        self.exercise('baseline')

    def test_public_login_rejects_missing_bound_cookie(self):
        class Response(io.BytesIO):
            status = 200
            class headers:
                @staticmethod
                def get_all(*args):
                    return []
        sdk = b'verified-sdk'
        responses = [Response(json.dumps({'status': 'ready', 'release': 'candidate'}).encode()),
            Response(), Response(), Response(), Response(sdk),
            Response(json.dumps({'appId': release.APP_ID, 'state': 's' * 32}).encode())]
        with patch.object(release.urllib.request, 'urlopen', side_effect=responses):
            with self.assertRaisesRegex(release.UpgradeError, 'OAUTH_COOKIE_MISSING'):
                release.public_checks('candidate', release.hashlib.sha256(sdk).hexdigest())


if __name__ == '__main__':
    unittest.main()
