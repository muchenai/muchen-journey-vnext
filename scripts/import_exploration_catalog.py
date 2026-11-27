"""Explicit, rerunnable import of the owner-supplied exploration curriculum.

Only missing seed stable keys are inserted. Existing tasks, submissions,
reviews, enrollments and administrator edits are never rewritten.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path
from sqlalchemy import select
from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.exploration_models import ExplorationMaterial
from journey_api.exploration_service import default_requirements, publication_command, publish_catalog
from journey_api.identity import add_audit
from journey_api.models import Role, RoleAssignment, TaskDefinition, TaskDefinitionStatus, TaskVersion, User, UserStatus
from journey_api.review_admin_access import require_super
from journey_api.review_admin_models import PublishedTaskContent, ReviewAdminTask
from journey_api.review_admin_routes import TaskContent, task_content_for_publish

SEED_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api" / "journey_api"


def import_catalog(session, organization_id, author_id, reviewer_id):
    from journey_api.config import get_settings
    if get_settings().app_env not in {"local", "test"}:
        raise ValueError("The owner-authorized curriculum import is restricted to local/test environments.")
    users = {user.id: user for user in session.scalars(select(User).where(User.organization_id == organization_id,
        User.id.in_([author_id, reviewer_id]), User.status == UserStatus.ACTIVE))}
    if author_id not in users or reviewer_id not in users:
        raise ValueError("Author and reviewer must be active users in the selected organization.")
    roles = set(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == author_id,
        RoleAssignment.organization_id == organization_id)))
    reviewer_roles = set(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == reviewer_id,
        RoleAssignment.organization_id == organization_id)))
    if Role.REVIEWER not in roles or Role.REVIEWER not in reviewer_roles:
        raise ValueError("The task author and content reviewer must have the real Reviewer role.")
    actor = Actor(id=author_id, organization_id=organization_id, roles=frozenset(roles),
                  display_name=users[author_id].display_name, entry_role=Role.REVIEWER)
    require_super(session, actor)
    items = json.loads((SEED_ROOT / "exploration_seed.json").read_text(encoding="utf-8-sig"))
    inserted, preserved = [], []
    for index, item in enumerate(items, 1):
        stable_key = f"EXPLORATION-DYNAMIC-20261117-{index:02}"
        existing = session.scalar(select(TaskDefinition.id).where(TaskDefinition.organization_id == organization_id,
            TaskDefinition.stable_key == stable_key))
        if existing:
            preserved.append(str(existing))
            continue
        task_id = uuid.uuid5(organization_id, stable_key)
        materials = []
        if item.get("url"):
            materials.append(dict(id=f"material-{index}-1", name=item["materialTitle"], type="link", url=item["url"]))
        elif item.get("assetPath"):
            raw = (SEED_ROOT / "exploration_checkout_qr.png").read_bytes()
            file_id = uuid.uuid5(organization_id, "exploration-checkout-qr-20261117")
            if not session.get(ExplorationMaterial, file_id):
                session.add(ExplorationMaterial(id=file_id, organization_id=organization_id, uploaded_by=author_id,
                    name="exploration-checkout-qr.png", kind="image", mime="image/png", size=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(), content=raw))
            materials.append(dict(id=str(file_id), name=item["materialTitle"], type="image", mime="image/png",
                size=len(raw), url="exploration-material:" + str(file_id)))
        if item.get("assessmentUrl"):
            materials.append(dict(id=f"material-{index}-assessment", name=item["assessmentTitle"], type="link", url=item["assessmentUrl"]))
        data = TaskContent(title=item["title"], summary=item["summary"], camp="exploration", order=index,
            completionMode=item["completionMode"], assessmentUrl=item.get("assessmentUrl", ""), materials=materials,
            requirements=default_requirements(item["completionMode"], seed=True)).model_dump(mode="json")
        definition = TaskDefinition(id=task_id, organization_id=organization_id, created_by=author_id,
            stable_key=stable_key, status=TaskDefinitionStatus.PUBLISHED, revision=1)
        session.add(definition)
        session.flush()
        profile = ReviewAdminTask(task_definition_id=task_id, organization_id=organization_id,
            revision=1, status="published", content=data)
        session.add(profile)
        command = publication_command(data, **task_content_for_publish(data), expected_revision=1, reviewed_by=reviewer_id,
            verified_material_urls=[material["url"] for material in materials if material["type"] == "link"])
        values = command.model_dump(mode="json", exclude={"expected_revision", "reviewed_by", "verified_material_urls"})
        values["content_source_notes"] = ["用户授权本地导入参考课程，尚未执行独立人工内容复核。"]
        values["reviewer_calibration_note"] = "用户授权本地导入参考课程，尚未执行独立人工内容复核。"
        version = TaskVersion(id=uuid.uuid4(), organization_id=organization_id, task_definition_id=task_id,
            version=1, **values, learning_experience={}, rubric_version=command.rubric.version,
            published_by=author_id, reviewed_by=reviewer_id)
        session.add(version)
        session.flush()
        session.add(PublishedTaskContent(task_version_id=version.id, organization_id=organization_id, content=data))
        publish_catalog(session, definition, profile)
        add_audit(session, request_id="exploration-seed-20261117", organization_id=organization_id,
            actor_id=author_id, action="exploration.seed_imported", resource_type="task_definition", resource_id=task_id,
            result="SUCCESS", details={"stable_key": stable_key, "reviewed_by": str(reviewer_id), "source": "owner-supplied-curriculum"})
        inserted.append(str(task_id))
    return dict(inserted=inserted, preserved=preserved)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=uuid.UUID, required=True)
    parser.add_argument("--author-id", type=uuid.UUID, required=True)
    parser.add_argument("--reviewer-id", type=uuid.UUID, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        result = import_catalog(session, args.organization_id, args.author_id, args.reviewer_id)
        session.commit()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
