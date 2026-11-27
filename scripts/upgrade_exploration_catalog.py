"""Publish only the eight owner-approved reference courses, preserving old work.

This is an explicit production operation, never an application startup seed.
Without --apply the CLI runs a read-only plan. APP_ENV is never changed. The
caller owns the transaction; all inserts and preservation checks are atomic.
Old formal journeys have different learning contracts and are not remapped to
these courses, completed on a learner's behalf, or rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import uuid

from sqlalchemy import select, text

import journey_api
from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.exploration_models import ExplorationCatalogTask, ExplorationMaterial
from journey_api.exploration_service import default_requirements, publication_command, publish_catalog
from journey_api.identity import add_audit
from journey_api.models import Organization, Role, RoleAssignment, TaskDefinition, TaskDefinitionStatus, TaskVersion, User, UserStatus
from journey_api.review_admin_access import permissions, require_super
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from journey_api.review_admin_routes import TaskContent, task_content_for_publish

TARGET_SCHEMA = "0064_profile_mall_points"
SEED_ROOT = Path(journey_api.__file__).resolve().parent
STABLE_KEYS = tuple(f"EXPLORATION-DYNAMIC-20261117-{index:02}" for index in range(1, 9))
NEW_TABLES = frozenset({"exploration_catalog_tasks", "exploration_work", "exploration_progress",
    "exploration_materials", "exploration_self_checks"})
INSERT_TABLES = frozenset({"task_definitions", "task_versions", "review_admin_tasks", "published_task_content", "audit_entries"})
VOLATILE_TABLES = frozenset({"worker_heartbeats", "directory_sync", "directory_members"})


def curriculum():
    raw = (SEED_ROOT / "exploration_seed.json").read_bytes()
    items = json.loads(raw.decode("utf-8-sig"))
    if len(items) != 8 or [item["completionMode"] for item in items] != ["learning"] * 6 + ["assessment", "checkin"]:
        raise ValueError("REFERENCE_CURRICULUM_CHANGED")
    if items[-1]["title"] != "培训签退" or any("测试" in item["title"] for item in items):
        raise ValueError("REFERENCE_CURRICULUM_CHANGED")
    qr = (SEED_ROOT / "exploration_checkout_qr.png").read_bytes()
    if not qr.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("INVALID_CHECKOUT_QR")
    return items, qr, hashlib.sha256(raw).hexdigest()


def authorized_author(session, organization_id, author_id, *, lock):
    user_query = select(User).where(User.id == author_id,
        User.organization_id == organization_id, User.status == UserStatus.ACTIVE)
    if lock:
        user_query = user_query.with_for_update()
    user = session.scalar(user_query.execution_options(populate_existing=True))
    roles = frozenset(session.scalars(select(RoleAssignment.role).where(
        RoleAssignment.user_id == author_id, RoleAssignment.organization_id == organization_id)))
    if user is None or Role.REVIEWER not in roles:
        raise ValueError("ACTIVE_REAL_REVIEWER_REQUIRED")
    actor = Actor(id=author_id, organization_id=organization_id, roles=roles,
                  display_name=user.display_name, entry_role=Role.REVIEWER)
    if lock:
        require_super(session, actor)
    elif not permissions(session, actor)["isSuperAdmin"]:
        raise ValueError("ACTIVE_SUPER_ADMIN_REQUIRED")
    return actor


def existing_course(session, organization_id, stable_key):
    definition = session.scalar(select(TaskDefinition).where(TaskDefinition.organization_id == organization_id,
        TaskDefinition.stable_key == stable_key))
    if definition is None:
        return None
    profile = session.get(ReviewAdminTask, definition.id)
    entry = session.get(ExplorationCatalogTask, definition.id)
    version = session.scalar(select(TaskVersion).where(TaskVersion.organization_id == organization_id,
        TaskVersion.task_definition_id == definition.id).order_by(TaskVersion.version.desc()).limit(1))
    published = session.get(PublishedTaskContent, version.id) if version else None
    if (not profile or profile.organization_id != organization_id or profile.content.get("camp") != "exploration"
            or not entry or entry.organization_id != organization_id or not published
            or published.organization_id != organization_id or published.content.get("camp") != "exploration"):
        raise ValueError("EXISTING_REFERENCE_COURSE_INCOMPLETE:" + stable_key)
    return definition


def existing_business_rows(session):
    """Keep row hashes in memory; never print submissions, identities or hashes.

    A multiset includes each row's primary key through to_jsonb. Original rows
    must survive byte-for-byte; only explicitly permitted tables may gain rows.
    New catalog positions can change as courses are inserted before sign-out.
    """
    tables = session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")).scalars()
    result = {}
    for table in tables:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", table):
            raise ValueError("INVALID_TABLE")
        # Alembic's revision changes during the additive migration itself;
        # it is schema metadata rather than a learner/business record.
        if table == "alembic_version" or table in NEW_TABLES | VOLATILE_TABLES:
            continue
        rows = session.execute(text(f'SELECT md5(to_jsonb(t)::text), count(*) FROM "{table}" t GROUP BY 1')).all()
        result[table] = Counter({digest: count for digest, count in rows})
    return result


def verify_preserved(before, after):
    if before.keys() != after.keys():
        raise ValueError("BUSINESS_SCHEMA_CHANGED")
    for table, original in before.items():
        actual = after[table]
        if original - actual or (table not in INSERT_TABLES and actual != original):
            raise ValueError("EXISTING_BUSINESS_RECORD_CHANGED:" + table)


def upgrade_catalog(session, organization_id, author_id, authorization_reference, *, apply=False):
    if not authorization_reference.strip() or len(authorization_reference) > 180:
        raise ValueError("OWNER_AUTHORIZATION_REFERENCE_REQUIRED")
    if list(session.execute(text("SELECT version_num FROM alembic_version")).scalars()) != [TARGET_SCHEMA]:
        raise ValueError("EXACT_SCHEMA_REQUIRED")
    actor = authorized_author(session, organization_id, author_id, lock=apply)
    if apply:
        # Serializes against the exact same organization boundary as publishing.
        session.scalar(select(Organization.id).where(Organization.id == organization_id).with_for_update())
    items, qr, seed_sha = curriculum()
    existing = [existing_course(session, organization_id, key) for key in STABLE_KEYS]
    result = {"mode": "apply" if apply else "plan", "schema": TARGET_SCHEMA,
        "organization_id": str(organization_id), "author_id": str(author_id), "seed_sha256": seed_sha,
        "qr_sha256": hashlib.sha256(qr).hexdigest(), "independent_review": False,
        "legacy_progress_rewritten": False, "inserted": [],
        "preserved": [str(row.id) for row in existing if row],
        "missing": [key for key, row in zip(STABLE_KEYS, existing) if row is None]}
    if not apply or not result["missing"]:
        result["business_records_preserved"] = True
        return result
    before = existing_business_rows(session)
    for index, (item, stable_key, found) in enumerate(zip(items, STABLE_KEYS, existing), 1):
        if found:
            continue
        task_id = uuid.uuid5(organization_id, stable_key)
        if session.get(TaskDefinition, task_id) is not None:
            raise ValueError("DETERMINISTIC_TASK_ID_COLLISION")
        materials, task_files = [], []
        if item.get("url"):
            materials.append(dict(id=f"material-{index}-1", name=item["materialTitle"], type="link", url=item["url"]))
        else:
            material_id = uuid.uuid5(organization_id, "exploration-checkout-qr-20261117")
            stored = session.get(ExplorationMaterial, material_id)
            qr_sha = hashlib.sha256(qr).hexdigest()
            if stored and (stored.organization_id != organization_id or stored.sha256 != qr_sha or stored.content != qr):
                raise ValueError("CHECKOUT_QR_ID_COLLISION")
            if not stored:
                session.add(ExplorationMaterial(id=material_id, organization_id=organization_id, uploaded_by=author_id,
                    name="exploration-checkout-qr.png", kind="image", mime="image/png", size=len(qr), sha256=qr_sha, content=qr))
            materials.append(dict(id=str(material_id), name=item["materialTitle"], type="image", mime="image/png",
                size=len(qr), url="exploration-material:" + str(material_id)))
        if item.get("assessmentUrl"):
            task_files.append(dict(id=f"material-{index}-assessment", name=item["assessmentTitle"],
                type="link", url=item["assessmentUrl"]))
        content = TaskContent(title=item["title"], summary=item["summary"], camp="exploration", order=index,
            completionMode=item["completionMode"], materials=materials, taskFiles=task_files,
            requirements=default_requirements(item["completionMode"], seed=True)).model_dump(mode="json")
        definition = TaskDefinition(id=task_id, organization_id=organization_id, created_by=actor.id,
            stable_key=stable_key, status=TaskDefinitionStatus.PUBLISHED, revision=1)
        session.add(definition)
        session.flush()
        profile = ReviewAdminTask(task_definition_id=task_id, organization_id=organization_id,
            revision=1, status="published", content=content)
        session.add(profile)
        # reviewed_by is a legacy required column. Record the direct publisher,
        # and explicitly disclose that no independent review was performed.
        command = publication_command(content, **task_content_for_publish(content), expected_revision=1,
            reviewed_by=actor.id, verified_material_urls=[])
        values = command.model_dump(mode="json", exclude={"expected_revision", "reviewed_by", "verified_material_urls"})
        values["content_source_notes"] = ["用户提供并授权上线的探索营参考课程。", "授权记录：" + authorization_reference,
            "超级管理员直接发布，未执行独立内容复核；未声称验证外部材料链接权限。"]
        values["reviewer_calibration_note"] = "超级管理员直接发布；无独立复核，不代表已完成 Reviewer 校准。"
        version = TaskVersion(id=uuid.uuid5(task_id, "published-v1"), organization_id=organization_id,
            task_definition_id=task_id, version=1, **values, learning_experience={},
            rubric_version=command.rubric.version, published_by=actor.id, reviewed_by=actor.id)
        session.add(version)
        session.flush()
        session.add(PublishedTaskContent(task_version_id=version.id, organization_id=organization_id, content=content))
        publish_catalog(session, definition, profile)
        add_audit(session, request_id="exploration-production-catalog-20261117", organization_id=organization_id,
            actor_id=actor.id, action="exploration.production_course_initialized", resource_type="task_definition",
            resource_id=task_id, result="SUCCESS", details={"stable_key": stable_key,
                "source": "owner-supplied-reference-curriculum", "authorization_reference": authorization_reference,
                "publication_policy": "super_admin_direct", "independent_review": False,
                "external_links_verified": False, "seed_sha256": seed_sha, "legacy_records_rewritten": False})
        result["inserted"].append(str(task_id))
    session.flush()
    verify_preserved(before, existing_business_rows(session))
    result["business_records_preserved"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=uuid.UUID, required=True)
    parser.add_argument("--author-id", type=uuid.UUID, required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal.begin() as session:
        if not args.apply:
            session.execute(text("SET TRANSACTION READ ONLY"))
        result = upgrade_catalog(session, args.organization_id, args.author_id, args.authorization_reference, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
