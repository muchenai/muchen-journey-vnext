"""Verified offline upgrade of the existing Journey database and API/Web only."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
from urllib.parse import quote, urlsplit, urlunsplit

from canary_schema_upgrade import (
    Upgrade, UpgradeError, ROOT, COPY_FILES, ENV_FILES, PACKAGE_FILES,
    changed_env, compose, digest, env_values, read_file, require, run, write_new,
)
from prepare import ExplorationPreparation, BASE

ORG = "10000000-0000-4000-8000-000000000001"
PRIMARY = "934d4bab-2494-4ed3-ac15-9378913b9c01"
POOL = ["10000000-0000-4000-8000-000000000003", PRIMARY, "fc74182c-048c-41de-bae6-c7ccd95f0a93"]
EXCLUDED = "f76350f4-9251-4c82-a4d5-3a80b1e4514f"
TARGET_SCHEMA = "0032_shared_learner_review"
LOGIN_CONFIG = {
    "FEISHU_LEARNER_REGISTRATION_ENABLED": "true",
    "FEISHU_LEARNER_ORGANIZATION_ID": ORG,
    "FEISHU_LEARNER_REVIEWER_ID": PRIMARY,
    "FEISHU_LEARNER_SHARED_REVIEWER_IDS": ",".join(POOL),
    "REVIEWER_EXCLUDED_USER_IDS": EXCLUDED,
}


def event(step):
    print(json.dumps({"step": step}), flush=True)


def add_env(raw, changes):
    original = env_values(raw)
    present = {key: value for key, value in changes.items() if key in original}
    output = changed_env(raw, present)
    if output and not output.endswith(b"\n"):
        output += b"\n"
    for key, value in changes.items():
        require(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) and "\n" not in value and "\r" not in value, "ENV_CHANGE_INVALID")
        if key not in original:
            output += f"{key}={value}\n".encode()
    require(env_values(output) == {**original, **changes}, "ENV_EXTRA_CHANGE")
    return output


def stream_sha(handle):
    value = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def file_sha(path):
    require(path.is_file() and not path.is_symlink(), "ARCHIVE_PATH")
    with path.open("rb") as handle:
        return stream_sha(handle)


class Activation(ExplorationPreparation):
    def __init__(self, manifest, package):
        Upgrade.__init__(self, manifest, package)
        self.base = Path(manifest["base_release"])
        require(self.base == ROOT / "releases" / (BASE + "-learner-35975348184-1"), "BASE_PATH")
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["candidate"]), "CANDIDATE")
        self.new = ROOT / "releases" / (manifest["candidate"] + "-exploration")
        self.backup = ROOT / "backups" / ("exploration-" + manifest["candidate"])

    def import_images(self):
        self.verify_base()
        for name in ("api", "web"):
            entry = self.manifest["archives"][name]
            archive = self.package / (name + ".tar.gz")
            require(not archive.exists(), "ARCHIVE_ALREADY_ASSEMBLED")
            with archive.open("xb") as target:
                for part in entry["chunks"]:
                    require(re.fullmatch(name + r"\.part[0-9]{4}", part["file"]), "CHUNK_NAME")
                    source = self.package / part["file"]
                    require(file_sha(source) == part["sha256"], "CHUNK_SHA")
                    with source.open("rb") as handle:
                        shutil.copyfileobj(handle, target)
            require(file_sha(archive) == entry["gzip_sha256"], "ARCHIVE_SHA")
            with gzip.open(archive, "rb") as handle:
                require(stream_sha(handle) == entry["source_tar_sha256"], "SOURCE_TAR_SHA")
            event("IMPORT_" + name.upper())
            run(["docker", "load", "--input", str(archive)], timeout=600)
            # Runtime uses the immutable image-config digest from the verified
            # build artifact, not a mutable tag or a guessed registry digest.
            self.image_check(name, self.images[name], self.manifest["candidate"])
        for name, reference in self.old_images.items():
            Upgrade.image_check(self, name, reference, BASE)
        Upgrade.image_check(self, "dbrestore", self.images["dbrestore"])

    def image_check(self, name, reference, candidate=None):
        if name not in {"api", "web"} or reference != self.images.get(name):
            return Upgrade.image_check(self, name, reference, candidate)
        item = json.loads(run(["docker", "image", "inspect", reference]))[0]
        require(item["Id"] == reference, "CONFIG_DIGEST_MISMATCH")
        require(item["Os"] == "linux" and item["Architecture"] == "amd64", "IMAGE_PLATFORM")
        require(item["Config"]["Labels"].get("org.opencontainers.image.revision") == candidate, "IMAGE_REVISION")

    def stage(self, migration_password):
        self.verify_base()
        require(not self.new.exists() and not self.new.is_symlink(), "PREPARATION_EXISTS")
        require(len(migration_password) >= 20 and not any(c in migration_password for c in "\r\n"), "MIGRATION_SECRET_INVALID")
        originals = {name: read_file(self.base / name) for name in COPY_FILES + ENV_FILES}
        parsed = urlsplit(env_values(originals["secrets/api.env"])["DATABASE_URL"])
        require(parsed.scheme == "postgresql+psycopg" and parsed.hostname and parsed.port, "DATABASE_URL")
        migration_url = urlunsplit((parsed.scheme, f"journey_next_migrator:{quote(migration_password, safe='')}@{parsed.hostname}:{parsed.port}", parsed.path, parsed.query, ""))
        self.new.mkdir(mode=0o700)
        (self.new / "secrets").mkdir(mode=0o700)
        for name in COPY_FILES:
            write_new(self.new / name, originals[name], 0o644 if name.endswith(".pem") else stat.S_IMODE((self.base / name).stat().st_mode))
        changes = {
            ".deployment.env": {"CANDIDATE_COMMIT": self.manifest["candidate"], "API_IMAGE": self.images["api"], "WEB_IMAGE": self.images["web"]},
            "secrets/api.env": {"APP_RELEASE": self.manifest["candidate"], **LOGIN_CONFIG},
            "secrets/web.env": {"APP_RELEASE": self.manifest["candidate"]},
        }
        for name in ENV_FILES:
            write_new(self.new / name, add_env(originals[name], changes[name]))
        write_new(self.new / "secrets/migration.env", add_env(originals["secrets/api.env"], {"APP_RELEASE": self.manifest["candidate"], "DATABASE_URL": migration_url}))
        for name in PACKAGE_FILES:
            write_new(self.new / name, read_file(self.package / name), 0o644)
        before = json.loads(compose(self.base, "config", "--format", "json"))
        after = json.loads(compose(self.new, "config", "--format", "json"))
        normalized = json.loads(json.dumps(after).replace(str(self.new), str(self.base)))
        for service in ("api", "web"):
            normalized["services"][service]["image"] = self.old_images[service]
            normalized["services"][service]["environment"]["APP_RELEASE"] = BASE
        for key in LOGIN_CONFIG:
            old = before["services"]["api"]["environment"]
            if key in old:
                normalized["services"]["api"]["environment"][key] = old[key]
            else:
                normalized["services"]["api"]["environment"].pop(key, None)
        require(normalized == before, "COMPOSE_EXTRA_CHANGE")
        hashes = {name: digest(read_file(self.new / name)) for name in COPY_FILES + ENV_FILES + ("secrets/migration.env",) + PACKAGE_FILES}
        write_new(self.new / "schema-upgrade-prepared.json", json.dumps({"manifest": self.manifest, "hashes": hashes}, sort_keys=True).encode())
        self.verify_prepared()
        self.validate_staff()

    def validate_staff(self):
        # Do not create roles or relink identities. All pool roles must exist.
        script = f'''from sqlalchemy import text
from journey_api.db import SessionLocal
with SessionLocal() as s:
 s.execute(text("SET TRANSACTION READ ONLY"))
 rows=s.execute(text("select u.id::text,u.display_name from users u join role_assignments r on r.user_id=u.id and r.organization_id=u.organization_id where u.organization_id=:org and u.status='ACTIVE' and r.role='REVIEWER'"),{{"org":{ORG!r}}}).all()
 assert set({POOL!r} + [{EXCLUDED!r}]) <= {{r[0] for r in rows}}
 assert dict(rows)[{EXCLUDED!r}] == "许瀚文"
 assert dict(rows)[{PRIMARY!r}] == "李鑫波"
 print("REVIEWER_CONFIGURATION=PASS")
'''
        self.docker_api("secrets/api.env", "python", "-c", script, read_only=True)

    def guard(self):
        return json.loads(self.docker_api("secrets/migration.env", "python", "-c", read_file(self.package / "facts_guard.py").decode(), read_only=True, timeout=600))

    def validate_restored_database(self, network, restore_env):
        event("REHEARSE_MIGRATIONS_ON_RESTORED_COPY")
        prefix = ["docker", "run", "--rm", "--network", network, "--env-file", str(restore_env), self.images["api"]]
        guard = read_file(self.package / "facts_guard.py").decode()
        before = json.loads(run(prefix + ["python", "-c", guard], timeout=600))
        run(prefix + ["alembic", "upgrade", TARGET_SCHEMA], timeout=600)
        after = json.loads(run(prefix + ["python", "-c", guard], timeout=600))
        require(after == before, "RESTORE_MIGRATION_CHANGED_BUSINESS_FACTS")
        require(TARGET_SCHEMA in run(prefix + ["alembic", "current"]).decode(), "RESTORE_TARGET_SCHEMA")
        write_new(self.backup / "migration-rehearsal.json", json.dumps({"schema": TARGET_SCHEMA, "business_facts_preserved": True}).encode())

    def activate(self):
        self.verify_base()
        self.verify_prepared()
        receipt = json.loads(read_file(self.backup / "backup-receipt.json"))
        require(receipt["restore"] == "PASS" and receipt["candidate"] == self.manifest["candidate"], "BACKUP_RECEIPT")
        require(file_sha(self.backup / "canary.dump.enc") == receipt["backup_sha256"], "BACKUP_CHANGED")
        require(json.loads(read_file(self.backup / "migration-rehearsal.json"))["schema"] == TARGET_SCHEMA, "REHEARSAL_MISSING")
        event("BRIEF_JOURNEY_MAINTENANCE")
        baseline = None
        try:
            compose(self.base, "stop", "web", "api", timeout=90)
            baseline = self.guard()
            event("APPLY_ADDITIVE_SCHEMA_MIGRATIONS")
            self.docker_api("secrets/migration.env", "alembic", "upgrade", TARGET_SCHEMA, timeout=600)
            require(TARGET_SCHEMA in self.docker_api("secrets/migration.env", "alembic", "current").decode(), "TARGET_SCHEMA")
            require(self.guard() == baseline, "PRODUCTION_BUSINESS_FACTS_CHANGED")
            # Only columns/constraints were added; existing runtime table grants
            # remain valid and no privilege expansion is necessary.
            self.docker_api("secrets/api.env", "python", "-c", "from sqlalchemy import text; from journey_api.db import SessionLocal; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); assert s.execute(text(\"select count(*) from enrollments where review_assignment_mode <> 'ASSIGNED'\")).scalar_one()==0; print('RUNTIME_SCHEMA=PASS')", read_only=True)
            write_new(self.backup / "migration-receipt.json", json.dumps({"candidate": self.manifest["candidate"], "schema": TARGET_SCHEMA, "business_facts_preserved": True}).encode())
            self.probe_old_api()
            event("SWITCH_JOURNEY_API_AND_WEB")
            self.up(self.new)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")}, public=False)
            self.pointer(self.new)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")})
            write_new(self.new / "activation-receipt.json", json.dumps({"release": self.manifest["candidate"], "status": "PASS", "old_assignments_unchanged": True, "shared_reviewers": POOL, "excluded_reviewer": EXCLUDED}).encode())
        except (Exception, KeyboardInterrupt):
            if baseline is not None and self.guard() != baseline:
                raise UpgradeError("BUSINESS_WRITES_DETECTED_FORWARD_FIX_REQUIRED") from None
            event("RESTORE_PREVIOUS_APPLICATION")
            self.up(self.base)
            if self.current() != self.base:
                self.pointer(self.base)
            self.healthy(self.base, BASE, self.old_images)
            raise


def main():
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(socket.gethostname() == "journey-next-staging", "UNEXPECTED_HOST")
    require(ROOT.resolve() == ROOT, "ROOT_SYMLINK")
    os.umask(0o077)
    package = Path(__file__).resolve().parent
    manifest = json.loads(read_file(package / "manifest.json"))
    require(manifest["base_candidate"] == BASE and manifest["migrations"] == {"from": "0029_treasure_coaching_reviews", "to": TARGET_SCHEMA}, "MANIFEST")
    payload = json.loads(sys.stdin.read(16384))
    import fcntl
    descriptor = os.open(ROOT / ".schema-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = Activation(manifest, package)
        event("VERIFY_AND_IMPORT_OFFLINE_IMAGES")
        release.import_images()
        event("STAGE_EXISTING_PRODUCTION_CONFIGURATION")
        release.stage(payload["migration_password"])
        event("BACKUP_AND_PROVE_RESTORE")
        release.backup_migrate(payload["backup_key"])
        release.activate()
        event("RELEASE_COMPLETE")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"result": "STOP", "category": str(error) if isinstance(error, UpgradeError) else type(error).__name__, "do_not_retry_blindly": True}), flush=True)
        raise SystemExit(1)
