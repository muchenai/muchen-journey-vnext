"""Read-only review projection plus durable, owner-scoped read receipts.

Notifications share a finalized review's ID, so GETs and replayed finalizations
cannot duplicate reminders. No evaluation feedback is returned by this API.
"""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import DateTime, String, and_, cast, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from journey_api.auth import Actor, get_learner_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.exploration_models import ExplorationSelfCheck, ExplorationWork
from journey_api.models import (Assignment, AssignmentStatus, CoachingFeedback, Enrollment,
    EnrollmentStatus, Evaluation, LearnerNotificationRead, Review, ReviewStatus, Submission,
    SubmissionVersion, TaskVersion)

router = APIRouter(prefix="/api/v1/me/notifications")
assignment_router = APIRouter(prefix="/api/v1/me/assignments")


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
    human = (select(feed, LearnerNotificationRead.read_at, literal("HUMAN").label("source"))
        .outerjoin(LearnerNotificationRead, and_(
            LearnerNotificationRead.review_id == feed.c.id,
            LearnerNotificationRead.learner_id == actor.id,
            LearnerNotificationRead.organization_id == actor.organization_id)))
    proof = SubmissionVersion.ai_use["exploration_ai_evaluation"]
    # The immutable submission is the decision evidence. Mutable attempt JSON
    # supplies only the read receipt, never the AI score or the completion gate.
    ai = (select(ExplorationSelfCheck.id, Assignment.organization_id, Enrollment.learner_id,
        Assignment.id.label("assignment_id"), TaskVersion.title.label("task_title"),
        literal("PASS").label("decision"), ExplorationWork.completed_at.label("reviewed_at"),
        cast(ExplorationSelfCheck.details["notificationReadAt"].as_string(), DateTime(timezone=True)).label("read_at"),
        literal("AI").label("source"))
        .select_from(SubmissionVersion)
        .join(Submission, Submission.id == SubmissionVersion.submission_id)
        .join(Assignment, and_(Assignment.id == Submission.assignment_id,
            Assignment.organization_id == Submission.organization_id))
        .join(Enrollment, and_(Enrollment.id == Assignment.enrollment_id,
            Enrollment.organization_id == Assignment.organization_id))
        .join(TaskVersion, and_(TaskVersion.id == Assignment.task_version_id,
            TaskVersion.organization_id == Assignment.organization_id))
        .join(ExplorationWork, and_(ExplorationWork.assignment_id == Assignment.id,
            ExplorationWork.organization_id == Assignment.organization_id,
            ExplorationWork.user_id == Enrollment.learner_id))
        .join(ExplorationSelfCheck, and_(cast(ExplorationSelfCheck.id, String) == proof["attemptId"].as_string(),
            ExplorationSelfCheck.assignment_id == Assignment.id,
            ExplorationSelfCheck.task_version_id == Assignment.task_version_id,
            ExplorationSelfCheck.organization_id == Assignment.organization_id,
            ExplorationSelfCheck.user_id == Enrollment.learner_id))
        .where(Assignment.organization_id == actor.organization_id, Enrollment.learner_id == actor.id,
            Assignment.status == AssignmentStatus.COMPLETED, Enrollment.status == EnrollmentStatus.COMPLETED,
            ExplorationWork.completed_at.is_not(None),
            Submission.current_version_no == SubmissionVersion.version_no,
            proof["kind"].as_string() == "EXPLORATION_AI", proof["source"].as_string() == "AI",
            proof["passed"].as_boolean().is_(True), proof["validated"].as_boolean().is_(True),
            proof["assignmentId"].as_string() == cast(Assignment.id, String),
            proof["taskVersionId"].as_string() == cast(Assignment.task_version_id, String)))
    return union_all(human, ai).subquery()


def envelope(request: Request, data):
    return {"data": data, "request_id": request.state.request_id}


@assignment_router.get("/{assignment_id}/destination")
def assignment_destination(assignment_id: UUID, request: Request,
                           actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    """Resolve old and new task links without trusting a client-supplied module.

    Notifications keep their stable assignment URL. The mapping is scoped to the
    same learner and organization as the assignment before exposing a task ID.
    """
    row = session.execute(select(Enrollment.novice_task_id,
                                 ExplorationWork.task_id.label("exploration_task_id"))
        .select_from(Assignment)
        .join(Enrollment, and_(Enrollment.id == Assignment.enrollment_id,
                               Enrollment.organization_id == Assignment.organization_id))
        .outerjoin(ExplorationWork, and_(ExplorationWork.assignment_id == Assignment.id,
                                        ExplorationWork.organization_id == actor.organization_id,
                                        ExplorationWork.user_id == actor.id))
        .where(Assignment.id == assignment_id, Assignment.organization_id == actor.organization_id,
               Enrollment.organization_id == actor.organization_id,
               Enrollment.learner_id == actor.id)).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的任务。")
    if row.exploration_task_id:
        return envelope(request, {"module": "exploration", "taskId": str(row.exploration_task_id)})
    if row.novice_task_id:
        return envelope(request, {"module": "village", "taskId": str(row.novice_task_id)})
    return envelope(request, {"module": "legacy", "taskId": None})


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
    items = [{"id": str(row.id), "assignmentId": str(row.assignment_id),
                   "taskTitle": row.task_title, "decision": row.decision,
                   "reviewedAt": row.reviewed_at.isoformat(),
                   "readAt": row.read_at.isoformat() if row.read_at else None,
                   **({"source": "AI"} if row.source == "AI" else {})} for row in rows[:limit]]
    return envelope(request, {
        "items": items,
        "unreadCount": unread,
        "nextCursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    })


def mark_read(request: Request, actor: Actor, session: Session, review_id: UUID | None = None):
    feed = with_read_state(actor)
    query = select(feed.c.id, feed.c.source)
    if review_id:
        query = query.where(feed.c.id == review_id)
    # One feed snapshot keeps later AI/human results unread. The old review FK
    # receipts remain dedicated to real human reviews.
    targets = session.execute(query).all()
    if review_id and not targets:
        raise ApiError(404, "NOT_FOUND", "没有找到可访问的通知。")
    human_ids = [row.id for row in targets if row.source == "HUMAN"]
    if human_ids:
        human = notifications(actor)
        session.execute(insert(LearnerNotificationRead).from_select(
            ["organization_id", "learner_id", "review_id", "read_at"],
            select(human.c.organization_id, human.c.learner_id, human.c.id, func.now())
                .where(human.c.id.in_(human_ids))
        ).on_conflict_do_nothing(index_elements=["organization_id", "learner_id", "review_id"]))
    ai_ids = [row.id for row in targets if row.source == "AI"]
    if ai_ids:
        for row in session.scalars(select(ExplorationSelfCheck).where(
                ExplorationSelfCheck.id.in_(ai_ids),
                ExplorationSelfCheck.organization_id == actor.organization_id,
                ExplorationSelfCheck.user_id == actor.id).order_by(ExplorationSelfCheck.id)
                .with_for_update().execution_options(populate_existing=True)):
            details = row.details or {}
            if not details.get("notificationReadAt"):
                row.details = {**details, "notificationReadAt": datetime.now(UTC).isoformat()}
    session.commit()
    return envelope(request, {"ok": True})


@router.post("/read-all")
def read_all(request: Request, actor: Actor = Depends(get_learner_actor), session: Session = Depends(get_db)):
    return mark_read(request, actor, session)


@router.post("/{review_id}/read")
def read_one(review_id: UUID, request: Request, actor: Actor = Depends(get_learner_actor),
             session: Session = Depends(get_db)):
    return mark_read(request, actor, session, review_id)
