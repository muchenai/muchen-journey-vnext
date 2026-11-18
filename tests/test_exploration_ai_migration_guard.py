"""The database guard admits inherited ownership only through a live mapping."""
import copy
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.models import Submission, SubmissionVersion
from test_dynamic_exploration import exploration
from test_dynamic_exploration_ai import ANSWER, ai, check
from test_exploration_ai_migrated_learner import (
    migrated_exploration,
    revoke_during_scoring,
)
from test_exploration_ai_publisher_contract import assert_ai_completion
from test_wp09_feishu_identity import assert_ok


@pytest.mark.parametrize("boundary", [
    "valid", "mapping_unused", "mapping_removed", "principal_disabled",
    "principal_role_removed", "record_owner_role_removed",
])
def test_raw_ai_evidence_insert_requires_live_inherited_ownership(
    migrated_exploration, ai, boundary
):
    case = migrated_exploration
    _, reviewer = ai
    reviewer.score_factor = .6
    result = assert_ok(check(case.learner, case.task, ANSWER))
    assert_ai_completion(result["task"], result["record"], case.content, 60)
    if boundary != "valid":
        revoke_during_scoring(case, boundary)
    # Bypass the service deliberately: the SQL trigger itself must reject
    # immutable AI evidence for an arbitrarily disabled/unmapped record owner.
    with SessionLocal() as session:
        original = session.scalar(select(SubmissionVersion)
            .join(Submission, Submission.id == SubmissionVersion.submission_id)
            .where(Submission.assignment_id == uuid.UUID(case.task["assignmentId"])))
        candidate = SubmissionVersion(
            id=uuid.uuid4(), submission_id=original.submission_id,
            version_no=original.version_no + 1, body=original.body,
            ai_use=copy.deepcopy(original.ai_use), created_by=original.created_by,
            created_at=original.created_at,
        )
        session.add(candidate)
        if boundary == "valid":
            session.flush()
        else:
            with pytest.raises(DBAPIError) as raised:
                session.flush()
            assert getattr(raised.value.orig, "sqlstate", None) == "23514"
            assert "AI completion does not match owned dynamic AI task" in str(raised.value.orig)
        session.rollback()
