"""Prepare, audit, and retire bounded synthetic WP-12B staging identities.

This operational module runs only inside the API image so session secrets never
leave the approved runtime. It creates clearly labelled synthetic organizations,
never real external identities or notification recipients, and retains business
facts while revoking every temporary session after the benchmark.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.identity import credential_hash
from journey_api.models import (
    Assignment,
    AssignmentStatus,
    Enrollment,
    EnrollmentStatus,
    Evaluation,
    IdentitySession,
    Organization,
    Outcome,
    Review,
    ReviewStatus,
    Role,
    RoleAssignment,
    Submission,
    SubmissionVersion,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.seed import (
    COMPLETION_CRITERIA,
    INSTRUCTIONS,
    REQUIRED_DELIVERABLES,
    RUBRIC,
)


ROOT = Path(os.environ.get("MJ_REPO_ROOT", Path.cwd())).resolve()
CONFIG_PATH = ROOT / "config" / "wp12b_multitenant_load.json"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,39}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class SyntheticError(RuntimeError):
    """Synthetic setup or evidence did not satisfy the bounded contract."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_config() -> dict[str, Any]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyntheticError("cannot read WP-12B load profile") from error
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise SyntheticError("WP-12B load profile is invalid")
    return config


def validate_runtime(candidate: str, confirmation: str) -> str:
    settings = get_settings()
    if settings.app_env not in {"local", "test", "staging"}:
        raise SyntheticError("WP-12B synthetic operations refuse production")
    if candidate != settings.app_release:
        raise SyntheticError("expected candidate differs from the running API release")
    if settings.app_env == "staging":
        if not SHA_RE.fullmatch(candidate):
            raise SyntheticError("staging WP-12B requires a full candidate SHA")
        if confirmation != f"PREPARE_WP12B_{candidate}":
            raise SyntheticError("staging WP-12B confirmation is invalid")
        return "STAGING_SYNTHETIC_MULTI_TENANT"
    if confirmation != "PREPARE_WP12B_LOCAL":
        raise SyntheticError("local WP-12B confirmation is invalid")
    return "LOCAL_SMOKE"


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise SyntheticError("run_id must be 6..40 lowercase letters, digits, or hyphens")


