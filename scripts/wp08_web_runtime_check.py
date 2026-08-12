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
        if self.path == "/api/v1/auth/feishu/start":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if payload not in ({"return_to": "/content"}, {"return_to": "/review"}):
                self.send_error(400)
                return
            body = json.dumps(
                {
                    "data": {
                        "authorization_url": (
                            "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
                            f"?state={'s' * 32}"
                        )
                    }
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Set-Cookie",
                "journey_next_oauth=runtime-browser; Path=/; HttpOnly; SameSite=Lax",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path != "/api/v1/auth/feishu/callback":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if payload != {"code": "runtime-code", "state": "s" * 32}:
            self.send_error(400)
            return
        body = json.dumps({"data": {"safe_entry": "/content"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Set-Cookie",
            "journey_next_session=runtime-only; Path=/; Secure; HttpOnly; SameSite=Lax",
        )
        self.send_header(
            "Set-Cookie",
            "journey_next_csrf=runtime-csrf; Path=/; Secure; SameSite=Lax",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/api/v1/reviews":
            self.send_error(404)
            return
        wrong_role = "journey_next_session=wrong-role-runtime-only" in self.headers.get(
            "Cookie", ""
        )
        body = json.dumps(
            {
                "error": {
                    "code": "FORBIDDEN" if wrong_role else "UNAUTHENTICATED",
                    "message": (
                        "Current role cannot enter Reviewer."
                        if wrong_role
                        else "vNext session is no longer valid."
                    ),
                },
                "request_id": "runtime-redacted-request",
            }
        ).encode()
        self.send_response(403 if wrong_role else 401)
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
                normalized_headers(response.headers),
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.read(),
            normalized_headers(error.headers),
        )


def normalized_headers(headers) -> dict[str, str]:  # type: ignore[no-untyped-def]
    result = {key.lower(): value for key, value in headers.items()}
    set_cookies = headers.get_all("Set-Cookie") or []
    if set_cookies:
        result["set-cookie"] = "\n".join(set_cookies)
    return result


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
                normalized_headers(response.headers),
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            error.read(),
            normalized_headers(error.headers),
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
    proxy_headers = {
        "Host": "staging-vnext.muchenai.com",
        "X-Forwarded-Host": "staging-vnext.muchenai.com",
        "X-Forwarded-Proto": "https",
    }
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

        review_status, _, review_headers = request_without_redirect(
            f"{base_url}/review", {}
        )
        if review_status != 303 or review_headers.get("location") != "/review/login":
            raise RuntimeError(
                "anonymous /review did not redirect to the dedicated login page: "
                f"status={review_status} location={review_headers.get('location')!r}"
            )
        if "no-store" not in review_headers.get("cache-control", ""):
            raise RuntimeError("anonymous /review redirect is cacheable")

        review_login_status, review_login_body, _ = request(
            f"{base_url}/review/login"
        )
        if review_login_status != 200:
            raise RuntimeError(
                f"Reviewer login page returned HTTP {review_login_status}"
            )
        if "使用飞书进入".encode() not in review_login_body:
            raise RuntimeError("Reviewer login page has no Feishu entry action")

        content_status, _, content_headers = request_without_redirect(
            f"{base_url}/content", {}
        )
        if content_status != 303 or content_headers.get("location") != "/content/login":
            raise RuntimeError(
                "anonymous /content did not redirect to the dedicated login page: "
                f"status={content_status} location={content_headers.get('location')!r}"
            )
        if "no-store" not in content_headers.get("cache-control", ""):
            raise RuntimeError("anonymous /content redirect is cacheable")

        content_login_status, content_login_body, _ = request(
            f"{base_url}/content/login"
        )
        if content_login_status != 200:
            raise RuntimeError(
                f"Content Editor login page returned HTTP {content_login_status}"
            )
        if "使用飞书进入".encode() not in content_login_body:
            raise RuntimeError("Content Editor login page has no Feishu entry action")

        oauth_start_status, _, oauth_start_headers = request_without_redirect(
            f"{base_url}/auth/feishu?return_to=%2Fcontent", proxy_headers,
        )
        if oauth_start_status != 303:
            raise RuntimeError(
                f"Content Editor OAuth start returned HTTP {oauth_start_status}"
            )
        authorization_url = oauth_start_headers.get("location", "")
        if not authorization_url.startswith(
            "https://accounts.feishu.cn/open-apis/authen/v1/authorize?"
        ):
            raise RuntimeError("Content Editor OAuth start left the approved Feishu host")
        if "journey_next_oauth=runtime-browser" not in oauth_start_headers.get(
            "set-cookie", ""
        ):
            raise RuntimeError("Content Editor OAuth start did not preserve browser context")

        reviewer_oauth_status, _, reviewer_oauth_headers = request_without_redirect(
            f"{base_url}/auth/feishu?return_to=%2Freview", proxy_headers,
        )
        if reviewer_oauth_status != 303:
            raise RuntimeError(
                f"Reviewer OAuth start returned HTTP {reviewer_oauth_status}"
            )
        if not reviewer_oauth_headers.get("location", "").startswith(
            "https://accounts.feishu.cn/open-apis/authen/v1/authorize?"
        ):
            raise RuntimeError("Reviewer OAuth start left the approved Feishu host")

        wrong_role_status, _, wrong_role_headers = request_without_redirect(
            f"{base_url}/review",
            {"Cookie": "journey_next_session=wrong-role-runtime-only"},
        )
        if wrong_role_status not in {303, 307} or wrong_role_headers.get("location") != (
            "/review/login?auth_error=FORBIDDEN"
        ):
            raise RuntimeError(
                "wrong-role Reviewer session did not reach the role login path: "
                f"status={wrong_role_status} location={wrong_role_headers.get('location')!r}"
            )

        expired_status, _, expired_headers = request_without_redirect(
            f"{base_url}/review",
            {"Cookie": "journey_next_session=revoked-runtime-only"},
        )
        if expired_status not in {303, 307} or expired_headers.get("location") != (
            "/review/login?auth_error=SESSION_EXPIRED"
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

        callback_status, _, callback_headers = request_without_redirect(
            f"{base_url}/auth/feishu/callback?code=runtime-code&state={'s' * 32}",
            proxy_headers,
        )
        if callback_status != 303:
            raise RuntimeError(f"OAuth callback returned HTTP {callback_status}")
        if callback_headers.get("location") != "/content":
            raise RuntimeError(
                "OAuth callback did not return a root-relative /content redirect: "
                f"{callback_headers.get('location')!r}"
            )
        if "journey_next_session=runtime-only" not in callback_headers.get("set-cookie", ""):
            raise RuntimeError("OAuth callback did not preserve the upstream session cookie")
        if "journey_next_csrf=runtime-csrf" not in callback_headers.get("set-cookie", ""):
            raise RuntimeError("OAuth callback did not preserve the upstream CSRF cookie")

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
        "WP08_WEB_RUNTIME=PASS readiness=200 anonymous_ops=401 anonymous_review=login-page"
        " anonymous_content=login-page expired_reviewer=explicit-relogin"
        " root=200 csp_nonce=per-request oauth_redirect=root-relative-content"
    )


if __name__ == "__main__":
    main()
