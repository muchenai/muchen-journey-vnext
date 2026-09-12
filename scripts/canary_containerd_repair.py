"""Repair the exact Docker/containerd pull failure on the staging host.

This intentionally restarts Docker (and therefore briefly interrupts containers),
but never touches the database, release symlink, compose files, or application data.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

API = "ghcr.io/muchenai/muchen-journey-vnext-api@sha256:7fffe983470eddbe91743f7894edbff3acd7e3b01e25ce773788c4efc9720026"


def run(args, timeout=60, **kwargs):
    started = time.monotonic()
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)
    return {"command": args[:3], "exit": p.returncode, "seconds": round(time.monotonic() - started, 2),
            "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}


def main():
    if sys.platform != "linux" or not hasattr(__import__("os"), "geteuid") or __import__("os").geteuid() != 0:
        raise RuntimeError("INVOCATION_INVALID")
    if subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip() != "journey-next-staging":
        raise RuntimeError("HOST_INVALID")
    before = run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"])
    restart = run(["systemctl", "restart", "docker"], timeout=120)
    if restart["exit"]:
        raise RuntimeError("DOCKER_RESTART_FAILED:" + json.dumps(restart))
    info = run(["docker", "info", "--format", "{{json .}}"])
    old = run(["docker", "inspect", "--format", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", "journey-next-greenfield-canary-api-1"])
    pull = run(["docker", "pull", API], timeout=1800)
    result = {"repair": "PASS" if pull["exit"] == 0 else "PULL_FAILED", "database_changed": False,
              "service_switched": False, "before": before, "restart": restart, "docker_info": info,
              "old_api_after_restart": old, "new_api_pull": pull}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if pull["exit"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"repair": "STOP", "error": str(exc), "database_changed": False, "service_switched": False}, separators=(",", ":")))
        raise SystemExit(1)
