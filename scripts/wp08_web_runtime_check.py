#!/usr/bin/env python3
"""Exercise the production Web readiness and anonymous /ops contracts."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT / "apps" / "web" / ".next" / "standalone"
RELEASE = "wp08-web-runtime-check"
SCRIPT_NONCE = re.compile(rb"<script\b[^>]*\bnonce=[\"']([^\"']+)", re.IGNORECASE)
SCRIPT_TAG = re.compile(rb"<script\b", re.IGNORECASE)
POLICY_NONCE = re.compile(r"(?:^|;\s*)script-src[^;]*'nonce-([^']+)'")


class IdentityApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/api/v1/auth/feishu/callback":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if payload != {"code": "runtime-code", "state": "s" * 32}:
            self.send_error(400)
            return
        body = json.dumps({"data": {"safe_entry": "/ops"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Set-Cookie",
            "journey_next_session=runtime-only; Path=/; Secure; HttpOnly; SameSite=Lax",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/api/v1/reviews":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "error": {
                    "code": "UNAUTHENTICATED",
                    "message": "vNext session is no longer valid.",
                },
                "request_id": "runtime-redacted-request",
            }
        ).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


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


def request_without_redirect(
    url: str, headers: dict[str, str]
) -> tuple[int, bytes, dict[str, str]]:
    opener = urllib.request.build_opener(NoRedirect)
    request_value = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request_value, timeout=2) as response:
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
    identity_api = ThreadingHTTPServer(("127.0.0.1", 0), IdentityApiHandler)
    identity_api_thread = threading.Thread(target=identity_api.serve_forever, daemon=True)
    identity_api_thread.start()
    identity_api_port = int(identity_api.server_address[1])
    environment = os.environ.copy()
    environment.update(
        {
            "ALLOW_FIXTURE_IDENTITY": "false",
            "API_INTERNAL_URL": f"http://127.0.0.1:{identity_api_port}",
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

        review_status, _, review_headers = request(f"{base_url}/review")
        if review_status != 401:
            raise RuntimeError(f"anonymous /review returned HTTP {review_status}")
        if "no-store" not in review_headers.get("cache-control", ""):
            raise RuntimeError("anonymous /review denial is cacheable")

        expired_status, _, expired_headers = request_without_redirect(
            f"{base_url}/review",
            {"Cookie": "journey_next_session=revoked-runtime-only"},
        )
        if expired_status not in {303, 307} or expired_headers.get("location") != (
            "/?auth_error=SESSION_EXPIRED&return_to=%2Freview"
        ):
            raise RuntimeError(
                "expired Reviewer session did not return to the explicit re-login path: "
                f"status={expired_status} location={expired_headers.get('location')!r}"
            )

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

        proxy_headers = {
            "Host": "staging-vnext.muchenai.com",
            "X-Forwarded-Host": "staging-vnext.muchenai.com",
            "X-Forwarded-Proto": "https",
        }
        callback_status, _, callback_headers = request_without_redirect(
            f"{base_url}/auth/feishu/callback?code=runtime-code&state={'s' * 32}",
            proxy_headers,
        )
        if callback_status != 303:
            raise RuntimeError(f"OAuth callback returned HTTP {callback_status}")
        if callback_headers.get("location") != "/ops":
            raise RuntimeError(
                "OAuth callback did not return a root-relative /ops redirect: "
                f"{callback_headers.get('location')!r}"
            )
        if "journey_next_session=runtime-only" not in callback_headers.get("set-cookie", ""):
            raise RuntimeError("OAuth callback did not preserve the upstream session cookie")

        invalid_status, _, invalid_headers = request_without_redirect(
            f"{base_url}/auth/feishu/callback?code=invalid",
            proxy_headers,
        )
        if invalid_status != 303 or invalid_headers.get("location") != (
            "/?auth_error=OAUTH_CALLBACK_INVALID"
        ):
            raise RuntimeError("invalid OAuth callback did not fail to a same-origin path")
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
        identity_api.shutdown()
        identity_api.server_close()
        identity_api_thread.join(timeout=5)

    print(
        "WP08_WEB_RUNTIME=PASS readiness=200 anonymous_ops=401 anonymous_review=401"
        " expired_reviewer=explicit-relogin root=200 csp_nonce=per-request"
        " oauth_redirect=root-relative"
    )


if __name__ == "__main__":
    main()
