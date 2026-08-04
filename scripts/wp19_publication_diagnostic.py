#!/usr/bin/env python3
"""Read-only, PII-free diagnosis of the failed formal Journey publication.

The command reads a fixed ten-minute Docker log window from the current staging
Web/API containers.  It never prints raw log lines: output is limited to
request IDs, HTTP status codes, exception classes, application stack frames,
and validated database object/constraint identifiers.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


AUTHORIZED_CANDIDATE = "ef0a512cf357001cfd8cb6803f65cc17ae697325"
WINDOW_START = "2026-08-04T01:20:00Z"
WINDOW_END = "2026-08-04T01:30:30Z"
DEPLOYED_CANDIDATE = Path("/srv/journey-next-staging/DEPLOYED_CANDIDATE")
COMPOSE_PROJECT = "journey-next-staging"
CONTAINERS = {
    "api": "journey-next-staging-api-1",
    "web": "journey-next-staging-web-1",
}
PUBLICATION_PATH = "/api/v1/ops/formal-journeys/publish"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SAFE_REQUEST_ID = re.compile(r"^req_[0-9a-f]{32}$")
TIMESTAMPED_LINE = re.compile(
    r"^(?P<timestamp>2026-08-04T01:(?:2[0-9]|30):[0-9]{2}(?:\.[0-9]+)?Z)\s(?P<body>.*)$"
)
ACCESS_STATUS = re.compile(
    r'POST\s+/api/v1/ops/formal-journeys/publish\s+HTTP/[^"\s]+"\s+(?P<status>[1-5][0-9]{2})'
)
REQUEST_ID = re.compile(r'"request_id"\s*:\s*"(?P<request_id>req_[0-9a-f]{32})"')
EXCEPTION_CLASS = re.compile(
    r"(?:(?:sqlalchemy\.exc|psycopg\.errors|builtins)\.)?"
    r"(?P<name>[A-Z][A-Za-z0-9_]{2,80}(?:"
    r"Error|Violation|Denied|Privilege|UndefinedTable|UndefinedColumn|"
    r"InvalidTextRepresentation|StringDataRightTruncation))\b"
)
APP_FRAME = re.compile(
    r'File "/app/apps/api/journey_api/(?P<file>[A-Za-z0-9_./-]+\.py)", line (?P<line>[1-9][0-9]{0,5})'
)
CONSTRAINT = re.compile(
    r"constraint\s+[\"'](?P<name>[A-Za-z_][A-Za-z0-9_]{0,127})[\"']",
    re.IGNORECASE,
)
DB_OBJECT_PATTERNS = (
    re.compile(
        r"permission denied for (?:table|schema|sequence)\s+[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_]{0,127})",
        re.IGNORECASE,
    ),
    re.compile(
        r"relation\s+[\"'](?P<name>[A-Za-z_][A-Za-z0-9_]{0,127})[\"']\s+does not exist",
        re.IGNORECASE,
    ),
    re.compile(
        r"column\s+[\"'](?P<name>[A-Za-z_][A-Za-z0-9_]{0,127})[\"']\s+.*does not exist",
        re.IGNORECASE,
    ),
)
CLASSIFIERS = {
    "permission denied": "permission_denied",
    "unique violation": "unique_violation",
    "uniqueviolation": "unique_violation",
    "foreign key violation": "foreign_key_violation",
    "foreignkeyviolation": "foreign_key_violation",
    "not null violation": "not_null_violation",
    "notnullviolation": "not_null_violation",
    "check violation": "check_violation",
    "checkviolation": "check_violation",
    "undefined table": "undefined_table",
    "undefinedtable": "undefined_table",
    "undefined column": "undefined_column",
    "undefinedcolumn": "undefined_column",
    "insufficient privilege": "insufficient_privilege",
    "insufficientprivilege": "insufficient_privilege",
    "invalid input value for enum": "invalid_text_representation",
    "invalidtextrepresentation": "invalid_text_representation",
    "string data right truncation": "string_data_right_truncation",
    "stringdatarighttruncation": "string_data_right_truncation",
    "internal server error": "internal_server_error",
    "unexpected response was received from the server": "server_action_unexpected_response",
}
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LOG_LINES = 20_000


class DiagnosticError(RuntimeError):
    """Raised when the bounded diagnostic cannot prove a safe result."""


def _run(*command: str) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = completed.stdout + completed.stderr
    if len(output.encode("utf-8")) > MAX_LOG_BYTES:
        raise DiagnosticError("bounded log output exceeds the safety limit")
    return output


def _verify_container(service: str, name: str) -> None:
    output = _run(
        "docker",
        "inspect",
        "--format",
        '{{.State.Running}}|{{index .Config.Labels "com.docker.compose.project"}}|'
        '{{index .Config.Labels "com.docker.compose.service"}}',
        name,
    ).strip()
    if output != f"true|{COMPOSE_PROJECT}|{service}":
        raise DiagnosticError(f"{service} container identity or state differs")


def _log_lines(service: str, name: str) -> list[str]:
    _verify_container(service, name)
    raw = _run(
        "docker",
        "logs",
        "--since",
        WINDOW_START,
        "--until",
        WINDOW_END,
        "--timestamps",
        name,
    )
    lines = raw.splitlines()
    if len(lines) > MAX_LOG_LINES:
        raise DiagnosticError("bounded log line count exceeds the safety limit")
    return lines


def classify_logs(logs: dict[str, list[str]]) -> dict[str, object]:
    statuses: list[int] = []
    request_ids: set[str] = set()
    exception_classes: set[str] = set()
    classifiers: set[str] = set()
    constraints: set[str] = set()
    database_objects: set[str] = set()
    app_frames: set[str] = set()
    timestamps: set[str] = set()
    line_counts: dict[str, int] = {}

    for service, lines in logs.items():
        line_counts[service] = len(lines)
        for line in lines:
            timestamp_match = TIMESTAMPED_LINE.fullmatch(line)
            if timestamp_match is None:
                continue
            timestamp = timestamp_match.group("timestamp")
            body = timestamp_match.group("body")
            lower = body.lower()
            relevant = PUBLICATION_PATH in body
            access = ACCESS_STATUS.search(body)
            if access is not None:
                statuses.append(int(access.group("status")))
                timestamps.add(timestamp)
                relevant = True
            if relevant:
                for request_match in REQUEST_ID.finditer(body):
                    request_id = request_match.group("request_id")
                    if SAFE_REQUEST_ID.fullmatch(request_id):
                        request_ids.add(request_id)

            for match in EXCEPTION_CLASS.finditer(body):
                exception_classes.add(match.group("name"))
                timestamps.add(timestamp)
            for phrase, code in CLASSIFIERS.items():
                if phrase in lower:
                    classifiers.add(code)
                    timestamps.add(timestamp)
            for match in CONSTRAINT.finditer(body):
                name = match.group("name")
                if SAFE_IDENTIFIER.fullmatch(name):
                    constraints.add(name)
                    timestamps.add(timestamp)
            for pattern in DB_OBJECT_PATTERNS:
                for match in pattern.finditer(body):
                    name = match.group("name")
                    if SAFE_IDENTIFIER.fullmatch(name):
                        database_objects.add(name)
                        timestamps.add(timestamp)
            for match in APP_FRAME.finditer(body):
                app_frames.add(f"{match.group('file')}:{match.group('line')}")
                timestamps.add(timestamp)

    result: dict[str, object] = {
        "app_frames": sorted(app_frames),
        "classifiers": sorted(classifiers),
        "constraints": sorted(constraints),
        "database_objects": sorted(database_objects),
        "exception_classes": sorted(exception_classes),
        "http_statuses": sorted(statuses),
        "line_counts": line_counts,
        "publication_attempt_count": len(statuses),
        "request_ids": sorted(request_ids),
        "technical_event_timestamps": sorted(timestamps),
        "window_end": WINDOW_END,
        "window_start": WINDOW_START,
    }
    if not statuses:
        raise DiagnosticError("no formal Journey publication request exists in the fixed window")
    if not any(status >= 500 for status in statuses):
        raise DiagnosticError("fixed window contains no failed formal Journey publication")
    root_classifiers = classifiers - {
        "internal_server_error",
        "server_action_unexpected_response",
    }
    if (
        not exception_classes
        and not root_classifiers
        and not constraints
        and not database_objects
        and not app_frames
    ):
        raise DiagnosticError("failed publication has no safely classifiable runtime error")
    return result


def collect(candidate: str) -> dict[str, object]:
    if candidate != AUTHORIZED_CANDIDATE:
        raise DiagnosticError("candidate differs from the authorized staging release")
    if DEPLOYED_CANDIDATE.read_text().strip() != candidate:
        raise DiagnosticError("deployed candidate marker differs")
    logs = {
        service: _log_lines(service, name)
        for service, name in CONTAINERS.items()
    }
    return {
        "candidate": candidate,
        "read_only": True,
        **classify_logs(logs),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    result = collect(args.candidate)
    print(
        "WP19_PUBLICATION_DIAGNOSTIC="
        + json.dumps(result, separators=(",", ":"), sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
