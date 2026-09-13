"""Application-only Canary switch. No migrations, database restore or identity bootstrap.

Prepare never changes running containers. Switch requires a separately supplied manifest
hash and explicit interruption acknowledgement. A failed switch rolls back once; rollback
recreates old application containers, never restores old database contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path("/srv/journey-next-production/canary")
BASE = "8f1b7e81dca9755c07babe10e1c270744a3d5717"
OLD = ROOT / "releases" / (BASE + "-34560076583")
PROJECT = "journey-next-greenfield-canary"
OLD_IMAGES = {
    "api": "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:93736fbdf9670503e97ec90c2b472f4b85a1893501a6162afac39df10fc05a69",
    "web": "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:e35136c749b3b7844ce391f304467823620195cb3437a9977f6438e81b53a0e9",
}
COPY_FILES = ("compose.canary.yaml", "compose.sh", "wp31_exec_env.py", "secrets/volcengine-rds-ca.pem")
ENV_FILES = (".deployment.env", "secrets/api.env", "secrets/web.env")


class UpgradeError(RuntimeError):
    """Fixed non-sensitive error categories only."""


def require(value, category):
    if not value:
        raise UpgradeError(category)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(args, *, cwd=None, timeout=30):
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        if Path(args[0]).name == "compose.sh":
            probe = subprocess.run(
                ["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + PROJECT,
                 "--format", "{{.Names}}|{{.State}}|{{.Status}}"],
                capture_output=True, timeout=10,
            )
            safe = probe.stdout.decode(errors="replace").strip().splitlines()
            names = [PROJECT + "-" + service + "-1" for service in ("api", "web")]
            details = subprocess.run(
                ["docker", "inspect", *names, "--format",
                 "{{.Name}}|{{.State.Status}}|{{.State.ExitCode}}|{{.State.Health.Status}}|{{with index .State.Health.Log 0}}{{.Output}}{{end}}"],
                capture_output=True, timeout=10,
            )
            detail_lines = []
            for line in details.stdout.decode(errors="replace").strip().splitlines():
                fields = line.split("|", 4)
                if len(fields) == 5:
                    fields[4] = re.sub(r"(?i)(secret|token|password|database_url|authorization)[^ ]*", "[REDACTED]", fields[4])[:512]
                    detail_lines.append("|".join(fields))
            print(json.dumps({"compose_failure": True, "compose_exit": result.returncode,
                              "containers": safe[:4], "health_probe": detail_lines[:4]},
                       separators=(",", ":")), flush=True)
        require(False, "COMMAND_FAILED")
    return result.stdout


def env(raw):
    require(b"\r" not in raw and b"\0" not in raw, "ENV_FORMAT")
    pairs = [line.split("=", 1) for line in raw.decode().splitlines()]
    require(all(len(p) == 2 and re.fullmatch(r"[A-Z][A-Z0-9_]*", p[0]) for p in pairs), "ENV_FORMAT")
    require(len({p[0] for p in pairs}) == len(pairs), "ENV_DUPLICATE")
    return dict(pairs)


def changed_env(raw, changes):
    before = env(raw)
    require(set(changes) <= before.keys(), "ENV_FIELD_MISSING")
    after = b"".join((key + "=" + changes[key]).encode() + (b"\n" if line.endswith(b"\n") else b"")
                     if (key := line.split(b"=", 1)[0].decode()) in changes else line
                     for line in raw.splitlines(keepends=True))
    require(env(after) == {**before, **changes}, "ENV_EXTRA_CHANGE")
    return after


def read_file(path):
    require(path.is_file() and not path.is_symlink() and path.resolve() == path, "UNSAFE_FILE")
    require(path.stat().st_size <= 1048576, "FILE_TOO_LARGE")
    return path.read_bytes()


def write_new(path, raw, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def load_manifest(path, expected):
    raw = read_file(path)
    require(re.fullmatch(r"[0-9a-f]{64}", expected) and digest(raw) == expected, "MANIFEST_HASH")
    m = json.loads(raw)
    require(set(m) == {"schema_version", "base_candidate", "candidate", "images", "compatibility"}, "MANIFEST_FIELDS")
    require(m["schema_version"] == 1 and m["base_candidate"] == BASE, "BASE_CANDIDATE")
    require(re.fullmatch(r"[0-9a-f]{40}", m["candidate"]) and m["candidate"] != BASE, "NEW_CANDIDATE")
    require(m["compatibility"] == "NO_SCHEMA_OR_IDENTITY_CHANGE", "COMPATIBILITY_REQUIRED")
    require(set(m["images"]) == {"api", "web"}, "IMAGE_SERVICES")
    for name, ref in m["images"].items():
        require(re.fullmatch(r"ghcr\.io/muchenai/muchen-journey-vnext-" + name + r"@sha256:[0-9a-f]{64}", ref), "IMAGE_REFERENCE")
        require(ref != OLD_IMAGES[name], "OLD_IMAGE_AS_NEW")
    return m


def compose(path, *args, timeout=30):
    return run([str(path / "compose.sh"), "-f", "compose.canary.yaml", *args], cwd=path, timeout=timeout)


class Upgrade:
    def __init__(self, manifest):
        self.m = manifest
        self.new = ROOT / "releases" / (manifest["candidate"] + "-app-upgrade")

    def current(self):
        link = ROOT / "current"
        require(link.is_symlink(), "CURRENT_NOT_SYMLINK")
        return link.resolve()

    def containers(self, allowed, *, allow_missing=False):
        names = [PROJECT + "-" + s + "-1" for s in ("api", "web")]
        actual = set(run(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + PROJECT, "--format", "{{.Names}}"]).decode().splitlines())
        require(actual <= set(names) and (allow_missing or actual == set(names)), "EXTRA_OR_MISSING_CONTAINER")
        records = json.loads(run(["docker", "inspect", *sorted(actual)])) if actual else []
        require(len(records) == len(actual), "CONTAINER_COUNT")
        for record in records:
            service = record["Config"]["Labels"]["com.docker.compose.service"]
            require(service in allowed, "CONTAINER_SERVICE")
            require(record["Config"]["Image"] in allowed[service], "UNEXPECTED_IMAGE")
            labels = record["Config"]["Labels"]
            require(labels["com.docker.compose.project"] == PROJECT, "CONTAINER_PROJECT")
            require(labels["com.docker.compose.project.working_dir"] in (str(OLD), str(self.new)), "CONTAINER_RELEASE")
        return records

    def healthy(self, release, candidate, images, *, public=True):
        for item in self.containers({k: {v} for k, v in images.items()}):
            require(item["State"]["Running"] and item["State"].get("Health", {}).get("Status") == "healthy", "UNHEALTHY")
            values = dict(pair.split("=", 1) for pair in item["Config"]["Env"])
            service = item["Config"]["Labels"]["com.docker.compose.service"]
            require(all(values.get(k) == v for k, v in env(read_file(release / "secrets" / (service + ".env"))).items()), "RUNTIME_ENV_DRIFT")
            require(values.get("APP_RELEASE") == candidate, "RUNTIME_RELEASE")
        if public:
            public_result = json.loads(run(["curl", "-fsS", "--connect-timeout", "3", "--max-time", "10", "https://journey.muchenai.com/health/ready"]))
            require(public_result == {"status": "ready", "release": candidate}, "PUBLIC_HEALTH")

    def image_check(self, service, ref, candidate):
        value = json.loads(run(["docker", "image", "inspect", ref]))[0]
        require(value["Os"] == "linux" and value["Architecture"] == "amd64", "IMAGE_PLATFORM")
        require(value["Config"]["Labels"]["org.opencontainers.image.revision"] == candidate, "IMAGE_REVISION")
        require(ref in value.get("RepoDigests", []), "IMAGE_DIGEST")

    def prepare(self):
        require(self.current() == OLD and OLD.resolve() == OLD, "CURRENT_CHANGED")
        require(not self.new.exists() and not self.new.is_symlink(), "PREPARATION_EXISTS")
        self.healthy(OLD, BASE, OLD_IMAGES)
        originals = {name: read_file(OLD / name) for name in COPY_FILES + ENV_FILES}
        for name in ENV_FILES:
            require(stat.S_IMODE((OLD / name).stat().st_mode) == 0o600, "ENV_PERMISSIONS")
        api, web, deployment = (env(originals[x]) for x in ("secrets/api.env", "secrets/web.env", ".deployment.env"))
        require(all(e.get("APP_RELEASE") == BASE and e.get("RELEASE_MARKER") == "PRODUCTION_CANARY_UAT" and e.get("ALLOW_FIXTURE_IDENTITY") == "false" for e in (api, web)), "CANARY_SETTINGS")
        require(api.get("ATTACHMENTS_ENABLED") == "false" and api.get("NOTIFICATION_RECIPIENTS_ENABLED") == "false", "SIDE_EFFECT_SETTINGS")
        from urllib.parse import urlsplit
        require(urlsplit(api["DATABASE_URL"]).path == "/journey_next_canary_20260901_c72fea5", "DATABASE_CHANGED")
        require(deployment.get("API_IMAGE") == OLD_IMAGES["api"] and deployment.get("WEB_IMAGE") == OLD_IMAGES["web"], "OLD_IMAGE_BINDING")
        for service in ("api", "web"):
            # All network pulls happen before a possible interruption.
            for ref, candidate in ((OLD_IMAGES[service], BASE), (self.m["images"][service], self.m["candidate"])):
                run(["docker", "pull", ref], timeout=600)
                self.image_check(service, ref, candidate)
        require(self.current() == OLD, "CURRENT_CHANGED")
        require(all(read_file(OLD / k) == v for k, v in originals.items()), "FILES_CHANGED")
        self.new.mkdir(mode=0o700)
        (self.new / "secrets").mkdir(mode=0o700)
        for name in COPY_FILES:
            write_new(self.new / name, originals[name], stat.S_IMODE((OLD / name).stat().st_mode))
        changes = {"secrets/api.env": {"APP_RELEASE": self.m["candidate"]}, "secrets/web.env": {"APP_RELEASE": self.m["candidate"]}, ".deployment.env": {"CANDIDATE_COMMIT": self.m["candidate"], "API_IMAGE": self.m["images"]["api"], "WEB_IMAGE": self.m["images"]["web"]}}
        for name in ENV_FILES:
            write_new(self.new / name, changed_env(originals[name], changes[name]))
        before = json.loads(compose(OLD, "config", "--format", "json"))
        after = json.loads(compose(self.new, "config", "--format", "json"))
        require(set(before["services"]) == set(after["services"]) == {"api", "web"}, "COMPOSE_SERVICES")
        normalized = json.loads(json.dumps(after).replace(str(self.new), str(OLD)))
        for service in ("api", "web"):
            normalized["services"][service]["image"] = OLD_IMAGES[service]
            normalized["services"][service]["environment"]["APP_RELEASE"] = BASE
        require(normalized == before, "COMPOSE_EXTRA_CHANGE")
        state = {"manifest": self.m, "old_hashes": {k: digest(v) for k, v in originals.items()}, "new_hashes": {k: digest(read_file(self.new / k)) for k in COPY_FILES + ENV_FILES}}
        write_new(self.new / "upgrade-prepared.json", json.dumps(state, sort_keys=True).encode())

    def verify_prepared(self):
        state = json.loads(read_file(self.new / "upgrade-prepared.json"))
        require(state["manifest"] == self.m, "MANIFEST_CHANGED")
        for path, key in ((OLD, "old_hashes"), (self.new, "new_hashes")):
            require(set(state[key]) == set(COPY_FILES + ENV_FILES), "PREPARED_FIELDS")
            require(all(digest(read_file(path / name)) == value for name, value in state[key].items()), "PREPARED_FILES_CHANGED")

    def pointer(self, path):
        temp = ROOT / (".current-app-upgrade-" + self.m["candidate"])
        os.symlink(path, temp)
        os.replace(temp, ROOT / "current")

    def up(self, path):
        compose(path, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "240", "api", "web", timeout=300)

    def rollback(self):
        self.verify_prepared()
        require(self.current() in (OLD, self.new), "CURRENT_CHANGED")
        self.containers({s: {OLD_IMAGES[s], self.m["images"][s]} for s in ("api", "web")}, allow_missing=True)
        for s in ("api", "web"):
            self.image_check(s, OLD_IMAGES[s], BASE)
        self.up(OLD)
        self.healthy(OLD, BASE, OLD_IMAGES)
        if self.current() != OLD:
            self.pointer(OLD)

    def switch(self):
        self.verify_prepared()
        require(self.current() == OLD, "CURRENT_CHANGED")
        self.healthy(OLD, BASE, OLD_IMAGES)
        for s in ("api", "web"):
            self.image_check(s, self.m["images"][s], self.m["candidate"])
            self.image_check(s, OLD_IMAGES[s], BASE)
        write_new(self.new / "upgrade-attempt.json", b'{"started":true}')
        try:
            self.up(self.new)
            self.healthy(self.new, self.m["candidate"], self.m["images"], public=False)
            self.pointer(self.new)
            self.healthy(self.new, self.m["candidate"], self.m["images"])
        except (Exception, KeyboardInterrupt) as error:
            failure_category = str(error) if isinstance(error, UpgradeError) else type(error).__name__
            try:
                self.rollback()
            except (Exception, KeyboardInterrupt):
                raise UpgradeError("SWITCH_FAILED_ROLLBACK_NOT_CONFIRMED") from None
            raise UpgradeError(f"SWITCH_FAILED_OLD_VERSION_HEALTHY:{failure_category}") from None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=("prepare", "switch", "rollback"))
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--acknowledge-interruption", action="store_true")
    args = p.parse_args()
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(args.phase == "prepare" or args.acknowledge_interruption, "INTERRUPTION_ACK_REQUIRED")
    require(ROOT.resolve() == ROOT and (ROOT / "releases").resolve() == ROOT / "releases", "ROOT_SYMLINK")
    os.umask(0o077)
    import fcntl
    fd = os.open(ROOT / ".app-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        upgrade = Upgrade(load_manifest(args.manifest.resolve(), args.manifest_sha256))
        getattr(upgrade, args.phase)()
        print(json.dumps({"phase": args.phase, "result": "PASS", "database_restored": False, "identity_initialized": False}))


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"result": "STOP", "category": str(error) if isinstance(error, UpgradeError) else type(error).__name__, "do_not_retry_blindly": True}))
        sys.exit(1)
