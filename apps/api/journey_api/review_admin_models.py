"""Presentation metadata for the real reviewer workbench, never a second submission store."""
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, CheckConstraint, String, Uuid, UniqueConstraint, func, false
from sqlalchemy.orm import Mapped, mapped_column
from journey_api.db import Base


class ReviewAdminTask(Base):
    __tablename__ = "review_admin_tasks"
    task_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TaskPublicationRequest(Base):
    __tablename__ = 'task_publication_requests'
    __table_args__ = (UniqueConstraint('task_id', 'task_revision', name='uq_publication_task_revision'),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('task_definitions.id'), index=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    task_revision: Mapped[int] = mapped_column()
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    verified_material_urls: Mapped[list] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(String(1000), default='')
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewAdminDecision(Base):
    __tablename__ = "review_admin_decisions"
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewClaim(Base):
    """Renewable exclusive lease for one immutable submission's review."""
    __tablename__ = "review_claims"
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewAdminCertification(Base):
    __tablename__ = "review_admin_certifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewAdminAccess(Base):
    """Explicit Review administration grants; never infer super admin from a name/role."""
    __tablename__ = "review_admin_access"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        CheckConstraint("access_role IN ('super_admin', 'admin')"),
        CheckConstraint("level IN ('初级', '中级', '高级')"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    access_role: Mapped[str] = mapped_column(String(20), default="admin")
    # Bootstrap-only authority, never accepted by the grant API or inherited.
    can_grant_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    level: Mapped[str] = mapped_column(String(10), default="初级")
    domain: Mapped[str] = mapped_column(String(40), default="产品开发")
    revision: Mapped[int] = mapped_column(default=1)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PublishedTaskContent(Base):
    __tablename__ = "published_task_content"
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class MedalDefinition(Base):
    __tablename__ = "medal_definitions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MedalRedemption(Base):
    __tablename__ = "medal_redemptions"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "medal_id", name="uq_medal_owner_once"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    medal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medal_definitions.id"))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NoviceUnlockDebit(Base):
    __tablename__ = "novice_unlock_debits"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_unlock_debit_positive"),)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enrollments.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