def open_private_output(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def write_private(path: Path, payload: dict[str, Any]) -> None:
    with open_private_output(path) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise SyntheticError("synthetic private output is not owner-only")


def new_session(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role,
    expires_at: datetime,
    session_secret: str,
) -> tuple[str, str]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session.add(
        IdentitySession(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            external_identity_id=None,
            role=role,
            token_hash=credential_hash(session_secret, "session", session_token),
            csrf_token_hash=credential_hash(session_secret, "csrf", csrf_token),
            expires_at=expires_at,
        )
    )
    return session_token, csrf_token


def actor_payload(
    organization_ref: str,
    role: Role,
    tokens: tuple[str, str],
    assignment_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "organization_ref": organization_ref,
        "role": role.value,
        "session_token": tokens[0],
        "csrf_token": tokens[1],
        "assignment_id": str(assignment_id) if assignment_id else None,
    }


def prepare(
    *,
    candidate: str,
    confirmation: str,
    run_id: str,
    organizations: int,
    learners_per_organization: int,
    reviewers_per_organization: int,
    output: Path,
) -> None:
    validate_run_id(run_id)
    scope = validate_runtime(candidate, confirmation)
    config = load_config()
    if scope == "STAGING_SYNTHETIC_MULTI_TENANT":
        expected = (
            config["organization_count"],
            config["learners_per_organization"],
            config["reviewers_per_organization"],
        )
        if (organizations, learners_per_organization, reviewers_per_organization) != expected:
            raise SyntheticError("staging synthetic counts differ from the approved profile")
    elif not (
        2 <= organizations <= 5
        and 1 <= learners_per_organization <= 5
        and 1 <= reviewers_per_organization <= 2
    ):
        raise SyntheticError("local smoke counts exceed the bounded profile")
    prefix = f"WP12B:{run_id}:"
    settings = get_settings()
    now = utc_now()
    expires_at = now + timedelta(hours=2)
    organization_payloads: list[dict[str, Any]] = []
    with SessionLocal.begin() as session:
        if session.scalar(
            select(func.count()).select_from(Organization).where(Organization.name.like(f"{prefix}%"))
        ):
            raise SyntheticError("run_id already exists; synthetic setup is not replayable")
        for org_index in range(organizations):
            organization_ref = f"org-{org_index + 1:03d}"
            organization_id = uuid.uuid4()
            session.add(Organization(id=organization_id, name=f"{prefix}{organization_ref}"))
            session.flush()

            reviewer_rows: list[tuple[uuid.UUID, tuple[str, str]]] = []
            reviewer_payloads: list[dict[str, Any]] = []
            for reviewer_index in range(reviewers_per_organization):
                user_id = uuid.uuid4()
                session.add(
                    User(
                        id=user_id,
                        organization_id=organization_id,
                        display_name=f"WP12B {organization_ref} reviewer-{reviewer_index + 1:02d}",
                        status=UserStatus.ACTIVE,
                    )
                )
                session.flush()
                session.add(
                    RoleAssignment(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        user_id=user_id,
                        role=Role.REVIEWER,
                    )
                )
                tokens = new_session(
                    session,
                    organization_id=organization_id,
                    user_id=user_id,
                    role=Role.REVIEWER,
                    expires_at=expires_at,
                    session_secret=settings.session_secret,
                )
                reviewer_rows.append((user_id, tokens))
                reviewer_payloads.append(actor_payload(organization_ref, Role.REVIEWER, tokens))
                session.flush()

            operator_id = uuid.uuid4()
            session.add(
                User(
                    id=operator_id,
                    organization_id=organization_id,
                    display_name=f"WP12B {organization_ref} operator",
                    status=UserStatus.ACTIVE,
                )
            )
            session.flush()
            session.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    user_id=operator_id,
                    role=Role.OPERATOR,
                )
            )
            operator_tokens = new_session(
                session,
                organization_id=organization_id,
                user_id=operator_id,
                role=Role.OPERATOR,
                expires_at=expires_at,
                session_secret=settings.session_secret,
            )
            session.flush()

            definition_id = uuid.uuid4()
            version_id = uuid.uuid4()
            session.add(
                TaskDefinition(
                    id=definition_id,
                    organization_id=organization_id,
                    stable_key="TSK-001",
                    status=TaskDefinitionStatus.PUBLISHED,
                    revision=1,
                    created_by=operator_id,
                )
            )
            session.flush()
            session.add(
                TaskVersion(
                    id=version_id,
                    organization_id=organization_id,
                    task_definition_id=definition_id,
                    version=1,
                    title="WP-12B 合成多租户验证",
                    purpose="验证候选在多组织并发下的容量和隔离。",
                    learner_outcome="完成一次无个人信息的合成提交。",
                    instructions=INSTRUCTIONS,
                    completion_criteria=COMPLETION_CRITERIA,
                    required_deliverables=REQUIRED_DELIVERABLES,
                    content_source_notes=["WP-12B synthetic load; no real PII"],
                    change_summary="建立合成多租户容量与隔离样本。",
                    reviewer_calibration_note="机器负载样本，不是人类 Reviewer 校准。",
                    allowed_attachment_types=[],
                    max_attachment_size_bytes=0,
                    reference_materials=[],
                    estimated_duration_minutes=60,
                    rubric=RUBRIC,
                    rubric_version=1,
                    reviewer_role=Role.REVIEWER.value,
                    feedback_sla_business_days=2,
                    sensitivity="INTERNAL",
                    audience=Role.LEARNER.value,
                    published_by=operator_id,
                    reviewed_by=reviewer_rows[0][0],
                )
            )
            session.flush()

            learner_payloads: list[dict[str, Any]] = []
            for learner_index in range(learners_per_organization):
                learner_id = uuid.uuid4()
                reviewer_id = reviewer_rows[learner_index % len(reviewer_rows)][0]
                enrollment_id = uuid.uuid4()
                assignment_id = uuid.uuid4()
                session.add(
                    User(
                        id=learner_id,
                        organization_id=organization_id,
                        display_name=f"WP12B {organization_ref} learner-{learner_index + 1:03d}",
                        status=UserStatus.ACTIVE,
                    )
                )
                session.flush()
                session.add(
                    RoleAssignment(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        user_id=learner_id,
                        role=Role.LEARNER,
                    )
                )
                session.add(
                    Enrollment(
                        id=enrollment_id,
                        organization_id=organization_id,
                        learner_id=learner_id,
                        reviewer_id=reviewer_id,
                        status=EnrollmentStatus.ACTIVE,
                        revision=1,
                    )
                )
                session.flush()
                session.add(
                    Assignment(
                        id=assignment_id,
                        organization_id=organization_id,
                        enrollment_id=enrollment_id,
                        task_definition_id=definition_id,
                        task_version_id=version_id,
                        position=1,
                        status=AssignmentStatus.AVAILABLE,
                        revision=1,
                    )
                )
                tokens = new_session(
                    session,
                    organization_id=organization_id,
                    user_id=learner_id,
                    role=Role.LEARNER,
                    expires_at=expires_at,
                    session_secret=settings.session_secret,
                )
                session.flush()
                learner_payloads.append(
                    actor_payload(organization_ref, Role.LEARNER, tokens, assignment_id)
                )
            organization_payloads.append(
                {
                    "ref": organization_ref,
                    "learners": learner_payloads,
                    "reviewers": reviewer_payloads,
                    "operator": actor_payload(organization_ref, Role.OPERATOR, operator_tokens),
                }
            )
    write_private(
        output,
        {
            "schema_version": 1,
            "classification": "SYNTHETIC_NO_REAL_PII",
            "scope": scope,
            "candidate_sha": candidate,
            "run_id": run_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "organizations": organization_payloads,
        },
    )


