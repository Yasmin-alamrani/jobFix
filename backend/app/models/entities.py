"""Persisted tables.

Every user-owned row carries `user_id` from day one. In single-user mode it is
stamped with a constant, so turning on real accounts later is a data migration
rather than a schema rewrite.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"), index=True)

    job_title: Mapped[str] = mapped_column(String(255), default="")
    industry: Mapped[str] = mapped_column(String(64), default="other")
    job_description: Mapped[str] = mapped_column(Text)

    overall_score: Mapped[float] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON)  # full AnalysisResult
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    resume: Mapped[Resume] = relationship(back_populates="analyses")


class Job(Base):
    """A normalized posting from any source (Phase 2)."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)

    title: Mapped[str] = mapped_column(String(512))
    company: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    apply_url: Mapped[str] = mapped_column(String(1024), default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    # 'ats_link' or 'email' -- decided at ingest, enforced before any send.
    channel: Mapped[str] = mapped_column(String(16), default="ats_link")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
