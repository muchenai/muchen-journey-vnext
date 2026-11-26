"""Published course editions, account-bound study records and earned experience."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from journey_api.db import Base


class WorkspaceCourse(Base):
    __tablename__ = "workspace_courses"
    __table_args__ = (Index("ix_workspace_courses_catalog", "organization_id", "scope"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scope: Mapped[str] = mapped_column(String(12))
    draft: Mapped[dict] = mapped_column(JSON)
    live: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class CourseStudyRecord(Base):
    __tablename__ = "course_study_records"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace_courses.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[dict] = mapped_column(JSON)


class CourseStudyPreference(Base):
    __tablename__ = "course_study_preferences"
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace_courses.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    saved: Mapped[bool] = mapped_column(default=False)


class CourseRosterCode(Base):
    __tablename__ = "course_roster_codes"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(40), unique=True)


class CourseStudyAward(Base):
    __tablename__ = "course_study_awards"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "award_key", name="uq_course_study_credit"),
        Index("ix_course_study_awards_org_learner", "organization_id", "user_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace_courses.id"))
    scope: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(340))
    award_key: Mapped[str] = mapped_column(String(120))
    xp: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
