from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.identity import add_audit
from journey_api.models import (
    JourneyCompletionPolicy,
    JourneyDefinition,
    JourneyDefinitionStatus,
    JourneyStageKind,
    JourneyStageVersion,
    JourneyVersion,
    ModuleContentPackageBinding,
    OutboxEvent,
    OutboxStatus,
    Role,
    RoleAssignment,
    TaskDefinition,
    TaskDefinitionStatus,
    TaskVersion,
    User,
    UserStatus,
)
from journey_api.schemas import (
    ConstructionModulePackageOut,
    ConstructionModulePackageResponse,
    PublishConstructionModulePackageCommand,
)


router = APIRouter(prefix="/api/v1")
INITIAL_MODULE_KEYS = {"ai-academy", "delivery-guild"}
MODULE_TITLES = {
    "ai-academy": "AI学院",
    "delivery-guild": "交付线公会",
}


def _envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def _reviewer(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_names: tuple[str, ...] | None = None,
) -> User:
    user = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if user is None or (
        allowed_names is not None and user.display_name not in allowed_names
    ):
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "Reviewer 必须是内容包具名名单中的同组织有效 Reviewer。",
        )
    return user


def _binding_out(
    session: Session,
    binding: ModuleContentPackageBinding,
    *,
    replay: bool = False,
) -> ConstructionModulePackageOut:
    version = session.get(JourneyVersion, binding.journey_version_id)
    stage = session.scalar(
        select(JourneyStageVersion).where(
            JourneyStageVersion.journey_version_id == binding.journey_version_id,
            JourneyStageVersion.organization_id == binding.organization_id,
            JourneyStageVersion.task_version_id == binding.task_version_id,
        )
    )
    if version is None or stage is None:
        raise ApiError(409, "VERSION_CONFLICT", "内容包发布谱系已不可用。")
    return ConstructionModulePackageOut(
        binding_id=binding.id,
        module_key=binding.module_key,
        package_id=binding.package_id,
        package_version=binding.package_version,
        package_sha256=binding.package_sha256,
        journey_version_id=version.id,
        journey_version=version.version,
        journey_stage_version_id=stage.id,
        task_version_id=binding.task_version_id,
        effective_at=binding.effective_at,
        expires_at=binding.expires_at,
        status="PUBLISHED_CONTENT_BOUND",
        idempotency_replay=replay,
    )


def _task_rubric_dimensions(task: TaskVersion) -> list[str]:
    raw = task.rubric.get("dimensions") if isinstance(task.rubric, dict) else None
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            return []
        label = item.get("title") or item.get("dimension_key")
        if not isinstance(label, str):
            return []
        result.append(label)
    return result


def _task_rubric_is_review_ready(task: TaskVersion) -> bool:
    """Reject a published module task that cannot drive a human final review."""
    raw = task.rubric.get("dimensions") if isinstance(task.rubric, dict) else None
    if not isinstance(raw, list) or not raw:
        return False
    for item in raw:
        if not isinstance(item, dict):
            return False
        if not isinstance(item.get("dimension_key"), str) or not item[
            "dimension_key"
        ].strip():
            return False
        if item.get("required") is not True:
            return False
        levels = item.get("levels")
        if not isinstance(levels, dict) or any(
            not isinstance(levels.get(level), str) or not levels[level].strip()
            for level in ("MEETS", "NEEDS_WORK")
        ):
            return False
        max_points = item.get("max_points")
        meets_threshold = item.get("meets_threshold")
        if (max_points is None) != (meets_threshold is None):
            return False
        if max_points is not None and (
            not isinstance(max_points, int)
            or isinstance(max_points, bool)
            or not isinstance(meets_threshold, int)
            or isinstance(meets_threshold, bool)
            or max_points < 1
            or not 0 <= meets_threshold <= max_points
        ):
            return False
    return True


