"""Organization-scoped course roles and the append-only offline XP ledger."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from journey_api.db import Base


class CourseManagementSettings(Base):
    __tablename__ = "course_management_settings"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(default=0)
    assignments: Mapped[dict] = mapped_column(JSON)
    issuers: Mapped[list] = mapped_column(JSON)
    tags: Mapped[list] = mapped_column(JSON)


class ExperienceRosterSnapshot(Base):
    __tablename__ = "experience_roster_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(["actor_id", "organization_id"], ["users.id", "users.organization_id"]),
        Index("ix_experience_roster_expiry", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recipients: Mapped[dict] = mapped_column(JSON)


class OfflineExperienceGrant(Base):
    __tablename__ = "offline_experience_grants"
    __table_args__ = (
        UniqueConstraint("organization_id", "batch", "user_id", name="uq_offline_xp_batch_learner"),
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        ForeignKeyConstraint(["issuer_id", "organization_id"], ["users.id", "users.organization_id"]),
        CheckConstraint("xp > 0 AND (points IS NULL OR (points > 0 AND xp = points * 10))", name="ck_offline_xp_amount"),
        Index("ix_offline_xp_learner", "organization_id", "user_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    issuer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    batch: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(240))
    points: Mapped[int | None] = mapped_column(BigInteger)
    xp: Mapped[int] = mapped_column(BigInteger)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MallPointExchange(Base):
    """An immutable receipt, keyed to the signed-in company account even after migration."""
    __tablename__ = "mall_point_exchanges"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"]),
        UniqueConstraint("organization_id", "user_id", "request_key", name="uq_mall_point_exchange_request"),
        CheckConstraint("points > 0 AND spent_xp > 0 AND spent_xp % points = 0", name="ck_mall_exchange_amounts"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    request_key: Mapped[str] = mapped_column(String(120))
    points: Mapped[int] = mapped_column(BigInteger)
    spent_xp: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
