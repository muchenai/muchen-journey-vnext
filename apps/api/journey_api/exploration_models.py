"""Persistent dynamic exploration catalog and learner-owned progress."""
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from journey_api.db import Base


class ExplorationCatalogTask(Base):
    __tablename__ = "exploration_catalog_tasks"
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)


class ExplorationWork(Base):
    __tablename__ = "exploration_work"
    __table_args__ = (UniqueConstraint("assignment_id", name="uq_exploration_work_assignment"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id"), primary_key=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"))
    opened_materials: Mapped[list] = mapped_column(JSON, default=list)
    checkin_confirmed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExplorationProgress(Base):
    __tablename__ = "exploration_progress"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    treasures: Mapped[dict] = mapped_column(JSON, default=dict)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExplorationMaterial(Base):
    __tablename__ = "exploration_materials"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(10))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str] = mapped_column(String(16), default="exploration", server_default="exploration")
    complete: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    chunked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExplorationMaterialChunk(Base):
    __tablename__ = "exploration_material_chunks"
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exploration_materials.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class ExplorationSelfCheck(Base):
    __tablename__ = "exploration_self_checks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id"), index=True)
    task_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_versions.id"))
    answer: Mapped[str] = mapped_column(String(8000))
    result: Mapped[str] = mapped_column(String(20000))
    status: Mapped[str] = mapped_column(String(16))
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
