"""Stage exact images and prove an encrypted backup; never migrate or switch live services.

Reuse the existing snapshot/restore machinery without changing its frozen older release.
The only entry point is prepare; restoring is restricted to a new isolated scratch DB.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from canary_schema_upgrade import (
    Upgrade, UpgradeError, ROOT, changed_env, digest, read_file, require, run, write_new,
)

CANDIDATE = "05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292"
BASE = "9a35f45053e903aa8e4d113aadbf7168d9ae9d0d"

class ExplorationPreparation(Upgrade):
    def __init__(self, manifest, package):
        super().__init__(manifest, package)
        self.base = Path(manifest["base_release"])
        require(self.base == ROOT / "releases" / (BASE + "-learner-35975348184-1"), "BASE_PATH")
        self.new = ROOT / "releases" / (CANDIDATE + "-exploration")
        self.backup = ROOT / "backups" / ("exploration-" + CANDIDATE)

    def recover_incomplete_backup(self):
        # Unknown prior work needs explicit reconciliation, never automatic deletion.
        require(not self.backup.exists(), "BACKUP_ALREADY_EXISTS_INSPECT_FIRST")

    def restore_encrypt_migrate(
        self,
        before: dict[str, object],
        dump: Path,
        encrypted: Path,
        verify: Path,
        backup_key: str,
    ) -> None:
        restore_name = "journey-schema-restore-" + str(self.manifest["candidate"])[:12]
        restore_password = hashlib.sha256((backup_key + str(self.manifest["candidate"])).encode()).hexdigest()
        network = restore_name
        network_created = False
        container_created = False
        require(subprocess.run(["docker", "network", "inspect", network], capture_output=True).returncode != 0, "RESTORE_NETWORK_EXISTS")
        require(subprocess.run(["docker", "container", "inspect", restore_name], capture_output=True).returncode != 0, "RESTORE_CONTAINER_EXISTS")
        try:
            run(["docker", "network", "create", network])
            network_created = True
            run([
                "docker", "run", "-d", "--name", restore_name, "--network", network,
                "-e", "POSTGRES_PASSWORD=" + restore_password, "-e", "POSTGRES_DB=restore",
                "-v", f"{self.backup}:/backup:ro", self.images["dbrestore"],
            ], timeout=120)
            container_created = True
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                probe = subprocess.run(["docker", "exec", restore_name, "pg_isready", "-U", "postgres", "-d", "restore"], capture_output=True)
                if probe.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise UpgradeError("RESTORE_DATABASE_NOT_READY")
            run([
                "docker", "exec", "-e", "PGPASSWORD=" + restore_password, restore_name,
                "pg_restore", "-h", "localhost", "-U", "postgres", "-d", "restore",
                "--exit-on-error", "--no-owner", "--no-acl", "/backup/canary.dump",
            ], timeout=900)
            restore_env = self.backup / "restore.env"
            restored_raw = changed_env(
                read_file(self.new / "secrets/migration.env"),
                {"DATABASE_URL": f"postgresql+psycopg://postgres:{restore_password}@{restore_name}:5432/restore"},
            )
            write_new(restore_env, restored_raw)
            restored_raw_json = run([
                "docker", "run", "--rm", "--network", network, "--env-file", str(restore_env),
                "-e", "PGOPTIONS=-c default_transaction_read_only=on", "-e", "REQUIRE_READ_ONLY=true",
                "-v", f"{self.package / 'db_facts_control.py'}:/tmp/db_facts.py:ro", self.images["api"],
                "python", "/tmp/db_facts.py",
            ], timeout=600)
            restored = json.loads(restored_raw_json)
            (self.backup / "restored.json").write_bytes(restored_raw_json)
            (self.backup / "restored.json").chmod(0o600)
            require(restored == before, "RESTORED_FACTS_DIFFER_FROM_DUMP_SNAPSHOT")
        finally:
            if container_created:
                subprocess.run(["docker", "rm", "-f", restore_name], capture_output=True)
            if network_created:
                subprocess.run(["docker", "network", "rm", network], capture_output=True)
            restore_env = self.backup / "restore.env"
            if restore_env.exists() and restore_env.is_file() and not restore_env.is_symlink():
                restore_env.unlink()
        encryption_env = os.environ.copy()
        encryption_env["CANARY_SCHEMA_BACKUP_KEY"] = backup_key
        run([
            "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt",
            "-in", str(dump), "-out", str(encrypted), "-pass", "env:CANARY_SCHEMA_BACKUP_KEY",
        ], timeout=900, env=encryption_env)
        run([
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",
            "-in", str(encrypted), "-out", str(verify), "-pass", "env:CANARY_SCHEMA_BACKUP_KEY",
        ], timeout=900, env=encryption_env)
        require(digest(read_file(verify, maximum=2_000_000_000)) == digest(read_file(dump, maximum=2_000_000_000)), "BACKUP_DECRYPT_VERIFY")
        receipt = {
            "candidate": self.manifest["candidate"], "migration": before["migration"],
            "backup_sha256": digest(read_file(encrypted, maximum=2_000_000_000)),
            "restore": "PASS", "production_migration_applied": False,
        }
        write_new(self.backup / "backup-receipt.json", json.dumps(receipt, sort_keys=True).encode())
        print(json.dumps(receipt, sort_keys=True), flush=True)


def main():
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(socket.gethostname() == "journey-next-staging", "UNEXPECTED_HOST")
    require(ROOT.resolve() == ROOT, "ROOT_SYMLINK")
    package = Path(__file__).resolve().parent
    manifest = json.loads(read_file(package / "manifest.json"))
    require(manifest["candidate"] == CANDIDATE and manifest["base_candidate"] == BASE, "CANDIDATE")
    require(manifest["migrations"] == {"from":"0029_treasure_coaching_reviews", "to":"0031_learner_feishu_login"}, "MIGRATIONS")
    payload = json.loads(sys.stdin.read(16384))
    os.umask(0o077)
    import fcntl
    descriptor = os.open(ROOT / ".schema-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        upgrade = ExplorationPreparation(manifest, package)
        upgrade.prepare(payload["actor"], payload["registry_token"], payload["migration_password"])
        inventory = upgrade.docker_api("secrets/migration.env", "python", "-c",
            read_file(package / "content_inventory.py").decode(), read_only=True)
        print(inventory.decode(), flush=True)
        upgrade.backup_migrate(payload["backup_key"])
        upgrade.verify_base()
        print(json.dumps({"preparation":"PASS", "candidate":CANDIDATE,
            "production_database_changed":False, "live_services_switched":False}))

if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"result":"STOP", "category":str(error) if isinstance(error, UpgradeError) else type(error).__name__, "do_not_retry_blindly":True}))
        raise SystemExit(1)
