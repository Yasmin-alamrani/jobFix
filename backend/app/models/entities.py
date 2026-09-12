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
    # Set only for a pasted CV. Rendering a paste to PDF and reading the text
    # back loses anything the render font cannot draw -- Arabic, most of all --
    # so the original is kept and used wherever text (rather than layout) is
    # what is wanted.
    source_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    profile: Mapped["StoredProfile | None"] = relationship(
        back_populates="resume", cascade="all, delete-orphan", uselist=False
    )
    # Tailoring proposals and saved versions are copies of the CV's contents,
    # so deleting the CV has to take them too -- otherwise "delete my data"
    # would leave the data behind in a different table.
    proposals: Mapped[list["TailorProposal"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    versions: Mapped[list["CvVersion"]] = relationship(
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


class StoredProfile(Base):
    """The CV read into entities, cached per resume.

    Extraction is a Claude call, and the same CV always yields the same profile,
    so it is computed once on first request and read from here afterwards --
    by the audit, by field matching, and later by tailoring and export.

    `prompt_version` records which prompt wording produced it. A profile
    extracted under an older prompt stays interpretable instead of silently
    mixing with newer ones.
    """

    __tablename__ = "cv_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    resume_id: Mapped[str] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True, unique=True
    )

    profile: Mapped[dict] = mapped_column(JSON)      # full CvProfile
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # {"fields": [FieldFit]}
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    resume: Mapped["Resume"] = relationship(back_populates="profile")


class TailorProposal(Base):
    """One run of tailoring against one job: the edits offered and the ones withheld.

    Stored so that accepting edits later refers to exactly what was reviewed.
    `base_profile` is a snapshot of the profile the edits were generated
    against; applying them to anything else would put a diff on the wrong text.
    """

    __tablename__ = "tailor_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)

    base_profile: Mapped[dict] = mapped_column(JSON)
    edits: Mapped[list] = mapped_column(JSON, default=list)
    blocked: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    resume: Mapped["Resume"] = relationship(back_populates="proposals")


class CvVersion(Base):
    """A named copy of the CV: the original, or the original plus accepted edits.

    `job_title` and `company` are copied rather than joined, so the list of
    versions still reads correctly if the job row is later replaced.
    """

    __tablename__ = "cv_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("tailor_proposals.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255))
    job_title: Mapped[str] = mapped_column(String(512), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    is_original: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped[dict] = mapped_column(JSON)
    accepted_edit_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    resume: Mapped["Resume"] = relationship(back_populates="versions")


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
