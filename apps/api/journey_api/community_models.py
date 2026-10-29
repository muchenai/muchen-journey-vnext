"""Organization-scoped knowledge and delivery guild records."""
import uuid
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from journey_api.db import Base


class CommunityState(Base):
    __tablename__ = 'community_states'
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    module: Mapped[str] = mapped_column(String(20), primary_key=True)
    revision: Mapped[int] = mapped_column(default=0)
    content: Mapped[dict] = mapped_column(JSON)


class KnowledgeFile(Base):
    __tablename__ = 'knowledge_files'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    size: Mapped[int] = mapped_column()
    complete: Mapped[bool] = mapped_column(default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('knowledge_files.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class GuildContribution(Base):
    __tablename__ = 'guild_contributions'
    __table_args__ = (UniqueConstraint('organization_id', 'user_id', 'task_id', name='uq_guild_first_completion'),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('task_definitions.id'))
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('evaluations.id'))
    content: Mapped[dict] = mapped_column(JSON)
