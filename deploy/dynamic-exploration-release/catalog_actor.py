"""Read-only configured-publisher check, shared before transfer and activation.

The standalone entry point runs inside the existing production API container.
It creates no container, changes no role and makes no external provider call.
Only the established production database receives read-only SQL queries.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import uuid

ROOT = Path("/srv/journey-next-production/canary")
API_BASE = "ef06970c1658f8d583bdaf9bd3a4fd90c13fdc49"  # gitleaks:allow -- public Git revision, not a credential.
WEB_BASE = "ca69b1e3d9afacc9bf175a8c7bd40f81a8b03329"
SOURCE_SCHEMA = "0056_guild_halls"
PROJECT = "journey-next-greenfield-canary"
SUCCESS = "CURRICULUM_ACTOR_VERIFIED"


class ActorPreflightError(RuntimeError):
    """Fixed failure category without production values or provider errors."""


def require(value, category):
    if not value:
        raise ActorPreflightError(category)


def actor_probe(organization=None, author=None):
    for value in (organization, author):
        if value is not None:
            require(str(uuid.UUID(value)) == value, "CURRICULUM_IDENTITY_CONFIG")
    # Reading settings loads the same UUIDs used by enrollment. Supplying exact
    # UUIDs additionally binds the activation check to its receipt-backed env.
    return "EXPECTED_ORG=" + repr(organization) + "; EXPECTED_AUTHOR=" + repr(author) + "\n" + r'''
import uuid
from sqlalchemy import select, text
from journey_api.config import get_settings
from journey_api.db import SessionLocal
from journey_api.models import User, UserStatus, RoleAssignment, Role
from journey_api.review_admin_models import ReviewAdminAccess
s = get_settings()
assert s.app_env == 'production' and not s.allow_fixture_identity
organization = s.feishu_learner_organization_id
author = s.feishu_learner_reviewer_id
assert organization is not None and author is not None, 'CURRICULUM_IDENTITY_CONFIG'
assert EXPECTED_ORG is None or organization == uuid.UUID(EXPECTED_ORG)
assert EXPECTED_AUTHOR is None or author == uuid.UUID(EXPECTED_AUTHOR)
with SessionLocal() as session:
    session.execute(text('SET TRANSACTION READ ONLY'))
    assert session.execute(text('SHOW transaction_read_only')).scalar_one() == 'on'
    assert session.execute(text('SELECT current_database()')).scalar_one() == 'journey_next_canary_20260901_c72fea5'
    assert list(session.execute(text('SELECT version_num FROM alembic_version')).scalars()) == ['0056_guild_halls']
    actor = session.scalar(select(User.id).join(ReviewAdminAccess, ReviewAdminAccess.user_id == User.id)
        .join(RoleAssignment, RoleAssignment.user_id == User.id).where(User.id == author,
            User.organization_id == organization, User.status == UserStatus.ACTIVE,
            ReviewAdminAccess.organization_id == organization, ReviewAdminAccess.access_role == 'super_admin',
            ReviewAdminAccess.revoked_at.is_(None), RoleAssignment.organization_id == organization,
            RoleAssignment.role == Role.REVIEWER))
print('CURRICULUM_ACTOR_VERIFIED' if actor is not None else 'CURRICULUM_CONFIGURED_AUTHOR_NOT_SUPERADMIN')
'''


def command(args, *, timeout=60):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ActorPreflightError("CURRICULUM_ACTOR_PREFLIGHT_TIMEOUT") from None
    require(result.returncode == 0, "CURRICULUM_ACTOR_PREFLIGHT_COMMAND_FAILED")
    return result.stdout


def preflight():
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    require(socket.gethostname() == "journey-next-staging", "UNEXPECTED_HOST")
    require(ROOT.resolve() == ROOT, "ROOT_SYMLINK")
    base = ROOT / "releases" / (WEB_BASE + "-learner-usability")
    current = ROOT / "current"
    require(current.is_symlink() and current.resolve(strict=True) == base and base.resolve() == base,
            "CURRICULUM_ACTOR_BASE_CHANGED")
    name = PROJECT + "-api-1"
    rows = json.loads(command(["docker", "inspect", name]))
    require(len(rows) == 1, "CURRICULUM_ACTOR_API_MISSING")
    api = rows[0]
    labels = api["Config"].get("Labels") or {}
    require(labels.get("com.docker.compose.project") == PROJECT
            and labels.get("com.docker.compose.service") == "api"
            and labels.get("org.opencontainers.image.revision") == API_BASE,
            "CURRICULUM_ACTOR_API_REVISION")
    require(api["State"]["Running"] and api["State"].get("Health", {}).get("Status") == "healthy",
            "CURRICULUM_ACTOR_API_UNHEALTHY")
    values = dict(pair.split("=", 1) for pair in api["Config"]["Env"])
    require(values.get("APP_RELEASE") == API_BASE, "CURRICULUM_ACTOR_API_RELEASE")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", api["Image"]), "CURRICULUM_ACTOR_API_IMAGE")
    # Use the inspected immutable container ID to avoid a name-replacement race.
    probe = command(["docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
        "-e", "REQUIRE_READ_ONLY=true", api["Id"], "python", "-c", actor_probe()])
    require(probe.strip() == SUCCESS.encode(), "CURRICULUM_CONFIGURED_AUTHOR_NOT_SUPERADMIN")
    print(json.dumps({"step": "CURRICULUM_ACTOR_PREFLIGHT", "result": "PASS", "read_only": True}), flush=True)


if __name__ == "__main__":
    try:
        preflight()
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) if isinstance(error, ActorPreflightError) else "CURRICULUM_ACTOR_PREFLIGHT_FAILED"
        print(json.dumps({"step": "CURRICULUM_ACTOR_PREFLIGHT", "result": "STOP", "category": reason}), flush=True)
        raise SystemExit(1)
