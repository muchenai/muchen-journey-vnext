#!/usr/bin/env python3
"""PII-free, read-only WP-11 observability audit for the staging host."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


EXPECTED_CONTAINERS = {
    "api": "journey-next-staging-api-1",
    "worker": "journey-next-staging-worker-1",
}
FORBIDDEN_LOG_FIELDS = {
    "authorization",
    "cookie",
    "request_body",
    "response_body",
    "receive_id",
    "recipient_fingerprint",
    "provider_message_id",
    "submission_body",
    "token",
}
RELEASE_RE = re.compile(r"^[0-9a-f]{40}$")
LOGCOLLECTOR_ROOT = Path("/usr/local/logcollector")
DEPLOYED_CANDIDATE = Path("/srv/journey-next-staging/DEPLOYED_CANDIDATE")


class AuditError(RuntimeError):
    """Raised when the physical staging contract is not satisfied."""


@dataclass(frozen=True)
class StructuredLogSummary:
    parsed: int
    expected_event_count: int
    release_match_count: int
    forbidden_fields: frozenset[str]


def _run(*command: str) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout


def _container_logs(name: str, lookback_seconds: int) -> str:
    completed = subprocess.run(
        ("docker", "logs", "--since", f"{lookback_seconds}s", name),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout + completed.stderr


def _nested_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _nested_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_keys(nested)


def summarize_json_lines(
    raw: str, *, expected_event: str, candidate: str
) -> StructuredLogSummary:
    parsed = 0
    expected_event_count = 0
    release_match_count = 0
    forbidden: set[str] = set()
    for line in raw.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        parsed += 1
        forbidden.update(FORBIDDEN_LOG_FIELDS.intersection(_nested_keys(payload)))
        if payload.get("event") == expected_event:
            expected_event_count += 1
            if payload.get("release") == candidate:
                release_match_count += 1
    return StructuredLogSummary(
        parsed=parsed,
        expected_event_count=expected_event_count,
        release_match_count=release_match_count,
        forbidden_fields=frozenset(forbidden),
    )


def validate_notification_summary(payload: dict[str, Any], candidate: str) -> None:
    expected = {
        "active_recipients": 0,
        "unsafe_without_recipient": 0,
        "external_receipts": 0,
        "notification_attempts": 0,
        "worker_release": candidate,
        "worker_fresh": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise AuditError(f"database invariant failed: {key}")


def _inspect_container(name: str) -> dict[str, Any]:
    raw = _run("docker", "inspect", name)
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) != 1:
        raise AuditError("container inspect result is ambiguous")
    value = values[0]
    if not isinstance(value, dict):
        raise AuditError("container inspect result is invalid")
    return value


def _notification_summary(
    container: str, candidate: str, deployed_since: datetime
) -> dict[str, Any]:
    code = r'''
import json
import sys
from sqlalchemy import text
from journey_api.db import SessionLocal

session = SessionLocal()
try:
    row = session.execute(text("""
        SELECT
          (SELECT count(*) FROM notification_endpoints WHERE status = 'ACTIVE') AS active_recipients,
          (SELECT count(*)
             FROM notification_deliveries d
             JOIN outbox_events e ON e.id = d.event_id
            WHERE d.channel = 'FEISHU'
              AND NOT EXISTS (
                    SELECT 1 FROM notification_endpoints n
                     WHERE n.organization_id = d.organization_id
                       AND n.user_id = d.recipient_user_id
                       AND n.channel = 'FEISHU'
                       AND n.status = 'ACTIVE'
              )
              AND NOT (
                    d.status = 'PENDING'
                AND d.attempt_count = d.attempt_offset
                AND e.status = 'PENDING'
              )) AS unsafe_without_recipient,
          (SELECT count(*) FROM external_notification_receipts
            WHERE created_at >= :deployed_since) AS external_receipts,
          (SELECT count(*) FROM notification_attempts
            WHERE attempted_at >= :deployed_since) AS notification_attempts,
          (SELECT release FROM worker_heartbeats WHERE worker_name = 'notification-worker') AS worker_release,
          (SELECT last_seen_at >= now() - interval '30 seconds'
             FROM worker_heartbeats WHERE worker_name = 'notification-worker') AS worker_fresh
    """), {"deployed_since": sys.argv[1]}).mappings().one()
    print(json.dumps(dict(row), separators=(",", ":"), sort_keys=True))
finally:
    session.close()
'''
    raw = _run(
        "docker",
        "exec",
        container,
        "python",
        "-c",
        code,
        deployed_since.isoformat(),
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AuditError("database summary is invalid")
    validate_notification_summary(payload, candidate)
    return payload


def _safe_logcollector_counts() -> dict[str, int]:
    patterns = {
        "permission_denied": re.compile(r"permission denied", re.IGNORECASE),
        "docker_connect": re.compile(
            r"docker.{0,80}(connect|socket|permission|error|fail)", re.IGNORECASE
        ),
        "container_runtime": re.compile(
            r"container.{0,80}(unsupported|error|fail|not found)", re.IGNORECASE
        ),
        "config_error": re.compile(
            r"(config|rule).{0,80}(invalid|error|fail)", re.IGNORECASE
        ),
    }
    counts = {name: 0 for name in patterns}
    if not LOGCOLLECTOR_ROOT.exists():
        return counts
    for path in (LOGCOLLECTOR_ROOT / "logs").glob("**/*"):
        if not path.is_file() or path.stat().st_size > 8_000_000:
            continue
        try:
            content = path.read_text(errors="ignore")[-2_000_000:]
        except OSError:
            continue
        for name, pattern in patterns.items():
            counts[name] += len(pattern.findall(content))
    return counts


def _logcollector_is_active() -> bool:
    completed = subprocess.run(
        ("systemctl", "is-active", "logcollector"),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "active"


def audit(candidate: str, lookback_seconds: int) -> None:
    if not RELEASE_RE.fullmatch(candidate):
        raise AuditError("candidate must be a full commit SHA")
    deployed = DEPLOYED_CANDIDATE.read_text().strip()
    if deployed != candidate:
        raise AuditError("deployed candidate differs from authorized candidate")

    summaries: dict[str, StructuredLogSummary] = {}
    expected_events = {"api": "http.request", "worker": "runtime.snapshot"}
    for service, container_name in EXPECTED_CONTAINERS.items():
        inspected = _inspect_container(container_name)
        if inspected.get("Name", "").lstrip("/") != container_name:
            raise AuditError(f"{service} container identity differs")
        if inspected.get("State", {}).get("Running") is not True:
            raise AuditError(f"{service} container is not running")
        log_driver = inspected.get("HostConfig", {}).get("LogConfig", {}).get("Type")
        if log_driver != "json-file":
            raise AuditError(f"{service} container does not use json-file logging")
        raw_logs = _container_logs(container_name, lookback_seconds)
        summary = summarize_json_lines(
            raw_logs, expected_event=expected_events[service], candidate=candidate
        )
        if summary.forbidden_fields:
            raise AuditError(f"{service} logs contain forbidden fields")
        if summary.expected_event_count < 1 or summary.release_match_count < 1:
            raise AuditError(f"{service} expected structured event is missing")
        summaries[service] = summary

    deployed_since = datetime.fromtimestamp(DEPLOYED_CANDIDATE.stat().st_mtime, UTC)
    database = _notification_summary(
        EXPECTED_CONTAINERS["api"], candidate, deployed_since
    )
    logcollector_active = _logcollector_is_active()
    socket_accessible = Path("/var/run/docker.sock").exists()
    errors = _safe_logcollector_counts()

    print("WP11_HOST_CANDIDATE_MATCH=PASS")
    print("WP11_DOCKER_LOG_DRIVER=PASS services=api,worker")
    print(
        "WP11_LOCAL_STRUCTURED_LOGS=PASS "
        f"api_events={summaries['api'].expected_event_count} "
        f"worker_snapshots={summaries['worker'].expected_event_count}"
    )
    print(
        "WP11_NO_RECIPIENT_SAFETY=PASS "
        f"active_recipients={database['active_recipients']} "
        f"external_receipts={database['external_receipts']} "
        f"notification_attempts={database['notification_attempts']}"
    )
    print(
        "WP11_LOGCOLLECTOR_HOST="
        f"{'PASS' if logcollector_active and socket_accessible else 'FAIL'} "
        f"active={str(logcollector_active).lower()} "
        f"docker_socket={str(socket_accessible).lower()}"
    )
    print(
        "WP11_LOGCOLLECTOR_SAFE_ERROR_COUNTS="
        + ",".join(f"{key}:{value}" for key, value in sorted(errors.items()))
    )
    if not logcollector_active or not socket_accessible:
        raise AuditError("LogCollector host prerequisites are not satisfied")
    print("WP11_HOST_OBSERVABILITY_AUDIT=PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--lookback-seconds", type=int, default=600)
    args = parser.parse_args()
    if not 60 <= args.lookback_seconds <= 3600:
        parser.error("--lookback-seconds must be between 60 and 3600")
    return args


def main() -> int:
    args = parse_args()
    try:
        audit(args.candidate, args.lookback_seconds)
    except (AuditError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"WP11_HOST_OBSERVABILITY_AUDIT=FAIL reason={error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
