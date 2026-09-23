"""Plan or apply the idempotent latest-version treasure coaching backfill."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.db import engine
from journey_api.models import (
    Assignment,
    Enrollment,
    EnrollmentStatus,
    JourneyStageKind,
    JourneyStageVersion,
    Review,
    ReviewKind,
    ReviewStatus,
    Submission,
    SubmissionVersion,
)


def candidates(session: Session, *, lock: bool = False):
    statement = (
        select(Assignment, Enrollment, Submission, SubmissionVersion, JourneyStageVersion)
        .join(Enrollment, Enrollment.id == Assignment.enrollment_id)
        .join(JourneyStageVersion, JourneyStageVersion.id == Assignment.journey_stage_version_id)
        .join(Submission, Submission.assignment_id == Assignment.id)
        .join(
            SubmissionVersion,
            (SubmissionVersion.submission_id == Submission.id)
            & (SubmissionVersion.version_no == Submission.current_version_no),
        )
        .outerjoin(Review, Review.submission_version_id == SubmissionVersion.id)
        .where(
            JourneyStageVersion.stage_kind == JourneyStageKind.TREASURE,
            Enrollment.status.in_(
                [
                    EnrollmentStatus.ACTIVE,
                    EnrollmentStatus.COMPLETED,
                    EnrollmentStatus.CANCELLED,
                ]
            ),
            Submission.current_version_no > 0,
            Review.id.is_(None),
        )
        .order_by(Assignment.organization_id, Enrollment.id, Assignment.position)
    )
    if lock:
        statement = statement.with_for_update(of=(Assignment, Submission))
    return session.execute(statement).all()


def summary(rows) -> dict[str, object]:
    return {
        "candidate_count": len(rows),
        "organization_count": len({str(row[0].organization_id) for row in rows}),
        "enrollment_count": len({str(row[1].id) for row in rows}),
        "assignment_ids": [str(row[0].id) for row in rows],
        "submission_version_ids": [str(row[3].id) for row in rows],
        "rule": "latest treasure SubmissionVersion only; ACTIVE/COMPLETED actionable; CANCELLED history-only",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "apply"])
    args = parser.parse_args()
    with Session(engine) as session:
        rows = candidates(session, lock=args.command == "apply")
        before = summary(rows)
        if args.command == "plan":
            print(json.dumps({"mode": "plan", **before}, ensure_ascii=False))
            return
        created = 0
        for assignment, enrollment, submission, version, _stage in rows:
            cancelled = enrollment.status == EnrollmentStatus.CANCELLED
            session.add(
                Review(
                    id=uuid.uuid4(),
                    organization_id=assignment.organization_id,
                    assignment_id=assignment.id,
                    submission_id=submission.id,
                    submission_version_id=version.id,
                    reviewer_id=enrollment.reviewer_id,
                    review_kind=ReviewKind.LEARNING_COACHING,
                    status=(
                        ReviewStatus.SUPERSEDED if cancelled else ReviewStatus.ASSIGNED
                    ),
                    superseded_at=datetime.now(UTC) if cancelled else None,
                    revision=1,
                )
            )
            created += 1
        session.flush()
        remaining = len(candidates(session))
        if remaining:
            raise RuntimeError(f"backfill verification failed: {remaining} candidates remain")
        session.commit()
        print(json.dumps({"mode": "apply", **before, "created": created, "remaining": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
