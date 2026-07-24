#!/usr/bin/env python3
"""Exercise the production Web readiness and anonymous /ops contracts."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT / "apps" / "web" / ".next" / "standalone"
RELEASE = "wp08-web-runtime-check"


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

    print("WP08_WEB_RUNTIME=PASS readiness=200 anonymous_ops=401")


if __name__ == "__main__":
    main()
