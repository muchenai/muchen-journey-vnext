#!/usr/bin/env python3
"""Bootstrap three controlled-Canary identities without exposing secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit


CANDIDATE = "5d2c42fdb9abdf4ca4e7756546fab99111f7c6c3"
CANARY_DATABASE = "journey_next_canary_20260901_c72fea5"
CONFIRMATION = "BOOTSTRAP_IDENTITIES_5D2C42F_PRODUCTION_CANARY"
_FIELDS = {
    "operator_user_id",
    "operator_display_name",
    "learner_user_id",
    "learner_display_name",
    "owner_user_id",
    "owner_display_name",
    "authorization_reference",
    "expires_in_minutes",
}
_AUTHORIZATION_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
_WP12B_ORGANIZATION_NAME = re.compile(
    r"^WP12B:wp12b-[1-9][0-9]{5,19}:org-[0-9]{3}$"
)


class BootstrapError(RuntimeError):
    def __init__(self, message: str, *, category: str = "BOOTSTRAP_REJECTED") -> None:
        super().__init__(message)
        self.category = category


REQUEST_CONTRACT_CATEGORY = "REQUEST_CONTRACT_REJECTED"
RUNTIME_CONTRACT_CATEGORY = "RUNTIME_CONTRACT_REJECTED"
IDENTITY_SECRET_CATEGORY = "IDENTITY_SECRET_REJECTED"
_INSECURE_IDENTITY_DEFAULTS = {
    "journey-next-local-session-secret-change-me",
    "journey-next-local-invite-secret-change-me",
    "journey-next-local-import-signing-key-change-me",
    "journey-next-local-identity-subject-secret",
}


def _uses_wp12b_namespace(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return normalized.startswith("wp12b:")


@dataclass(frozen=True)
class BootstrapRequest:
    operator_user_id: uuid.UUID
    operator_display_name: str
    learner_user_id: uuid.UUID
    learner_display_name: str
    owner_user_id: uuid.UUID
    owner_display_name: str
    authorization_reference: str
    expires_in_minutes: int


def _uuid_v4(value: object, field: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise BootstrapError(f"{field} must be UUIDv4") from error
    if parsed.version != 4:
        raise BootstrapError(f"{field} must be UUIDv4")
    return parsed


def _display_name(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise BootstrapError(f"{field} display name is invalid")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 120 or any(ord(char) < 32 for char in normalized):
        raise BootstrapError(f"{field} display name is invalid")
    return normalized


def parse_payload(payload: object) -> BootstrapRequest:
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise BootstrapError("bootstrap request fields differ")
    operator_id = _uuid_v4(payload["operator_user_id"], "operator_user_id")
    learner_id = _uuid_v4(payload["learner_user_id"], "learner_user_id")
    owner_id = _uuid_v4(payload["owner_user_id"], "owner_user_id")
    if len({operator_id, learner_id, owner_id}) != 3:
        raise BootstrapError("operator, learner, and owner user IDs must differ")
    operator_name = _display_name(payload["operator_display_name"], "operator")
    learner_name = _display_name(payload["learner_display_name"], "learner")
    owner_name = _display_name(payload["owner_display_name"], "owner")
    if len({operator_name, learner_name, owner_name}) != 3:
        raise BootstrapError("operator, learner, and owner display names must differ")
    authorization_reference = payload["authorization_reference"]
    if not isinstance(authorization_reference, str) or not _AUTHORIZATION_REFERENCE.fullmatch(
        authorization_reference
    ):
        raise BootstrapError("authorization reference must be a non-sensitive stable identifier")
    expires_in_minutes = payload["expires_in_minutes"]
    if isinstance(expires_in_minutes, bool) or not isinstance(expires_in_minutes, int):
        raise BootstrapError("bootstrap link lifetime must be 5-30 minutes")
    if not 5 <= expires_in_minutes <= 30:
        raise BootstrapError("bootstrap link lifetime must be 5-30 minutes")
    return BootstrapRequest(
        operator_user_id=operator_id,
        operator_display_name=operator_name,
        learner_user_id=learner_id,
        learner_display_name=learner_name,
        owner_user_id=owner_id,
        owner_display_name=owner_name,
        authorization_reference=authorization_reference,
        expires_in_minutes=expires_in_minutes,
    )


def parse_request(path: Path) -> BootstrapRequest:
    try:
        raw = sys.stdin.read() if str(path) == "-" else path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BootstrapError("bootstrap request is not valid JSON") from error
    return parse_payload(payload)


def parse_request_contract(path: Path) -> BootstrapRequest:
    """Parse the sealed request and expose only a stable failure category."""
    try:
        return parse_request(path)
    except BootstrapError as error:
        raise BootstrapError(
            "identity bootstrap request contract rejected",
            category=REQUEST_CONTRACT_CATEGORY,
        ) from error


def validate_runtime(
    database_url: str,
    *,
    app_env: str,
    release_marker: str,
    confirmation: str,
    database_kind: str = "source",
) -> None:
    if confirmation != CONFIRMATION:
        raise BootstrapError(f"confirmation must be {CONFIRMATION}")
    if app_env != "production" or release_marker != "PRODUCTION_CANARY_UAT":
        raise BootstrapError("identity bootstrap requires production Canary configuration")
    if not isinstance(database_url, str) or "\n" in database_url or "\r" in database_url:
        raise BootstrapError("Canary database URL is invalid")
    parsed = urlsplit(database_url)
    if parsed.scheme != "postgresql+psycopg" or parsed.hostname in {
        None,
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise BootstrapError("Canary database host is invalid")
    if parsed.username != "journey_next_migrator":
        raise BootstrapError("Canary database credentials are invalid")
    if database_kind != "canary" or parsed.path != f"/{CANARY_DATABASE}":
        raise BootstrapError("Canary database must be the exact isolated database")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("sslmode") != ["verify-full"]:
        raise BootstrapError("Canary database must use sslmode=verify-full")
    if query.get("sslrootcert") != ["/run/secrets/volcengine-rds-ca.pem"]:
        raise BootstrapError("Canary database CA path is invalid")


def validate_runtime_contract(
    database_url: str,
    *,
    app_env: str,
    release_marker: str,
    confirmation: str,
    database_kind: str = "source",
) -> None:
    """Validate runtime guards while suppressing implementation details."""
    try:
        validate_runtime(
            database_url,
            app_env=app_env,
            release_marker=release_marker,
            confirmation=confirmation,
            database_kind=database_kind,
        )
    except Exception as error:
        raise BootstrapError(
            "identity bootstrap runtime contract rejected",
            category=RUNTIME_CONTRACT_CATEGORY,
        ) from error


def validate_identity_secret(secret: object) -> None:
    """Validate the subject secret without ever returning or logging it."""
    if not isinstance(secret, str) or len(secret) < 32 or "\n" in secret or "\r" in secret:
        raise BootstrapError(
            "identity subject secret contract rejected",
            category=IDENTITY_SECRET_CATEGORY,
        )


def validate_identity_secret_set(
    *,
    identity_secret: object,
    session_secret: object,
    invite_secret: object,
    import_signing_key: object,
) -> None:
    """Mirror the application identity-secret contract without exposing values."""
    values = (identity_secret, session_secret, invite_secret, import_signing_key)
    if any(
        not isinstance(value, str)
        or len(value) < 32
        or "\n" in value
        or "\r" in value
        or value in _INSECURE_IDENTITY_DEFAULTS
        for value in values
    ) or len(set(values)) != len(values):
        raise BootstrapError(
            "identity secret set contract rejected",
            category=IDENTITY_SECRET_CATEGORY,
        )


def _contract_database_url(host: object, port: object, password: object) -> str:
    """Build the same target URL as the Canary bundle without writing a bundle."""
    if (
        not isinstance(host, str)
        or not re.fullmatch(r"[A-Za-z0-9.-]+", host)
        or host in {"localhost", "127.0.0.1"}
    ):
        raise BootstrapError(
            "Canary database host is invalid",
            category=RUNTIME_CONTRACT_CATEGORY,
        )
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise BootstrapError(
            "Canary database port is invalid",
            category=RUNTIME_CONTRACT_CATEGORY,
        )
    if not isinstance(password, str) or len(password) < 20 or "\n" in password or "\r" in password:
        raise BootstrapError(
            "Canary migration credential is invalid",
            category=RUNTIME_CONTRACT_CATEGORY,
        )
    return (
        "postgresql+psycopg://journey_next_migrator:"
        f"{quote(password, safe='')}@{host}:{port}/{CANARY_DATABASE}"
        "?sslmode=verify-full&sslrootcert=/run/secrets/volcengine-rds-ca.pem"
    )


def validate_application_settings_contract(
    settings: object,
    database_settings: object,
    *,
    confirmation: str,
    database_kind: str,
) -> None:
    """Validate loaded application settings without opening a database session."""
    try:
        database_url = settings.database_url
        app_env = settings.app_env
        release_marker = settings.release_marker
        identity_secret = settings.identity_subject_secret
        session_secret = settings.session_secret
        invite_secret = settings.invite_secret
        import_signing_key = settings.import_signing_key
        database_settings_url = database_settings.database_url
        db_pool_size = database_settings.db_pool_size
        db_max_overflow = database_settings.db_max_overflow
        db_pool_timeout_seconds = database_settings.db_pool_timeout_seconds
    except Exception as error:
        raise BootstrapError(
            "identity bootstrap runtime contract rejected",
            category=RUNTIME_CONTRACT_CATEGORY,
        ) from error
    validate_runtime_contract(
        database_url,
        app_env=app_env,
        release_marker=release_marker,
        confirmation=confirmation,
        database_kind=database_kind,
    )
    validate_identity_secret_set(
        identity_secret=identity_secret,
        session_secret=session_secret,
        invite_secret=invite_secret,
        import_signing_key=import_signing_key,
    )
    if database_settings_url != database_url or any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (db_pool_size, db_max_overflow, db_pool_timeout_seconds)
    ):
        raise BootstrapError(
            "identity bootstrap database settings contract rejected",
            category=RUNTIME_CONTRACT_CATEGORY,
        )
    if (
        not 1 <= db_pool_size <= 25
        or not 0 <= db_max_overflow <= 25
        or db_pool_size + db_max_overflow > 30
        or not 1 <= db_pool_timeout_seconds <= 30
    ):
        raise BootstrapError(
            "identity bootstrap database settings contract rejected",
            category=RUNTIME_CONTRACT_CATEGORY,
        )


def public_result(result: dict[str, object]) -> dict[str, object]:
    """Select the encrypted response fields; names and request material never leave the DB job."""
    fields = (
        "operator_user_id",
        "learner_user_id",
        "owner_user_id",
        "operator_roles",
        "owner_roles",
        "operator_link_id",
        "operator_link_start_path",
        "operator_link_expires_at",
        "expires_in_minutes",
    )
    return {field: result[field] for field in fields}


def bootstrap(session: object, request: BootstrapRequest, secret: str, now: datetime | None = None) -> dict[str, object]:
    """Create or exactly reuse the three controlled Canary identities."""
    validate_identity_secret(secret)
    # Imports stay inside the operation so request validation remains dependency-light and testable.
    from sqlalchemy import select

    from journey_api.identity import add_audit, utc_now
    from journey_api.models import Organization, Role, RoleAssignment, User, UserStatus
    from journey_api.wp09_bootstrap import (
        BootstrapError as OperatorLinkBootstrapError,
    )
    from journey_api.wp09_bootstrap import create_operator_link

    issued_at = now or utc_now()
    organizations = session.scalars(select(Organization)).all()
    malformed_wp12b_marker = any(
        _uses_wp12b_namespace(organization.name)
        and not _WP12B_ORGANIZATION_NAME.fullmatch(organization.name)
        for organization in organizations
    )
    business_organizations = [
        organization
        for organization in organizations
        if not _uses_wp12b_namespace(organization.name)
    ]
    if malformed_wp12b_marker or len(business_organizations) != 1:
        raise BootstrapError(
            "identity bootstrap organization topology is ambiguous",
            category="ORGANIZATION_TOPOLOGY_REJECTED",
        )
    organization = business_organizations[0]
    requested_user_ids = (
        request.operator_user_id,
        request.learner_user_id,
        request.owner_user_id,
    )
    existing_users = session.scalars(select(User).where(User.id.in_(requested_user_ids))).all()
    if existing_users and len(existing_users) != len(requested_user_ids):
        raise BootstrapError(
            "controlled identity state is partial",
            category="IDENTITY_STATE_REJECTED",
        )

    if existing_users:
        users_by_id = {user.id: user for user in existing_users}
        expected_user_ids = set(requested_user_ids)
        if set(users_by_id) != expected_user_ids:
            raise BootstrapError(
                "controlled identity state differs",
                category="IDENTITY_STATE_REJECTED",
            )
        expected_users = {
            request.operator_user_id: (
                organization.id,
                request.operator_display_name,
                UserStatus.ACTIVE,
            ),
            request.learner_user_id: (
                organization.id,
                request.learner_display_name,
                UserStatus.ACTIVE,
            ),
            request.owner_user_id: (
                organization.id,
                request.owner_display_name,
                UserStatus.ACTIVE,
            ),
        }
        if any(
            (
                users_by_id[user_id].organization_id,
                users_by_id[user_id].display_name,
                users_by_id[user_id].status,
            )
            != expected
            for user_id, expected in expected_users.items()
        ):
            raise BootstrapError(
                "controlled identity state differs",
                category="IDENTITY_STATE_REJECTED",
            )
        role_assignments = session.scalars(
            select(RoleAssignment).where(RoleAssignment.user_id.in_(requested_user_ids))
        ).all()
        actual_roles = {user_id: set() for user_id in requested_user_ids}
        for assignment in role_assignments:
            if (
                assignment.user_id not in actual_roles
                or assignment.organization_id != organization.id
            ):
                raise BootstrapError(
                    "controlled identity state differs",
                    category="IDENTITY_STATE_REJECTED",
                )
            actual_roles[assignment.user_id].add(assignment.role)
        expected_roles = {
            request.operator_user_id: {Role.OPERATOR, Role.REVIEWER},
            request.learner_user_id: set(),
            request.owner_user_id: {Role.LEARNER, Role.REVIEWER},
        }
        if actual_roles != expected_roles:
            raise BootstrapError(
                "controlled identity state differs",
                category="IDENTITY_STATE_REJECTED",
            )
        operator = users_by_id[request.operator_user_id]
        learner = users_by_id[request.learner_user_id]
        owner = users_by_id[request.owner_user_id]
    else:
        operator = User(
            id=request.operator_user_id,
            organization_id=organization.id,
            display_name=request.operator_display_name,
            status=UserStatus.ACTIVE,
        )
        learner = User(
            id=request.learner_user_id,
            organization_id=organization.id,
            display_name=request.learner_display_name,
            status=UserStatus.ACTIVE,
        )
        owner = User(
            id=request.owner_user_id,
            organization_id=organization.id,
            display_name=request.owner_display_name,
            status=UserStatus.ACTIVE,
        )
        session.add_all([operator, learner, owner])
        session.flush()
        session.add_all(
            [
                RoleAssignment(
                    id=uuid.uuid4(), organization_id=organization.id, user_id=operator.id, role=Role.OPERATOR
                ),
                RoleAssignment(
                    id=uuid.uuid4(), organization_id=organization.id, user_id=operator.id, role=Role.REVIEWER
                ),
                RoleAssignment(
                    id=uuid.uuid4(), organization_id=organization.id, user_id=owner.id, role=Role.LEARNER
                ),
                RoleAssignment(
                    id=uuid.uuid4(), organization_id=organization.id, user_id=owner.id, role=Role.REVIEWER
                ),
            ]
        )
        add_audit(
            session,
            request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
            organization_id=organization.id,
            action="identity.bootstrap_operator_created",
            resource_type="user",
            resource_id=operator.id,
            result="SUCCESS",
            details={"roles": [Role.OPERATOR.value, Role.REVIEWER.value], "authorization_reference": request.authorization_reference},
        )
        add_audit(
            session,
            request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
            organization_id=organization.id,
            action="identity.bootstrap_learner_target_created",
            resource_type="user",
            resource_id=learner.id,
            result="SUCCESS",
            details={"status": UserStatus.ACTIVE.value, "role_assignment": False, "authorization_reference": request.authorization_reference},
        )
        add_audit(
            session,
            request_id=f"wp31-identity-bootstrap:{uuid.uuid4()}",
            organization_id=organization.id,
            action="identity.bootstrap_owner_created",
            resource_type="user",
            resource_id=owner.id,
            result="SUCCESS",
            details={"roles": [Role.LEARNER.value, Role.REVIEWER.value], "authorization_reference": request.authorization_reference},
        )
    try:
        link = create_operator_link(
            session,
            target_user_id=operator.id,
            secret=secret,
            authorization_reference=request.authorization_reference,
            expires_in_minutes=request.expires_in_minutes,
            now=issued_at,
        )
    except OperatorLinkBootstrapError as error:
        raise BootstrapError(
            "operator link bootstrap was rejected",
            category="OPERATOR_LINK_REJECTED",
        ) from error
    return public_result(
        {
            "operator_user_id": str(operator.id),
            "learner_user_id": str(learner.id),
            "owner_user_id": str(owner.id),
            "owner_roles": [Role.LEARNER.value, Role.REVIEWER.value],
            "operator_roles": [Role.OPERATOR.value, Role.REVIEWER.value],
            "operator_link_id": link["link_id"],
            "operator_link_start_path": link["start_path"],
            "operator_link_expires_at": link["expires_at"],
            "expires_in_minutes": request.expires_in_minutes,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--database-kind", choices=("canary",), default="canary")
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument(
        "--settings-check",
        action="store_true",
        help="load application settings but do not open a database session",
    )
    parser.add_argument("--rds-host")
    parser.add_argument("--rds-port", type=int)
    args = parser.parse_args()
    try:
        request = parse_request_contract(args.request)
        if args.settings_check and not args.contract_only:
            raise BootstrapError(
                "settings check requires contract-only mode",
                category=RUNTIME_CONTRACT_CATEGORY,
            )
        if args.contract_only:
            if args.settings_check:
                if args.rds_host is not None or args.rds_port is not None:
                    raise BootstrapError(
                        "settings check cannot combine with raw RDS coordinates",
                        category=RUNTIME_CONTRACT_CATEGORY,
                    )
                validate_identity_secret_set(
                    identity_secret=os.environ.get(
                        "IDENTITY_SUBJECT_SECRET",
                        os.environ.get("WP09_IDENTITY_SUBJECT_SECRET", ""),
                    ),
                    session_secret=os.environ.get("SESSION_SECRET", ""),
                    invite_secret=os.environ.get("INVITE_SECRET", ""),
                    import_signing_key=os.environ.get("IMPORT_SIGNING_KEY", ""),
                )
                try:
                    from journey_api.config import get_database_settings, get_settings

                    settings = get_settings()
                    database_settings = get_database_settings()
                except Exception as error:
                    raise BootstrapError(
                        "identity bootstrap runtime contract rejected",
                        category=RUNTIME_CONTRACT_CATEGORY,
                    ) from error
                validate_application_settings_contract(
                    settings,
                    database_settings,
                    confirmation=args.confirm,
                    database_kind=args.database_kind,
                )
            else:
                if (args.rds_host is None) != (args.rds_port is None):
                    raise BootstrapError(
                        "Canary database coordinates are incomplete",
                        category=RUNTIME_CONTRACT_CATEGORY,
                    )
                if args.rds_host is not None:
                    database_url = _contract_database_url(
                        args.rds_host,
                        args.rds_port,
                        os.environ.get("WP08_MIGRATION_DB_PASSWORD", ""),
                    )
                    validate_identity_secret_set(
                        identity_secret=os.environ.get("WP09_IDENTITY_SUBJECT_SECRET", ""),
                        session_secret=os.environ.get("WP15_SESSION_SECRET", ""),
                        invite_secret=os.environ.get("WP15_INVITE_SECRET", ""),
                        import_signing_key=os.environ.get("WP15_IMPORT_SIGNING_KEY", ""),
                    )
                    identity_secret = os.environ.get("WP09_IDENTITY_SUBJECT_SECRET", "")
                    app_env = "production"
                    release_marker = "PRODUCTION_CANARY_UAT"
                else:
                    database_url = os.environ.get("DATABASE_URL", "")
                    identity_secret = os.environ.get(
                        "IDENTITY_SUBJECT_SECRET",
                        os.environ.get("WP09_IDENTITY_SUBJECT_SECRET", ""),
                    )
                    app_env = os.environ.get("APP_ENV", "")
                    release_marker = os.environ.get("RELEASE_MARKER", "")
                validate_runtime_contract(
                    database_url,
                    app_env=app_env,
                    release_marker=release_marker,
                    confirmation=args.confirm,
                    database_kind=args.database_kind,
                )
                validate_identity_secret(identity_secret)
            print(
                json.dumps(
                    {
                        "identity_contract_probe": "PASS",
                        "request_contract": "PASS",
                        "runtime_contract": "PASS",
                        "identity_secret_contract": "PASS",
                        "request_field_count": len(_FIELDS),
                        "request_identity_count": 3,
                    },
                    separators=(",", ":"),
                )
            )
            return 0

        validate_identity_secret_set(
            identity_secret=os.environ.get("IDENTITY_SUBJECT_SECRET", ""),
            session_secret=os.environ.get("SESSION_SECRET", ""),
            invite_secret=os.environ.get("INVITE_SECRET", ""),
            import_signing_key=os.environ.get("IMPORT_SIGNING_KEY", ""),
        )
        try:
            from journey_api.config import get_database_settings, get_settings

            settings = get_settings()
            database_settings = get_database_settings()
        except Exception as error:
            raise BootstrapError(
                "identity bootstrap runtime contract rejected",
                category=RUNTIME_CONTRACT_CATEGORY,
            ) from error
        validate_application_settings_contract(
            settings,
            database_settings,
            confirmation=args.confirm,
            database_kind=args.database_kind,
        )

        from journey_api.db import SessionLocal

        with SessionLocal() as session:
            result = bootstrap(session, request, settings.identity_subject_secret)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except BootstrapError as error:
        print(
            f"WP31_IDENTITY_BOOTSTRAP=FAIL category={error.category}",
            file=sys.stderr,
        )
        return 2
    except Exception:
        # This privileged job must never put SQL parameters, identity data, or
        # infrastructure details from an unexpected exception into Actions logs.
        print(
            "WP31_IDENTITY_BOOTSTRAP=FAIL category=BOOTSTRAP_RUNTIME_REJECTED",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