def synthetic_organization_ids(session: Session, run_id: str) -> list[uuid.UUID]:
    validate_run_id(run_id)
    return list(
        session.scalars(
            select(Organization.id)
            .where(Organization.name.like(f"WP12B:{run_id}:%"))
            .order_by(Organization.name)
        ).all()
    )


def scalar_count(session: Session, model: type[Any], organization_ids: list[uuid.UUID]) -> int:
    organization_id = getattr(model, "organization_id")
    return int(
        session.scalar(
            select(func.count()).select_from(model).where(organization_id.in_(organization_ids))
        )
        or 0
    )


def audit(*, candidate: str, run_id: str, output: Path) -> None:
    settings = get_settings()
    if candidate != settings.app_release:
        raise SyntheticError("audit candidate differs from the running API release")
    config = load_config()
    with SessionLocal() as session:
        organization_ids = synthetic_organization_ids(session, run_id)
        if not organization_ids:
            raise SyntheticError("synthetic run does not exist")
        organizations = len(organization_ids)
        expected_learners = int(
            session.scalar(
                select(func.count())
                .select_from(RoleAssignment)
                .where(
                    RoleAssignment.organization_id.in_(organization_ids),
                    RoleAssignment.role == Role.LEARNER,
                )
            )
            or 0
        )
        expected_reviewers = int(
            session.scalar(
                select(func.count())
                .select_from(RoleAssignment)
                .where(
                    RoleAssignment.organization_id.in_(organization_ids),
                    RoleAssignment.role == Role.REVIEWER,
                )
            )
            or 0
        )
        expected_operators = int(
            session.scalar(
                select(func.count())
                .select_from(RoleAssignment)
                .where(
                    RoleAssignment.organization_id.in_(organization_ids),
                    RoleAssignment.role == Role.OPERATOR,
                )
            )
            or 0
        )
        expected_users = expected_learners + expected_reviewers + expected_operators
        users = scalar_count(session, User, organization_ids)
        assignments = scalar_count(session, Assignment, organization_ids)
        submissions = scalar_count(session, Submission, organization_ids)
        reviews = scalar_count(session, Review, organization_ids)
        evaluations = scalar_count(session, Evaluation, organization_ids)
        outcomes = scalar_count(session, Outcome, organization_ids)
        completed_assignments = int(
            session.scalar(
                select(func.count())
                .select_from(Assignment)
                .where(
                    Assignment.organization_id.in_(organization_ids),
                    Assignment.status == AssignmentStatus.COMPLETED,
                )
            )
            or 0
        )
        finalized_reviews = int(
            session.scalar(
                select(func.count())
                .select_from(Review)
                .where(
                    Review.organization_id.in_(organization_ids),
                    Review.status == ReviewStatus.FINALIZED,
                )
            )
            or 0
        )
        duplicate_facts = int(
            session.scalar(
                text(
                    """
                    SELECT count(*) FROM (
                      SELECT a.id
                      FROM assignments a
                      LEFT JOIN submissions s ON s.assignment_id = a.id
                      LEFT JOIN reviews r ON r.assignment_id = a.id
                      LEFT JOIN outcomes o ON o.assignment_id = a.id
                      WHERE a.organization_id = ANY(:organization_ids)
                      GROUP BY a.id
                      HAVING count(DISTINCT s.id) <> 1
                         OR count(DISTINCT r.id) <> 1
                         OR count(DISTINCT o.id) <> 1
                    ) invalid
                    """
                ),
                {"organization_ids": organization_ids},
            )
            or 0
        )
        cross_org_mismatches = int(
            session.scalar(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM enrollments e
                        JOIN users l ON l.id=e.learner_id
                        JOIN users r ON r.id=e.reviewer_id
                        WHERE e.organization_id<>l.organization_id OR e.organization_id<>r.organization_id)
                      + (SELECT count(*) FROM assignments a
                        JOIN enrollments e ON e.id=a.enrollment_id
                        JOIN task_versions tv ON tv.id=a.task_version_id
                        WHERE a.organization_id<>e.organization_id
                           OR a.organization_id<>tv.organization_id
                           OR a.task_definition_id<>tv.task_definition_id)
                      + (SELECT count(*) FROM submissions s JOIN assignments a ON a.id=s.assignment_id
                        WHERE s.organization_id<>a.organization_id)
                      + (SELECT count(*) FROM reviews r
                        JOIN assignments a ON a.id=r.assignment_id
                        JOIN users u ON u.id=r.reviewer_id
                        WHERE r.organization_id<>a.organization_id OR r.organization_id<>u.organization_id)
                      + (SELECT count(*) FROM evaluations e JOIN reviews r ON r.id=e.review_id
                        WHERE e.organization_id<>r.organization_id OR e.assignment_id<>r.assignment_id)
                      + (SELECT count(*) FROM outcomes o
                        JOIN evaluations e ON e.id=o.source_evaluation_id
                        JOIN enrollments n ON n.id=o.enrollment_id
                        WHERE o.organization_id<>e.organization_id OR o.organization_id<>n.organization_id)
                    """
                )
            )
            or 0
        )
        profile_mismatches = 0
        if settings.app_env == "staging":
            profile_mismatches = sum(
                (
                    organizations != int(config["organization_count"]),
                    expected_learners
                    != organizations * int(config["learners_per_organization"]),
                    expected_reviewers
                    != organizations * int(config["reviewers_per_organization"]),
                    expected_operators
                    != organizations * int(config["operators_per_organization"]),
                )
            )
        incomplete_flows = profile_mismatches + sum(
            (
                users != expected_users,
                assignments != expected_learners,
                submissions != expected_learners,
                reviews != expected_learners,
                evaluations != expected_learners,
                outcomes != expected_learners,
                completed_assignments != expected_learners,
                finalized_reviews != expected_learners,
            )
        )
    status = "PASS" if not (duplicate_facts or cross_org_mismatches or incomplete_flows) else "FAIL"
    write_private(
        output,
        {
            "schema_version": 1,
            "scope": (
                "STAGING_SYNTHETIC_MULTI_TENANT"
                if settings.app_env == "staging"
                else "LOCAL_SMOKE"
            ),
            "candidate_sha": candidate,
            "run_id": run_id,
            "completed_at": utc_now().isoformat(),
            "status": status,
            "counts": {
                "organizations": organizations,
                "users": users,
                "assignments": assignments,
                "submissions": submissions,
                "reviews": reviews,
                "evaluations": evaluations,
                "outcomes": outcomes,
            },
            "metrics": {
                "cross_org_mismatches": cross_org_mismatches,
                "duplicate_facts": duplicate_facts,
                "incomplete_flows": incomplete_flows,
            },
            "real_person_data_used": False,
            "notifications_sent_by_audit": False,
            "production_mutation_executed": False,
        },
    )
    if status != "PASS":
        raise SyntheticError("synthetic database audit failed")


def retire(*, candidate: str, run_id: str, output: Path) -> None:
    settings = get_settings()
    if candidate != settings.app_release:
        raise SyntheticError("retire candidate differs from the running API release")
    now = utc_now()
    with SessionLocal.begin() as session:
        organization_ids = synthetic_organization_ids(session, run_id)
        if not organization_ids:
            raise SyntheticError("synthetic run does not exist")
        users = list(
            session.scalars(select(User).where(User.organization_id.in_(organization_ids))).all()
        )
        sessions = list(
            session.scalars(
                select(IdentitySession).where(
                    IdentitySession.organization_id.in_(organization_ids),
                    IdentitySession.revoked_at.is_(None),
                )
            ).all()
        )
        for identity_session in sessions:
            identity_session.revoked_at = now
        for user in users:
            user.status = UserStatus.DISABLED
    with SessionLocal() as session:
        organization_ids = synthetic_organization_ids(session, run_id)
        active_sessions = int(
            session.scalar(
                select(func.count())
                .select_from(IdentitySession)
                .where(
                    IdentitySession.organization_id.in_(organization_ids),
                    IdentitySession.revoked_at.is_(None),
                )
            )
            or 0
        )
        active_users = int(
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.organization_id.in_(organization_ids),
                    User.status == UserStatus.ACTIVE,
                )
            )
            or 0
        )
    status = "PASS" if active_sessions == 0 and active_users == 0 else "FAIL"
    write_private(
        output,
        {
            "schema_version": 1,
            "scope": (
                "STAGING_SYNTHETIC_MULTI_TENANT"
                if settings.app_env == "staging"
                else "LOCAL_SMOKE"
            ),
            "candidate_sha": candidate,
            "run_id": run_id,
            "completed_at": utc_now().isoformat(),
            "status": status,
            "metrics": {
                "revoked_sessions": len(sessions),
                "disabled_users": len(users),
                "active_sessions": active_sessions,
                "active_users": active_users,
            },
            "business_facts_deleted": False,
            "notifications_sent": False,
            "production_mutation_executed": False,
        },
    )
    if status != "PASS":
        raise SyntheticError("synthetic identities were not fully retired")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--candidate", required=True)
    prepare_parser.add_argument("--confirmation", required=True)
    prepare_parser.add_argument("--run-id", required=True)
    prepare_parser.add_argument("--organizations", type=int, required=True)
    prepare_parser.add_argument("--learners-per-organization", type=int, required=True)
    prepare_parser.add_argument("--reviewers-per-organization", type=int, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    for name in ("audit", "retire"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--candidate", required=True)
        command_parser.add_argument("--run-id", required=True)
        command_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "prepare":
            prepare(
                candidate=args.candidate,
                confirmation=args.confirmation,
                run_id=args.run_id,
                organizations=args.organizations,
                learners_per_organization=args.learners_per_organization,
                reviewers_per_organization=args.reviewers_per_organization,
                output=args.output,
            )
            print("WP12B_SYNTHETIC_PREPARE=PASS output=owner-only")
        elif args.command == "audit":
            audit(candidate=args.candidate, run_id=args.run_id, output=args.output)
            print("WP12B_SYNTHETIC_AUDIT=PASS output=owner-only")
        elif args.command == "retire":
            retire(candidate=args.candidate, run_id=args.run_id, output=args.output)
            print("WP12B_SYNTHETIC_RETIRE=PASS output=owner-only")
        return 0
    except SyntheticError as error:
        print(f"WP12B_SYNTHETIC_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
