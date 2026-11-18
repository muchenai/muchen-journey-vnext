"""Migrate dynamic exploration additively, initialize its catalog and replace API/Web."""
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
import uuid
from urllib.parse import quote, urlsplit, urlunsplit

from canary_schema_upgrade import (
    Upgrade, UpgradeError, ROOT, COPY_FILES, ENV_FILES,
    changed_env, compose, digest, env_values, read_file, require, run, write_new,
)
from prepare import ExplorationPreparation
from disk_space import DiskSpaceError, check_space
from image_transport import source_config_digest, verify_loaded_image, cleanup_verified_transports
from catalog_actor import actor_probe, SUCCESS as ACTOR_SUCCESS

BASE = "ef06970c1658f8d583bdaf9bd3a4fd90c13fdc49"
WEB_BASE = "ca69b1e3d9afacc9bf175a8c7bd40f81a8b03329"
BASE_DIRECTORY = WEB_BASE + "-learner-usability"
PREVIOUS_WEB_DIRECTORY = "40cb1c2ce1899b8f3eaef780df431975fa7bf701-learner-usability"
API_BASE_DIRECTORY = BASE + "-learner-refinements"
PROJECT = "journey-next-greenfield-canary"
SOURCE_SCHEMA = "0056_guild_halls"
TARGET_SCHEMA = "0060_migrated_ai_ownership"
NEW_TABLES = ("exploration_catalog_tasks", "exploration_work", "exploration_progress", "exploration_materials", "exploration_self_checks")
PACKAGE_FILES = ("manifest.json", "db_facts.py", "grant_runtime.py")
AUTHORIZATION = "owner-authorized-learner-admin-release-20261117"
SECRET_FILES = {
    "ai_api_key": "secrets/ai_api_key",
    "ai_feishu_app_secret": "secrets/ai_feishu_app_secret",
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


def protected_containers():
    """Fingerprint every container except the two approved application services."""
    ids = run(["docker", "ps", "-aq"]).decode().split()
    require(ids, "CONTAINERS_MISSING")
    result = {}
    for item in json.loads(run(["docker", "inspect", *ids])):
        labels = item["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") == PROJECT and labels.get("com.docker.compose.service") in {"api", "web"}:
            continue
        result[item["Name"]] = {key: item[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}
        result[item["Name"]]["Mounts"] = sorted(item["Mounts"], key=lambda mount: json.dumps(mount, sort_keys=True))
    return result


def verify_protected_containers(expected):
    actual = protected_containers()
    changes = []
    for name in sorted(set(expected) | set(actual)):
        before, after = expected.get(name), actual.get(name)
        if before == after:
            continue
        fields = ["container_presence"] if before is None or after is None else [field for field in before if before[field] != after[field]]
        changes.append({"container_id": (after or before)["Id"], "fields": fields})
    if changes:
        print(json.dumps({"step": "PROTECTED_RUNTIME_DIFFERENCE", "changes": changes}), flush=True)
    require(not changes, "PROTECTED_CONTAINER_CHANGED")


class Activation(ExplorationPreparation):
    def __init__(self, manifest, package):
        Upgrade.__init__(self, manifest, package)
        self.base = Path(manifest["base_release"])
        require(self.base == ROOT / "releases" / BASE_DIRECTORY, "BASE_PATH")
        require(manifest["base_candidate"] == BASE and manifest["base_web_candidate"] == WEB_BASE, "BASE_CANDIDATES")
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["candidate"]) and manifest["candidate"] not in {BASE, WEB_BASE}, "CANDIDATE")
        require(manifest.get("schema_version") == 3, "MANIFEST_VERSION")
        self.new = ROOT / "releases" / (manifest["candidate"] + "-dynamic-exploration")
        self.backup = ROOT / "backups" / ("dynamic-exploration-" + manifest["candidate"])
        api_base = ROOT / "releases" / API_BASE_DIRECTORY
        previous = json.loads(read_file(api_base / "schema-upgrade-prepared.json"))["manifest"]
        api_receipt = json.loads(read_file(api_base / "activation-receipt.json"))
        web_receipt = json.loads(read_file(self.base / "web-release-receipt.json"))
        require(previous["candidate"] == BASE and api_receipt["release"] == BASE
                and api_receipt["status"] == "PASS" and api_receipt["schema"] == SOURCE_SCHEMA, "API_BASE_RECEIPT")
        require(web_receipt["result"] == "PASS" and web_receipt["web_candidate"] == WEB_BASE
                and web_receipt["api_candidate"] == BASE and web_receipt["schema"] == SOURCE_SCHEMA
                and web_receipt["previous_release"] == str(ROOT / "releases" / PREVIOUS_WEB_DIRECTORY)
                and web_receipt.get("release_kind") == "learner-usability-web"
                and web_receipt.get("api_container_unchanged") is True
                and web_receipt.get("other_containers_unchanged") is True
                and web_receipt.get("database_writes") == 0, "WEB_BASE_RECEIPT")
        require(manifest.get("curriculum_authorization") == AUTHORIZATION, "CURRICULUM_AUTHORIZATION")
        require(manifest["migrations"] == {"from": SOURCE_SCHEMA, "to": TARGET_SCHEMA}, "SCHEMA_PIN")
        require(re.fullmatch(r"[0-9]+", manifest["package_run_id"]), "PACKAGE_RUN")
        require(manifest["database"] == "journey_next_canary_20260901_c72fea5", "DATABASE_PIN")
        require(manifest["old_images"] == {}, "OLD_IMAGE_OVERRIDE")
        manifest["old_images"] = {"api": previous["images"]["api"], "web": web_receipt["web_image_id"]}
        for reference in manifest["old_images"].values():
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", reference), "OLD_IMAGE_ID")
        hashes = web_receipt["configuration_hashes"]
        require(set(COPY_FILES + ENV_FILES) <= hashes.keys() and set(SECRET_FILES.values()) <= hashes.keys(), "BASE_CONFIGURATION_PROOF")
        require(all(isinstance(name, str) and (name in set(COPY_FILES + ENV_FILES) | {"db_facts.py", "grant_runtime.py"}
                    or re.fullmatch(r"secrets/[A-Za-z0-9_.-]+", name)) for name in hashes), "BASE_CONFIGURATION_PATH")
        require(all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()), "BASE_CONFIGURATION_HASH")
        self.base_hashes = hashes
        self.verify_base_configuration()

    def verify_base_configuration(self):
        require(all(digest(read_file(self.base / name)) == expected for name, expected in self.base_hashes.items()), "BASE_CONFIGURATION_CHANGED")
        deployment = env_values(read_file(self.base / ".deployment.env"))
        require(deployment["API_IMAGE"] == self.old_images["api"] and deployment["WEB_IMAGE"] == self.old_images["web"], "BASE_IMAGE_DRIFT")
        require(env_values(read_file(self.base / "secrets/api.env"))["APP_RELEASE"] == BASE, "API_BASE_RELEASE")
        require(env_values(read_file(self.base / "secrets/web.env"))["APP_RELEASE"] == WEB_BASE, "WEB_BASE_RELEASE")

    def verify_base(self):
        self.verify_base_configuration()
        super().verify_base()
        probe = "from sqlalchemy import text; from journey_api.db import SessionLocal; import json; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); print(json.dumps(list(s.execute(text('SELECT version_num FROM alembic_version')).scalars()))); s.rollback(); s.close()"
        require(json.loads(compose(self.base, "exec", "-T", "api", "python", "-c", probe)) == [SOURCE_SCHEMA], "BASE_SCHEMA")


    def restore_encrypt_migrate(self, before, dump, encrypted, verify, backup_key):
        from restore_backup import restore_verified_backup
        return restore_verified_backup(self, before, dump, encrypted, verify, backup_key, sys.modules[__name__])

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
        check_space("IMPORT", self.manifest["disk_budget"]["import"])
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
            # The historical config_digest field holds Docker's image identity.
            # Containerd can identify an OCI index/manifest rather than the
            # config blob. Resolve the config through the verified source graph.
            with gzip.open(archive, "rb") as handle:
                config_digest = source_config_digest(handle, entry["config_digest"])
            event("IMPORT_" + name.upper())
            run(["docker", "load", "--input", str(archive)], timeout=600)
            # Docker/containerd may rewrap an imported image in a new manifest.
            # Prove its original config (including rootfs diff IDs), then pin
            # the actual locally loaded immutable ID. Never deploy by tag.
            loaded = json.loads(run(["docker", "image", "inspect", entry["source_reference"]]))[0]
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", loaded["Id"]), "LOADED_IMAGE_ID")
            verify_loaded_image(loaded["Id"], config_digest)
            self.manifest["images"][name] = loaded["Id"]
            self.image_check(name, self.images[name], self.manifest["candidate"])
        for name, reference in self.old_images.items():
            self.image_check(name, reference, BASE if name == "api" else WEB_BASE)
        Upgrade.image_check(self, "dbrestore", self.images["dbrestore"])
        self.verify_runtime_dependencies()
        cleanup_verified_transports(self.package, self.manifest)

    def verify_runtime_dependencies(self):
        # The owner-approved braces exception applies to development tools only.
        # Inspect the actual loaded production image before staging or downtime.
        probe = """
const fs=require('fs'), p=require('path'); let count=0;
function walk(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){
 const f=p.join(d,e.name);
 if(e.isDirectory()&&!e.isSymbolicLink()) walk(f);
 else if(e.name==='package.json'&&JSON.parse(fs.readFileSync(f,'utf8')).name==='braces') count++;
}}
walk('/app'); console.log(JSON.stringify({braces:count}));
"""
        result = json.loads(run(["docker", "run", "--rm", "--network", "none",
                                 self.images["web"], "node", "-e", probe], timeout=60))
        require(result == {"braces": 0}, "WAIVED_DEPENDENCY_IN_RUNTIME")

    def image_check(self, name, reference, candidate=None):
        if name not in {"api", "web"} or not re.fullmatch(r"sha256:[0-9a-f]{64}", reference):
            return Upgrade.image_check(self, name, reference, candidate)
        item = json.loads(run(["docker", "image", "inspect", reference]))[0]
        require(item["Id"] == reference, "CONFIG_DIGEST_MISMATCH")
        require(item["Os"] == "linux" and item["Architecture"] == "amd64", "IMAGE_PLATFORM")
        require(item["Config"]["Labels"].get("org.opencontainers.image.revision") == candidate, "IMAGE_REVISION")

    def stage(self, migration_password):
        self.verify_base()
        require(not self.new.exists() and not self.new.is_symlink(), "PREPARATION_EXISTS")
        require(len(migration_password) >= 20 and not any(c in migration_password for c in "\r\n"), "MIGRATION_SECRET_INVALID")
        originals = {name: read_file(self.base / name) for name in self.base_hashes}
        metadata = {name: (self.base / name).stat() for name in originals}
        parsed = urlsplit(env_values(originals["secrets/api.env"])["DATABASE_URL"])
        require(parsed.scheme == "postgresql+psycopg" and parsed.hostname and parsed.port, "DATABASE_URL")
        migration_url = urlunsplit((parsed.scheme, f"journey_next_migrator:{quote(migration_password, safe='')}@{parsed.hostname}:{parsed.port}", parsed.path, parsed.query, ""))
        self.new.mkdir(mode=0o700)
        secret_metadata = (self.base / "secrets").stat()
        (self.new / "secrets").mkdir(mode=stat.S_IMODE(secret_metadata.st_mode))
        os.chown(self.new / "secrets", secret_metadata.st_uid, secret_metadata.st_gid)
        # Preserve all receipt-bound secrets and mounted files, including their
        # owner and mode. Only the maintenance probe env is regenerated below.
        for name, raw in originals.items():
            if name in ENV_FILES or name in PACKAGE_FILES or name == "secrets/migration.env":
                continue
            info = metadata[name]
            write_new(self.new / name, raw, stat.S_IMODE(info.st_mode))
            os.chown(self.new / name, info.st_uid, info.st_gid)
        changes = {
            ".deployment.env": {"CANDIDATE_COMMIT": self.manifest["candidate"], "API_IMAGE": self.images["api"], "WEB_IMAGE": self.images["web"]},
            "secrets/api.env": {"APP_RELEASE": self.manifest["candidate"]},
            "secrets/web.env": {"APP_RELEASE": self.manifest["candidate"]},
        }
        for name in ENV_FILES:
            info = metadata[name]
            write_new(self.new / name, add_env(originals[name], changes[name]), stat.S_IMODE(info.st_mode))
            os.chown(self.new / name, info.st_uid, info.st_gid)
        # Database-only probes and isolated restore containers require no AI or SMS credentials.
        maintenance = {"APP_RELEASE": self.manifest["candidate"], "DATABASE_URL": migration_url,
                       "AI_SELF_CHECK_ENABLED": "false", "AI_API_KEY_FILE": "", "AI_API_KEY": "",
                       "AI_FEISHU_APP_ID": "", "AI_FEISHU_APP_SECRET": "", "AI_FEISHU_APP_SECRET_FILE": "",
                       "PHONE_OTP_ENABLED": "false", "PHONE_OTP_PROVIDER": "DISABLED"}
        write_new(self.new / "secrets/migration.env", add_env(originals["secrets/api.env"], maintenance))
        for name in PACKAGE_FILES:
            raw = json.dumps(self.manifest, sort_keys=True).encode() if name == "manifest.json" else read_file(self.package / name)
            write_new(self.new / name, raw, 0o644)
        before = json.loads(compose(self.base, "config", "--format", "json"))
        after = json.loads(compose(self.new, "config", "--format", "json"))
        normalized = json.loads(json.dumps(after).replace(str(self.new), str(self.base)))
        for service in ("api", "web"):
            normalized["services"][service]["image"] = self.old_images[service]
            normalized["services"][service]["environment"]["APP_RELEASE"] = before["services"][service]["environment"]["APP_RELEASE"]
        require(normalized == before, "COMPOSE_EXTRA_CHANGE")
        names = set(originals) | set(PACKAGE_FILES) | {"secrets/migration.env"}
        hashes = {name: digest(read_file(self.new / name)) for name in names}
        write_new(self.new / "schema-upgrade-prepared.json", json.dumps({"manifest": self.manifest, "hashes": hashes}, sort_keys=True).encode())
        self.verify_prepared()

    def docker_api(self, env_file, *args, read_only=False, timeout=300):
        require(env_file in {"secrets/api.env", "secrets/migration.env"}, "PROBE_ENV")
        if not read_only:
            allowed_write = env_file == "secrets/migration.env" and (
                args in {("alembic", "upgrade", TARGET_SCHEMA), ("python", "/tmp/grant_runtime.py")}
                or args == tuple(self.catalog_command(apply=True)))
            require(allowed_write, "PRODUCTION_WRITE_PROBE_FORBIDDEN")
        command = ["docker", "run", "--rm", "--network", "host", "--env-file", str(self.new / env_file)]
        if env_file == "secrets/api.env":
            for key, path in SECRET_FILES.items():
                command += ["-v", f"{self.new / path}:/run/secrets/{key}:ro"]
        for source, target in (("secrets/volcengine-rds-ca.pem", "/run/secrets/volcengine-rds-ca.pem"),
                               ("db_facts.py", "/tmp/db_facts.py"), ("grant_runtime.py", "/tmp/grant_runtime.py")):
            command += ["-v", f"{self.new / source}:{target}:ro"]
        if read_only:
            command += ["-e", "PGOPTIONS=-c default_transaction_read_only=on", "-e", "REQUIRE_READ_ONLY=true"]
        return run(command + [self.images["api"], *args], timeout=timeout)

    def verify_runtime_schema(self):
        probe = "from sqlalchemy import text; from journey_api.db import SessionLocal; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); "
        probe += "assert list(s.execute(text('SELECT version_num FROM alembic_version')).scalars()) == [" + repr(TARGET_SCHEMA) + "]; "
        probe += "; ".join(f"assert s.execute(text('select count(*) from {name}')).scalar_one()>=0" for name in NEW_TABLES)
        self.docker_api("secrets/api.env", "python", "-c", probe, read_only=True)

    def verify_login_configuration(self):
        # Validate the actual mounted secrets and production settings without
        # creating an account, consuming a code, sending SMS or calling AI.
        probe = """
import json
from journey_api.config import get_settings
from journey_api.main import app
from fastapi import Response
from journey_api.identity import set_session_cookies, clear_session_cookies, SESSION_COOKIE, STAFF_SESSION_COOKIE, CSRF_COOKIE, STAFF_CSRF_COOKIE
assert len({SESSION_COOKIE, STAFF_SESSION_COOKIE, CSRF_COOKIE, STAFF_CSRF_COOKIE}) == 4
learner=Response(); staff=Response(); logout=Response()
set_session_cookies(learner, 'probe', 'csrf', 60)
set_session_cookies(staff, 'probe', 'csrf', 60, staff=True)
clear_session_cookies(logout, staff=True)
assert all(STAFF_SESSION_COOKIE not in value for value in learner.headers.getlist('set-cookie'))
assert all(not value.startswith(SESSION_COOKIE+'=') and not value.startswith(CSRF_COOKIE+'=') for value in staff.headers.getlist('set-cookie')+logout.headers.getlist('set-cookie'))
s=get_settings()
assert s.app_env == 'production' and not s.allow_fixture_identity
assert s.password_login_enabled and s.phone_otp_enabled and s.phone_otp_provider == 'VOLCENGINE'
assert s.ai_self_check_enabled and s.ai_comment_mention_owner and s.ai_api_key and s.ai_feishu_app_secret
paths=app.openapi()['paths']
assert all('/api/v1/auth/password/'+p in paths for p in ['login','register','reset'])
assert all('/api/v1/review-admin/'+p in paths for p in ['tasks','reviews','members'])
assert s.feishu_oauth_enabled
from journey_api.novice_economy import POINT_TYPES
from journey_api.review_admin_routes import DOMAINS
assert len(POINT_TYPES) == 18 and len(DOMAINS) == 8
from typing import get_args
from journey_api.publishing_departments import PublishingDepartment
assert len(get_args(PublishingDepartment)) == 19
assert '/api/v1/review-admin/members/{user_id}/department' in paths
assert '/api/v1/review-admin/members/{user_id}/demote' in paths
assert '/api/v1/review-admin/community/{module}' in paths
assert '/api/v1/me/knowledge/{module}' in paths
from journey_api.medal_catalog import BADGE_ARTWORKS
assert len(BADGE_ARTWORKS) == 87
assert '/api/v1/review-admin/publications' in paths
assert all(path in paths for path in ['/api/v1/ops/academy/courses', '/api/v1/me/academy',
    '/api/v1/me/academy/courses/{course_id}/video', '/api/v1/me/academy/courses/{course_id}/cover'])
import shutil
assert shutil.which('ffmpeg') and shutil.which('ffprobe')
assert s.ai_model == 'deepseek-v4.1-flash' and s.ai_fallback_model == 'deepseek-v4-pro-0813'
assert all('/api/v1/me/novice/'+p in paths for p in ['tasks','medals','wallet','growth'])
assert all(p in paths for p in ['/api/v1/me/guild', '/api/v1/me/guild/join',
    '/api/v1/me/guild/tasks', '/api/v1/me/guild/requests', '/api/v1/review-admin/guild-requests',
    '/api/v1/review-admin/guild-requests/{request_id}/review'])
assert '/api/v1/me/notifications' in paths and '/api/v1/me/learner-profile' in paths
print(json.dumps({'login_config':'PASS','ai_config_preserved':True,'sms_sent':0}))
"""
        result = json.loads(self.docker_api("secrets/api.env", "python", "-c", probe, read_only=True))
        require(result == {"login_config": "PASS", "ai_config_preserved": True, "sms_sent": 0}, "LOGIN_CONFIG_CHECK")
        event("LOGIN_AND_EXISTING_AI_CONFIG_VERIFIED")

    def guard(self):
        return json.loads(self.docker_api("secrets/migration.env", "python", "-c", read_file(self.package / "facts_guard.py").decode(), read_only=True, timeout=600))

    def verify_restore_space(self):
        size = int(self.docker_api("secrets/migration.env", "python", "-c",
            "from sqlalchemy import text; from journey_api.db import SessionLocal; "
            "s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); "
            "print(s.execute(text('select pg_database_size(current_database())')).scalar_one())", read_only=True).strip())
        require(size > 0, "DATABASE_SIZE_INVALID")
        # Source dump, isolated restored data, encrypted backup and its verified
        # plaintext copy coexist briefly. Keep reserve on both data filesystems.
        check_space("RESTORE", max(2*1024**3, 4*size + 512*1024**2))


    def catalog_command(self, *, apply=False):
        # These UUIDs are already bound to the actual production organization
        # and its configured enrollment reviewer. Never select by display name
        # or silently grant a reviewer new administrator privileges.
        values = env_values(read_file(self.base / "secrets/api.env"))
        organization = values.get("FEISHU_LEARNER_ORGANIZATION_ID", "")
        author = values.get("FEISHU_LEARNER_REVIEWER_ID", "")
        try:
            valid = all(str(uuid.UUID(value)) == value for value in (organization, author))
        except (ValueError, TypeError):
            valid = False
        require(valid, "CURRICULUM_IDENTITY_CONFIG")
        args = ["python", "scripts/upgrade_exploration_catalog.py", "--organization-id", organization,
                "--author-id", author, "--authorization-reference", AUTHORIZATION]
        return args + (["--apply"] if apply else [])

    def verify_catalog_actor(self):
        args = self.catalog_command()
        organization, author = args[3], args[5]
        probe = actor_probe(organization, author)
        require(self.docker_api("secrets/migration.env", "python", "-c", probe, read_only=True).strip()
                == ACTOR_SUCCESS.encode(), "CURRICULUM_CONFIGURED_AUTHOR_NOT_SUPERADMIN")

    def catalog_initialize(self, *, prefix=None):
        command = self.catalog_command(apply=True)
        raw = self.docker_api("secrets/migration.env", *command, timeout=600) if prefix is None else run(prefix + command, timeout=600)
        result = json.loads(raw)
        require(result.get("mode") == "apply" and result.get("schema") == TARGET_SCHEMA
                and result.get("business_records_preserved") is True
                and result.get("legacy_progress_rewritten") is False
                and result.get("independent_review") is False
                and result.get("organization_id") == command[3] and result.get("author_id") == command[5]
                and len(result.get("inserted", [])) + len(result.get("preserved", [])) == 8
                and re.fullmatch(r"[0-9a-f]{64}", result.get("seed_sha256", "")),
                "CURRICULUM_INITIALIZATION_PROOF")
        # The importer proves every preexisting business row is identical;
        # only the fixed source-controlled curriculum may add rows.
        return result

    @staticmethod
    def existing_facts(value):
        return {name: row for name, row in value.items() if name not in NEW_TABLES}

    def validate_restored_database(self, network, restore_env):
        event("REHEARSE_DYNAMIC_EXPLORATION_ON_RESTORED_COPY")
        prefix = ["docker", "run", "--rm", "--network", network, "--env-file", str(restore_env), self.images["api"]]
        guard = read_file(self.package / "facts_guard.py").decode()
        before = json.loads(run(prefix + ["python", "-c", guard], timeout=600))
        require(run(prefix + ["alembic", "heads"], timeout=60).decode().strip() == TARGET_SCHEMA + " (head)", "CANDIDATE_SCHEMA_HEAD")
        require(SOURCE_SCHEMA in run(prefix + ["alembic", "current"]).decode(), "RESTORE_SOURCE_SCHEMA")
        run(prefix + ["alembic", "upgrade", TARGET_SCHEMA], timeout=600)
        after = json.loads(run(prefix + ["python", "-c", guard], timeout=600))
        require(self.existing_facts(after) == self.existing_facts(before), "RESTORE_MIGRATION_CHANGED_BUSINESS_FACTS")
        require(set(NEW_TABLES) <= after.keys() and all(after[name][0] == 0 for name in NEW_TABLES), "RESTORE_NEW_TABLES_NOT_EMPTY")
        require(TARGET_SCHEMA in run(prefix + ["alembic", "current"]).decode(), "RESTORE_TARGET_SCHEMA")
        plan = json.loads(run(prefix + self.catalog_command(), timeout=600))
        require(plan.get("mode") == "plan" and not plan.get("inserted")
                and plan.get("business_records_preserved") is True,
                "RESTORE_CURRICULUM_PLAN")
        initialized = self.catalog_initialize(prefix=prefix)
        # A second execution must preserve administrator content and add no
        # duplicate tasks, documents or audit events.
        first = json.loads(run(prefix + ["python", "-c", guard], timeout=600))
        self.catalog_initialize(prefix=prefix)
        require(json.loads(run(prefix + ["python", "-c", guard], timeout=600)) == first, "RESTORE_IMPORT_NOT_IDEMPOTENT")
        self.verify_old_application_on_restore(network, restore_env)
        require(json.loads(run(prefix + ["python", "-c", guard], timeout=600)) == first, "OLD_APPLICATION_PROBE_WROTE_DATA")
        write_new(self.backup / "migration-rehearsal.json", json.dumps({"candidate": self.manifest["candidate"],
            "from": SOURCE_SCHEMA, "to": TARGET_SCHEMA, "existing_business_rows_preserved": True,
            "curriculum_initialized": True, "curriculum_source_sha256": initialized["seed_sha256"],
            "import_idempotent": True, "old_application_compatibility": "PASS"}).encode())

    def verify_old_application_on_restore(self, network, restore_env):
        # TestClient without a lifespan context exercises real middleware and
        # readiness without starting the external directory synchronization loop.
        # Every DB connection is read-only and points solely at the restored DB.
        probe = """
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from journey_api.main import app
from journey_api.db import SessionLocal
from journey_api.models import TaskVersion
from journey_api.review_admin_models import PublishedTaskContent
client = TestClient(app, base_url='https://journey.muchenai.com')
try:
    response = client.get('/health/ready')
    assert response.status_code == 200 and response.json()['status'] == 'ok'
    with SessionLocal() as session:
        assert session.execute(text('SHOW transaction_read_only')).scalar_one() == 'on'
        assert session.scalar(select(TaskVersion.id).limit(1)) is not None
        assert session.scalar(select(PublishedTaskContent.task_version_id).limit(1)) is not None
finally:
    client.close()
print('OLD_APPLICATION_SCHEMA_COMPATIBLE')
"""
        prefix = ["docker", "run", "--rm", "--network", network, "--env-file", str(restore_env),
            "-e", "PGOPTIONS=-c default_transaction_read_only=on", "-e", "REQUIRE_READ_ONLY=true", self.old_images["api"]]
        require(run(prefix + ["python", "-c", probe], timeout=120).strip() == b"OLD_APPLICATION_SCHEMA_COMPATIBLE",
                "OLD_APPLICATION_SCHEMA_INCOMPATIBLE")

    def activate(self):
        self.verify_base()
        self.verify_prepared()
        verify_protected_containers(self.protected_runtime)
        receipt = json.loads(read_file(self.backup / "backup-receipt.json"))
        require(receipt["restore"] == "PASS" and receipt["candidate"] == self.manifest["candidate"], "BACKUP_RECEIPT")
        require(file_sha(self.backup / "canary.dump.enc") == receipt["backup_sha256"], "BACKUP_CHANGED")
        require(receipt["migration"] == SOURCE_SCHEMA and receipt["production_migration_applied"] is False, "BACKUP_SCHEMA")
        rehearsal = json.loads(read_file(self.backup / "migration-rehearsal.json"))
        require(rehearsal.get("candidate") == self.manifest["candidate"] and rehearsal.get("from") == SOURCE_SCHEMA
                and rehearsal.get("to") == TARGET_SCHEMA and rehearsal.get("curriculum_initialized") is True
                and rehearsal.get("import_idempotent") is True and rehearsal.get("existing_business_rows_preserved") is True
                and rehearsal.get("old_application_compatibility") == "PASS",
                "RESTORE_SCHEMA_PROOF")
        self.verify_catalog_actor()
        busy = self.docker_api("secrets/migration.env", "python", "-c",
            "from sqlalchemy import text; from journey_api.db import SessionLocal; s=SessionLocal(); s.execute(text('SET TRANSACTION READ ONLY')); print(s.execute(text(\"select count(*) from ai_self_checks where status in ('RUNNING','SENDING')\")).scalar_one())", read_only=True)
        require(busy.strip() == b"0", "AI_REQUEST_IN_PROGRESS_RETRY_AFTER_COMPLETION")
        event("BRIEF_JOURNEY_MAINTENANCE")
        post_initialization = None
        switched = False
        try:
            compose(self.base, "stop", "web", "api", timeout=90)
            before = self.guard()
            require(SOURCE_SCHEMA in self.docker_api("secrets/migration.env", "alembic", "current", read_only=True).decode(), "SOURCE_SCHEMA")
            event("UPGRADE_DYNAMIC_EXPLORATION_SCHEMA")
            self.docker_api("secrets/migration.env", "alembic", "upgrade", TARGET_SCHEMA, timeout=600)
            after = self.guard()
            require(self.existing_facts(after) == self.existing_facts(before), "PRODUCTION_MIGRATION_CHANGED_BUSINESS_FACTS")
            require(set(NEW_TABLES) <= after.keys() and all(after[name][0] == 0 for name in NEW_TABLES), "PRODUCTION_NEW_TABLES_NOT_EMPTY")
            self.docker_api("secrets/migration.env", "python", "/tmp/grant_runtime.py")
            event("INITIALIZE_OWNER_APPROVED_CURRICULUM")
            initialized = self.catalog_initialize()
            require(initialized["seed_sha256"] == rehearsal["curriculum_source_sha256"], "CURRICULUM_SOURCE_CHANGED")
            write_new(self.backup / "curriculum-initialization.json", json.dumps(initialized, sort_keys=True).encode())
            post_initialization = self.guard()
            self.verify_runtime_schema()
            event("SWITCH_JOURNEY_API_AND_WEB")
            switched = True
            self.up(self.new)
            verify_protected_containers(self.protected_runtime)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")}, public=False)
            self.pointer(self.new)
            self.healthy(self.new, self.manifest["candidate"], {name: self.images[name] for name in ("api", "web")})
            for path in ("/join", "/review/login", "/ops/login"):
                run(["curl", "-fsS", "--connect-timeout", "3", "--max-time", "15", "-o", "/dev/null", "https://journey.muchenai.com" + path])
            for path in ("/api/learner/guild", "/api/learner/profile/history", "/api/review-native/guild-requests", "/api/learner/exploration", "/api/review-native"):
                status = run(["curl", "-sS", "--connect-timeout", "3", "--max-time", "15", "-o", "/dev/null", "-w", "%{http_code}", "https://journey.muchenai.com" + path])
                require(status.strip() == b"401", "UNAUTHENTICATED_ACCESS_NOT_PROTECTED")
            final = {"release": self.manifest["candidate"], "status": "PASS", "old_assignments_unchanged": True,
                "schema": TARGET_SCHEMA, "database_schema_changed": True, "previous_web_release": WEB_BASE,
                "previous_api_release": BASE, "package_run_id": self.manifest["package_run_id"],
                "other_containers_unchanged": True, "curriculum_source_sha256": initialized["seed_sha256"],
                "existing_business_rows_preserved": True, "curriculum_initialized": True}
            write_new(self.new / "activation-receipt.json", json.dumps(final, sort_keys=True).encode())
            print(json.dumps(final, sort_keys=True), flush=True)
        except (Exception, KeyboardInterrupt):
            if switched:
                try:
                    compose(self.new, "stop", "web", "api", timeout=90)
                except (Exception, KeyboardInterrupt):
                    # The write boundary cannot be proven if candidate shutdown
                    # failed. Attempt to restore its availability rather than
                    # rolling the old API over a potentially writing service.
                    self.up(self.new)
                    if self.current() != self.new:
                        self.pointer(self.new)
                    raise UpgradeError("CANDIDATE_STOP_UNCONFIRMED_FORWARD_FIX_REQUIRED") from None
                try:
                    unchanged = post_initialization is not None and self.guard() == post_initialization
                except Exception:
                    unchanged = False
                if not unchanged:
                    # Learner activity after the candidate started is durable.
                    # Keep schema/content and candidate runtime available for a
                    # forward fix; never replay a DB backup over new work.
                    self.up(self.new)
                    if self.current() != self.new:
                        self.pointer(self.new)
                    raise UpgradeError("BUSINESS_WRITES_DETECTED_FORWARD_FIX_REQUIRED") from None
            # Before candidate startup only the additive DDL and the transactional,
            # source-controlled curriculum import can have run. The old services
            # remain compatible and must restart even if a diagnostic probe fails.
            event("RESTORE_PREVIOUS_APPLICATION")
            self.up(self.base)
            if self.current() != self.base:
                self.pointer(self.base)
            self.healthy(self.base, BASE, self.old_images)
            verify_protected_containers(self.protected_runtime)
            raise


