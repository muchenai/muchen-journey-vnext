"""Read-only review projection plus durable, owner-scoped read receipts.

Notifications share a finalized review's ID, so GETs and replayed finalizations
cannot duplicate reminders. No evaluation feedback is returned by this API.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_learner_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import (Assignment, CoachingFeedback, Enrollment, Evaluation,
    LearnerNotificationRead, Review, ReviewStatus, TaskVersion)

router = APIRouter(prefix="/api/v1/me/notifications")


def notifications(actor: Actor):
    decision = func.coalesce(Evaluation.decision, CoachingFeedback.decision)
    return (select(Review.id, Review.organization_id, Enrollment.learner_id,
                   Review.assignment_id, TaskVersion.title.label("task_title"),
                   decision.label("decision"), Review.finalized_at.label("reviewed_at"))
        .join(Assignment, and_(Assignment.id == Review.assignment_id,
                              Assignment.organization_id == Review.organization_id))
        .join(Enrollment, and_(Enrollment.id == Assignment.enrollment_id,
                              Enrollment.organization_id == Assignment.organization_id))
        .join(TaskVersion, and_(TaskVersion.id == Assignment.task_version_id,
                               TaskVersion.organization_id == Assignment.organization_id))
        .outerjoin(Evaluation, and_(Evaluation.review_id == Review.id,
                                   Evaluation.organization_id == Review.organization_id))
        .outerjoin(CoachingFeedback, and_(CoachingFeedback.review_id == Review.id,
                                         CoachingFeedback.organization_id == Review.organization_id))
        .where(Review.organization_id == actor.organization_id,
               Enrollment.learner_id == actor.id, Review.status == ReviewStatus.FINALIZED,
               decision.in_(["PASS", "REVISION_REQUIRED"]))
        .subquery())


def with_read_state(actor: Actor):
    feed = notifications(actor)
    return (select(feed, LearnerNotificationRead.read_at)
        .outerjoin(LearnerNotificationRead, and_(
            LearnerNotificationRead.review_id == feed.c.id,
            LearnerNotificationRead.learner_id == actor.id,
            LearnerNotificationRead.organization_id == actor.organization_id)).subquery())


def envelope(request: Request, data):
    return {"data": data, "request_id": request.state.request_id}


@router.get("")
def list_notifications(request: Request, cursor: UUID | None = None,
                       limit: int = Query(default=30, ge=1, le=100),
                       actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    feed = with_read_state(actor)
    query = select(feed).where(feed.c.read_at.is_(None))
    if cursor:
        anchor = session.execute(select(feed).where(feed.c.id == cursor)).first()
        if anchor is None:
            raise ApiError(404, "NOT_FOUND", "没有找到可访问的通知。")
        query = query.where(or_(feed.c.reviewed_at < anchor.reviewed_at,
            and_(feed.c.reviewed_at == anchor.reviewed_at, feed.c.id < anchor.id)))
    rows = session.execute(query.order_by(feed.c.reviewed_at.desc(), feed.c.id.desc()).limit(limit + 1)).all()
    unread = session.scalar(select(func.count()).select_from(feed).where(feed.c.read_at.is_(None)))
    return envelope(request, {
        "items": [{"id": str(row.id), "assignmentId": str(row.assignment_id),
                   "taskTitle": row.task_title, "decision": row.decision,
                   "reviewedAt": row.reviewed_at.isoformat(),
                   "readAt": row.read_at.isoformat() if row.read_at else None} for row in rows[:limit]],
        "unreadCount": unread,
        "nextCursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    })


def mark_read(request: Request, actor: Actor, session: Session, review_id: UUID | None = None):
    feed = notifications(actor)
    query = select(feed.c.organization_id, feed.c.learner_id, feed.c.id, func.now())
    if review_id:
        if session.scalar(select(feed.c.id).where(feed.c.id == review_id)) is None:
            raise ApiError(404, "NOT_FOUND", "没有找到可访问的通知。")
        query = query.where(feed.c.id == review_id)
    # One insert-select snapshot: later review results remain unread.
    session.execute(insert(LearnerNotificationRead).from_select(
        ["organization_id", "learner_id", "review_id", "read_at"], query
    ).on_conflict_do_nothing(index_elements=["organization_id", "learner_id", "review_id"]))
    session.commit()
    return envelope(request, {"ok": True})


@router.post("/read-all")
def read_all(request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    return mark_read(request, actor, session)


@router.post("/{review_id}/read")
def read_one(review_id: UUID, request: Request, actor: Actor = Depends(get_learner_actor),
             session: Session = Depends(get_db)):
    return mark_read(request, actor, session, review_id)
