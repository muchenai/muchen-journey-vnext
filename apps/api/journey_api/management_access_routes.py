"""Staff-authenticated course permissions and auditable training XP grants."""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from journey_api.academy_routes import TAGS, require_staff_entry
from journey_api.auth import Actor, get_actor
from journey_api.db import get_db
from journey_api.experience_permissions import (
    ISSUER_CHANGE, eligible_issuer_ids, issuer_history, issuer_names, require_issuer,
    require_issuer_configurator, settings_for,
)
from journey_api.management_access import fail
from journey_api.management_access_models import CourseManagementSettings, ExperienceRosterSnapshot, OfflineExperienceGrant
from journey_api.models import CompletionCode, ExternalIdentity, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_routes import audit, cached_directory_profiles, directory_for, directory_subject, envelope

router = APIRouter(prefix="/api/v1/ops", dependencies=[Depends(require_staff_entry)])
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
MAX_SAFE_INTEGER = 2**53 - 1


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetIssuers(Command):
    action: Literal["configure"]
    revision: int = Field(ge=0, strict=True)
    issuers: list[uuid.UUID | None] = Field(min_length=2, max_length=2)


class MatchNames(Command):
    names: list[Name] = Field(min_length=1, max_length=1000)


class GrantRow(Command):
    learnerId: uuid.UUID
    name: Name | None = None
    xp: int | None = Field(default=None, gt=0, le=MAX_SAFE_INTEGER, strict=True)
    points: int | None = Field(default=None, gt=0, le=MAX_SAFE_INTEGER // 10, strict=True)


class Grant(Command):
    action: Literal["grant"]
    mode: Literal["single", "list"]
    batch: Name
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
    rows: list[GrantRow] = Field(min_length=1, max_length=1000)
    snapshotId: uuid.UUID | None = None


@router.get("/experience/permissions")
def read_issuer_settings(request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer_configurator(session, actor)
    state = settings_for(session, actor)
    slots = state.issuers if state else []
    revision = state.revision if state else 0
    ids = [uuid.UUID(value) for value in slots if value]
    names = dict(session.execute(select(User.id, User.display_name).where(User.id.in_(ids),
        User.organization_id == actor.organization_id)).all()) if ids else {}
    profiles = cached_directory_profiles(session, actor, list(names))
    eligible = eligible_issuer_ids(session, actor.organization_id, ids)
    selected = []
    for pid in ids:
        profile = profiles.get(pid) or {}
        selected.append({"id": str(pid), "name": profile.get("name") or names.get(pid, "已失效成员"),
            "employeeNo": profile.get("employee_no") or "", "hasManagementAccess": pid in eligible})
    return envelope(request, {"revision": revision, "issuers": slots, "selected": selected,
                              "history": issuer_history(session, actor.organization_id, revision)})


@router.get("/experience/permissions/search")
def search_issuer_candidates(request: Request, q: str=Query(min_length=1,max_length=60),
                            actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer_configurator(session, actor)
    if not q.strip():
        fail("请输入成员姓名或工号。")
    result = directory_for(actor).search(q.strip())
    subjects = {p["open_id"]: directory_subject(p["open_id"]) for p in result["items"]}
    bound = dict(session.execute(select(ExternalIdentity.subject, ExternalIdentity.user_id).where(
        ExternalIdentity.provider == "FEISHU", ExternalIdentity.organization_id == actor.organization_id,
        ExternalIdentity.revoked_at.is_(None), ExternalIdentity.subject.in_(subjects.values()))).all()) if subjects else {}
    eligible = eligible_issuer_ids(session, actor.organization_id, list(bound.values()))
    items = []
    for profile in result["items"]:
        open_id = profile["open_id"]
        pid = bound.get(subjects[open_id])
        items.append({"id": str(pid) if pid else None, "openId": open_id, "name": profile["name"],
            "employeeNo": profile.get("employee_no") or "", "hasManagementAccess": pid in eligible,
            "avatar": profile.get("avatar") or "", "jobTitle": profile.get("job_title") or "",
            "departments": profile.get("departments") or [], "departmentPaths": profile.get("department_paths") or []})
    return envelope(request, {**result, "items": items})


@router.post("/experience/permissions")
def configure_issuers(body: SetIssuers, request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer_configurator(session, actor)
    row = settings_for(session, actor, lock=True)
    if (row.revision if row else 0) != body.revision:
        fail("配置已被更新，请重新打开后再保存。", 409)
    occupied = [pid for pid in body.issuers if pid is not None]
    if len(set(occupied)) != len(occupied):
        fail("请选择两位不同的发放管理员。")
    eligible = eligible_issuer_ids(session, actor.organization_id, occupied)
    for pid in occupied:
        if pid not in eligible:
            name = session.scalar(select(User.display_name).where(User.id == pid, User.organization_id == actor.organization_id))
            if name:
                fail(f"「{name}」尚未开通管理系统访问权限。请先在「成员认证」中为其开通权限")
            fail("所选成员已失效，请重新搜索选择。")
    before = list(row.issuers) if row and row.issuers else [None, None]
    after = [str(pid) if pid else None for pid in body.issuers]
    if before == after:
        return envelope(request, {"configured": True})
    names = issuer_names(session, actor.organization_id, {pid for pid in before + after if pid})
    names[str(actor.id)] = actor.display_name
    if row is None:
        row = CourseManagementSettings(organization_id=actor.organization_id, revision=0, assignments={}, tags=list(TAGS))
        session.add(row)
    row.issuers = after
    row.revision += 1
    audit(session, request, actor, ISSUER_CHANGE, actor.organization_id, {
        "revision": row.revision, "beforeIssuers": before, "issuers": after, "names": names,
    })
    session.commit()
    return envelope(request, {"configured": True})


def learner_directory(session, actor, only=None):
    query = select(User).join(RoleAssignment, RoleAssignment.user_id == User.id).where(
        User.organization_id == actor.organization_id, User.status == UserStatus.ACTIVE,
        RoleAssignment.organization_id == actor.organization_id, RoleAssignment.role == Role.LEARNER)
    if only is not None:
        query = query.where(User.id.in_(only))
    users = session.scalars(query.order_by(User.display_name, User.id)).all()
    profiles = cached_directory_profiles(session, actor, [u.id for u in users])
    people = []
    for user in users:
        profile = profiles.get(user.id) or {}
        people.append({"id": str(user.id), "name": profile.get("name") or user.display_name,
                       "department": "、".join(profile.get("department_paths") or profile.get("departments") or []),
                       "detail": profile.get("employee_no") or ""})
    return people


@router.get("/experience")
def read_experience(request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer(session, actor)
    query = select(OfflineExperienceGrant).where(OfflineExperienceGrant.organization_id == actor.organization_id
        ).order_by(OfflineExperienceGrant.created_at.desc(), OfflineExperienceGrant.id.desc())
    view = {"current": {"id": str(actor.id), "name": actor.display_name}, "canGrant": True,
        "learners": learner_directory(session, actor),
        "grants": [{**g.content, "id": str(g.id), "batch": g.batch, "reason": g.reason, "xp": g.xp,
            "points": g.points, "time": g.created_at.isoformat()} for g in session.scalars(query)]}
    return envelope(request, view)


@router.post("/experience/directory")
def match_directory(body: MatchNames, request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer(session, actor, lock=True)
    names = list(dict.fromkeys(body.names))
    groups = {name: [] for name in names}
    for person in learner_directory(session, actor):
        if person["name"] in groups:
            groups[person["name"]].append(person)
    recipients = {}
    for people in groups.values():
        labels = [(p["department"], p["detail"]) for p in people]
        for person, label in zip(people, labels):
            if labels.count(label) > 1:
                person["indistinguishable"] = True
            else:
                recipients[person["id"]] = person["name"]
    now = datetime.now(UTC)
    session.execute(delete(ExperienceRosterSnapshot).where(ExperienceRosterSnapshot.expires_at <= now))
    snapshot = ExperienceRosterSnapshot(organization_id=actor.organization_id, actor_id=actor.id,
        recipients=recipients, expires_at=now + timedelta(minutes=30))
    session.add(snapshot)
    session.flush()
    result = {"source":"local", "sourceLabel":"本地学员及已绑定的飞书成员", "snapshotId":str(snapshot.id),
              "matches":[{"name":name, "candidates":people} for name, people in groups.items()]}
    session.commit()
    return envelope(request, result)


@router.post("/experience")
def change_experience(body: Grant, request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_issuer(session, actor, lock=True)
    result = issue_grants(session, actor, body)
    audit(session, request, actor, "experience.granted", actor.organization_id, result)
    session.commit()
    return envelope(request, result)


def issue_grants(session, actor, body):
    ids = [r.learnerId for r in body.rows]
    if len(set(ids)) != len(ids):
        fail("同一名单中不能重复发放给同一位学员。")
    # Staff requests already lock their own user row; the organization lock serializes
    # batches without locking another staff member who is also receiving XP.
    owners = dict(session.execute(select(CompletionCode.migrated_to_user_id, CompletionCode.user_id).where(
        CompletionCode.organization_id == actor.organization_id, CompletionCode.migrated_to_user_id.in_(ids),
        CompletionCode.used_at.is_not(None))).all())
    recipients = {p["id"]:p for p in learner_directory(session, actor, ids)}
    if len(recipients) != len(ids):
        fail("部分学员已停用或不属于当前组织。", 409)
    if body.mode == "list":
        snapshot = session.scalar(select(ExperienceRosterSnapshot).where(
            ExperienceRosterSnapshot.id == body.snapshotId, ExperienceRosterSnapshot.actor_id == actor.id,
            ExperienceRosterSnapshot.organization_id == actor.organization_id,
            ExperienceRosterSnapshot.expires_at > datetime.now(UTC)))
        if not snapshot or any(not row.name or snapshot.recipients.get(str(row.learnerId)) != row.name
                                or recipients[str(row.learnerId)]["name"] != row.name for row in body.rows):
            fail("名单匹配已变更或过期，请重新核对。", 409)
    elif len(ids) != 1 or body.snapshotId:
        fail("单人发放仅可选择一位学员。")
    previous = {g.user_id:g for g in session.scalars(select(OfflineExperienceGrant).where(
        OfflineExperienceGrant.organization_id == actor.organization_id, OfflineExperienceGrant.batch == body.batch,
        OfflineExperienceGrant.user_id.in_(set(ids) | set(owners.values()))))}
    pending = []
    total = 0
    for row in body.rows:
        if (row.xp is None) == (row.points is None) or (body.mode == "list" and row.points is None):
            fail("单人发放请选择一种单位，名单导入需填写线下积分。")
        person = recipients[str(row.learnerId)]
        xp = row.xp if row.xp is not None else row.points * 10
        total += xp
        if total > MAX_SAFE_INTEGER:
            fail("本批次经验合计超出可用范围。")
        record_id = owners.get(row.learnerId, row.learnerId)
        existing = previous.get(record_id) or previous.get(row.learnerId)
        if existing:
            if (existing.xp, existing.points, existing.reason) != (xp, row.points, body.reason):
                fail("该学员在此批次已有不同的金额或事由，请核对记录。", 409)
            continue
        pending.append(OfflineExperienceGrant(organization_id=actor.organization_id, user_id=record_id,
            issuer_id=actor.id, xp=xp, points=row.points, batch=body.batch, reason=body.reason,
            content={"name":person["name"], "department":person["department"], "by":actor.display_name}))
    session.add_all(pending)
    return {"added":len(pending), "skipped":len(body.rows)-len(pending)}