def main():
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(socket.gethostname() == "journey-next-staging", "UNEXPECTED_HOST")
    require(ROOT.resolve() == ROOT, "ROOT_SYMLINK")
    os.umask(0o077)
    from restore_backup import install_safe_command_reporting
    install_safe_command_reporting(sys.modules[__name__])
    package = Path(__file__).resolve().parent
    manifest = json.loads(read_file(package / "manifest.json"))
    require(manifest["base_candidate"] == BASE and manifest["migrations"] == {"from": SOURCE_SCHEMA, "to": TARGET_SCHEMA}, "MANIFEST")
    payload = json.loads(sys.stdin.read(16384))
    import fcntl
    descriptor = os.open(ROOT / ".schema-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = Activation(manifest, package)
        release.protected_runtime = protected_containers()
        event("VERIFY_AND_IMPORT_OFFLINE_IMAGES")
        release.import_images()
        event("STAGE_EXISTING_PRODUCTION_CONFIGURATION")
        release.stage(payload["migration_password"])
        release.verify_login_configuration()
        release.verify_catalog_actor()
        release.verify_restore_space()
        event("BACKUP_AND_PROVE_RESTORE")
        release.backup_migrate(payload["backup_key"])
        release.activate()
        event("RELEASE_COMPLETE")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        category = str(error) if isinstance(error, (UpgradeError, DiskSpaceError)) else type(error).__name__
        if isinstance(error, AssertionError) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", str(error)):
            category = str(error)
        print(json.dumps({"result": "STOP", "category": category, "do_not_retry_blindly": True}), flush=True)
        raise SystemExit(1)
