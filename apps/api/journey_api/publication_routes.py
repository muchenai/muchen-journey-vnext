"""Atomic approval of submitted task snapshots; ordinary staff cannot publish."""
import uuid
from datetime import UTC, datetime
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import TaskDefinition, User, UserStatus, RoleAssignment, Role
from journey_api.review_admin_models import TaskPublicationRequest, ReviewAdminTask
from journey_api.review_admin_access import require_publisher, require_super, access_for, permissions
from journey_api.review_admin_routes import envelope, audit, task_data, task_content_for_publish

router = APIRouter(prefix='/api/v1/review-admin')

def pending_publication(session, task_id):
    return session.scalar(select(TaskPublicationRequest).where(TaskPublicationRequest.task_id == task_id,
        TaskPublicationRequest.status == 'pending'))

def ensure_editable(session, task_id):
    if pending_publication(session, task_id):
        raise ApiError(409, 'PUBLICATION_PENDING', '任务正在等待发布审核，审核结束后才能修改。')

def publication_view(session, row):
    owner = session.get(User, row.submitted_by)
    reviewer = session.get(User, row.reviewed_by) if row.reviewed_by else None
    return dict(id=str(row.id), taskId=str(row.task_id), revision=row.revision, status=row.status,
        task=row.content, submittedBy=dict(id=str(row.submitted_by), name=owner.display_name),
        submittedAt=row.created_at.isoformat(), comment=row.comment,
        reviewedBy=dict(id=str(reviewer.id), name=reviewer.display_name) if reviewer else None,
        reviewedAt=row.reviewed_at.isoformat() if row.reviewed_at else None)

@router.get('/publications')
def publications(request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_publisher(session, actor)
    query = select(TaskPublicationRequest).where(TaskPublicationRequest.organization_id == actor.organization_id)
    if not permissions(session, actor)['isSuperAdmin']:
        query = query.where(TaskPublicationRequest.submitted_by == actor.id)
    rows = session.scalars(query.order_by(TaskPublicationRequest.created_at.desc())).all()
    return envelope(request, dict(items=[publication_view(session, row) for row in rows]))

class SubmitPublication(BaseModel):
    expected_revision: int = Field(ge=1)
    verified_material_urls: list[str] = Field(default_factory=list)

@router.post('/tasks/{task_id}/submit-publication')
def submit(task_id: uuid.UUID, command: SubmitPublication, request: Request,
           actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_publisher(session, actor)
    definition = session.scalar(select(TaskDefinition).where(TaskDefinition.id == task_id,
        TaskDefinition.organization_id == actor.organization_id, TaskDefinition.created_by == actor.id).with_for_update())
    if not definition: raise ApiError(404, 'NOT_FOUND', '任务草稿不存在。')
    row = session.get(ReviewAdminTask, task_id)
    if not row or row.revision != command.expected_revision:
        raise ApiError(409, 'VERSION_CONFLICT', '草稿已更新，请重新打开。')
    require_publisher(session, actor, row.content.get('difficulty'))
    previous = session.scalar(select(TaskPublicationRequest).where(TaskPublicationRequest.task_id == task_id,
        TaskPublicationRequest.task_revision == row.revision))
    if previous: return envelope(request, task_data(session, definition))
    ensure_editable(session, task_id)
    if row.status == 'archived': raise ApiError(409, 'INVALID_STATE', '请先恢复任务再提交审核。')
    task_content_for_publish(row.content)
    if row.content.get('camp') != 'novice': raise ApiError(409, 'NOT_AVAILABLE', '探索营发布暂未开放。')
    links = list(dict.fromkeys(m['url'] for m in row.content['materials'] if m['type'] == 'link'))
    if command.verified_material_urls != links:
        raise ApiError(422, 'MATERIAL_LINK_VERIFICATION_REQUIRED', '请确认全部学习材料链接可供学员访问。')
    approval = TaskPublicationRequest(id=uuid.uuid4(), organization_id=actor.organization_id,
        task_id=task_id, submitted_by=actor.id, task_revision=row.revision, revision=1, status='pending',
        content=dict(row.content), verified_material_urls=links, comment='')
    session.add(approval)
    audit(session, request, actor, 'task.publication_submitted', approval.id, {'task_id':str(task_id)})
    session.commit()
    return envelope(request, task_data(session, definition))

class DecidePublication(BaseModel):
    expected_revision: int = Field(ge=1)
    decision: Literal['approved', 'rejected']
    comment: str = Field(default='', max_length=1000)
    @model_validator(mode='after')
    def reason(self):
        self.comment = self.comment.strip()
        if self.decision == 'rejected' and not self.comment: raise ValueError('请填写退回原因')
        return self

@router.post('/publications/{publication_id}/decision')
def decide(publication_id: uuid.UUID, command: DecidePublication, request: Request,
           actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_super(session, actor)
    row = session.scalar(select(TaskPublicationRequest).where(TaskPublicationRequest.id == publication_id,
        TaskPublicationRequest.organization_id == actor.organization_id))
    if not row: raise ApiError(404, 'NOT_FOUND', '发布申请不存在。')
    definition = session.scalar(select(TaskDefinition).where(TaskDefinition.id == row.task_id,
        TaskDefinition.organization_id == actor.organization_id).with_for_update())
    session.refresh(row, with_for_update=True)
    if row.status != 'pending' or row.revision != command.expected_revision:
        raise ApiError(409, 'VERSION_CONFLICT', '申请已被处理，请刷新后查看审核结果。')
    profile = session.get(ReviewAdminTask, row.task_id)
    if not profile or profile.revision != row.task_revision or profile.content != row.content:
        raise ApiError(409, 'VERSION_CONFLICT', '提交版本已变化，不能发布。')
    if command.decision == 'approved':
        owner = session.get(User, row.submitted_by)
        access = access_for(session, row.submitted_by, actor.organization_id)
        roles = set(session.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == row.submitted_by,
            RoleAssignment.organization_id == actor.organization_id)))
        if owner.status != UserStatus.ACTIVE or (access and access.revoked_at) or not roles.intersection({Role.REVIEWER, Role.OPERATOR}):
            raise ApiError(409, 'AUTHOR_UNAVAILABLE', '提交人管理权限已失效，不能发布。')
    row.status, row.comment = command.decision, command.comment
    row.reviewed_by, row.reviewed_at, row.revision = actor.id, datetime.now(UTC), row.revision + 1
    audit(session, request, actor, 'task.publication_'+command.decision, row.id, {'task_id':str(row.task_id)})
    if command.decision == 'approved':
        from journey_api.routes import publish_task_version
        from journey_api.schemas import PublishTaskVersionCommand
        body = task_content_for_publish(row.content)
        profile.status = 'published'
        request.state.approved_publication_task_id = row.task_id
        publish_task_version(row.task_id, PublishTaskVersionCommand(**body, expected_revision=definition.revision,
            reviewed_by=actor.id, verified_material_urls=row.verified_material_urls), request,
            idempotency_key='publication-'+str(row.id), actor=actor, session=session)
    else:
        session.commit()
    return envelope(request, publication_view(session, row))
