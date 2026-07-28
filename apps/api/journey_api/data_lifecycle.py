"""Read-only WP-12 retention and data-rights planning.

This module deliberately has no APPLY command. It inventories records that have
reached an approved retention cutoff and overdue data-rights requests without
mutating business facts. A later reviewed executor must preserve legal holds,
foreign-key integrity, attachment object deletion, and immutable audit evidence.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.db import SessionLocal
from journey_api.models import (
    Attachment,
    AuditEntry,
    DataRightsRequest,
    DataRightsRequestStatus,
    Evaluation,
    ExternalIdentity,
    ExternalIdentityLink,
    ExternalNotificationReceipt,
    IdempotencyRecord,
    IdentitySession,
    Invite,
    JoinContext,
    LocalNotificationReceipt,
    NotificationAttempt,
    NotificationDelivery,
    NotificationEndpoint,
    OAuthLoginState,
    Outcome,
    Submission,
    SubmissionVersion,
)


DEFAULT_POLICY_PATH = Path("config") / "wp12_data_lifecycle.json"
EXPECTED_RETENTION_DAYS = {
    "identity": 1095,
    "submissions": 1095,
    "evaluations": 1095,
    "outcomes": 1095,
    "audit": 1095,
    "attachments": 365,
    "notifications": 180,
    "idempotency": 30,
}


class DataLifecycleError(RuntimeError):
    """The lifecycle policy or requested planning time is unsafe."""


@dataclass(frozen=True)
class DataLifecyclePolicy:
    schema_version: int
    policy_version: str
    data_rights_due_days: int
    retention_days: dict[str, int]


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> DataLifecyclePolicy:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DataLifecycleError(f"data lifecycle policy is unavailable: {error}") from error
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "policy_version",
        "data_rights_due_days",
        "retention_days",
    }:
        raise DataLifecycleError("data lifecycle policy has unknown or missing fields")
    if raw["schema_version"] != 1 or raw["data_rights_due_days"] != 30:
        raise DataLifecycleError("data lifecycle policy version or rights deadline is invalid")
    retention = raw["retention_days"]
    if retention != EXPECTED_RETENTION_DAYS:
        raise DataLifecycleError("data lifecycle retention periods differ from DEC-008")
    version = raw["policy_version"]
    if not isinstance(version, str) or len(version) != 10:
        raise DataLifecycleError("data lifecycle policy version must be an ISO date")
    return DataLifecyclePolicy(
        schema_version=1,
        policy_version=version,
        data_rights_due_days=30,
        retention_days=dict(retention),
    )


def _count_before(
    session: Session,
    model: type[Any],
    timestamp: Any,
    cutoff: datetime,
) -> int:
    return int(
        session.scalar(select(func.count()).select_from(model).where(timestamp < cutoff))
        or 0
    )


def retention_plan(
    session: Session,
    policy: DataLifecyclePolicy,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise DataLifecycleError("as_of must be timezone-aware")
    as_of = as_of.astimezone(UTC)
    cutoffs = {
        name: as_of - timedelta(days=days)
        for name, days in policy.retention_days.items()
    }
    eligible = {
        "identity.external_identities": _count_before(
            session, ExternalIdentity, ExternalIdentity.verified_at, cutoffs["identity"]
        ),
        "identity.external_identity_links": _count_before(
            session,
            ExternalIdentityLink,
            ExternalIdentityLink.created_at,
            cutoffs["identity"],
        ),
        "identity.sessions": _count_before(
            session, IdentitySession, IdentitySession.created_at, cutoffs["identity"]
        ),
        "identity.invites": _count_before(
            session, Invite, Invite.created_at, cutoffs["identity"]
        ),
        "identity.join_contexts": _count_before(
            session, JoinContext, JoinContext.created_at, cutoffs["identity"]
        ),
        "identity.oauth_states": _count_before(
            session, OAuthLoginState, OAuthLoginState.created_at, cutoffs["identity"]
        ),
        "submissions.roots": _count_before(
            session, Submission, Submission.created_at, cutoffs["submissions"]
        ),
        "submissions.versions": _count_before(
            session,
            SubmissionVersion,
            SubmissionVersion.created_at,
            cutoffs["submissions"],
        ),
        "evaluations": _count_before(
            session, Evaluation, Evaluation.created_at, cutoffs["evaluations"]
        ),
        "outcomes": _count_before(
            session, Outcome, Outcome.created_at, cutoffs["outcomes"]
        ),
        "audit": _count_before(
            session, AuditEntry, AuditEntry.occurred_at, cutoffs["audit"]
        ),
        "attachments": _count_before(
            session, Attachment, Attachment.created_at, cutoffs["attachments"]
        ),
        "notifications.deliveries": _count_before(
            session,
            NotificationDelivery,
            NotificationDelivery.created_at,
            cutoffs["notifications"],
        ),
        "notifications.endpoints": _count_before(
            session,
            NotificationEndpoint,
            NotificationEndpoint.created_at,
            cutoffs["notifications"],
        ),
        "notifications.attempts": _count_before(
            session,
            NotificationAttempt,
            NotificationAttempt.attempted_at,
            cutoffs["notifications"],
        ),
        "notifications.local_receipts": _count_before(
            session,
            LocalNotificationReceipt,
            LocalNotificationReceipt.created_at,
            cutoffs["notifications"],
        ),
        "notifications.external_receipts": _count_before(
            session,
            ExternalNotificationReceipt,
            ExternalNotificationReceipt.created_at,
            cutoffs["notifications"],
        ),
        "idempotency": _count_before(
            session,
            IdempotencyRecord,
            IdempotencyRecord.created_at,
            cutoffs["idempotency"],
        ),
    }
    overdue_rights_requests = int(
        session.scalar(
            select(func.count())
            .select_from(DataRightsRequest)
            .where(
                DataRightsRequest.status == DataRightsRequestStatus.OPEN,
                DataRightsRequest.legal_hold.is_(False),
                DataRightsRequest.due_at < as_of,
            )
        )
        or 0
    )
    legal_holds = int(
        session.scalar(
            select(func.count())
            .select_from(DataRightsRequest)
            .where(
                DataRightsRequest.status == DataRightsRequestStatus.OPEN,
                DataRightsRequest.legal_hold.is_(True),
            )
        )
        or 0
    )
    return {
        "schema_version": 1,
        "policy_version": policy.policy_version,
        "mode": "PLAN_ONLY",
        "as_of": as_of.isoformat(),
        "cutoffs": {
            name: cutoff.isoformat() for name, cutoff in sorted(cutoffs.items())
        },
        "eligible_counts": dict(sorted(eligible.items())),
        "overdue_data_rights_requests": overdue_rights_requests,
        "active_legal_holds": legal_holds,
        "mutations_executed": False,
        "contains_record_identifiers": False,
    }


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DataLifecycleError("as_of must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DataLifecycleError("as_of must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    policy_check = commands.add_parser("policy-check")
    policy_check.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    plan = commands.add_parser("plan")
    plan.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    plan.add_argument("--as-of")
    args = parser.parse_args()
    try:
        policy = load_policy(args.policy)
        if args.command == "policy-check":
            result: dict[str, Any] = {
                "status": "PASS",
                "policy_version": policy.policy_version,
                "data_rights_due_days": policy.data_rights_due_days,
                "retention_days": policy.retention_days,
                "mutations_executed": False,
            }
        else:
            with SessionLocal() as session:
                result = retention_plan(
                    session,
                    policy,
                    as_of=parse_as_of(args.as_of),
                )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (DataLifecycleError, OSError) as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": str(error),
                    "mutations_executed": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
