"""Presentation metadata for the real reviewer workbench, never a second submission store."""
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
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


class ReviewAdminDecision(Base):
    __tablename__ = "review_admin_decisions"
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReviewAdminCertification(Base):
    __tablename__ = "review_admin_certifications"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
