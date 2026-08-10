#!/usr/bin/env python3
"""Observable, PII-free production surface checks for one bounded attempt."""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


ORIGIN = "https://journey.muchenai.com"
RELEASES = {
    "baseline": "8e56e759152efcbf17f4373f2132e02a8762af81",
    "cutover": "ff53052847a268d025bceb93c3eab37986d50219",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return None


def request(path: str) -> tuple[int, dict[str, str], bytes]:
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), NoRedirect()
    )
    req = urllib.request.Request(
        ORIGIN + path, headers={"User-Agent": "wp15-wartime-acceptance/1"}
    )
    try:
        with opener.open(req, timeout=5) as response:
            return response.status, dict(response.headers.items()), response.read(1_000_001)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read(1_000_001)


def emit(attempt: int, check: str, result: bool, **fields: object) -> bool:
    safe = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"WP15_SURFACE_CHECK attempt={attempt} check={check} "
        f"result={'PASS' if result else 'FAIL'} {safe}".rstrip()
    )
    return result


def check(attempt: int, profile: str) -> bool:
    candidate = RELEASES[profile]
    results: list[bool] = []
    root_status, _, _ = request("/")
    results.append(emit(attempt, "root", root_status == 200, status=root_status, expected=200))

    health_status, _, health_body = request("/health/ready")
    try:
        health = json.loads(health_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        health = {}
    ready = (
        health_status == 200
        and health.get("status") == "ready"
        and health.get("release") == candidate
    )
    results.append(
        emit(
            attempt,
            "readiness",
            ready,
            status=health_status,
            ready=health.get("status", "missing"),
            release=health.get("release", "missing"),
            expected_release=candidate,
        )
    )

    for route, name in (("/ops", "ops_denied"), ("/review", "review_denied")):
        status, _, _ = request(route)
        results.append(emit(attempt, name, status == 401, status=status, expected=401))

    if profile == "cutover":
        content_status, content_headers, _ = request("/content")
        location = content_headers.get("Location", content_headers.get("location", ""))
        cache_control = content_headers.get(
            "Cache-Control", content_headers.get("cache-control", "")
        )
        results.append(
            emit(
                attempt,
                "content_redirect",
                content_status == 303 and location == "/content/login",
                status=content_status,
                location=location or "missing",
            )
        )
        results.append(
            emit(
                attempt,
                "content_cache",
                "no-store" in cache_control.lower(),
                expected="no-store",
                actual="no-store" if "no-store" in cache_control.lower() else "missing",
            )
        )

        login_status, _, login_body = request("/content/login")
        login_cta = "使用飞书进入".encode() in login_body
        results.append(
            emit(attempt, "content_login", login_status == 200, status=login_status, expected=200)
        )
        results.append(
            emit(
                attempt,
                "content_login_cta",
                login_cta,
                expected="present",
                actual="present" if login_cta else "missing",
            )
        )

    oauth_status, oauth_headers, _ = request("/auth/feishu?return_to=%2Fops")
    oauth_location = oauth_headers.get("Location", oauth_headers.get("location", ""))
    provider = urllib.parse.urlsplit(oauth_location)
    query = urllib.parse.parse_qs(provider.query)
    callback = urllib.parse.urlsplit(query.get("redirect_uri", [""])[0])
    oauth_ok = (
        oauth_status == 303
        and provider.scheme == "https"
        and provider.hostname == "accounts.feishu.cn"
        and provider.path == "/open-apis/authen/v1/authorize"
        and callback.scheme == "https"
        and callback.hostname == "journey.muchenai.com"
        and callback.path == "/auth/feishu/callback"
        and not callback.query
        and not callback.fragment
    )
    results.append(
        emit(
            attempt,
            "feishu_oauth",
            oauth_ok,
            status=oauth_status,
            provider=provider.hostname or "missing",
            callback_host=callback.hostname or "missing",
            callback_path=callback.path or "missing",
        )
    )
    return all(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--profile", choices=sorted(RELEASES), required=True)
    args = parser.parse_args()
    if not 1 <= args.attempt <= 12:
        raise SystemExit("attempt must be between 1 and 12")
    return 0 if check(args.attempt, args.profile) else 1


if __name__ == "__main__":
    raise SystemExit(main())
