from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping


POLICY_DOMAIN = b"muchen-journey-policy-snapshot.v1\n"
SCOPE_DOMAIN = b"muchen-journey-controlled-task-authorization-scope.v1\n"
POLICY_KEYS = frozenset(
    {
        "policy_schema",
        "policy_version",
        "training_purpose",
        "allowed_input_schema_ref",
        "data_classification",
        "deidentification_rule_ref",
        "production_isolation_rule_ref",
        "production_actions_allowed",
        "production_credential_allowed",
        "prohibited_action_codes",
        "learner_visibility",
        "reviewer_visibility",
        "operator_visibility",
        "reviewer_substitution_rule_ref",
        "evidence_retention_days",
        "evidence_disposition",
        "help_escalation_ref",
    }
)
SET_ARRAY_KEYS = frozenset(
    {
        "prohibited_action_codes",
        "learner_visibility",
        "reviewer_visibility",
        "operator_visibility",
    }
)


class ControlledTaskContractError(ValueError):
    pass


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ControlledTaskContractError("canonical contract forbids floating-point values")
    if isinstance(value, list):
        return [_nfc(item) for item in value]
    if isinstance(value, tuple):
        return [_nfc(item) for item in value]
    if isinstance(value, Mapping):
        return {_nfc(str(key)): _nfc(item) for key, item in value.items()}
    raise ControlledTaskContractError("canonical contract contains an unsupported value")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    normalized = _nfc(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_policy_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if set(snapshot) != POLICY_KEYS:
        raise ControlledTaskContractError("policy snapshot keys do not match v1")
    normalized = _nfc(snapshot)
    if normalized["policy_schema"] != "muchen-journey-controlled-task-policy.v1":
        raise ControlledTaskContractError("policy snapshot schema is not v1")
    if normalized["production_actions_allowed"] is not False:
        raise ControlledTaskContractError("policy cannot allow production actions")
    if normalized["production_credential_allowed"] is not False:
        raise ControlledTaskContractError("policy cannot allow production credentials")
    if not isinstance(normalized["evidence_retention_days"], int) or normalized[
        "evidence_retention_days"
    ] <= 0:
        raise ControlledTaskContractError("policy retention must be a positive integer")
    if normalized["evidence_disposition"] not in {"DELETE", "ARCHIVE"}:
        raise ControlledTaskContractError("policy evidence disposition is invalid")
    for key in SET_ARRAY_KEYS:
        values = normalized[key]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item.strip() for item in values)
            or len(set(values)) != len(values)
        ):
            raise ControlledTaskContractError(f"policy set {key} is invalid")
        normalized[key] = sorted(values)
    return normalized


def policy_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    canonical = canonical_policy_snapshot(snapshot)
    return hashlib.sha256(POLICY_DOMAIN + canonical_json_bytes(canonical)).hexdigest()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ControlledTaskContractError("authorization time must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def authorization_scope_document(
    *,
    organization_id: uuid.UUID,
    authorized_project_ref: str,
    target_journey_version_id: uuid.UUID,
    target_journey_stage_version_id: uuid.UUID,
    task_version_id: uuid.UUID,
    task_version_sha256: str,
    authorization_version: int,
    project_owner_user_id: uuid.UUID,
    newcomer_operations_owner_user_id: uuid.UUID,
    data_security_owner_user_id: uuid.UUID,
    reviewer_owner_user_id: uuid.UUID,
    primary_reviewer_user_id: uuid.UUID,
    backup_reviewer_user_id: uuid.UUID,
    policy_snapshot_ref: str,
    policy_snapshot_version: str,
    policy_snapshot_sha256: str,
    policy_evidence_ref: str,
    policy_evidence_sha256: str,
    valid_from: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "organization_id": str(organization_id),
        "authorization_scope": "NEWCOMER_CONTROLLED_TRAINING",
        "authorized_project_ref": unicodedata.normalize("NFC", authorized_project_ref),
        "target_journey_version_id": str(target_journey_version_id),
        "target_journey_stage_version_id": str(target_journey_stage_version_id),
        "task_version_id": str(task_version_id),
        "task_version_sha256": task_version_sha256,
        "authorization_version": authorization_version,
        "project_owner_user_id": str(project_owner_user_id),
        "newcomer_operations_owner_user_id": str(newcomer_operations_owner_user_id),
        "data_security_owner_user_id": str(data_security_owner_user_id),
        "reviewer_owner_user_id": str(reviewer_owner_user_id),
        "primary_reviewer_user_id": str(primary_reviewer_user_id),
        "backup_reviewer_user_id": str(backup_reviewer_user_id),
        "policy_snapshot_ref": unicodedata.normalize("NFC", policy_snapshot_ref),
        "policy_snapshot_version": unicodedata.normalize("NFC", policy_snapshot_version),
        "policy_snapshot_sha256": policy_snapshot_sha256,
        "policy_evidence_ref": unicodedata.normalize("NFC", policy_evidence_ref),
        "policy_evidence_sha256": policy_evidence_sha256,
        "valid_from": _utc_text(valid_from),
        "expires_at": _utc_text(expires_at),
    }


def authorization_scope_sha256(**values: Any) -> str:
    return hashlib.sha256(
        SCOPE_DOMAIN + canonical_json_bytes(authorization_scope_document(**values))
    ).hexdigest()
