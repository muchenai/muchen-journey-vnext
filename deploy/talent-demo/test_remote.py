import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('remote', Path(__file__).with_name('remote.py'))
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class DeploymentBoundaries(unittest.TestCase):
    def test_archive_escape_and_symlink_rejected(self):
        for name, kind in [('dist-standalone/../../escape', tarfile.REGTYPE), ('/etc/escape', tarfile.REGTYPE), ('dist-standalone/link', tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d); archive = root/'payload.tar.gz'
                with tarfile.open(archive, 'w:gz') as tf:
                    member = tarfile.TarInfo(name); member.type = kind; member.linkname = '/etc'
                    tf.addfile(member, io.BytesIO())
                with self.assertRaises(AssertionError): remote.unpack_payload(archive, root/'release')
                self.assertFalse((root/'escape').exists())

    def route_fixture(self, root):
        config = root/'Caddyfile'; original = b'{ admin off }\njourney.example { respond ok }\n'
        config.write_bytes(original)
        stage = root/'stage'; stage.mkdir()
        edge = json.dumps([{'Mounts': [{'Destination': '/etc/caddy/Caddyfile', 'Type': 'bind', 'Source': str(config)}]}])
        return config, original, stage, edge

    def test_proxy_drift_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); config, original, stage, edge = self.route_fixture(root)
            with patch.object(remote, 'ROOT', root), patch.object(remote, 'journey_ready'), patch.object(remote, 'internal_ready'), patch.object(remote, 'capture', return_value=edge), patch.object(remote, 'run') as run:
                with self.assertRaisesRegex(AssertionError, 'drift'): remote.route(stage, {'revision': 'a'*40})
                run.assert_not_called(); self.assertEqual(config.read_bytes(), original)

    def test_failed_proxy_health_rolls_back_same_inode(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); config, original, stage, edge = self.route_fixture(root); inode = config.stat().st_ino
            checks = [None] + [RuntimeError('health failed')]*30 + [None]
            with patch.object(remote, 'ROOT', root), patch.object(remote, 'PROXY_SHA', hashlib.sha256(original).hexdigest()), patch.object(remote, 'journey_ready', side_effect=checks), patch.object(remote, 'internal_ready'), patch.object(remote, 'capture', return_value=edge), patch.object(remote, 'gateway', return_value='172.18.0.1'), patch.object(remote, 'run') as run, patch.object(remote.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'health failed'): remote.route(stage, {'revision': 'a'*40})
                self.assertEqual(config.read_bytes(), original); self.assertEqual(config.stat().st_ino, inode)
                self.assertEqual(sum(c.args == ('docker', 'restart', remote.EDGE) for c in run.call_args_list), 2)


if __name__ == '__main__': unittest.main()
