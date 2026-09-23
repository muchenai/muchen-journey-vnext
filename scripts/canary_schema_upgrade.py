"""Pinned, phase-separated Canary schema/application upgrade.

The package containing this file is immutable.  ``prepare`` only stages images and
files. ``backup-migrate`` creates an encrypted backup, proves a restore in an
ephemeral PostgreSQL container, and applies the additive migration while the old
application remains live. ``switch`` changes only API/Web containers and may roll
back while no coaching facts exist. ``backfill`` is the irreversible boundary:
after it creates coaching reviews, only a forward fix is safe because the old API
does not understand coaching review semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path("/srv/journey-next-production/canary")
PROJECT = "journey-next-greenfield-canary"
DATABASE = "journey_next_canary_20260901_c72fea5"
PACKAGE_FILES = ("manifest.json", "db_facts.py", "grant_runtime.py")
COPY_FILES = ("compose.canary.yaml", "compose.sh", "wp31_exec_env.py", "secrets/volcengine-rds-ca.pem")
ENV_FILES = (".deployment.env", "secrets/api.env", "secrets/web.env")
SNAPSHOT_ID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{8}-[0-9A-Fa-f]+$")


class UpgradeError(RuntimeError):
    """Fixed, non-sensitive failure category."""


def require(value: object, category: str) -> None:
    if not value:
        raise UpgradeError(category)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run(args: list[str], *, cwd: Path | None = None, timeout: int = 30,
        env: dict[str, str] | None = None, input_data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, timeout=timeout, env=env, input=input_data
        )
    except subprocess.TimeoutExpired:
        raise UpgradeError("COMMAND_TIMEOUT") from None
    if result.returncode:
        raise UpgradeError("COMMAND_FAILED")
    return result.stdout


def read_file(path: Path, *, maximum: int = 2_000_000) -> bytes:
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, "UNSAFE_FILE")
    require(path.stat().st_size <= maximum, "FILE_TOO_LARGE")
    return path.read_bytes()


def write_new(path: Path, raw: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fchmod(handle.fileno(), mode)
        os.fsync(handle.fileno())


def env_values(raw: bytes) -> dict[str, str]:
    require(b"\r" not in raw and b"\0" not in raw, "ENV_FORMAT")
    pairs: list[tuple[str, str]] = []
    for line in raw.decode().splitlines():
        require("=" in line, "ENV_FORMAT")
        key, value = line.split("=", 1)
        require(re.fullmatch(r"[A-Z][A-Z0-9_]*", key), "ENV_FORMAT")
        pairs.append((key, value))
    require(len(pairs) == len({key for key, _ in pairs}), "ENV_DUPLICATE")
    return dict(pairs)


def changed_env(raw: bytes, changes: dict[str, str]) -> bytes:
    before = env_values(raw)
    require(set(changes) <= before.keys(), "ENV_FIELD_MISSING")
    result = []
    for line in raw.splitlines(keepends=True):
        key = line.split(b"=", 1)[0].decode()
        if key in changes:
            result.append((key + "=" + changes[key]).encode() + (b"\n" if line.endswith(b"\n") else b""))
        else:
            result.append(line)
    after = b"".join(result)
    require(env_values(after) == {**before, **changes}, "ENV_EXTRA_CHANGE")
    return after


def load_manifest(path: Path, expected_sha256: str) -> dict[str, object]:
    raw = read_file(path)
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) and digest(raw) == expected_sha256, "MANIFEST_HASH")
    value = json.loads(raw)
    require(set(value) == {
        "schema_version", "base_candidate", "candidate", "database", "migrations",
        "images", "old_images", "compatibility",
    }, "MANIFEST_FIELDS")
    require(value["schema_version"] == 2, "MANIFEST_VERSION")
    require(value["base_candidate"] == "b8a5dd580eaec72945cbe4f0e37c1152ee4645a1", "BASE_CANDIDATE")
    require(re.fullmatch(r"[0-9a-f]{40}", str(value["candidate"])), "CANDIDATE")
    require(value["database"] == DATABASE, "DATABASE_CHANGED")
    require(value["migrations"] == {"from": "0028_canary_main_merge", "to": "0029_treasure_coaching_reviews"}, "MIGRATION_RANGE")
    require(value["compatibility"] == "ADDITIVE_SCHEMA_THEN_IMMUTABLE_BACKFILL", "COMPATIBILITY")
    require(set(value["images"]) == {"api", "web", "dbrestore"}, "IMAGE_FIELDS")
    require(set(value["old_images"]) == {"api", "web"}, "OLD_IMAGE_FIELDS")
    patterns = {
        "api": r"ghcr\.io/muchenai/muchen-journey-vnext-api@sha256:[0-9a-f]{64}",
        "web": r"ghcr\.io/muchenai/muchen-journey-vnext-web@sha256:[0-9a-f]{64}",
        "dbrestore": r"ghcr\.io/muchenai/muchen-journey-vnext-dbrestore@sha256:[0-9a-f]{64}",
    }
    for name, pattern in patterns.items():
        require(re.fullmatch(pattern, str(value["images"][name])), "IMAGE_REFERENCE")
    for name in ("api", "web"):
        require(re.fullmatch(patterns[name], str(value["old_images"][name])), "OLD_IMAGE_REFERENCE")
        require(value["images"][name] != value["old_images"][name], "IMAGE_UNCHANGED")
    return value


def compose(path: Path, *args: str, timeout: int = 30) -> bytes:
    return run([str(path / "compose.sh"), "-f", "compose.canary.yaml", *args], cwd=path, timeout=timeout)


class Upgrade:
    def __init__(self, manifest: dict[str, object], package: Path):
        self.manifest = manifest
        self.package = package
        self.base = ROOT / "releases" / (str(manifest["base_candidate"]) + "-app-upgrade")
        self.new = ROOT / "releases" / (str(manifest["candidate"]) + "-schema-upgrade")
        self.backup = ROOT / "backups" / ("schema-" + str(manifest["candidate"]))

    @property
    def images(self) -> dict[str, str]:
        return self.manifest["images"]  # type: ignore[return-value]

    @property
    def old_images(self) -> dict[str, str]:
        return self.manifest["old_images"]  # type: ignore[return-value]

    def current(self) -> Path:
        pointer = ROOT / "current"
        require(pointer.is_symlink(), "CURRENT_NOT_SYMLINK")
        return pointer.resolve()

    def containers(self, images: dict[str, set[str]], *, allow_missing: bool = False) -> list[dict[str, object]]:
        expected = {PROJECT + "-api-1", PROJECT + "-web-1"}
        actual = set(run([
            "docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + PROJECT,
            "--format", "{{.Names}}",
        ]).decode().splitlines())
        require(actual <= expected and (allow_missing or actual == expected), "EXTRA_OR_MISSING_CONTAINER")
        rows = json.loads(run(["docker", "inspect", *sorted(actual)])) if actual else []
        for row in rows:
            labels = row["Config"]["Labels"]
            service = labels["com.docker.compose.service"]
            require(service in images and row["Config"]["Image"] in images[service], "UNEXPECTED_IMAGE")
        return rows

    def healthy(self, release: Path, candidate: str, images: dict[str, str], *, public: bool = True) -> None:
        for row in self.containers({name: {reference} for name, reference in images.items()}):
            require(row["State"]["Running"] and row["State"].get("Health", {}).get("Status") == "healthy", "UNHEALTHY")
            values = dict(pair.split("=", 1) for pair in row["Config"]["Env"])
            require(values.get("APP_RELEASE") == candidate, "RUNTIME_RELEASE")
        if public:
            ready = json.loads(run([
                "curl", "-fsS", "--connect-timeout", "3", "--max-time", "10",
                "https://journey.muchenai.com/health/ready",
            ]))
            require(ready == {"status": "ready", "release": candidate}, "PUBLIC_HEALTH")

    def image_check(self, name: str, reference: str, candidate: str | None = None) -> None:
        row = json.loads(run(["docker", "image", "inspect", reference]))[0]
        require(row["Os"] == "linux" and row["Architecture"] == "amd64", "IMAGE_PLATFORM")
        require(reference in row.get("RepoDigests", []), "IMAGE_DIGEST")
        if candidate is not None:
            require(row["Config"]["Labels"].get("org.opencontainers.image.revision") == candidate, "IMAGE_REVISION")

    def verify_base(self) -> None:
        require(self.current() == self.base and self.base.resolve() == self.base, "CURRENT_CHANGED")
        self.healthy(self.base, str(self.manifest["base_candidate"]), self.old_images)
        api = env_values(read_file(self.base / "secrets/api.env"))
        require(urlsplit(api["DATABASE_URL"]).path == "/" + DATABASE, "DATABASE_CHANGED")
        require(api.get("ALLOW_FIXTURE_IDENTITY") == "false", "FIXTURE_IDENTITY")

    def prepare(self, actor: str, registry_token: str, migration_password: str) -> None:
        self.verify_base()
        require(not self.new.exists() and not self.new.is_symlink(), "PREPARATION_EXISTS")
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", actor), "ACTOR_INVALID")
        require(registry_token and len(registry_token) <= 4096 and not any(c.isspace() for c in registry_token), "TOKEN_INVALID")
        require(len(migration_password) >= 20 and "\n" not in migration_password and "\r" not in migration_password, "MIGRATION_SECRET_INVALID")
        originals = {name: read_file(self.base / name) for name in COPY_FILES + ENV_FILES}
        api_values = env_values(originals["secrets/api.env"])
        parsed = urlsplit(api_values["DATABASE_URL"])
        require(parsed.scheme == "postgresql+psycopg" and parsed.hostname and parsed.port, "DATABASE_URL")
        migration_url = urlunsplit((
            parsed.scheme,
            f"journey_next_migrator:{quote(migration_password, safe='')}@{parsed.hostname}:{parsed.port}",
            parsed.path,
            parsed.query,
            "",
        ))
        docker_config = Path(tempfile.mkdtemp(prefix=".schema-registry-", dir=self.package))
        previous = os.environ.get("DOCKER_CONFIG")
        os.environ["DOCKER_CONFIG"] = str(docker_config)
        try:
            login = subprocess.run(
                ["docker", "login", "ghcr.io", "-u", actor, "--password-stdin"],
                input=registry_token.encode(), capture_output=True, timeout=30,
            )
            require(login.returncode == 0, "REGISTRY_LOGIN_FAILED")
            registry_token = ""
            for name, reference in self.images.items():
                run(["docker", "pull", reference], timeout=1800)
                self.image_check(name, reference, str(self.manifest["candidate"]) if name in {"api", "web"} else None)
            for name, reference in self.old_images.items():
                run(["docker", "pull", reference], timeout=1800)
                self.image_check(name, reference, str(self.manifest["base_candidate"]))
        finally:
            if previous is None:
                os.environ.pop("DOCKER_CONFIG", None)
            else:
                os.environ["DOCKER_CONFIG"] = previous
            require(docker_config.resolve().parent == self.package and not docker_config.is_symlink(), "CREDENTIAL_PATH")
            shutil.rmtree(docker_config)
        self.new.mkdir(mode=0o700)
        (self.new / "secrets").mkdir(mode=0o700)
        for name in COPY_FILES:
            mode = 0o644 if name.endswith(".pem") else stat.S_IMODE((self.base / name).stat().st_mode)
            write_new(self.new / name, originals[name], mode)
        changes = {
            ".deployment.env": {
                "CANDIDATE_COMMIT": str(self.manifest["candidate"]),
                "API_IMAGE": self.images["api"],
                "WEB_IMAGE": self.images["web"],
            },
            "secrets/api.env": {"APP_RELEASE": str(self.manifest["candidate"])},
            "secrets/web.env": {"APP_RELEASE": str(self.manifest["candidate"])},
        }
        for name in ENV_FILES:
            write_new(self.new / name, changed_env(originals[name], changes[name]))
        migration_raw = changed_env(
            originals["secrets/api.env"],
            {"APP_RELEASE": str(self.manifest["candidate"]), "DATABASE_URL": migration_url},
        )
        write_new(self.new / "secrets/migration.env", migration_raw)
        for name in PACKAGE_FILES:
            # These are non-secret scripts mounted into the unprivileged API image.
            write_new(self.new / name, read_file(self.package / name), 0o644)
        before = json.loads(compose(self.base, "config", "--format", "json"))
        after = json.loads(compose(self.new, "config", "--format", "json"))
        normalized = json.loads(json.dumps(after).replace(str(self.new), str(self.base)))
        for service in ("api", "web"):
            normalized["services"][service]["image"] = self.old_images[service]
            normalized["services"][service]["environment"]["APP_RELEASE"] = str(self.manifest["base_candidate"])
        require(normalized == before, "COMPOSE_EXTRA_CHANGE")
        hashes = {name: digest(read_file(self.new / name)) for name in COPY_FILES + ENV_FILES + ("secrets/migration.env",) + PACKAGE_FILES}
        write_new(self.new / "schema-upgrade-prepared.json", json.dumps({"manifest": self.manifest, "hashes": hashes}, sort_keys=True).encode())
        self.verify_prepared()

    def verify_prepared(self) -> None:
        state = json.loads(read_file(self.new / "schema-upgrade-prepared.json"))
        require(state["manifest"] == self.manifest, "MANIFEST_CHANGED")
        require(all(digest(read_file(self.new / name)) == value for name, value in state["hashes"].items()), "PREPARED_FILES_CHANGED")
        require(stat.S_IMODE((self.new / "secrets/migration.env").stat().st_mode) == 0o600, "ENV_PERMISSIONS")

    def docker_api(self, env_file: str, *args: str, read_only: bool = False, timeout: int = 300) -> bytes:
        command = [
            "docker", "run", "--rm", "--network", "host", "--env-file", str(self.new / env_file),
            "-v", f"{self.new / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro",
            "-v", f"{self.new / 'db_facts.py'}:/tmp/db_facts.py:ro",
            "-v", f"{self.new / 'grant_runtime.py'}:/tmp/grant_runtime.py:ro",
        ]
        if read_only:
            command += ["-e", "PGOPTIONS=-c default_transaction_read_only=on", "-e", "REQUIRE_READ_ONLY=true"]
        return run(command + [self.images["api"], *args], timeout=timeout)

    def facts(self, output: Path, env_file: str = "secrets/migration.env") -> dict[str, object]:
        raw = self.docker_api(
            env_file, "python", "/app/scripts/canary_schema_facts_entry.py",
            read_only=True, timeout=600,
        )
        output.write_bytes(raw)
        output.chmod(0o600)
        return json.loads(raw)

    def recover_incomplete_backup(self) -> None:
        if not self.backup.exists() and not self.backup.is_symlink():
            return
        require(
            self.backup.is_dir()
            and not self.backup.is_symlink()
            and self.backup.resolve() == self.backup,
            "BACKUP_PATH_UNSAFE",
        )
        allowed = {"before.json", "restored.json", "canary.dump"}
        entries = list(self.backup.iterdir())
        require(
            {entry.name for entry in entries} <= allowed
            and all(entry.is_file() and not entry.is_symlink() for entry in entries),
            "INCOMPLETE_BACKUP_REQUIRES_MANUAL_RECOVERY",
        )
        for entry in entries:
            entry.unlink()
        self.backup.rmdir()

    def backup_diagnose(self) -> None:
        self.verify_base()
        self.verify_prepared()
        require(
            self.backup.is_dir() and not self.backup.is_symlink(),
            "INCOMPLETE_BACKUP_MISSING",
        )
        require(
            not (self.backup / "migration-receipt.json").exists()
            and not (self.backup / "canary.dump.enc").exists(),
            "BACKUP_DIAGNOSE_REFUSES_COMPLETED_STATE",
        )
        before = json.loads(read_file(self.backup / "before.json"))
        restored = json.loads(read_file(self.backup / "restored.json"))
        current_path = self.package / "current-diagnostic.json"
        current = self.facts(current_path)
        tables = sorted(set(before["counts"]) | set(restored["counts"]))
        count_differences = {
            table: {
                "source": before["counts"].get(table),
                "restored": restored["counts"].get(table),
            }
            for table in tables
            if before["counts"].get(table) != restored["counts"].get(table)
        }
        fingerprint_differences = sorted(
            table
            for table in set(before["content_fingerprints"]) | set(restored["content_fingerprints"])
            if before["content_fingerprints"].get(table)
            != restored["content_fingerprints"].get(table)
        )
        print(json.dumps({
            "source_migration": before["migration"],
            "restored_migration": restored["migration"],
            "schema_equal": before["schema_sha256"] == restored["schema_sha256"],
            "active_notification_recipients_equal": before["active_notification_recipients"]
            == restored["active_notification_recipients"],
            "count_differences": count_differences,
            "fingerprint_difference_tables": fingerprint_differences,
            "current_source_facts_equal": current == before,
        }, sort_keys=True))

    def snapshot_dump(self, dump: Path, pg_env: dict[str, str]) -> dict[str, object]:
        snapshot_script = self.package / "wp31_database_snapshot.py"
        read_file(snapshot_script)
        exchange = self.backup / "snapshot-exchange"
        exchange.mkdir(mode=0o700)
        snapshot_id_path = exchange / "snapshot-id"
        release_path = exchange / "snapshot-release"
        holder = "journey-schema-snapshot-" + str(self.manifest["candidate"])[:12]
        created = False
        try:
            require(
                subprocess.run(
                    ["docker", "container", "inspect", holder], capture_output=True
                ).returncode != 0,
                "SNAPSHOT_CONTAINER_EXISTS",
            )
            run([
                "docker", "run", "-d", "--name", holder, "--user", "0:0",
                "--network", "host", "--env-file", str(self.new / "secrets/migration.env"),
                "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                "-v", f"{self.new / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro",
                "-v", f"{snapshot_script}:/tmp/wp31_database_snapshot.py:ro",
                "-v", f"{exchange}:/exchange", self.images["api"],
                "python", "/tmp/wp31_database_snapshot.py",
                "--exchange-dir", "/exchange", "--timeout-seconds", "900",
            ], timeout=120)
            created = True
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if snapshot_id_path.is_file() and not snapshot_id_path.is_symlink():
                    break
                running = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", holder],
                    capture_output=True,
                )
                require(
                    running.returncode == 0 and running.stdout.strip() == b"true",
                    "SNAPSHOT_HOLDER_EXITED",
                )
                time.sleep(1)
            else:
                raise UpgradeError("SNAPSHOT_NOT_READY")
            require(stat.S_IMODE(snapshot_id_path.stat().st_mode) == 0o600, "SNAPSHOT_ID_MODE")
            snapshot_id = read_file(snapshot_id_path, maximum=256).decode().strip()
            require(SNAPSHOT_ID.fullmatch(snapshot_id), "SNAPSHOT_ID_INVALID")
            run([
                "docker", "run", "--rm", "--network", "host",
                "-e", "PGPASSWORD", "-e", "PGSSLMODE", "-e", "PGSSLROOTCERT",
                "-v", f"{self.new / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro",
                "-v", f"{self.backup}:/backup", self.images["dbrestore"],
                "pg_dump", "-h", pg_env["PGHOST"], "-p", pg_env["PGPORT"],
                "-U", pg_env["PGUSER"], "-d", DATABASE, "--format=custom",
                "--compress=9", "--no-owner", "--no-acl", "--snapshot=" + snapshot_id,
                "--file=/backup/canary.dump",
            ], timeout=900, env=pg_env)
            raw = run([
                "docker", "run", "--rm", "--network", "host",
                "--env-file", str(self.new / "secrets/migration.env"),
                "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                "-e", "REQUIRE_READ_ONLY=true", "-e", "WP31_DATABASE_SNAPSHOT=" + snapshot_id,
                "-v", f"{self.new / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro",
                "-v", f"{self.new / 'db_facts.py'}:/tmp/db_facts.py:ro",
                "-v", f"{snapshot_script}:/tmp/wp31_database_snapshot.py:ro",
                self.images["api"], "python", "/tmp/db_facts.py",
            ], timeout=600)
            before = json.loads(raw)
            (self.backup / "before.json").write_bytes(raw)
            (self.backup / "before.json").chmod(0o600)
            write_new(release_path, b"")
            status = run(["docker", "wait", holder], timeout=30).decode().strip()
            require(status == "0", "SNAPSHOT_RELEASE_FAILED")
            run(["docker", "rm", holder], timeout=30)
            created = False
            return before
        finally:
            if created:
                subprocess.run(["docker", "rm", "-f", holder], capture_output=True)
            for path in (snapshot_id_path, exchange / ".snapshot-id.pending", release_path):
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            if exchange.is_dir() and not exchange.is_symlink():
                exchange.rmdir()

    def backup_migrate(self, backup_key: str) -> None:
        self.verify_base()
        self.verify_prepared()
        require(len(backup_key) >= 32 and "\n" not in backup_key and "\r" not in backup_key, "BACKUP_SECRET_INVALID")
        self.recover_incomplete_backup()
        require(not self.backup.exists() and not self.backup.is_symlink(), "BACKUP_EXISTS")
        self.backup.mkdir(parents=True, mode=0o700)
        before_path = self.backup / "before.json"
        dump = self.backup / "canary.dump"
        encrypted = self.backup / "canary.dump.enc"
        migration = env_values(read_file(self.new / "secrets/migration.env"))
        parsed = urlsplit(migration["DATABASE_URL"])
        pg_env = os.environ.copy()
        pg_env.update({
            "PGPASSWORD": unquote(parsed.password or ""), "PGSSLMODE": "verify-full",
            "PGSSLROOTCERT": "/run/secrets/volcengine-rds-ca.pem",
            "PGHOST": parsed.hostname or "", "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username or ""),
        })
        require(pg_env["PGHOST"] and pg_env["PGUSER"], "DATABASE_URL")
        before = self.snapshot_dump(dump, pg_env)
        require(before_path.is_file() and before["migration"] == self.manifest["migrations"]["from"], "SOURCE_MIGRATION")
        verify = self.backup / "verify.dump"
        try:
            self.restore_encrypt_migrate(before, dump, encrypted, verify, backup_key)
        finally:
            for path in (dump, verify):
                if path.is_file() and not path.is_symlink():
                    path.unlink()

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
                "-v", f"{self.new / 'db_facts.py'}:/tmp/db_facts.py:ro", self.images["api"],
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
        self.docker_api("secrets/migration.env", "alembic", "upgrade", "head", timeout=900)
        current = self.docker_api("secrets/migration.env", "alembic", "current", timeout=300).decode()
        require(str(self.manifest["migrations"]["to"]) in current, "TARGET_MIGRATION")
        self.docker_api(
            "secrets/migration.env", "python", "/tmp/grant_runtime.py", timeout=300
        )
        after = self.facts(self.backup / "after-migration.json")
        require(after["migration"] == self.manifest["migrations"]["to"], "TARGET_MIGRATION")
        for table, count in before["counts"].items():
            require(after["counts"].get(table) == count, "BUSINESS_FACT_CHANGED")
        for table in ("coaching_feedback", "ai_advisory_records"):
            require(after["counts"].get(table) == 0, "NEW_FACTS_BEFORE_BACKFILL")
        self.probe_old_api()
        receipt = {
            "candidate": self.manifest["candidate"], "from": before["migration"],
            "to": after["migration"], "backup_sha256": digest(read_file(encrypted, maximum=2_000_000_000)),
            "restore": "PASS", "old_application_compatibility": "PASS",
            "business_counts_unchanged": True,
        }
        write_new(self.backup / "migration-receipt.json", json.dumps(receipt, sort_keys=True).encode())

    def probe_old_api(self) -> None:
        name = "journey-schema-old-probe-" + str(self.manifest["candidate"])[:12]
        require(subprocess.run(["docker", "container", "inspect", name], capture_output=True).returncode != 0, "OLD_PROBE_CONTAINER_EXISTS")
        created = False
        try:
            run([
                "docker", "run", "-d", "--name", name, "--network", "host",
                "--env-file", str(self.base / "secrets/api.env"),
                "-v", f"{self.base / 'secrets/volcengine-rds-ca.pem'}:/run/secrets/volcengine-rds-ca.pem:ro",
                self.old_images["api"],
                "uvicorn", "journey_api.main:app", "--host", "127.0.0.1", "--port", "18081",
            ], timeout=120)
            created = True
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                result = subprocess.run(["curl", "-fsS", "--connect-timeout", "2", "--max-time", "3", "http://127.0.0.1:18081/health/ready"], capture_output=True)
                if result.returncode == 0:
                    value = json.loads(result.stdout)
                    require(value["release"] == self.manifest["base_candidate"], "OLD_COMPATIBILITY_RELEASE")
                    return
                time.sleep(1)
            raise UpgradeError("OLD_APPLICATION_INCOMPATIBLE")
        finally:
            if created:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    def pointer(self, path: Path) -> None:
        temporary = ROOT / (".current-schema-upgrade-" + str(self.manifest["candidate"]))
        os.symlink(path, temporary)
        os.replace(temporary, ROOT / "current")

    def up(self, path: Path) -> None:
        compose(path, "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                "--force-recreate", "--wait", "--wait-timeout", "240", "api", "web", timeout=300)

    def coaching_fact_count(self) -> int:
        output = self.docker_api(
            "secrets/migration.env", "python", "-c",
            "from sqlalchemy import text; from journey_api.db import engine; "
            "c=engine.connect(); print(c.execute(text(\"select count(*) from reviews where review_kind='LEARNING_COACHING'\")).scalar_one())",
            read_only=True,
        )
        return int(output.strip())

    def rollback_pre_backfill(self) -> None:
        self.verify_prepared()
        require(not (self.new / "backfill-complete.json").exists(), "BACKFILL_ALREADY_COMPLETED")
        require(self.coaching_fact_count() == 0, "COACHING_FACTS_EXIST_FORWARD_FIX_ONLY")
        self.containers({name: {self.old_images[name], self.images[name]} for name in ("api", "web")}, allow_missing=True)
        self.up(self.base)
        self.healthy(self.base, str(self.manifest["base_candidate"]), self.old_images)
        if self.current() != self.base:
            self.pointer(self.base)

    def switch(self) -> None:
        self.verify_prepared()
        require((self.backup / "migration-receipt.json").is_file(), "MIGRATION_RECEIPT_MISSING")
        require(self.current() == self.base, "CURRENT_CHANGED")
        require(self.coaching_fact_count() == 0, "COACHING_FACTS_EXIST_BEFORE_SWITCH")
        self.healthy(self.base, str(self.manifest["base_candidate"]), self.old_images)
        write_new(self.new / "switch-attempt.json", b'{"started":true}')
        try:
            self.up(self.new)
            self.healthy(self.new, str(self.manifest["candidate"]), {name: self.images[name] for name in ("api", "web")}, public=False)
            self.pointer(self.new)
            self.healthy(self.new, str(self.manifest["candidate"]), {name: self.images[name] for name in ("api", "web")})
        except (Exception, KeyboardInterrupt) as error:
            category = str(error) if isinstance(error, UpgradeError) else type(error).__name__
            try:
                self.rollback_pre_backfill()
            except (Exception, KeyboardInterrupt):
                raise UpgradeError("SWITCH_FAILED_ROLLBACK_NOT_CONFIRMED") from None
            raise UpgradeError("SWITCH_FAILED_OLD_VERSION_HEALTHY:" + category) from None

    def backfill(self) -> None:
        self.verify_prepared()
        require(self.current() == self.new, "CURRENT_CHANGED")
        require(not (self.new / "backfill-complete.json").exists(), "BACKFILL_ALREADY_COMPLETED")
        self.healthy(self.new, str(self.manifest["candidate"]), {name: self.images[name] for name in ("api", "web")})
        before = self.facts(self.backup / "before-backfill.json", "secrets/api.env")
        plan_raw = self.docker_api("secrets/api.env", "python", "-m", "journey_api.coaching_backfill", "plan", timeout=600)
        plan = json.loads(plan_raw)
        (self.backup / "backfill-plan-private.json").write_bytes(plan_raw)
        (self.backup / "backfill-plan-private.json").chmod(0o600)
        print(json.dumps({
            "mode": "plan",
            "candidate_count": plan["candidate_count"],
            "organization_count": plan["organization_count"],
            "enrollment_count": plan["enrollment_count"],
            "scope": plan["rule"],
        }, ensure_ascii=False, sort_keys=True), flush=True)
        apply_raw = self.docker_api("secrets/api.env", "python", "-m", "journey_api.coaching_backfill", "apply", timeout=900)
        applied = json.loads(apply_raw)
        require(applied["candidate_count"] == plan["candidate_count"] and applied["created"] == plan["candidate_count"] and applied["remaining"] == 0, "BACKFILL_RESULT")
        after = self.facts(self.backup / "after-backfill.json", "secrets/api.env")
        expected_delta = int(plan["candidate_count"])
        for table, count in before["counts"].items():
            expected = count + expected_delta if table == "reviews" else count
            require(after["counts"].get(table) == expected, "BACKFILL_UNEXPECTED_FACT_CHANGE")
        require(after["migration"] == self.manifest["migrations"]["to"], "TARGET_MIGRATION")
        receipt = {
            "candidate": self.manifest["candidate"], "created_reviews": expected_delta,
            "remaining": 0, "evaluation_delta": 0, "submission_version_delta": 0,
            "assignment_delta": 0, "enrollment_delta": 0, "outcome_delta": 0,
            "rollback_policy": "FORWARD_FIX_ONLY",
        }
        write_new(self.new / "backfill-complete.json", json.dumps(receipt, sort_keys=True).encode())
        print(json.dumps(receipt, sort_keys=True))

    def inspect(self) -> None:
        current = self.current()
        result = {
            "current_release": current.name,
            "candidate": self.manifest["candidate"],
            "prepared": self.new.is_dir(),
            "migration_complete": (self.backup / "migration-receipt.json").is_file(),
            "backfill_complete": (self.new / "backfill-complete.json").is_file(),
        }
        print(json.dumps(result, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "backup-migrate", "backup-diagnose", "switch", "backfill", "rollback-pre-backfill", "inspect"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--actor")
    args = parser.parse_args()
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(ROOT.resolve() == ROOT and (ROOT / "releases").resolve() == ROOT / "releases", "ROOT_SYMLINK")
    package = Path(__file__).resolve().parent
    manifest = load_manifest(args.manifest.resolve(), args.manifest_sha256)
    upgrade = Upgrade(manifest, package)
    os.umask(0o077)
    import fcntl
    descriptor = os.open(ROOT / ".schema-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.phase == "prepare":
            payload = json.loads(sys.stdin.read(16384))
            upgrade.prepare(args.actor or "", payload.get("registry_token", ""), payload.get("migration_password", ""))
        elif args.phase == "backup-migrate":
            upgrade.backup_migrate(sys.stdin.read(4097).strip())
        else:
            getattr(upgrade, args.phase.replace("-", "_"))()
    print(json.dumps({"phase": args.phase, "result": "PASS", "candidate": manifest["candidate"]}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({
            "result": "STOP",
            "category": str(error) if isinstance(error, UpgradeError) else type(error).__name__,
            "do_not_retry_blindly": True,
        }, sort_keys=True))
        raise SystemExit(1)
