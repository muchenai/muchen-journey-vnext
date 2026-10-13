import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
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

    def exercise(self, fail):
        baseline = 'fc591682249c34d7737144e7753ddef5da7aa554'
        web_baseline = '47d97050331282634de67fc063a282c2c4bb6e8c'
        candidate = '1' * 40
        image_id = 'sha256:' + '2' * 64
        config = b'{"rootfs":{"diff_ids":[]}}'
        config_digest = 'sha256:' + hashlib.sha256(config).hexdigest()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as tar:
            for name, data in [('manifest.json', b'[{"Config":"config.json"}]'), ('config.json', config)]:
                info = tarfile.TarInfo(name); info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        tar_bytes = buffer.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            base = root / 'releases' / (web_baseline + '-feishu-inline-login')
            (base / 'secrets').mkdir(parents=True)
            for name in release.COPY_FILES:
                (base / name).write_bytes(b'preserve file')
            (base / '.deployment.env').write_text('WEB_IMAGE=old\nCANDIDATE_COMMIT='+web_baseline+'\n')
            (base / 'secrets/web.env').write_text('APP_RELEASE='+web_baseline+'\n')
            (base / 'secrets/api.env').write_text('APP_RELEASE='+baseline+'\n')
            (root / 'current').symlink_to(base)
            package = root / 'exploration-runs/1-1-activate'
            package.mkdir(parents=True)
            zipped = gzip.compress(tar_bytes)
            (package / 'web.part0000').write_bytes(zipped)
            (package / 'manifest.json').write_text(json.dumps({'candidate': candidate, 'base_candidate': web_baseline, 'archive': {
                'chunks': [{'file': 'web.part0000', 'sha256': hashlib.sha256(zipped).hexdigest()}],
                'gzip_sha256': hashlib.sha256(zipped).hexdigest(), 'tar_sha256': hashlib.sha256(tar_bytes).hexdigest(),
                'config_digest': config_digest, 'reference': 'verified-web'}}))
            before = {'services': {'api': {'image': 'api-old'}, 'web': {'image': 'old', 'environment': {'APP_RELEASE': web_baseline}}}}
            operations = []
            def compose(path, *args, **kwargs):
                if args[0] == 'config':
                    result = copy.deepcopy(before)
                    if path != base:
                        result['services']['web'] = {'image': image_id, 'environment': {'APP_RELEASE': candidate}}
                    return json.dumps(result).encode()
                operations.append((path, args))
                if fail and path != base:
                    raise release.UpgradeError('SIMULATED_UNHEALTHY_WEB')
                return b''
            def run(args, **kwargs):
                if args[1:3] == ['image', 'inspect']:
                    return json.dumps([{'Id': image_id, 'Os': 'linux', 'Architecture': 'amd64',
                        'Config': {'Labels': {'org.opencontainers.image.revision': candidate}}}]).encode()
                if args[1:3] == ['image', 'save']:
                    Path(args[4]).write_bytes(tar_bytes)
                return b''
            def container(service):
                return {'Id': 'api-stable' if service == 'api' else 'web-id', 'Image': image_id,
                        'Config': {'Env': ['APP_RELEASE='+(baseline if service == 'api' else web_baseline)]}}
            def urlopen(*args, **kwargs):
                stream = io.BytesIO(json.dumps({'status': 'ready', 'release': candidate}).encode())
                stream.status = 200
                return stream
            with patch.object(release, 'ROOT', root), patch.object(release.socket, 'gethostname', return_value='journey-next-staging'), \
                 patch.object(release, 'compose', side_effect=compose), patch.object(release, 'run', side_effect=run), \
                 patch.object(release, 'container', side_effect=container), patch.object(release.urllib.request, 'urlopen', side_effect=urlopen):
                if fail:
                    with self.assertRaisesRegex(release.UpgradeError, 'SIMULATED_UNHEALTHY_WEB'):
                        release.activate(package)
                    self.assertEqual((root/'current').resolve(), base)
                    self.assertEqual(operations[-1][0], base)
                else:
                    release.activate(package)
                    new = (root/'current').resolve()
                    self.assertNotEqual(new, base)
                    self.assertEqual((new/'secrets/api.env').read_bytes(), (base/'secrets/api.env').read_bytes())
                    self.assertTrue(json.loads((new/'web-release-receipt.json').read_text())['api_container_unchanged'])
                self.assertTrue(operations)
                for _, args in operations:
                    self.assertEqual(args[-1], 'web')
                    self.assertIn('--no-deps', args)

    def test_success_switches_only_web(self):
        self.exercise(False)

    def test_failed_web_health_rolls_back_only_web(self):
        self.exercise(True)
