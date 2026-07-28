#!/usr/bin/env python3
"""Bounded local-only WP-12 HTTP performance evidence.

The command refuses non-loopback targets, uses fixture identities, performs no
business commands, and never claims staging availability. It is a repeatable
engineering baseline for the later real staging benchmark.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts" / "wp12"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ReadinessError(RuntimeError):
    """The requested local benchmark is unsafe or failed its contract."""


@dataclass(frozen=True)
class Probe:
    name: str
    path: str
    headers: dict[str, str]


PROBES = (
    Probe("readiness", "/health/ready", {}),
    Probe(
        "learner_current_action",
        "/api/v1/me/current-action",
        {"X-Fixture-Role": "LEARNER"},
    ),
    Probe(
        "reviewer_queue",
        "/api/v1/reviews",
        {"X-Fixture-Role": "REVIEWER"},
    ),
    Probe(
        "operator_runtime",
        "/api/v1/ops/runtime-status",
        {"X-Fixture-Role": "OPERATOR"},
    ),
)


def validate_loopback_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOCAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ReadinessError("benchmark target must be a plain loopback HTTP origin")
    try:
        port = parsed.port
    except ValueError as error:
        raise ReadinessError("benchmark target has an invalid port") from error
    if port is None or not 1 <= port <= 65535:
        raise ReadinessError("benchmark target must include a valid TCP port")
    return value.rstrip("/")


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ReadinessError("cannot calculate a percentile without samples")
    if not 0 < percentile <= 1:
        raise ReadinessError("percentile must be in the interval (0, 1]")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def request_once(
    base_url: str,
    probe: Probe,
    *,
    timeout_seconds: float,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> tuple[int, float]:
    request = urllib.request.Request(
        f"{base_url}{probe.path}",
        headers={**probe.headers, "Accept": "application/json"},
        method="GET",
    )
    started = time.perf_counter()
    try:
        with opener(request, timeout=timeout_seconds) as response:  # type: ignore[attr-defined]
            response.read(1)  # type: ignore[attr-defined]
            status = int(response.status)  # type: ignore[attr-defined]
    except urllib.error.HTTPError as error:
        status = error.code
    except (OSError, urllib.error.URLError) as error:
        raise ReadinessError(f"{probe.name} request failed: {error}") from error
    return status, time.perf_counter() - started


def summarize(
    observations: dict[str, list[tuple[int, float]]],
    *,
    p95_budget_seconds: float,
) -> tuple[str, dict[str, dict[str, float | int | str]]]:
    report: dict[str, dict[str, float | int | str]] = {}
    passed = True
    for name, samples in observations.items():
        latencies = [elapsed for _, elapsed in samples]
        successful = sum(status == 200 for status, _ in samples)
        p95 = nearest_rank(latencies, 0.95)
        endpoint_status = (
            "PASS"
            if successful == len(samples) and p95 <= p95_budget_seconds
            else "FAIL"
        )
        passed = passed and endpoint_status == "PASS"
        report[name] = {
            "samples": len(samples),
            "successful": successful,
            "p50_seconds": round(nearest_rank(latencies, 0.50), 6),
            "p95_seconds": round(p95, 6),
            "max_seconds": round(max(latencies), 6),
            "budget_seconds": p95_budget_seconds,
            "status": endpoint_status,
        }
    return ("PASS" if passed else "FAIL"), report


def write_private_json(document: dict[str, object]) -> Path:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = ARTIFACT_ROOT / (
        f"local-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{secrets.token_hex(4)}.json"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ReadinessError("benchmark artifact is not owner-only")
    return path


def benchmark(
    base_url: str,
    *,
    samples: int,
    warmup: int,
    p95_budget_seconds: float,
    timeout_seconds: float,
) -> Path:
    if not 5 <= samples <= 500 or not 0 <= warmup <= 50:
        raise ReadinessError("samples must be 5..500 and warmup must be 0..50")
    if not 0 < p95_budget_seconds <= 10 or not 0 < timeout_seconds <= 15:
        raise ReadinessError("benchmark budgets are outside the bounded local contract")
    base_url = validate_loopback_base_url(base_url)
    for probe in PROBES:
        for _ in range(warmup):
            status, _ = request_once(
                base_url, probe, timeout_seconds=timeout_seconds
            )
            if status != 200:
                raise ReadinessError(f"{probe.name} warmup returned HTTP {status}")
    observations = {
        probe.name: [
            request_once(base_url, probe, timeout_seconds=timeout_seconds)
            for _ in range(samples)
        ]
        for probe in PROBES
    }
    status, endpoints = summarize(
        observations, p95_budget_seconds=p95_budget_seconds
    )
    path = write_private_json(
        {
            "schema_version": 1,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "scope": "LOCAL_FIXTURE_READ_ONLY",
            "target": base_url,
            "status": status,
            "endpoints": endpoints,
            "mutations_executed": False,
            "staging_benchmark": "NOT_RUN",
            "pilot_availability_99_5_percent": "NOT_RUN",
        }
    )
    if status != "PASS":
        raise ReadinessError(f"local benchmark failed; evidence: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=f"http://127.0.0.1:{os.environ.get('MJ_API_PORT', '38000')}",
    )
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--p95-budget-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        print(
            benchmark(
                args.base_url,
                samples=args.samples,
                warmup=args.warmup,
                p95_budget_seconds=args.p95_budget_seconds,
                timeout_seconds=args.timeout_seconds,
            )
        )
        return 0
    except ReadinessError as error:
        print(f"WP12_LOCAL_READINESS_ERROR: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
