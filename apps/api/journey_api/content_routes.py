from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.idempotency import find_replay, store_result
from journey_api.identity import add_audit, utc_now
from journey_api.learning_materials import reviewable_material_links
from journey_api.models import (
    ContentDraft,
    ContentDraftStatus,
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
    ContentDraftListOut,
    ContentDraftListResponse,
    ContentDraftOut,
    ContentDraftResponse,
    ContentEditorOut,
    ContentEditorResponse,
    CreateContentDraftCommand,
    CreateContentEditorCommand,
    PublishContentDraftCommand,
    SubmitContentDraftCommand,
    TaskContentInput,
    TaskDefinitionListOut,
    TaskDefinitionListResponse,
    TaskDefinitionOut,
    TaskVersionSummaryOut,
    TaskVersionOut,
    TaskVersionResponse,
    UpdateContentDraftCommand,
)

router = APIRouter(prefix="/api/v1")


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def ensure_revision(actual: int, expected: int) -> None:
    if actual != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "状态已更新，请确认最新内容后重试。",
            details={"current_revision": actual},
        )


def draft_out(
    session: Session, draft: ContentDraft, *, replay: bool = False
) -> ContentDraftOut:
    definition = session.scalar(
        select(TaskDefinition).where(
            TaskDefinition.id == draft.task_definition_id,
            TaskDefinition.organization_id == draft.organization_id,
        )
    )
    if definition is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "内容草稿缺少任务定义。")
    return ContentDraftOut(
        id=draft.id,
        task_definition_id=draft.task_definition_id,
        stable_key=definition.stable_key,
        owner_id=draft.owner_id,
        status=draft.status.value,
        revision=draft.revision,
        content=TaskContentInput.model_validate(draft.content),
        submitted_at=draft.submitted_at,
        published_at=draft.published_at,
        published_task_version_id=draft.published_task_version_id,
        idempotency_replay=replay,
    )


def task_version_out(
    version: TaskVersion, stable_key: str, *, replay: bool = False
) -> TaskVersionOut:
    return TaskVersionOut(
        id=version.id,
        task_definition_id=version.task_definition_id,
        stable_key=stable_key,
        version=version.version,
        title=version.title,
        purpose=version.purpose,
        learner_outcome=version.learner_outcome,
        instructions=version.instructions,
        completion_criteria=version.completion_criteria,
        required_deliverables=version.required_deliverables,
        content_source_notes=version.content_source_notes,
        change_summary=version.change_summary,
        reviewer_calibration_note=version.reviewer_calibration_note,
        allowed_attachment_types=version.allowed_attachment_types,
        max_attachment_size_bytes=version.max_attachment_size_bytes,
        reference_materials=version.reference_materials,
        learning_materials=version.learning_materials,
        learning_experience=version.learning_experience,
        estimated_duration_minutes=version.estimated_duration_minutes,
        rubric=version.rubric,
        rubric_version=version.rubric_version,
        reviewer_role=version.reviewer_role,
        feedback_sla_business_days=version.feedback_sla_business_days,
        sensitivity=version.sensitivity,
        audience=version.audience,
        published_by=version.published_by,
        reviewed_by=version.reviewed_by,
        published_at=version.published_at,
        idempotency_replay=replay,
    )


def owned_draft(
    session: Session, actor: Actor, draft_id: uuid.UUID, *, lock: bool = False
) -> ContentDraft:
    statement = select(ContentDraft).where(
        ContentDraft.id == draft_id,
        ContentDraft.organization_id == actor.organization_id,
        ContentDraft.owner_id == actor.id,
    )
    if lock:
        statement = statement.with_for_update()
    draft = session.scalar(statement)
    if draft is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的内容草稿。")
    return draft


def definition_out(session: Session, definition: TaskDefinition) -> TaskDefinitionOut:
    versions = session.scalars(
        select(TaskVersion)
        .where(TaskVersion.task_definition_id == definition.id)
        .order_by(TaskVersion.version)
    ).all()
    return TaskDefinitionOut(
        id=definition.id,
        stable_key=definition.stable_key,
        status=definition.status.value,
        revision=definition.revision,
        content_owner_id=definition.created_by,
        versions=[
            TaskVersionSummaryOut(
                id=version.id,
                version=version.version,
                title=version.title,
                published_at=version.published_at,
                material_links=reviewable_material_links(version.learning_materials),
            )
            for version in versions
        ],
    )


