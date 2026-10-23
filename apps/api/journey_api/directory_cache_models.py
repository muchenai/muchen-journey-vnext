"""Search-only company directory; never an authorization source."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from journey_api.db import Base


class DirectorySync(Base):
    __tablename__ = 'directory_sync'
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    member_count: Mapped[int] = mapped_column(default=0)
    department_tree: Mapped[list | None] = mapped_column(JSON, nullable=True)


class DirectoryMember(Base):
    __tablename__ = 'directory_members'
    __table_args__ = (Index('ix_directory_members_search', 'organization_id', 'app_id', 'search_name'),)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    open_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    search_name: Mapped[str] = mapped_column(String(255))
    profile: Mapped[dict] = mapped_column(JSON)
