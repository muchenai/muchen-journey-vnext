"""Prepare one pinned application package; no switch, restore or bootstrap entrypoint.

Invoked on ECS by the separately authorized prepare-only workflow. A short-lived
registry token arrives on stdin and is stored only in an isolated Docker config.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

CANDIDATE = "3fa84fdfe0d0e38fbab0b649e6a78f49713be10d"
PACKAGE_RUN = 34589305423
HASHES = {
    "canary_app_upgrade.py": "be73bd2beb4224f4afe57d220fe624e58ba919b8a63206f9f88d2c1384421858",
    "manifest.json": "90ebd5a71306ee97b1ea6080ae34b7d42317f3712b85c6da0b717afe70806310",
    "compatibility.json": "6ad1d24dc00eb5668b5fb9d4a96810b8465a3d8baf8cbe6b2fe3bd6491e6fb64",
}


class PreparationError(RuntimeError):
    pass


def verify_package(directory):
    for name, expected in HASHES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
            raise PreparationError("UNSAFE_PACKAGE_FILE")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise PreparationError("PACKAGE_HASH_MISMATCH")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest["candidate"] != CANDIDATE:
        raise PreparationError("CANDIDATE_MISMATCH")
    return manifest


def command_label(args):
    if args[:2] == ["docker", "pull"]:
        return "pull_" + ("api" if "-api@" in args[2] else "web")
    if args[:3] == ["docker", "image", "inspect"]:
        return "image_inspect"
    if args[:2] == ["docker", "inspect"]:
        return "container_inspect"
    if args[:2] == ["docker", "ps"]:
        return "container_list"
    if args[0] == "curl":
        return "public_readiness"
    if Path(args[0]).name == "compose.sh" and args[1:] == ["-f", "compose.canary.yaml", "config", "--format", "json"]:
        return "compose_config"
    raise PreparationError("COMMAND_NOT_ALLOWED")


def safe_run(args, *, cwd=None, timeout=30):
    label = command_label(args)
    if label.startswith("pull_") and timeout < 1800:
        timeout = 1800
    print(json.dumps({"step": label, "state": "START"}), flush=True)
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise PreparationError(label + ":TIMEOUT") from None
    if p.returncode:
        # Never emit raw Docker inspect/config output or uncontrolled stderr.
        stderr = p.stderr.lower()
        reason = "UNAUTHORIZED" if b"unauthorized" in stderr or b"denied" in stderr else "NONZERO_EXIT"
        raise PreparationError(label + ":" + reason)
    print(json.dumps({"step": label, "state": "PASS"}), flush=True)
    return p.stdout


def prepare(directory, actor, token):
    if sys.platform != "linux" or os.geteuid() != 0:
        raise PreparationError("LINUX_ROOT_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,99}", actor):
        raise PreparationError("ACTOR_INVALID")
    if not token or len(token) > 4096 or any(c.isspace() for c in token):
        raise PreparationError("TOKEN_INVALID")
    manifest = verify_package(directory)
    spec = importlib.util.spec_from_file_location("pinned_app_upgrade", directory / "canary_app_upgrade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run = safe_run
    module.load_manifest(directory / "manifest.json", HASHES["manifest.json"])
    root = module.ROOT
    if root.resolve() != root or (root / "releases").resolve() != root / "releases":
        raise PreparationError("ROOT_SYMLINK")
    import fcntl
    fd = os.open(root / ".app-upgrade.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        upgrade = module.Upgrade(manifest)
        if upgrade.current() != module.OLD:
            raise PreparationError("CURRENT_CHANGED")
        if upgrade.new.exists() or upgrade.new.is_symlink():
            raise PreparationError("PREPARATION_ALREADY_EXISTS_INSPECT_FIRST")
        upgrade.healthy(module.OLD, module.BASE, module.OLD_IMAGES)
        config = Path(tempfile.mkdtemp(prefix=".registry-", dir=directory))
        previous = os.environ.get("DOCKER_CONFIG")
        os.environ["DOCKER_CONFIG"] = str(config)
        try:
            p = subprocess.run(["docker", "login", "ghcr.io", "-u", actor, "--password-stdin"],
                               input=token.encode(), capture_output=True, timeout=30)
            token = ""
            if p.returncode:
                raise PreparationError("REGISTRY_LOGIN_FAILED")
            print(json.dumps({"step": "temporary_registry_login", "state": "PASS"}), flush=True)
            upgrade.prepare()
            upgrade.verify_prepared()
            upgrade.healthy(module.OLD, module.BASE, module.OLD_IMAGES)
            if upgrade.current() != module.OLD:
                raise PreparationError("CURRENT_CHANGED")
        finally:
            if previous is None:
                os.environ.pop("DOCKER_CONFIG", None)
            else:
                os.environ["DOCKER_CONFIG"] = previous
            if config.is_symlink() or config.resolve().parent != directory:
                raise PreparationError("CREDENTIAL_CLEANUP_PATH_CHANGED")
            shutil.rmtree(config)
    result = {"phase": "prepare", "result": "PASS", "candidate": CANDIDATE,
              "package_run": PACKAGE_RUN, "switch_performed": False,
              "database_restored": False, "identity_initialized": False,
              "temporary_registry_credentials_removed": True}
    with (directory / "result.json").open("x") as f:
        json.dump(result, f)
    print(json.dumps(result), flush=True)


def main():
    os.umask(0o077)
    directory = Path(__file__).resolve().parent
    expected_root = Path("/srv/journey-next-production/canary/app-prepare-runs")
    if directory.parent != expected_root or expected_root.resolve() != expected_root:
        raise PreparationError("REMOTE_DIRECTORY_INVALID")
    if not re.fullmatch(r"[0-9]+-[0-9]+", directory.name) or len(sys.argv) != 2:
        raise PreparationError("INVOCATION_INVALID")
    prepare(directory, sys.argv[1], sys.stdin.read(4097).strip())


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"result": "STOP", "category": str(error) if isinstance(error, PreparationError) else type(error).__name__,
                          "do_not_retry_blindly": True}), flush=True)
        sys.exit(1)
