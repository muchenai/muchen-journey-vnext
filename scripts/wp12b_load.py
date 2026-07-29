#!/usr/bin/env python3
"""Fail-closed WP-12B multi-tenant HTTP load and isolation runner.

The runner consumes an owner-only synthetic session bundle prepared inside the
API container. It never provisions identities, changes cloud resources, sends
notifications, or prints session material. Staging execution is accepted only
for the canonical HTTPS host and an exact deployed 40-character candidate.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "wp12b_multitenant_load.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "wp12b-staging-load.yml"
ARTIFACT_ROOT = ROOT / "artifacts" / "wp12b"
PRIVATE_ROOT = ROOT / "evidence" / "private"
STAGING_ORIGIN = "https://staging-vnext.muchenai.com"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,39}$")


class LoadError(RuntimeError):
    """The load contract, execution, or evidence failed closed."""


@dataclass(frozen=True)
class SessionActor:
    organization_ref: str
    role: str
    session_token: str
    csrf_token: str
    assignment_id: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Cookie": (
                f"journey_next_session={self.session_token}; "
                f"journey_next_csrf={self.csrf_token}"
            ),
        }

    def command_headers(self, idempotency_key: str) -> dict[str, str]:
        return {
            **self.headers,
            "Content-Type": "application/json",
            "X-CSRF-Token": self.csrf_token,
            "Idempotency-Key": idempotency_key,
        }


@dataclass(frozen=True)
class OrganizationActors:
    ref: str
    learners: tuple[SessionActor, ...]
    reviewers: tuple[SessionActor, ...]
    operator: SessionActor


@dataclass(frozen=True)
class Observation:
    operation: str
    expected_status: int
    actual_status: int
    elapsed_seconds: float


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Treat redirects as responses so synthetic cookies never cross origins."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoadError(f"cannot read JSON contract {path}") from error
    if not isinstance(payload, dict):
        raise LoadError(f"JSON contract {path} must contain an object")
    return payload


def require_owner_only(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise LoadError(f"private bundle must be owner-only: {path}")


def exact_int(config: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LoadError(f"{key} must be an integer in {minimum}..{maximum}")
    return value


def exact_number(config: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LoadError(f"{key} must be numeric")
    numeric = float(value)
    if not minimum <= numeric <= maximum:
        raise LoadError(f"{key} must be in {minimum}..{maximum}")
    return numeric


def load_contract(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = read_json(path)
    expected_keys = {
        "schema_version",
        "scope",
        "organization_count",
        "learners_per_organization",
        "reviewers_per_organization",
        "operators_per_organization",
        "peak_concurrency",
        "steady_state_seconds",
        "steady_requests_per_second",
        "burst_seconds",
        "burst_requests_per_second",
        "p95_budget_seconds",
        "request_timeout_seconds",
        "max_http_5xx",
        "max_unexpected_responses",
        "max_cross_org_leaks",
        "max_duplicate_facts",
        "max_state_conflicts",
    }
    if set(config) != expected_keys:
        raise LoadError("WP-12B load contract fields differ from the approved schema")
    if config["schema_version"] != 1 or config["scope"] != "STAGING_SYNTHETIC_MULTI_TENANT":
        raise LoadError("WP-12B load contract identity is invalid")
    exact_int(config, "organization_count", 2, 100)
    exact_int(config, "learners_per_organization", 1, 500)
    exact_int(config, "reviewers_per_organization", 1, 20)
    if exact_int(config, "operators_per_organization", 1, 5) != 1:
        raise LoadError("WP-12B requires exactly one synthetic operator per organization")
    exact_int(config, "peak_concurrency", 1, 500)
    exact_int(config, "steady_state_seconds", 60, 3600)
    exact_int(config, "steady_requests_per_second", 1, 500)
    exact_int(config, "burst_seconds", 10, 600)
    exact_int(config, "burst_requests_per_second", 1, 1000)
    exact_number(config, "p95_budget_seconds", 0.05, 10.0)
    exact_number(config, "request_timeout_seconds", 1.0, 30.0)
    for key in (
        "max_http_5xx",
        "max_unexpected_responses",
        "max_cross_org_leaks",
        "max_duplicate_facts",
        "max_state_conflicts",
    ):
        if exact_int(config, key, 0, 1000) != 0:
            raise LoadError(f"{key} must remain zero for Alpha")
    if config["burst_requests_per_second"] <= config["steady_requests_per_second"]:
        raise LoadError("burst rate must exceed steady-state rate")
    return config


def validate_workflow_source(source: str) -> None:
    required = (
        "workflow_dispatch:",
        "environment: staging",
        "inputs.confirmation == format('RUN_WP12B_{0}', inputs.candidate)",
        "git merge-base --is-ancestor",
        "cat /srv/journey-next-staging/DEPLOYED_CANDIDATE",
        "python3 scripts/wp12b_load.py contract-check",
        "python3 scripts/wp12b_load.py run",
        "python3 scripts/wp12b_load.py verify",
        "if: always() && steps.prepare.outputs.run_id != ''",
        "python -m journey_api.wp12b_synthetic retire",
        "if: always() && steps.frozen.outputs.security_group_id != ''",
        "scripts.wp08_security_group close",
        "shred -u /tmp/wp12b-bundle-",
    )
    missing = [item for item in required if item not in source]
    if missing:
        raise LoadError(f"WP-12B workflow is missing required contracts: {missing}")
    forbidden = (
        "terraform apply",
        "terraform plan",
        "phase=deploy",
        "phase=provision",
        "NOTIFICATION_ENDPOINT",
        "FEISHU_APP_SECRET",
        "session_token",
    )
    found = [item for item in forbidden if item in source]
    if found:
        raise LoadError(f"WP-12B workflow contains forbidden operations: {found}")
    upload_step = source.split("- name: Upload PII-free evidence", 1)
    if len(upload_step) != 2 or "wp12b-bundle" in upload_step[1]:
        raise LoadError("WP-12B workflow may expose the private session bundle")


def validate_workflow(path: Path = WORKFLOW_PATH) -> None:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LoadError("cannot read WP-12B staging workflow") from error
    validate_workflow_source(source)


def validate_origin(value: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise LoadError("load target must be a plain origin without credentials or path")
    if value.rstrip("/") == STAGING_ORIGIN:
        return STAGING_ORIGIN, "staging"
    if parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS and parsed.port:
        return value.rstrip("/"), "local"
    raise LoadError("load target must be canonical staging HTTPS or loopback HTTP")


def actor_from_json(value: object, *, expected_role: str, organization_ref: str) -> SessionActor:
    if not isinstance(value, dict) or set(value) != {
        "organization_ref",
        "role",
        "session_token",
        "csrf_token",
        "assignment_id",
    }:
        raise LoadError("synthetic actor bundle is malformed")
    if value["organization_ref"] != organization_ref or value["role"] != expected_role:
        raise LoadError("synthetic actor scope or role is inconsistent")
    session_token = value["session_token"]
    csrf_token = value["csrf_token"]
    assignment_id = value["assignment_id"]
    if not isinstance(session_token, str) or len(session_token) < 32:
        raise LoadError("synthetic session token is invalid")
    if not isinstance(csrf_token, str) or len(csrf_token) < 32:
        raise LoadError("synthetic CSRF token is invalid")
    if assignment_id is not None and not isinstance(assignment_id, str):
        raise LoadError("synthetic assignment reference is invalid")
    if expected_role == "LEARNER" and not assignment_id:
        raise LoadError("synthetic learner is missing an assignment")
    if expected_role != "LEARNER" and assignment_id is not None:
        raise LoadError("non-learner synthetic actor must not carry an assignment")
    return SessionActor(
        organization_ref=organization_ref,
        role=expected_role,
        session_token=session_token,
        csrf_token=csrf_token,
        assignment_id=assignment_id,
    )


def load_bundle(path: Path, config: dict[str, Any], *, smoke: bool) -> tuple[dict[str, Any], tuple[OrganizationActors, ...]]:
    require_owner_only(path)
    bundle = read_json(path)
    if set(bundle) != {
        "schema_version",
        "classification",
        "scope",
        "candidate_sha",
        "run_id",
        "created_at",
        "expires_at",
        "organizations",
    }:
        raise LoadError("synthetic session bundle fields are invalid")
    if bundle["schema_version"] != 1 or bundle["classification"] != "SYNTHETIC_NO_REAL_PII":
        raise LoadError("synthetic session bundle identity is invalid")
    if bundle["scope"] not in {"LOCAL_SMOKE", "STAGING_SYNTHETIC_MULTI_TENANT"}:
        raise LoadError("synthetic session bundle scope is invalid")
    try:
        created_at = datetime.fromisoformat(bundle["created_at"])
        expires_at = datetime.fromisoformat(bundle["expires_at"])
    except (TypeError, ValueError) as error:
        raise LoadError("synthetic session bundle timestamps are invalid") from error
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None or expires_at.tzinfo is None:
        raise LoadError("synthetic session bundle timestamps must include a timezone")
    if expires_at <= created_at or expires_at <= now:
        raise LoadError("synthetic session bundle is expired or has an invalid lifetime")
    if expires_at - created_at > timedelta(hours=2, minutes=1):
        raise LoadError("synthetic session bundle lifetime exceeds the approved window")
    if not isinstance(bundle["run_id"], str) or not RUN_ID_RE.fullmatch(bundle["run_id"]):
        raise LoadError("synthetic run_id is invalid")
    organizations_raw = bundle["organizations"]
    if not isinstance(organizations_raw, list):
        raise LoadError("synthetic organizations must be a list")
    expected_orgs = len(organizations_raw) if smoke else config["organization_count"]
    if len(organizations_raw) != expected_orgs or len(organizations_raw) < 2:
        raise LoadError("synthetic organization count differs from the load profile")
    organizations: list[OrganizationActors] = []
    seen_refs: set[str] = set()
    for raw in organizations_raw:
        if not isinstance(raw, dict) or set(raw) != {"ref", "learners", "reviewers", "operator"}:
            raise LoadError("synthetic organization bundle is malformed")
        ref = raw["ref"]
        if not isinstance(ref, str) or not re.fullmatch(r"org-[0-9]{3}", ref) or ref in seen_refs:
            raise LoadError("synthetic organization reference is invalid or duplicated")
        seen_refs.add(ref)
        learners_raw = raw["learners"]
        reviewers_raw = raw["reviewers"]
        if not isinstance(learners_raw, list) or not isinstance(reviewers_raw, list):
            raise LoadError("synthetic role lists are malformed")
        expected_learners = len(learners_raw) if smoke else config["learners_per_organization"]
        expected_reviewers = len(reviewers_raw) if smoke else config["reviewers_per_organization"]
        if len(learners_raw) != expected_learners or len(reviewers_raw) != expected_reviewers:
            raise LoadError("synthetic role counts differ from the load profile")
        organizations.append(
            OrganizationActors(
                ref=ref,
                learners=tuple(actor_from_json(item, expected_role="LEARNER", organization_ref=ref) for item in learners_raw),
                reviewers=tuple(actor_from_json(item, expected_role="REVIEWER", organization_ref=ref) for item in reviewers_raw),
                operator=actor_from_json(raw["operator"], expected_role="OPERATOR", organization_ref=ref),
            )
        )
    return bundle, tuple(organizations)


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise LoadError("cannot calculate latency without samples")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


class Runner:
    def __init__(self, origin: str, timeout_seconds: float) -> None:
        self.origin = origin
        self.timeout_seconds = timeout_seconds
        self._observations: list[Observation] = []
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(NoRedirectHandler())

    @property
    def observations(self) -> tuple[Observation, ...]:
        with self._lock:
            return tuple(self._observations)

    def request(
        self,
        operation: str,
        path: str,
        *,
        actor: SessionActor | None = None,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        expected_status: int = 200,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = actor.headers if actor is not None else {"Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            if actor is None or idempotency_key is None:
                raise LoadError("command requests require an actor and idempotency key")
            headers = actor.command_headers(idempotency_key)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"{self.origin}{path}", headers=headers, data=body, method=method
        )
        started = time.perf_counter()
        raw = b""
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - validated origin and redirects disabled
                status = int(response.status)
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = int(error.code)
            raw = error.read()
        except (OSError, urllib.error.URLError) as error:
            status = 599
            raw = b""
        elapsed = time.perf_counter() - started
        with self._lock:
            self._observations.append(Observation(operation, expected_status, status, elapsed))
        if not raw:
            return status, {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return status, {}
        return status, decoded if isinstance(decoded, dict) else {}


def data_envelope(response: dict[str, Any]) -> Any:
    return response.get("data") if isinstance(response, dict) else None


def learner_flow(runner: Runner, actor: SessionActor, foreign_assignment_id: str, run_id: str) -> None:
    status, current_payload = runner.request("learner.current_action.pre", "/api/v1/me/current-action", actor=actor)
    current = data_envelope(current_payload)
    if status != 200 or not isinstance(current, dict) or current.get("resource_id") != actor.assignment_id:
        return
    runner.request(
        "isolation.learner_foreign_assignment",
        f"/api/v1/me/assignments/{foreign_assignment_id}",
        actor=actor,
        expected_status=404,
    )
    start_status, start_payload = runner.request(
        "learner.assignment_start",
        f"/api/v1/me/assignments/{actor.assignment_id}/start",
        actor=actor,
        method="POST",
        payload={"expected_revision": current.get("revision")},
        idempotency_key=f"wp12b-{run_id}-start-{hashlib.sha256(actor.session_token.encode()).hexdigest()[:16]}",
    )
    started = data_envelope(start_payload)
    if start_status != 200 or not isinstance(started, dict):
        return
    runner.request(
        "learner.submission_create",
        f"/api/v1/me/assignments/{actor.assignment_id}/submissions",
        actor=actor,
        method="POST",
        payload={
            "expected_revision": started.get("revision"),
            "body": (
                "合成压测问题：当前行动需要保持唯一。事实一：这是无个人信息的 WP-12B 样本。"
                "事实二：所有引用均绑定合成组织。行动：提交、评审并核对隔离；"
                "若出现跨组织可见、重复事实或状态冲突则立即停止。"
            ),
        },
        idempotency_key=f"wp12b-{run_id}-submit-{hashlib.sha256(actor.csrf_token.encode()).hexdigest()[:16]}",
    )


def reviewer_queue(runner: Runner, actor: SessionActor) -> list[dict[str, Any]]:
    status, payload = runner.request("reviewer.queue", "/api/v1/reviews", actor=actor)
    data = data_envelope(payload)
    items = data.get("items") if isinstance(data, dict) else None
    if status != 200 or not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def reviewer_flow(runner: Runner, actor: SessionActor, review: dict[str, Any], run_id: str) -> None:
    review_id = review.get("id")
    revision = review.get("revision")
    if not isinstance(review_id, str) or not isinstance(revision, int):
        return
    token_ref = hashlib.sha256(actor.session_token.encode()).hexdigest()[:12]
    start_status, start_payload = runner.request(
        "reviewer.review_start",
        f"/api/v1/reviews/{review_id}/start",
        actor=actor,
        method="POST",
        payload={"expected_revision": revision},
        idempotency_key=f"wp12b-{run_id}-review-start-{token_ref}-{review_id[-8:]}",
    )
    started = data_envelope(start_payload)
    if start_status != 200 or not isinstance(started, dict):
        return
    runner.request(
        "reviewer.review_finalize",
        f"/api/v1/reviews/{review_id}/finalize",
        actor=actor,
        method="POST",
        payload={
            "expected_revision": started.get("review_revision"),
            "overall_decision": "APPROVE",
            "overall_feedback": "合成材料满足固定四维合同；仅用于 WP-12B 容量与隔离验证。",
            "rubric_evaluations": [
                {"dimension_key": key, "rating": "MEETS", "feedback": "合成证据满足该维度。"}
                for key in (
                    "problem_clarity",
                    "evidence_quality",
                    "action_feasibility",
                    "validation_design",
                )
            ],
        },
        idempotency_key=f"wp12b-{run_id}-review-final-{token_ref}-{review_id[-8:]}",
    )


def run_parallel(tasks: Iterable[Callable[[], None]], concurrency: int) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(task) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def scheduled_reads(
    runner: Runner,
    probes: tuple[Callable[[], None], ...],
    *,
    duration_seconds: int,
    requests_per_second: int,
    concurrency: int,
) -> None:
    if not probes:
        raise LoadError("scheduled read phase has no probes")
    total = duration_seconds * requests_per_second
    interval = 1.0 / requests_per_second
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures: list[concurrent.futures.Future[None]] = []
        for index in range(total):
            deadline = started + index * interval
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            futures.append(executor.submit(probes[index % len(probes)]))
        for future in futures:
            future.result()


def summarize(observations: tuple[Observation, ...], config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not observations:
        raise LoadError("load execution produced no observations")
    grouped: dict[str, list[Observation]] = {}
    for item in observations:
        grouped.setdefault(item.operation, []).append(item)
    endpoints: dict[str, Any] = {}
    all_pass = True
    for operation, items in sorted(grouped.items()):
        latencies = [item.elapsed_seconds for item in items]
        unexpected = sum(item.actual_status != item.expected_status for item in items)
        p95 = nearest_rank(latencies, 0.95)
        operation_pass = unexpected == 0 and p95 <= float(config["p95_budget_seconds"])
        all_pass = all_pass and operation_pass
        endpoints[operation] = {
            "requests": len(items),
            "expected_status": items[0].expected_status,
            "unexpected_responses": unexpected,
            "p50_seconds": round(nearest_rank(latencies, 0.50), 6),
            "p95_seconds": round(p95, 6),
            "max_seconds": round(max(latencies), 6),
            "budget_seconds": config["p95_budget_seconds"],
            "status": "PASS" if operation_pass else "FAIL",
        }
    http_5xx = sum(item.actual_status >= 500 for item in observations)
    state_conflicts = sum(item.actual_status == 409 for item in observations)
    cross_org_leaks = sum(
        item.operation.startswith("isolation.") and item.actual_status != item.expected_status
        for item in observations
    )
    unexpected_total = sum(item.actual_status != item.expected_status for item in observations)
    all_pass = all_pass and all(
        (
            http_5xx <= config["max_http_5xx"],
            state_conflicts <= config["max_state_conflicts"],
            cross_org_leaks <= config["max_cross_org_leaks"],
            unexpected_total <= config["max_unexpected_responses"],
        )
    )
    return ("PASS" if all_pass else "FAIL"), {
        "requests": len(observations),
        "http_5xx": http_5xx,
        "state_conflicts": state_conflicts,
        "cross_org_leaks": cross_org_leaks,
        "unexpected_responses": unexpected_total,
        "endpoints": endpoints,
    }


def owner_only_write(root: Path, prefix: str, payload: dict[str, Any]) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (
        f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{secrets.token_hex(4)}.json"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def execute(origin: str, bundle_path: Path, *, smoke: bool) -> Path:
    config = load_contract()
    origin, environment = validate_origin(origin)
    bundle, organizations = load_bundle(bundle_path, config, smoke=smoke)
    candidate = bundle["candidate_sha"]
    if environment == "staging":
        if smoke or bundle["scope"] != "STAGING_SYNTHETIC_MULTI_TENANT" or not isinstance(candidate, str) or not SHA_RE.fullmatch(candidate):
            raise LoadError("staging execution requires the full approved profile and candidate SHA")
    elif bundle["scope"] != "LOCAL_SMOKE":
        raise LoadError("loopback execution requires a LOCAL_SMOKE bundle")
    runner = Runner(origin, float(config["request_timeout_seconds"]))
    readiness_status, readiness = runner.request("readiness", "/health/ready")
    if readiness_status != 200 or not isinstance(readiness.get("release"), str):
        raise LoadError("target readiness did not return a release")
    if readiness["release"] != candidate:
        raise LoadError("target release differs from the prepared synthetic bundle")

    concurrency = min(8, config["peak_concurrency"]) if smoke else config["peak_concurrency"]
    learners = [
        (organization_index, organization, actor)
        for organization_index, organization in enumerate(organizations)
        for actor in organization.learners
    ]
    run_parallel(
        (
            lambda actor=actor, organization_index=organization_index: learner_flow(
                runner,
                actor,
                organizations[(organization_index + 1) % len(organizations)]
                .learners[0]
                .assignment_id
                or "",
                bundle["run_id"],
            )
            for organization_index, _organization, actor in learners
        ),
        concurrency,
    )

    review_queues: dict[str, tuple[SessionActor, list[dict[str, Any]]]] = {}
    for organization in organizations:
        for reviewer in organization.reviewers:
            review_queues[f"{organization.ref}:{len(review_queues)}"] = (reviewer, reviewer_queue(runner, reviewer))
    expected_reviews = len(learners)
    actual_reviews = sum(len(items) for _, items in review_queues.values())
    if actual_reviews != expected_reviews:
        raise LoadError(f"review queue count mismatch: expected {expected_reviews}, got {actual_reviews}")

    queues_by_org: dict[str, list[tuple[SessionActor, dict[str, Any]]]] = {}
    first_review_by_org: dict[str, str] = {}
    for reviewer, items in review_queues.values():
        queues_by_org.setdefault(reviewer.organization_ref, []).extend((reviewer, item) for item in items)
        if items and isinstance(items[0].get("id"), str):
            first_review_by_org.setdefault(reviewer.organization_ref, items[0]["id"])
    for index, organization in enumerate(organizations):
        foreign_ref = organizations[(index + 1) % len(organizations)].ref
        foreign_review = first_review_by_org.get(foreign_ref)
        if foreign_review:
            runner.request(
                "isolation.reviewer_foreign_review",
                f"/api/v1/reviews/{foreign_review}",
                actor=organization.reviewers[0],
                expected_status=404,
            )
    run_parallel(
        (
            lambda reviewer=reviewer, review=review: reviewer_flow(
                runner, reviewer, review, bundle["run_id"]
            )
            for entries in queues_by_org.values()
            for reviewer, review in entries
        ),
        concurrency,
    )

    probes: list[Callable[[], None]] = [
        lambda: runner.request("readiness", "/health/ready"),
    ]
    for organization in organizations:
        learner = organization.learners[0]
        reviewer = organization.reviewers[0]
        operator = organization.operator
        probes.extend(
            (
                lambda actor=learner: runner.request("learner.current_action.post", "/api/v1/me/current-action", actor=actor),
                lambda actor=learner: runner.request("learner.result", "/api/v1/me/result", actor=actor),
                lambda actor=reviewer: runner.request("reviewer.queue.post", "/api/v1/reviews", actor=actor),
                lambda actor=operator: runner.request("operator.runtime", "/api/v1/ops/runtime-status", actor=actor),
            )
        )
    steady_seconds = 2 if smoke else config["steady_state_seconds"]
    steady_rate = min(10, config["steady_requests_per_second"]) if smoke else config["steady_requests_per_second"]
    burst_seconds = 1 if smoke else config["burst_seconds"]
    burst_rate = min(20, config["burst_requests_per_second"]) if smoke else config["burst_requests_per_second"]
    scheduled_reads(runner, tuple(probes), duration_seconds=steady_seconds, requests_per_second=steady_rate, concurrency=concurrency)
    scheduled_reads(runner, tuple(probes), duration_seconds=burst_seconds, requests_per_second=burst_rate, concurrency=concurrency)

    status, metrics = summarize(runner.observations, config)
    report = {
        "schema_version": 1,
        "scope": "LOCAL_SMOKE" if smoke else "STAGING_SYNTHETIC_MULTI_TENANT",
        "candidate_sha": candidate,
        "run_id": bundle["run_id"],
        "started_at": bundle["created_at"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "organizations": len(organizations),
            "learners": len(learners),
            "reviewers": sum(len(item.reviewers) for item in organizations),
            "operators": len(organizations),
            "peak_concurrency": concurrency,
            "steady_state_seconds": steady_seconds,
            "steady_requests_per_second": steady_rate,
            "burst_seconds": burst_seconds,
            "burst_requests_per_second": burst_rate,
        },
        "metrics": metrics,
        "status": status,
        "staging_benchmark": "PASS" if not smoke and status == "PASS" else "NOT_RUN",
        "pilot_availability_99_5_percent": "NOT_RUN",
        "production_mutation_executed": False,
        "notifications_sent_by_runner": False,
        "session_material_recorded": False,
    }
    path = owner_only_write(ARTIFACT_ROOT, "multitenant-load", report)
    if status != "PASS":
        raise LoadError(f"multi-tenant load failed; evidence: {path}")
    return path


def verify_evidence(load_path: Path, audit_path: Path, retired_path: Path) -> dict[str, Any]:
    config = load_contract()
    documents = [read_json(path) for path in (load_path, audit_path, retired_path)]
    load, audit, retired = documents
    shared = (load.get("candidate_sha"), load.get("run_id"))
    if not SHA_RE.fullmatch(str(shared[0])) or not RUN_ID_RE.fullmatch(str(shared[1])):
        raise LoadError("staging evidence is not bound to a candidate and run")
    for document in documents:
        if (document.get("candidate_sha"), document.get("run_id")) != shared:
            raise LoadError("WP-12B evidence candidate or run binding differs")
        if document.get("status") != "PASS":
            raise LoadError("WP-12B evidence contains a non-PASS document")
    metrics = load.get("metrics")
    audit_metrics = audit.get("metrics")
    retired_metrics = retired.get("metrics")
    if not isinstance(metrics, dict) or any(metrics.get(key) != 0 for key in ("http_5xx", "state_conflicts", "cross_org_leaks", "unexpected_responses")):
        raise LoadError("load metrics do not close the zero-tolerance gates")
    if not isinstance(audit_metrics, dict) or any(audit_metrics.get(key) != 0 for key in ("cross_org_mismatches", "duplicate_facts", "incomplete_flows")):
        raise LoadError("database audit does not close isolation and fact gates")
    if not isinstance(retired_metrics, dict) or retired_metrics.get("active_sessions") != 0 or retired_metrics.get("active_users") != 0:
        raise LoadError("synthetic identities were not fully retired")
    if load.get("staging_benchmark") != "PASS" or load.get("scope") != config["scope"]:
        raise LoadError("staging benchmark was not executed under the approved scope")
    return {
        "schema_version": 1,
        "candidate_sha": shared[0],
        "run_id": shared[1],
        "status": "PASS",
        "decision": "WP12B_CLOSED",
        "multi_tenant_isolation": "PASS",
        "staging_performance_p95": "PASS",
        "synthetic_identities_retired": "PASS",
        "pilot_availability_99_5_percent": "NOT_RUN",
        "production_mutation_executed": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("contract-check")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--origin", required=True)
    run_parser.add_argument("--bundle", type=Path, required=True)
    run_parser.add_argument("--smoke", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--load", type=Path, required=True)
    verify_parser.add_argument("--audit", type=Path, required=True)
    verify_parser.add_argument("--retired", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "contract-check":
            config = load_contract()
            validate_workflow()
            print(
                "WP12B_CONTRACT=PASS "
                f"organizations={config['organization_count']} "
                f"learners={config['organization_count'] * config['learners_per_organization']} "
                f"peak_concurrency={config['peak_concurrency']} "
                "staging_mutation_executed=false"
            )
        elif args.command == "run":
            print(execute(args.origin, args.bundle, smoke=args.smoke))
        elif args.command == "verify":
            evidence = verify_evidence(args.load, args.audit, args.retired)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(evidence, handle, ensure_ascii=False, indent=2, sort_keys=True)
                    handle.write("\n")
            print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        return 0
    except LoadError as error:
        print(f"WP12B_LOAD_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
