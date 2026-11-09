"""Persistent guild membership, practice and independently reviewed certification."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from journey_api.db import Base


class GuildCertificationRequest(Base):
    __tablename__ = "guild_certification_requests"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_guild_request_level"),
        CheckConstraint("status IN ('pending','approved','returned')", name="ck_guild_request_status"),
        CheckConstraint("reviewer_id IS NULL OR reviewer_id <> user_id", name="ck_guild_request_no_self_review"),
        CheckConstraint("(status = 'pending' AND reviewer_id IS NULL AND reviewed_at IS NULL) OR "
                        "(status <> 'pending' AND reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
                        name="ck_guild_request_review_state"),
        CheckConstraint("(guild_id IS NULL AND task_snapshot IS NULL) OR (guild_id IS NOT NULL AND task_snapshot IS NOT NULL)", name="ck_guild_request_task_scope"),
        Index("uq_guild_pending_request", "organization_id", "user_id", unique=True,
              postgresql_where=text("status = 'pending' AND guild_id IS NULL")),
        Index("uq_guild_approved_level", "organization_id", "user_id", "level", unique=True,
              postgresql_where=text("status = 'approved' AND guild_id IS NULL")),
        Index("uq_guild_scoped_pending", "organization_id", "user_id", "guild_id", unique=True,
              postgresql_where=text("status = 'pending' AND guild_id IS NOT NULL")),
        Index("uq_guild_scoped_approved", "organization_id", "user_id", "guild_id", "level", unique=True,
              postgresql_where=text("status = 'approved' AND guild_id IS NOT NULL")),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    student_name: Mapped[str] = mapped_column(String(200))
    level: Mapped[int]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    evidence: Mapped[list] = mapped_column(JSON)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewer_name: Mapped[str] = mapped_column(String(200), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, default="")
    guild_id: Mapped[str | None] = mapped_column(String(40))
    task_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)


class GuildMembership(Base):
    __tablename__ = "guild_memberships"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GuildSelection(Base):
    __tablename__ = "guild_selections"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(40))


class GuildTaskSubmission(Base):
    __tablename__ = "guild_task_submissions"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_guild_submission_level"),
        CheckConstraint("revision > 0", name="ck_guild_submission_revision"),
        CheckConstraint("status IN ('draft','submitted')", name="ck_guild_submission_status"),
        CheckConstraint("(status = 'draft' AND submitted_at IS NULL) OR (status = 'submitted' AND submitted_at IS NOT NULL)", name="ck_guild_submission_time"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    level: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(80))
    task_version: Mapped[int]
    artifact: Mapped[str] = mapped_column(Text)
    checks: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int]
