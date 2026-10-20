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
import tarfile
from urllib.parse import quote, urlsplit, urlunsplit

from canary_schema_upgrade import (
    Upgrade, UpgradeError, ROOT, COPY_FILES, ENV_FILES, PACKAGE_FILES,
    changed_env, compose, digest, env_values, read_file, require, run, write_new,
)
from prepare import ExplorationPreparation

BASE = "106a599b1e7d80d51336d93aa28d980939f4e8f0"
WEB_BASE = "106a599b1e7d80d51336d93aa28d980939f4e8f0"
SOURCE_SCHEMA = "0035_phone_password_login"
TARGET_SCHEMA = "0037_ai_self_check_revisions"
NEW_TABLES = ("ai_self_checks",)
AI_CONFIG = {
    "AI_SELF_CHECK_ENABLED": "true",
    "AI_COMMENT_MENTION_OWNER": "true",
    "AI_BASE_URL": "https://ark-api.touf.shop/v1",
    "AI_MODEL": "deepseek-v4-pro",
    "AI_FEISHU_APP_ID": "cli_aaadd24ffbbadcfd",
    "AI_API_KEY_FILE": "/run/secrets/ai_api_key",
    "AI_FEISHU_APP_SECRET_FILE": "/run/secrets/ai_feishu_app_secret",
}
SECRET_FILES = {
    "ai_api_key": "secrets/ai_api_key",
    "ai_feishu_app_secret": "secrets/ai_feishu_app_secret",
}


def mount_ai_secrets(raw):
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    anchor = b"      - ./secrets/volcengine-rds-ca.pem:/run/secrets/volcengine-rds-ca.pem:ro" + newline
    require(raw.count(anchor) == 1, "API_VOLUME_ANCHOR")
    extra = b"".join(f"      - ./{path}:/run/secrets/{key}:ro".encode() + newline
                     for key, path in SECRET_FILES.items())
    return raw.replace(anchor, anchor + extra)


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


def verify_exported_config(path, expected):
    with tarfile.open(path, "r") as archive:
        stream = archive.extractfile("manifest.json")
        require(stream is not None, "EXPORTED_MANIFEST_MISSING")
        manifests = json.load(stream)
        require(len(manifests) == 1, "EXPORTED_IMAGE_COUNT")
        config = archive.getmember(manifests[0]["Config"])
        require(config.isfile() and config.size <= 2_000_000, "EXPORTED_CONFIG_INVALID")
        content = archive.extractfile(config)
        require(content is not None and "sha256:" + stream_sha(content) == expected, "EXPORTED_CONFIG_DIGEST")