@router.post(
    "/ops/module-content-packages/publish",
    response_model=ConstructionModulePackageResponse,
)
def publish_construction_module_package(
    command: PublishConstructionModulePackageCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    package = command.package
    if package.module_key not in INITIAL_MODULE_KEYS:
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "本入口只承载 AI学院或交付线公会的首个签署内容包。",
        )
    if len(package.task_versions) != 1 or len(package.rubrics) != 1:
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "首发内容包必须且只能绑定一个任务版本和一个 Rubric。",
        )
    package_task = package.task_versions[0]
    package_rubric = package.rubrics[0]
    if package_task.execution_environment != "SIMULATION":
        raise ApiError(
            409,
            "CONTROLLED_TASK_AUTHORIZATION_REQUIRED",
            "受控真实任务必须另经现有 ControlledTaskAuthorization 纵切，不在内容发布时放行。",
        )

    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="construction_module_package.publish",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        binding = session.get(
            ModuleContentPackageBinding, uuid.UUID(str(replay["binding_id"]))
        )
        if binding is None or binding.organization_id != actor.organization_id:
            raise ApiError(409, "VERSION_CONFLICT", "幂等发布结果已不可用。")
        return _envelope(request, _binding_out(session, binding, replay=True))

    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now is None or package.effective_at > db_now:
        raise ApiError(409, "CONTENT_PACKAGE_NOT_EFFECTIVE", "内容包尚未生效。")
    if package.expires_at is not None and db_now >= package.expires_at:
        raise ApiError(409, "CONTENT_PACKAGE_EXPIRED", "内容包已过有效期。")

    owner = session.scalar(
        select(User).where(
            User.id == command.owner_user_id,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
        )
    )
    if owner is None or owner.display_name != package.owner.person_name:
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "Owner 签署姓名必须与同组织有效 Person 精确绑定。",
        )
    primary = _reviewer(
        session,
        organization_id=actor.organization_id,
        user_id=command.primary_reviewer_user_id,
        allowed_names=package.reviewer_policy.primary_reviewers,
    )
    backup = _reviewer(
        session,
        organization_id=actor.organization_id,
        user_id=command.backup_reviewer_user_id,
        allowed_names=package.reviewer_policy.backup_reviewers,
    )
    _reviewer(
        session,
        organization_id=actor.organization_id,
        user_id=command.reviewed_by,
    )
    if owner.id in {primary.id, backup.id} or primary.id == backup.id:
        raise ApiError(422, "CONTENT_BINDING_INVALID", "Owner 与主备 Reviewer 必须分离。")

    row = session.execute(
        select(TaskVersion, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == TaskVersion.task_definition_id)
        .where(
            TaskVersion.id == command.task_version_id,
            TaskVersion.organization_id == actor.organization_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.status == TaskDefinitionStatus.PUBLISHED,
        )
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可绑定的已发布 TaskVersion。")
    task, task_definition = row
    if (
        task_definition.stable_key != package_task.task_key
        or str(task.version) != package_task.version
        or task.purpose != package_task.purpose
        or task.required_deliverables != list(package_task.deliverables)
        or str(task.rubric_version) != package_rubric.version
        or _task_rubric_dimensions(task) != list(package_rubric.dimensions)
        or not _task_rubric_is_review_ready(task)
        or task.reviewer_role != "REVIEWER"
    ):
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "TaskVersion 或 Rubric 与 Owner 签署内容包不一致。",
        )
    if package.module_key == "ai-academy" and not task.learning_materials:
        raise ApiError(
            422,
            "CONTENT_BINDING_INVALID",
            "AI学院首单元必须绑定至少一项异步学习材料。",
        )

    definition_key = package.module_key.upper()
    definition = session.scalar(
        select(JourneyDefinition)
        .where(
            JourneyDefinition.organization_id == actor.organization_id,
            JourneyDefinition.stable_key == definition_key,
        )
        .with_for_update()
    )
    if definition is None:
        if command.expected_current_version != 0:
            raise ApiError(409, "VERSION_CONFLICT", "模块当前版本已变化。")
        definition = JourneyDefinition(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            stable_key=definition_key,
            status=JourneyDefinitionStatus.PUBLISHED,
            revision=1,
            created_by=actor.id,
        )
        session.add(definition)
        session.flush()
        current_version = 0
    else:
        current_version = session.scalar(
            select(func.max(JourneyVersion.version)).where(
                JourneyVersion.journey_definition_id == definition.id,
                JourneyVersion.organization_id == actor.organization_id,
            )
        ) or 0
        if current_version != command.expected_current_version:
            raise ApiError(409, "VERSION_CONFLICT", "模块当前版本已变化。")

    version = JourneyVersion(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        journey_definition_id=definition.id,
        version=current_version + 1,
        title=f"{MODULE_TITLES[package.module_key]} · {package.content_items[0].title}",
        purpose=package_task.purpose,
        change_summary=f"绑定 Owner 已签署内容包 {package.package_id}@{package.version}。",
        content_review_note=f"module-content-package:{package.sha256}",
        published_by=actor.id,
        reviewed_by=command.reviewed_by,
    )
    session.add(version)
    session.flush()
    stage = JourneyStageVersion(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        journey_version_id=version.id,
        stable_key=package_task.task_key,
        position=0,
        stage_kind=JourneyStageKind.ASSESSMENT,
        completion_policy=JourneyCompletionPolicy.REVIEW_REQUIRED,
        task_version_id=task.id,
        title=task.title,
        short_description=task.learner_outcome[:300],
    )
    session.add(stage)
    binding = ModuleContentPackageBinding(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        journey_version_id=version.id,
        task_version_id=task.id,
        package_id=package.package_id,
        package_version=package.version,
        module_key=package.module_key,
        package_sha256=package.sha256,
        task_package_sha256=package_task.sha256,
        rubric_package_sha256=package_rubric.sha256,
        owner_user_id=owner.id,
        owner_role=package.owner.role,
        owner_signed_at=package.owner.signed_at,
        effective_at=package.effective_at,
        expires_at=package.expires_at,
        source_refs=list(package.source_refs),
        reviewer_pool_ref=package.reviewer_policy.pool_ref,
        primary_reviewer_user_id=primary.id,
        backup_reviewer_user_id=backup.id,
        first_response_sla_minutes=package.reviewer_policy.first_response_sla_minutes,
        completion_sla_minutes=package.reviewer_policy.completion_sla_minutes,
        visibility=list(package.data_policy.visibility),
        data_classification=package.content_items[0].data_classification,
        retention_policy=package.data_policy.retention_policy,
        package_document=package.canonical_document(),
        created_by_user_id=actor.id,
    )
    session.add(binding)
    session.flush()
    result = {"binding_id": str(binding.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="construction_module_package.publish",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type="module_content_package.published.v1",
            aggregate_type="module_content_package_binding",
            aggregate_id=binding.id,
            payload={"aggregate_id": str(binding.id), "module_key": package.module_key},
            status=OutboxStatus.PENDING,
        )
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="module_content_package.published",
        resource_type="module_content_package_binding",
        resource_id=binding.id,
        result="SUCCESS",
        details={
            "module_key": package.module_key,
            "package_id": package.package_id,
            "package_version": package.version,
            "package_sha256": package.sha256,
            "journey_version_id": str(version.id),
            "task_version_id": str(task.id),
        },
    )
    session.commit()
    return _envelope(request, _binding_out(session, binding))
