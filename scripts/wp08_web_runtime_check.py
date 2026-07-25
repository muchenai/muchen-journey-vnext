#!/usr/bin/env python3
"""Exercise the production Web readiness and anonymous /ops contracts."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT / "apps" / "web" / ".next" / "standalone"
RELEASE = "wp08-web-runtime-check"
SCRIPT_NONCE = re.compile(rb"<script\b[^>]*\bnonce=[\"']([^\"']+)", re.IGNORECASE)
SCRIPT_TAG = re.compile(rb"<script\b", re.IGNORECASE)
POLICY_NONCE = re.compile(r"(?:^|;\s*)script-src[^;]*'nonce-([^']+)'")


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def request(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return (
                response.status,
                response.read(),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.read(),
            {key.lower(): value for key, value in error.headers.items()},
        )


def main() -> None:
    server = STANDALONE / "server.js"
    if not server.is_file():
        raise SystemExit("WP08_WEB_RUNTIME_ERROR: production build is missing")

    port = unused_port()
    environment = os.environ.copy()
    environment.update(
        {
            "ALLOW_FIXTURE_IDENTITY": "false",
            "API_INTERNAL_URL": "http://127.0.0.1:1",
            "APP_ENV": "staging",
            "APP_RELEASE": RELEASE,
            "HOSTNAME": "127.0.0.1",
            "NODE_ENV": "production",
            "PORT": str(port),
        }
    )
    process = subprocess.Popen(
        ["node", "server.js"],
        cwd=STANDALONE,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                raise RuntimeError("Web process exited before becoming ready")
            try:
                ready_status, ready_body, ready_headers = request(
                    f"{base_url}/health/ready"
                )
                if ready_status == 200:
                    break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Web readiness timed out")
            time.sleep(0.2)

        payload = json.loads(ready_body)
        if payload != {"status": "ready", "release": RELEASE}:
            raise RuntimeError(f"unexpected readiness payload: {payload}")
        if "no-store" not in ready_headers.get("cache-control", ""):
            raise RuntimeError("readiness response is cacheable")

        ops_status, _, ops_headers = request(f"{base_url}/ops")
        if ops_status != 401:
            raise RuntimeError(f"anonymous /ops returned HTTP {ops_status}")
        if "no-store" not in ops_headers.get("cache-control", ""):
            raise RuntimeError("anonymous /ops denial is cacheable")

        root_status, root_body, root_headers = request(f"{base_url}/")
        if root_status != 200:
            raise RuntimeError(f"root page returned HTTP {root_status}")
        policy = root_headers.get("content-security-policy", "")
        policy_nonce = POLICY_NONCE.search(policy)
        if policy_nonce is None:
            raise RuntimeError("root response CSP has no script nonce")
        script_count = len(SCRIPT_TAG.findall(root_body))
        script_nonces = {
            nonce.decode("ascii") for nonce in SCRIPT_NONCE.findall(root_body)
        }
        if script_count < 1 or script_nonces != {policy_nonce.group(1)}:
            raise RuntimeError("root scripts do not share the response CSP nonce")
        _, _, second_headers = request(f"{base_url}/")
        second_nonce = POLICY_NONCE.search(
            second_headers.get("content-security-policy", "")
        )
        if second_nonce is None or second_nonce.group(1) == policy_nonce.group(1):
            raise RuntimeError("CSP nonce is not unique per request")
    except Exception as error:
        process.terminate()
        output = process.communicate(timeout=5)[0]
        raise SystemExit(f"WP08_WEB_RUNTIME_ERROR: {error}\n{output}") from error
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    print(
        "WP08_WEB_RUNTIME=PASS readiness=200 anonymous_ops=401"
        " root=200 csp_nonce=per-request"
    )


if __name__ == "__main__":
    main()
