import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('exploration_transfer', ROOT / 'deploy/exploration-release/transfer_package.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)
REMOTE = '/srv/journey-next-production/canary/exploration-runs/123-1-activate'


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.files = [Path(self.tmp.name) / f'api.part{i:04}' for i in range(5)]
        for path in self.files:
            path.write_bytes(b'payload')

    def test_success_transfers_every_file_with_bounded_concurrency(self):
        processes = [Mock() for _ in self.files]
        for process in processes:
            process.poll.return_value = 0
        output = io.StringIO()
        with patch.object(transfer.subprocess, 'Popen', side_effect=processes) as start, redirect_stdout(output):
            transfer.transfer_files(self.files, 'private-host', REMOTE, ['-i', 'private-key'], parallel=2)
        self.assertEqual(start.call_count, len(self.files))
        self.assertIn('"files_completed": 5', output.getvalue())
        self.assertNotIn('private-host', output.getvalue())
        self.assertNotIn('private-key', output.getvalue())

    def test_failure_kills_active_uploads_and_does_not_start_queued_files(self):
        failed, running = Mock(), Mock()
        failed.poll.return_value = 1
        running.poll.return_value = None
        with patch.object(transfer.subprocess, 'Popen', side_effect=[failed, running]) as start:
            with self.assertRaisesRegex(transfer.TransferError, 'PACKAGE_TRANSFER_FAILED:api.part0000'):
                transfer.transfer_files(self.files, 'host', REMOTE, [], parallel=2)
        self.assertEqual(start.call_count, 2)
        running.kill.assert_called_once()
        running.wait.assert_called_once()

    def test_timeout_kills_all_active_uploads_without_waiting_for_more_files(self):
        processes = [Mock(), Mock()]
        for process in processes:
            process.poll.return_value = None
        with patch.object(transfer.subprocess, 'Popen', side_effect=processes) as start, \
             patch.object(transfer.time, 'monotonic', side_effect=[0, 0, 0, 901]):
            with self.assertRaisesRegex(transfer.TransferError, 'PACKAGE_TRANSFER_TIMEOUT:api.part0000'):
                transfer.transfer_files(self.files, 'host', REMOTE, [], parallel=2)
        self.assertEqual(start.call_count, 2)
        for process in processes:
            process.kill.assert_called_once()
            process.wait.assert_called_once()

    def test_invalid_remote_or_package_is_rejected_before_network_access(self):
        with patch.object(transfer.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(transfer.TransferError, 'INVALID_REMOTE_DIRECTORY'):
                transfer.transfer_files(self.files, 'host', '/srv/other', [])
            self.files[-1].unlink()
            with self.assertRaisesRegex(transfer.TransferError, 'INVALID_PACKAGE_FILE'):
                transfer.transfer_files(self.files, 'host', REMOTE, [])
            start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
