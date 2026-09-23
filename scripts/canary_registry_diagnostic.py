"""Read-only ECS/GHCR diagnosis for the pinned API image."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time

API = "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:7e4d1ae0de84712045e4119d855bc47a2f30f438653ffaaefff1494369ef9d0d"
WEB = "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:381bd7d0e82c8d95aed4990782bf6fb9edc91d0d21eb6f8535714fb703c5285b"
DBRESTORE = "ghcr.io/muchenai/muchen-journey-vnext-dbrestore@sha256:1517ffbd8fdf7c4946535604bfa8df5299456b7749e5396c0edcbb345fe76d6a"
OLD_API = "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:1e1fd3bdff18f049fffb711e080f55f54cebe227bd197cbd34f858c7f847c45d"


def prepare_processes(proc_root=Path("/proc")):
    """Only emit known operation labels and pinned image references, never argv/env."""
    rows = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            role = None
            reference = None
            if len(argv) >= 3 and Path(argv[0]).name == "docker" and argv[1] == "pull":
                role = "docker_image_download"
                reference = next((value for value in argv[2:] if value in {API, WEB, DBRESTORE, OLD_API}), None)
            elif any(Path(value).name == "canary_schema_upgrade.py" for value in argv):
                role = "schema_upgrade"
            if role:
                rows.append({"pid": int(entry.name), "operation": role, "pinned_image": reference})
        except (OSError, ValueError):
            continue
    return rows


def active_content():
    """Summarize download progress without exposing URLs or authorization fields."""
    result = subprocess.run(["ctr", "--namespace", "moby", "content", "active"], capture_output=True, text=True, timeout=20)
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and re.search(r"sha256:[0-9a-f]{64}", fields[0]):
            rows.append({"digest": re.search(r"sha256:[0-9a-f]{64}", fields[0]).group(),
                         "size": fields[1] if re.fullmatch(r"[0-9.A-Za-z]+", fields[1]) else "unknown",
                         "age": fields[2] if re.fullmatch(r"[0-9.A-Za-z]+", fields[2]) else "unknown"})
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "downloads": rows}


class DiagnosticError(RuntimeError):
    pass


def run(args, timeout=40):
    start = time.monotonic()
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"command": args[:3], "status": "TIMEOUT", "seconds": round(time.monotonic() - start, 2)}
    out = {"command": args[:3], "status": "PASS" if p.returncode == 0 else "FAIL",
           "exit": p.returncode, "seconds": round(time.monotonic() - start, 2)}
    if p.returncode == 0 and args[:2] in (["df", "-P"], ["docker", "info"], ["docker", "system"], ["bash", "-lc"]):
        out["output"] = p.stdout[-12000:]
    if p.returncode == 0 and args[:3] == ["docker", "manifest", "inspect"]:
        try:
            value = json.loads(p.stdout)
            manifests = value.get("manifests", []) if isinstance(value, dict) else []
            layers = value.get("layers", []) if isinstance(value, dict) else []
            if manifests:
                out["platforms"] = [x.get("platform") for x in manifests]
            if layers:
                sizes = [int(x.get("size", 0)) for x in layers]
                out.update(layer_count=len(sizes), compressed_bytes=sum(sizes), layer_sizes=sizes)
        except (ValueError, TypeError):
            out["manifest_parse"] = "FAILED"
    if p.returncode:
        low = p.stderr.lower()
        out["error_category"] = "UNAUTHORIZED" if "unauthorized" in low or "denied" in low else "COMMAND_FAILED"
    return out


def run_shell(command, timeout=40):
    return run(["bash", "-lc", command], timeout=timeout)


def main():
    if os.geteuid() != 0 or sys.platform != "linux" or len(sys.argv) != 2:
        raise DiagnosticError("INVOCATION_INVALID")
    actor, token = sys.argv[1], sys.stdin.read(4097).strip()
    if not actor or not token:
        raise DiagnosticError("REGISTRY_CREDENTIAL_MISSING")
    with tempfile.TemporaryDirectory(prefix="registry-diagnostic-", dir="/tmp") as config:
        os.environ["DOCKER_CONFIG"] = config
        login = subprocess.run(["docker", "login", "ghcr.io", "-u", actor, "--password-stdin"], input=token, text=True, capture_output=True, timeout=30)
        token = ""
        if login.returncode:
            raise DiagnosticError("REGISTRY_LOGIN_FAILED")
        result = {"diagnostic": "PASS", "pull_performed": False, "container_changed": False,
                  "database_changed": False, "credential_cleanup": False,
                  "prepare_processes": prepare_processes(),
                  "active_content": active_content(),
                  "old_api": run(["docker", "image", "inspect", OLD_API]),
                  "disk_root": run(["df", "-P", "/"]),
                  "docker_info": run(["docker", "info", "--format", "{{json .}}"]),
                  "docker_disk_usage": run(["docker", "system", "df", "--format", "{{json .}}"]),
                  "docker_disk_usage_verbose": run(["docker", "system", "df", "-v"], timeout=30),
                  "containerd_snapshots": run(["ctr", "--namespace", "moby", "snapshots", "ls"], timeout=30),
                  "containerd_leases": run(["ctr", "--namespace", "moby", "leases", "ls"], timeout=30),
                  "docker_service_log": run_shell("journalctl -u docker --since '2026-09-12 00:00:00' --no-pager -n 100", timeout=30),
                  "new_api_manifest": run(["docker", "manifest", "inspect", API], timeout=60),
                  "new_web_manifest": run(["docker", "manifest", "inspect", WEB], timeout=60),
                  "restore_manifest": run(["docker", "manifest", "inspect", DBRESTORE], timeout=60),
                  # GHCR deliberately returns 401 for an unauthenticated /v2/ probe;
                  # transport reachability is the signal here, not HTTP auth status.
                  "network_probe": run(["curl", "-sS", "--connect-timeout", "5", "--max-time", "20", "-o", "/dev/null", "-w", "%{http_code}", "https://ghcr.io/v2/"], timeout=30)}
    result["credential_cleanup"] = True
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as e:
        print(json.dumps({"diagnostic": "STOP", "category": str(e) if isinstance(e, DiagnosticError) else type(e).__name__, "pull_performed": False, "do_not_retry_blindly": True}))
        raise SystemExit(1)
