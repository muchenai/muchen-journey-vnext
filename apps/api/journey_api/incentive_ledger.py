"""Append-only incentive facts isolated from formal people conclusions.

This module deliberately contains no point values, badge rules, automatic award
path, or formal-gate mutation. Callers must supply a separately approved rule
reference and an existing PASS human Evaluation for the same Person.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from journey_api.models import (
    Decision,
    Evaluation,
    IncentiveLedgerEntry,
    IncentiveType,
    Outcome,
)
from journey_api.shared_domain import JourneyModuleKey


SHA256 = re.compile(r"^[0-9a-f]{64}$")


class IncentiveLedgerError(ValueError):
    pass


def append_incentive_entry(
    session: Session,
    *,
    organization_id: uuid.UUID,
    person_id: uuid.UUID,
    module_key: JourneyModuleKey,
    incentive_type: IncentiveType,
    source_outcome_id: uuid.UUID,
    rule_ref: str,
    rule_sha256: str,
    created_by: uuid.UUID,
    amount: int | None = None,
    label: str | None = None,
    correction_of_entry_id: uuid.UUID | None = None,
    correction_reason: str | None = None,
) -> IncentiveLedgerEntry:
    """Prepare one append-only entry; transaction ownership stays with caller."""
    if not rule_ref.strip() or len(rule_ref) > 300 or not SHA256.fullmatch(rule_sha256):
        raise IncentiveLedgerError("an approved rule reference and SHA-256 are required")
    numeric = incentive_type in {IncentiveType.POINTS, IncentiveType.XP}
    if numeric:
        if amount is None or amount == 0 or label is not None:
            raise IncentiveLedgerError("POINTS and XP require one non-zero delta")
    elif amount is not None or label is None or not label.strip():
        raise IncentiveLedgerError("BADGE and RANK require one label and no amount")

    source = session.execute(
        select(Outcome, Evaluation)
        .join(Evaluation, Evaluation.id == Outcome.source_evaluation_id)
        .where(
            Outcome.id == source_outcome_id,
            Outcome.organization_id == organization_id,
            Outcome.learner_id == person_id,
            Evaluation.organization_id == organization_id,
        )
    ).first()
    if (
        source is None
        or source[0].status != "HANDOFF_READY"
        or source[1].decision != Decision.PASS
    ):
        raise IncentiveLedgerError(
            "incentive source must be an immutable Outcome backed by a PASS human Evaluation for the same Person"
        )

    correction = None
    if correction_of_entry_id is not None:
        correction = session.scalar(
            select(IncentiveLedgerEntry)
            .where(IncentiveLedgerEntry.id == correction_of_entry_id)
            .with_for_update()
        )
        if (
            correction is None
            or correction.organization_id != organization_id
            or correction.person_id != person_id
            or correction.module_key != module_key.value
            or correction.incentive_type != incentive_type
            or correction.source_outcome_id != source_outcome_id
        ):
            raise IncentiveLedgerError(
                "correction must preserve the original Person, module, type and source"
            )
        if correction_reason is None or len(correction_reason.strip()) < 10:
            raise IncentiveLedgerError("correction requires an auditable reason")
    elif correction_reason is not None:
        raise IncentiveLedgerError("correction reason requires an original entry")

    entry = IncentiveLedgerEntry(
        id=uuid.uuid4(),
        organization_id=organization_id,
        person_id=person_id,
        module_key=module_key.value,
        incentive_type=incentive_type,
        amount=amount,
        label=label.strip() if label is not None else None,
        source_outcome_id=source_outcome_id,
        rule_ref=rule_ref.strip(),
        rule_sha256=rule_sha256,
        correction_of_entry_id=(correction.id if correction is not None else None),
        correction_reason=(
            correction_reason.strip() if correction_reason is not None else None
        ),
        created_by=created_by,
    )
    session.add(entry)
    session.flush()
    return entry