class Activation(ExplorationPreparation):
    def __init__(self, manifest, package):
        Upgrade.__init__(self, manifest, package)
        self.base = Path(manifest["base_release"])
        require(self.base == ROOT / "releases" / (WEB_BASE + "-phone-login"), "BASE_PATH")
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["candidate"]), "CANDIDATE")
        self.new = ROOT / "releases" / (manifest["candidate"] + "-ai-self-check")
        self.backup = ROOT / "backups" / ("ai-self-check-" + manifest["candidate"])

    def healthy(self, release, candidate, images, *, public=True):
        for row in self.containers({name: {reference} for name, reference in images.items()}):
            service = row["Config"]["Labels"]["com.docker.compose.service"]
            expected = WEB_BASE if release == self.base and service == "web" else candidate
            values = dict(pair.split("=", 1) for pair in row["Config"]["Env"])
            require(row["State"]["Running"] and row["State"].get("Health", {}).get("Status") == "healthy", "UNHEALTHY")
            require(values.get("APP_RELEASE") == expected, "RUNTIME_RELEASE")
        if public:
            ready = json.loads(run(["curl", "-fsS", "--connect-timeout", "3", "--max-time", "10", "https://journey.muchenai.com/health/ready"]))
            require(ready == {"status": "ready", "release": WEB_BASE if release == self.base else candidate}, "PUBLIC_HEALTH")

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
            # Docker/containerd may rewrap an imported image in a new manifest.
            # Prove its original config (including rootfs diff IDs), then pin
            # the actual locally loaded immutable ID. Never deploy by tag.
            loaded = json.loads(run(["docker", "image", "inspect", entry["source_reference"]]))[0]
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", loaded["Id"]), "LOADED_IMAGE_ID")
            exported = self.package / (name + "-verification.tar")
            require(not exported.exists(), "VERIFICATION_FILE_EXISTS")
            try:
                run(["docker", "image", "save", "--output", str(exported), loaded["Id"]], timeout=600)
                verify_exported_config(exported, entry["config_digest"])
            finally:
                if exported.is_file() and not exported.is_symlink():
                    exported.unlink()
            self.manifest["images"][name] = loaded["Id"]
            self.image_check(name, self.images[name], self.manifest["candidate"])
        for name, reference in self.old_images.items():
            self.image_check(name, reference, BASE if name == "api" else WEB_BASE)
        Upgrade.image_check(self, "dbrestore", self.images["dbrestore"])

    def image_check(self, name, reference, candidate=None):
        if name not in {"api", "web"} or not re.fullmatch(r"sha256:[0-9a-f]{64}", reference):
            return Upgrade.image_check(self, name, reference, candidate)
        item = json.loads(run(["docker", "image", "inspect", reference]))[0]
        require(item["Id"] == reference, "CONFIG_DIGEST_MISMATCH")
        require(item["Os"] == "linux" and item["Architecture"] == "amd64", "IMAGE_PLATFORM")
        require(item["Config"]["Labels"].get("org.opencontainers.image.revision") == candidate, "IMAGE_REVISION")

    def stage(self, migration_password, credentials):
        self.verify_base()
        require(set(credentials) == set(SECRET_FILES), "AI_CREDENTIAL_FIELDS")
        for value in credentials.values():
            require(isinstance(value, str) and 16 <= len(value) <= 4096
                    and not any(c.isspace() for c in value), "AI_CREDENTIAL_INVALID")
        require(not self.new.exists() and not self.new.is_symlink(), "PREPARATION_EXISTS")
        require(len(migration_password) >= 20 and not any(c in migration_password for c in "\r\n"), "MIGRATION_SECRET_INVALID")
        originals = {name: read_file(self.base / name) for name in COPY_FILES + ENV_FILES}
        parsed = urlsplit(env_values(originals["secrets/api.env"])["DATABASE_URL"])
        require(parsed.scheme == "postgresql+psycopg" and parsed.hostname and parsed.port, "DATABASE_URL")
        migration_url = urlunsplit((parsed.scheme, f"journey_next_migrator:{quote(migration_password, safe='')}@{parsed.hostname}:{parsed.port}", parsed.path, parsed.query, ""))
        self.new.mkdir(mode=0o700)
        (self.new / "secrets").mkdir(mode=0o700)
        for key, path in SECRET_FILES.items():
            write_new(self.new / path, credentials[key].encode(), 0o600)
            # The image runs as UID 10001. The parent directory stays root-only
            # on the host; Docker mounts only these two files into the API.
            os.chown(self.new / path, 10001, 10001)
        for name in COPY_FILES:
            raw = mount_ai_secrets(originals[name]) if name == "compose.canary.yaml" else originals[name]
            write_new(self.new / name, raw, 0o644 if name.endswith(".pem") else stat.S_IMODE((self.base / name).stat().st_mode))
        changes = {
            ".deployment.env": {"CANDIDATE_COMMIT": self.manifest["candidate"], "API_IMAGE": self.images["api"], "WEB_IMAGE": self.images["web"]},
            "secrets/api.env": {"APP_RELEASE": self.manifest["candidate"], **AI_CONFIG},
            "secrets/web.env": {"APP_RELEASE": self.manifest["candidate"]},
        }
        for name in ENV_FILES:
            write_new(self.new / name, add_env(originals[name], changes[name]))
        write_new(self.new / "secrets/migration.env", add_env(originals["secrets/api.env"], {"APP_RELEASE": self.manifest["candidate"], "DATABASE_URL": migration_url}))
        for name in PACKAGE_FILES:
            raw = json.dumps(self.manifest, sort_keys=True).encode() if name == "manifest.json" else read_file(self.package / name)
            write_new(self.new / name, raw, 0o644)
        before = json.loads(compose(self.base, "config", "--format", "json"))
        after = json.loads(compose(self.new, "config", "--format", "json"))
        normalized = json.loads(json.dumps(after).replace(str(self.new), str(self.base)))
        volumes = normalized["services"]["api"]["volumes"]
        for key, path in SECRET_FILES.items():
            expected = {"type": "bind", "source": str(self.base / path),
                        "target": "/run/secrets/" + key, "read_only": True,
                        "bind": {"create_host_path": True}}
            require(expected in volumes, "AI_SECRET_MOUNT")
            volumes.remove(expected)
        for service in ("api", "web"):
            normalized["services"][service]["image"] = self.old_images[service]
            normalized["services"][service]["environment"]["APP_RELEASE"] = before["services"][service]["environment"]["APP_RELEASE"]
        for key in AI_CONFIG:
            old = before["services"]["api"]["environment"]
            if key in old:
                normalized["services"]["api"]["environment"][key] = old[key]
            else:
                normalized["services"]["api"]["environment"].pop(key, None)
        require(normalized == before, "COMPOSE_EXTRA_CHANGE")
        hashes = {name: digest(read_file(self.new / name)) for name in COPY_FILES + ENV_FILES + ("secrets/migration.env",) + PACKAGE_FILES + tuple(SECRET_FILES.values())}
        write_new(self.new / "schema-upgrade-prepared.json", json.dumps({"manifest": self.manifest, "hashes": hashes}, sort_keys=True).encode())
        self.verify_prepared()

    def docker_api(self, env_file, *args, read_only=False, timeout=300):
        if env_file != "secrets/api.env":
            return super().docker_api(env_file, *args, read_only=read_only, timeout=timeout)
        command = ["docker", "run", "--rm", "--network", "host", "--env-file", str(self.new / env_file)]
        for key, path in SECRET_FILES.items():
            command += ["-v", f"{self.new / path}:/run/secrets/{key}:ro"]
        for source, target in (("secrets/volcengine-rds-ca.pem", "/run/secrets/volcengine-rds-ca.pem"),
                               ("db_facts.py", "/tmp/db_facts.py"), ("grant_runtime.py", "/tmp/grant_runtime.py")):
            command += ["-v", f"{self.new / source}:{target}:ro"]
        if read_only:
            command += ["-e", "PGOPTIONS=-c default_transaction_read_only=on", "-e", "REQUIRE_READ_ONLY=true"]
        return run(command + [self.images["api"], *args], timeout=timeout)

    def verify_ai_access(self):
        event("VERIFY_AI_CONFIGURATION_AND_REFERENCE_ACCESS")
        # No learner document, comment creation or notification in preflight.
        probe = """
import json
from journey_api.config import get_settings
from journey_api.ai_self_check_clients import FeishuDocuments, request_json
from journey_api.ai_self_check_rules import references_for, QUESTION_URLS
s=get_settings()
assert s.ai_self_check_enabled and s.ai_comment_mention_owner
d=FeishuDocuments(s)
urls={url for stage in ['DAY-0',*QUESTION_URLS] for _,url in references_for(stage)}
for url in urls:
    kind,token=d.resolve_reference(url)
    assert d.read_reference(kind,token).body
r=request_json(s.ai_base_url.rstrip('/')+'/chat/completions',token=s.ai_api_key,timeout=180,service='AI',body={
    'model':s.ai_model,'stream':False,'max_tokens':64,
    'messages':[{'role':'user','content':'Connectivity check. Reply with OK only.'}]})
assert r.get('choices') and r['choices'][0].get('message',{}).get('content')
print(json.dumps({'ai_access':'PASS','readable_references':len(urls),'comments_sent':0}))
"""
        result = json.loads(self.docker_api("secrets/api.env", "python", "-c", probe, read_only=True, timeout=600))
        require(result == {"ai_access": "PASS", "readable_references": 13, "comments_sent": 0}, "AI_ACCESS_CHECK")
        event("AI_ACCESS_VERIFIED")

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
            self.docker_api("secrets/migration.env", "python", "/tmp/grant_runtime.py")
            self.docker_api("secrets/api.env", "python", "-c", "from sqlalchemy import text; from journey_api.db import SessionLocal; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); " + "; ".join(f"assert s.execute(text('select count(*) from {name}')).scalar_one()==0" for name in NEW_TABLES), read_only=True)
            write_new(self.backup / "migration-receipt.json", json.dumps({"candidate": self.manifest["candidate"], "schema": TARGET_SCHEMA, "business_facts_preserved": True}).encode())
            self.probe_old_api()
            event("SWITCH_JOURNEY_API_AND_WEB")
            self.up(self.new)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")}, public=False)
            self.pointer(self.new)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")})
            for path in ("/join", "/review/login", "/ops/login"):
                run(["curl", "-fsS", "--connect-timeout", "3", "--max-time", "15", "-o", "/dev/null", "https://journey.muchenai.com" + path])
            write_new(self.new / "activation-receipt.json", json.dumps({"release": self.manifest["candidate"], "status": "PASS", "old_assignments_unchanged": True, "schema": TARGET_SCHEMA, "ai_self_check_enabled": True}).encode())
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
    require(manifest["base_candidate"] == BASE and manifest["migrations"] == {"from": SOURCE_SCHEMA, "to": TARGET_SCHEMA}, "MANIFEST")
    payload = json.loads(sys.stdin.read(16384))
    import fcntl
    descriptor = os.open(ROOT / ".schema-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = Activation(manifest, package)
        event("VERIFY_AND_IMPORT_OFFLINE_IMAGES")
        release.import_images()
        event("STAGE_EXISTING_PRODUCTION_CONFIGURATION")
        release.stage(payload["migration_password"], {key: payload[key] for key in SECRET_FILES})
        release.verify_ai_access()
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
