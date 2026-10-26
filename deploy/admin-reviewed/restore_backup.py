"""Wait for authenticated TCP, not the PostgreSQL bootstrap Unix socket."""
import hashlib
import json
import os
import subprocess
import sys
import time
from diagnose_backup import error_category


def phase(name):
    print(json.dumps({'backup_step':name}), flush=True)


def wait_restore_ready(name, password, *, timeout=120):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            result=subprocess.run(['docker','exec','-e','PGPASSWORD='+password,name,
                'psql','-h','127.0.0.1','-U','postgres','-d','restore','-v','ON_ERROR_STOP=1','-Atqc','SELECT 1'],
                capture_output=True,timeout=10)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0 and result.stdout.strip() == b'1':
            return
        time.sleep(1)
    raise RuntimeError('RESTORE_AUTHENTICATED_TCP_NOT_READY')


def install_safe_command_reporting(module):
    def checked(args, *, cwd=None, timeout=30, env=None, input_data=None):
        try:
            result=subprocess.run(args,cwd=cwd,capture_output=True,timeout=timeout,env=env,input=input_data)
        except subprocess.TimeoutExpired:
            raise module.UpgradeError('COMMAND_TIMEOUT') from None
        if result.returncode:
            component=next((name for name in ('pg_dump','pg_restore','psql','openssl','alembic','python') if name in args),'DOCKER')
            category=error_category(result.stderr)
            print(json.dumps({'command_component':component,'category':category,'exit_code':result.returncode}),flush=True)
            raise module.UpgradeError('COMMAND_FAILED:'+category)
        return result.stdout
    for target in (module,sys.modules['canary_schema_upgrade'],sys.modules['prepare']):
        target.run=checked


def restore_verified_backup(self, before, dump, encrypted, verify, backup_key, module):
    run,require,read_file,write_new,changed_env,digest,UpgradeError = (module.run,module.require,module.read_file,module.write_new,module.changed_env,module.digest,module.UpgradeError)
    phase('RESTORE_CONTAINER_SETUP')
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
        phase('RESTORE_AUTHENTICATED_TCP_READINESS')
        wait_restore_ready(restore_name, restore_password)
        phase('RESTORE_DATABASE_DUMP')
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
        phase('RESTORE_COMPARE_BUSINESS_FACTS')
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
        phase('RESTORE_VERIFY_EXISTING_SCHEMA')
        self.validate_restored_database(network, restore_env)
    finally:
        if container_created:
            subprocess.run(["docker", "rm", "-f", restore_name], capture_output=True)
        if network_created:
            subprocess.run(["docker", "network", "rm", network], capture_output=True)
        restore_env = self.backup / "restore.env"
        if restore_env.exists() and restore_env.is_file() and not restore_env.is_symlink():
            restore_env.unlink()
    phase('BACKUP_ENCRYPT_AND_VERIFY')
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

