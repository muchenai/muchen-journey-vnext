"""Persistent academy courses, review submissions, video chunks and learner records."""
import uuid
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column
from journey_api.db import Base


class AcademyVideo(Base):
    __tablename__ = 'academy_videos'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column()
    complete: Mapped[bool] = mapped_column(default=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcademyVideoChunk(Base):
    __tablename__ = 'academy_video_chunks'
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('academy_videos.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class AcademyCourse(Base):
    __tablename__ = 'academy_courses'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16), default='published')
    review_status: Mapped[str | None] = mapped_column(String(16))
    review_reason: Mapped[str] = mapped_column(default='')
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    video_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('academy_videos.id'), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcademyLearningRecord(Base):
    __tablename__ = 'academy_learning_records'
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('academy_courses.id'), primary_key=True)
    favorite: Mapped[bool] = mapped_column(default=False)
    seconds: Mapped[float] = mapped_column(default=0)
    duration: Mapped[float] = mapped_column(default=0)
    progress: Mapped[float] = mapped_column(default=0)
    completed: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcademyCourseCover(Base):
    __tablename__ = 'academy_course_covers'
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('academy_courses.id', ondelete='CASCADE'), primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    claim_id: Mapped[uuid.UUID | None] = mapped_column()
    data: Mapped[bytes | None] = mapped_column(LargeBinary)
    sha256: Mapped[str | None] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