@router.get("/content/task-definitions", response_model=TaskDefinitionListResponse)
def list_editable_task_definitions(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    definitions = session.scalars(
        select(TaskDefinition)
        .where(
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.status != TaskDefinitionStatus.WITHDRAWN,
        )
        .order_by(TaskDefinition.stable_key)
    ).all()
    return envelope(
        request,
        TaskDefinitionListOut(
            items=[definition_out(session, definition) for definition in definitions]
        ),
    )


@router.get("/content/drafts", response_model=ContentDraftListResponse)
def list_owned_drafts(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    drafts = session.scalars(
        select(ContentDraft)
        .where(
            ContentDraft.organization_id == actor.organization_id,
            ContentDraft.owner_id == actor.id,
        )
        .order_by(ContentDraft.updated_at.desc(), ContentDraft.id)
        .limit(100)
    ).all()
    return envelope(
        request,
        ContentDraftListOut(items=[draft_out(session, draft) for draft in drafts]),
    )


@router.get("/content/drafts/{draft_id}", response_model=ContentDraftResponse)
def get_owned_draft(
    draft_id: uuid.UUID,
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    return envelope(request, draft_out(session, owned_draft(session, actor, draft_id)))


@router.post(
    "/content/task-definitions/{task_definition_id}/drafts",
    response_model=ContentDraftResponse,
)
def create_content_draft(
    task_definition_id: uuid.UUID,
    command: CreateContentDraftCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    payload = {
        "task_definition_id": str(task_definition_id),
        **command.model_dump(mode="json"),
    }
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="content_draft.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        draft = owned_draft(session, actor, uuid.UUID(str(replay["id"])))
        return envelope(request, draft_out(session, draft, replay=True))
    definition = session.scalar(
        select(TaskDefinition).where(
            TaskDefinition.id == task_definition_id,
            TaskDefinition.organization_id == actor.organization_id,
            TaskDefinition.status != TaskDefinitionStatus.WITHDRAWN,
        )
    )
    if definition is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可编辑的任务定义。")
    draft = ContentDraft(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        task_definition_id=definition.id,
        owner_id=actor.id,
        status=ContentDraftStatus.DRAFT,
        revision=1,
        content=command.content.model_dump(mode="json"),
    )
    session.add(draft)
    result = {"id": str(draft.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="content_draft.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="content_draft.created",
        resource_type="content_draft",
        resource_id=draft.id,
        result="SUCCESS",
        details={"stable_key": definition.stable_key},
    )
    session.commit()
    return envelope(request, draft_out(session, draft))


@router.put("/content/drafts/{draft_id}", response_model=ContentDraftResponse)
def update_content_draft(
    draft_id: uuid.UUID,
    command: UpdateContentDraftCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    payload = {"draft_id": str(draft_id), **command.model_dump(mode="json")}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="content_draft.update",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        draft = owned_draft(session, actor, uuid.UUID(str(replay["id"])))
        return envelope(request, draft_out(session, draft, replay=True))
    draft = owned_draft(session, actor, draft_id, lock=True)
    ensure_revision(draft.revision, command.expected_revision)
    if draft.status != ContentDraftStatus.DRAFT:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已提交的内容正文不可原地修改。")
    draft.content = command.content.model_dump(mode="json")
    draft.revision += 1
    result = {"id": str(draft.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="content_draft.update",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="content_draft.updated",
        resource_type="content_draft",
        resource_id=draft.id,
        result="SUCCESS",
        details={"revision": draft.revision},
    )
    session.commit()
    return envelope(request, draft_out(session, draft))


@router.post(
    "/content/drafts/{draft_id}/submit", response_model=ContentDraftResponse
)
def submit_content_draft(
    draft_id: uuid.UUID,
    command: SubmitContentDraftCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.CONTENT_EDITOR)
    payload = {"draft_id": str(draft_id), **command.model_dump(mode="json")}
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="content_draft.submit",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        draft = owned_draft(session, actor, uuid.UUID(str(replay["id"])))
        return envelope(request, draft_out(session, draft, replay=True))
    draft = owned_draft(session, actor, draft_id, lock=True)
    ensure_revision(draft.revision, command.expected_revision)
    if draft.status != ContentDraftStatus.DRAFT:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "当前内容草稿不能重复提交。")
    draft.status = ContentDraftStatus.SUBMITTED
    draft.submitted_at = utc_now()
    draft.revision += 1
    result = {"id": str(draft.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="content_draft.submit",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="content_draft.submitted",
        resource_type="content_draft",
        resource_id=draft.id,
        result="SUCCESS",
        details={"review_note_provided": True, "revision": draft.revision},
    )
    session.commit()
    return envelope(request, draft_out(session, draft))


@router.get("/ops/content-drafts", response_model=ContentDraftListResponse)
def list_submitted_content_drafts(
    request: Request,
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    drafts = session.scalars(
        select(ContentDraft)
        .where(
            ContentDraft.organization_id == actor.organization_id,
            ContentDraft.status == ContentDraftStatus.SUBMITTED,
        )
        .order_by(ContentDraft.submitted_at, ContentDraft.id)
        .limit(100)
    ).all()
    return envelope(
        request,
        ContentDraftListOut(items=[draft_out(session, draft) for draft in drafts]),
    )


@router.post("/ops/content-editors", response_model=ContentEditorResponse)
def create_content_editor(
    command: CreateContentEditorCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = command.model_dump(mode="json")
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="content_editor.create",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        user = session.scalar(
            select(User)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(
                User.id == uuid.UUID(str(replay["user_id"])),
                User.organization_id == actor.organization_id,
                RoleAssignment.organization_id == actor.organization_id,
                RoleAssignment.role == Role.CONTENT_EDITOR,
            )
        )
        if user is None:
            raise ApiError(409, "VERSION_CONFLICT", "幂等身份结果已不可用。")
        return envelope(
            request,
            ContentEditorOut(
                user_id=user.id,
                display_name=user.display_name,
                idempotency_replay=True,
            ),
        )
    existing = session.scalar(
        select(User.id)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.CONTENT_EDITOR,
        )
        .with_for_update()
    )
    if existing is not None:
        raise ApiError(
            409,
            "CONTENT_EDITOR_ALREADY_EXISTS",
            "当前组织已有有效 Content Editor；请使用身份访问面板绑定或撤销。",
        )
    user = User(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        display_name=command.display_name,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    session.add(
        RoleAssignment(
            id=uuid.uuid4(),
            organization_id=actor.organization_id,
            user_id=user.id,
            role=Role.CONTENT_EDITOR,
        )
    )
    result = {"user_id": str(user.id)}
    store_result(
        session,
        actor_id=actor.id,
        command="content_editor.create",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="content_editor.created",
        resource_type="user",
        resource_id=user.id,
        result="SUCCESS",
        details={"role": Role.CONTENT_EDITOR.value},
    )
    session.commit()
    return envelope(
        request,
        ContentEditorOut(user_id=user.id, display_name=user.display_name),
    )


@router.post(
    "/ops/content-drafts/{draft_id}/publish", response_model=TaskVersionResponse
)
def publish_content_draft(
    draft_id: uuid.UUID,
    command: PublishContentDraftCommand,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(get_actor),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    require_role(actor, Role.OPERATOR)
    payload = {"draft_id": str(draft_id), **command.model_dump(mode="json")}
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    replay = find_replay(
        session,
        actor_id=actor.id,
        command="content_draft.publish",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        version = session.get(TaskVersion, uuid.UUID(str(replay["task_version_id"])))
        definition = session.get(
            TaskDefinition, uuid.UUID(str(replay["task_definition_id"]))
        )
        if (
            version is None
            or definition is None
            or version.organization_id != actor.organization_id
            or definition.organization_id != actor.organization_id
        ):
            raise ApiError(409, "VERSION_CONFLICT", "幂等发布结果已不可用。")
        return envelope(
            request, task_version_out(version, definition.stable_key, replay=True)
        )
    draft = session.scalar(
        select(ContentDraft)
        .where(
            ContentDraft.id == draft_id,
            ContentDraft.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if draft is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可发布的内容草稿。")
    ensure_revision(draft.revision, command.expected_revision)
    if draft.status != ContentDraftStatus.SUBMITTED:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "只有已提交复核的草稿可以发布。")
    definition = session.scalar(
        select(TaskDefinition)
        .where(
            TaskDefinition.id == draft.task_definition_id,
            TaskDefinition.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if definition is None:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "内容草稿缺少任务定义。")
    ensure_revision(definition.revision, command.expected_definition_revision)
    if definition.status == TaskDefinitionStatus.WITHDRAWN:
        raise ApiError(409, "INVALID_STATE_TRANSITION", "已撤销的任务定义不能发布。")
    reviewer = session.scalar(
        select(User)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(
            User.id == command.reviewed_by,
            User.organization_id == actor.organization_id,
            User.status == UserStatus.ACTIVE,
            RoleAssignment.organization_id == actor.organization_id,
            RoleAssignment.role == Role.REVIEWER,
        )
    )
    if reviewer is None:
        raise ApiError(422, "VALIDATION_FAILED", "内容复核人必须是同组织有效 Reviewer。")
    content = TaskContentInput.model_validate(draft.content)
    expected_material_links = reviewable_material_links(
        [item.model_dump(mode="json") for item in content.learning_materials]
    )
    expected_material_urls = [item["url"] for item in expected_material_links]
    if command.verified_material_urls != expected_material_urls:
        raise ApiError(
            422,
            "MATERIAL_LINK_VERIFICATION_REQUIRED",
            "必须逐项打开并确认当前草稿中的全部材料链接。",
            details={
                "expected_count": len(expected_material_urls),
                "verified_count": len(command.verified_material_urls),
            },
        )
    next_version = (
        session.scalar(
            select(func.max(TaskVersion.version)).where(
                TaskVersion.task_definition_id == definition.id
            )
        )
        or 0
    ) + 1
    version = TaskVersion(
        id=uuid.uuid4(),
        organization_id=actor.organization_id,
        task_definition_id=definition.id,
        version=next_version,
        title=content.title.strip(),
        purpose=content.purpose.strip(),
        learner_outcome=content.learner_outcome.strip(),
        instructions=content.instructions,
        completion_criteria=content.completion_criteria,
        required_deliverables=content.required_deliverables,
        content_source_notes=content.content_source_notes,
        change_summary=content.change_summary.strip(),
        reviewer_calibration_note=content.reviewer_calibration_note.strip(),
        allowed_attachment_types=content.allowed_attachment_types,
        max_attachment_size_bytes=content.max_attachment_size_bytes,
        reference_materials=content.reference_materials,
        learning_materials=[
            item.model_dump(mode="json") for item in content.learning_materials
        ],
        learning_experience={},
        estimated_duration_minutes=content.estimated_duration_minutes,
        rubric=content.rubric.model_dump(mode="json"),
        rubric_version=content.rubric.version,
        reviewer_role=content.reviewer_role,
        feedback_sla_business_days=content.feedback_sla_business_days,
        sensitivity=content.sensitivity,
        audience=content.audience,
        published_by=actor.id,
        reviewed_by=command.reviewed_by,
    )
    session.add(version)
    session.flush()
    now = utc_now()
    definition.status = TaskDefinitionStatus.PUBLISHED
    definition.revision += 1
    draft.status = ContentDraftStatus.PUBLISHED
    draft.published_at = now
    draft.published_task_version_id = version.id
    draft.revision += 1
    result = {
        "task_version_id": str(version.id),
        "task_definition_id": str(definition.id),
    }
    store_result(
        session,
        actor_id=actor.id,
        command="content_draft.publish",
        key=idempotency_key,
        payload=payload,
        response=result,
    )
    session.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type="task_version.published.v1",
            aggregate_type="task_definition",
            aggregate_id=definition.id,
            payload={"aggregate_id": str(definition.id)},
            status=OutboxStatus.PENDING,
        )
    )
    add_audit(
        session,
        request_id=request.state.request_id,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="content_draft.published",
        resource_type="task_version",
        resource_id=version.id,
        result="SUCCESS",
        details={
            "draft_id": str(draft.id),
            "stable_key": definition.stable_key,
            "version": next_version,
            "drafted_by": str(draft.owner_id),
            "reviewed_by": str(command.reviewed_by),
            "material_count": len(content.learning_materials),
            "verified_material_link_count": len(expected_material_urls),
        },
    )
    session.commit()
    return envelope(request, task_version_out(version, definition.stable_key))
