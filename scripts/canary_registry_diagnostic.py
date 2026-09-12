"""Read-only ECS/GHCR diagnosis for the pinned API image."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

API = "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:7fffe983470eddbe91743f7894edbff3acd7e3b01e25ce773788c4efc9720026"
WEB = "ghcr.io/muchenai/muchen-journey-vnext-web@sha256:0788e5f191344394ae83d3c349bef25c33e3782fcb999c33a4ffc5fe703feb72"
OLD_API = "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:93736fbdf9670503e97ec90c2b472f4b85a1893501a6162afac39df10fc05a69"


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
                  "old_api": run(["docker", "image", "inspect", OLD_API]),
                  "new_api_manifest": run(["docker", "manifest", "inspect", API], timeout=60),
                  "new_web_manifest": run(["docker", "manifest", "inspect", WEB], timeout=60),
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
