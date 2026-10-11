"""Preparation must prove restore integrity without upgrading the live database."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('exploration_prepare', ROOT / 'deploy/exploration-release/prepare.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest = json.loads((ROOT / 'deploy/exploration-release/manifest.json').read_text())
        self.upgrade = prepare.ExplorationPreparation(manifest, self.root)
        self.upgrade.new = self.root / 'new'
        self.upgrade.backup = self.root / 'backup'
        (self.upgrade.new / 'secrets').mkdir(parents=True)
        self.upgrade.backup.mkdir()
        (self.upgrade.new / 'secrets/migration.env').write_text('DATABASE_URL=postgresql+psycopg://migrator:password@source:5432/production\n')
        self.before = {'migration':'0029_treasure_coaching_reviews','counts':{'users':42}}
        self.dump = self.upgrade.backup / 'canary.dump'
        self.dump.write_bytes(b'known-consistent-snapshot')
        self.encrypted = self.upgrade.backup / 'canary.dump.enc'
        self.verify = self.upgrade.backup / 'verify.dump'
        self.commands = []

    def run_command(self, args, **kwargs):
        self.commands.append(args)
        if args[-2:] == ['python','/tmp/db_facts.py']:
            return json.dumps(self.restored).encode()
        if args[0] == 'openssl':
            Path(args[args.index('-out')+1]).write_bytes(self.dump.read_bytes())
        return b''

    def subprocess_run(self, args, **kwargs):
        self.commands.append(args)
        return subprocess.CompletedProcess(args, 1 if 'inspect' in args else 0, b'', b'')

    def exercise_restore(self, restored):
        self.restored = restored
        with patch.object(prepare, 'run', side_effect=self.run_command), patch.object(prepare.subprocess, 'run', side_effect=self.subprocess_run):
            self.upgrade.restore_encrypt_migrate(self.before, self.dump, self.encrypted, self.verify, 'backup-key-that-is-long-enough-for-tests')

    def test_verified_backup_never_executes_live_migration_or_service_switch(self):
        self.exercise_restore(self.before)
        receipt = json.loads((self.upgrade.backup / 'backup-receipt.json').read_text())
        self.assertEqual(receipt['restore'], 'PASS')
        self.assertFalse(receipt['production_migration_applied'])
        self.assertTrue(self.encrypted.exists())
        for command in self.commands:
            self.assertNotIn('alembic', command)
            self.assertNotIn('compose', command)
            if 'pg_restore' in command:
                self.assertEqual(command[command.index('-d')+1], 'restore')
        self.assertFalse((self.upgrade.backup / 'restore.env').exists())

    def test_restore_mismatch_blocks_receipt_and_encryption(self):
        with self.assertRaisesRegex(prepare.UpgradeError, 'RESTORED_FACTS_DIFFER'):
            self.exercise_restore({'migration':'0029_treasure_coaching_reviews','counts':{'users':41}})
        self.assertFalse(self.encrypted.exists())
        self.assertFalse((self.upgrade.backup / 'backup-receipt.json').exists())
        self.assertFalse((self.upgrade.backup / 'restore.env').exists())
        self.assertTrue(any(command[:3] == ['docker','network','rm'] for command in self.commands))

    def test_existing_backup_is_preserved_and_requires_inspection(self):
        with self.assertRaisesRegex(prepare.UpgradeError, 'BACKUP_ALREADY_EXISTS'):
            self.upgrade.recover_incomplete_backup()
        self.assertEqual(self.dump.read_bytes(), b'known-consistent-snapshot')

    def test_unexpected_release_path_is_rejected(self):
        manifest = dict(self.upgrade.manifest, base_release='/srv/unrelated')
        with self.assertRaisesRegex(prepare.UpgradeError, 'BASE_PATH'):
            prepare.ExplorationPreparation(manifest, self.root)

if __name__ == '__main__':
    unittest.main()
