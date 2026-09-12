"""Tailoring and saved CV versions.

The flow is propose → review → save, and the security of it rests on one rule:
**the client sends edit IDs, never text.** A proposal is generated and stored
server-side; accepting edits means naming which stored edits to apply. So a
version can only ever contain the original CV plus edits that passed the
provenance check -- there is no request a client can make that puts its own
words into a saved CV.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.analyst import tailor
from app.agents.analyst.profile import CvProfile
from app.agents.analyst.provenance import PLACEHOLDER
from app.api.resumes import claude_errors, ensure_profile, owned_resume
from app.core.config import get_settings
from app.core.ratelimit import analysis_limit
from app.models.db import get_db
from app.models.entities import CvVersion, Job, Resume, StoredProfile, TailorProposal
from app.prompts import tailor_v1

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tailor"])

# Below this there is not enough of a posting to tailor against.
MIN_DESCRIPTION = 50


class JobIn(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    apply_url: str = ""
    source: str = "pasted"


class TailorRequest(BaseModel):
    resume_id: str
    # One of these. A scout result is referenced by ID and resolved from the
    # server's own cache, so the posting text is never round-tripped through
    # the client; a pasted posting or an audited one arrives as fields.
    scout_job_id: str = ""
    job: JobIn | None = None


class ProposalOut(BaseModel):
    proposal_id: str
    job_id: str
    job_title: str
    company: str
    edits: list[dict]
    blocked: list[dict]
    gaps: list[dict]
    prompt_version: str


class SaveVersionRequest(BaseModel):
    name: str = ""
    accepted_ids: list[str] = Field(default_factory=list)


class VersionOut(BaseModel):
    id: str
    name: str
    resume_id: str
    job_id: str | None
    job_title: str
    company: str
    is_original: bool
    accepted_edit_ids: list[str]
    placeholders: int
    created_at: datetime
    profile: dict


def _resolve_job(db: Session, request: TailorRequest) -> Job:
    """The target job as a stored row, from whichever form it arrived in."""
    settings = get_settings()

    if request.scout_job_id:
        from app.api.scout import _CACHE

        candidate = _CACHE.get(request.resume_id, {}).get(request.scout_job_id)
        if candidate is None:
            raise HTTPException(
                409, "That search result has expired. Run the search again, then tailor."
            )
        posting = candidate.job
        fields = JobIn(
            title=posting.title, company=posting.company, location=posting.location,
            description=posting.description, apply_url=posting.apply_url,
            source=posting.source or "search",
        )
    elif request.job is not None:
        fields = request.job
    else:
        raise HTTPException(422, "Say which job to tailor for.")

    if len(fields.description.strip()) < MIN_DESCRIPTION:
        raise HTTPException(
            422,
            "There is not enough of the job description to tailor against. "
            "Paste the full posting, including its requirements.",
        )

    if fields.apply_url:
        existing = (
            db.query(Job)
            .filter_by(user_id=settings.default_user_id, apply_url=fields.apply_url)
            .first()
        )
        if existing is not None:
            existing.description = fields.description
            return existing

    job = Job(
        user_id=settings.default_user_id,
        title=fields.title or "Untitled role",
        company=fields.company,
        location=fields.location,
        description=fields.description,
        apply_url=fields.apply_url,
        source=fields.source,
    )
    db.add(job)
    db.flush()
    return job


def ensure_original(db: Session, resume: Resume, stored: StoredProfile) -> CvVersion:
    """The untouched CV as a version of its own, so it sits in the same list as
    the tailored ones and can be exported the same way."""
    original = db.query(CvVersion).filter_by(resume_id=resume.id, is_original=True).first()
    if original is None:
        original = CvVersion(
            user_id=resume.user_id, resume_id=resume.id, name="Original",
            is_original=True, profile=stored.profile, accepted_edit_ids=[],
        )
        db.add(original)
        db.flush()
    return original


def _version_out(row: CvVersion) -> VersionOut:
    text = CvProfile.model_validate(row.profile).all_text
    return VersionOut(
        id=row.id, name=row.name, resume_id=row.resume_id, job_id=row.job_id,
        job_title=row.job_title, company=row.company, is_original=row.is_original,
        accepted_edit_ids=list(row.accepted_edit_ids or []),
        placeholders=len(PLACEHOLDER.findall(text)),
        created_at=row.created_at, profile=row.profile,
    )


def _owned_version(db: Session, version_id: str) -> CvVersion:
    row = db.get(CvVersion, version_id)
    if row is None or row.user_id != get_settings().default_user_id:
        raise HTTPException(404, "Version not found.")
    return row


@router.post("/tailor", response_model=ProposalOut, dependencies=[Depends(analysis_limit)])
def create_proposal(request: TailorRequest, db: Session = Depends(get_db)) -> ProposalOut:
    """Propose edits for one job. One Claude call; the result is stored so that
    accepting edits later refers to exactly what was reviewed."""
    resume = owned_resume(db, request.resume_id)
    job = _resolve_job(db, request)
    stored = ensure_profile(db, resume)
    profile = CvProfile.model_validate(stored.profile)

    with claude_errors("tailoring"):
        proposal = tailor.propose(
            profile, job_title=job.title, company=job.company,
            job_description=job.description,
        )

    row = TailorProposal(
        user_id=resume.user_id, resume_id=resume.id, job_id=job.id,
        base_profile=stored.profile,
        edits=[e.model_dump(mode="json") for e in proposal.edits],
        blocked=[e.model_dump(mode="json") for e in proposal.blocked],
        gaps=[g.model_dump(mode="json") for g in proposal.gaps],
        prompt_version=tailor_v1.VERSION,
    )
    db.add(row)
    ensure_original(db, resume, stored)
    db.commit()

    return ProposalOut(
        proposal_id=row.id, job_id=job.id, job_title=job.title, company=job.company,
        edits=row.edits, blocked=row.blocked, gaps=row.gaps,
        prompt_version=row.prompt_version,
    )


@router.post("/tailor/{proposal_id}/versions", response_model=VersionOut)
def save_version(
    proposal_id: str, request: SaveVersionRequest, db: Session = Depends(get_db)
) -> VersionOut:
    """Apply the accepted edits and store the result as a named version.

    No model call, so no rate limit: this is arithmetic over stored data. The
    two checks before storing should never fire, because every edit was already
    checked when proposed -- they are here so that the guarantee is about the
    document the user will send, not only about each piece of it.
    """
    proposal = db.get(TailorProposal, proposal_id)
    if proposal is None or proposal.user_id != get_settings().default_user_id:
        raise HTTPException(404, "That set of suggestions no longer exists.")

    edits = [tailor.Edit.model_validate(e) for e in proposal.edits]
    blocked_ids = {e["id"] for e in proposal.blocked}
    withheld = sorted(set(request.accepted_ids) & blocked_ids)
    if withheld:
        raise HTTPException(
            422,
            "Those suggestions were withheld because they would have added "
            f"something your CV does not say ({', '.join(withheld)}), so they "
            "cannot be accepted.",
        )

    base = CvProfile.model_validate(proposal.base_profile)
    try:
        tailored = tailor.apply_edits(base, edits, request.accepted_ids)
    except tailor.UnknownEdit as exc:
        raise HTTPException(422, str(exc)) from exc

    job = db.get(Job, proposal.job_id) if proposal.job_id else None
    findings = tailor.introduced_into(base, tailored, job.description if job else "")
    changed = tailor.untouchable_changes(base, tailored)
    if findings or changed:
        log.error("tailored version failed its backstop: %s %s", findings, changed)
        raise HTTPException(
            500,
            "This version failed a final check against your original CV and was "
            "not saved. Nothing was changed.",
        )

    default_name = " — ".join(x for x in (job.title if job else "", job.company if job else "") if x)
    row = CvVersion(
        user_id=proposal.user_id, resume_id=proposal.resume_id,
        job_id=proposal.job_id, proposal_id=proposal.id,
        name=(request.name.strip() or default_name or "Tailored CV")[:255],
        job_title=job.title if job else "", company=job.company if job else "",
        is_original=False, profile=tailored.model_dump(mode="json"),
        accepted_edit_ids=sorted(set(request.accepted_ids)),
    )
    db.add(row)
    db.commit()
    return _version_out(row)


@router.get("/resumes/{resume_id}/versions", response_model=list[VersionOut])
def list_versions(resume_id: str, db: Session = Depends(get_db)) -> list[VersionOut]:
    """Every saved version of a CV: the original first, then newest first."""
    resume = owned_resume(db, resume_id)
    stored = db.query(StoredProfile).filter_by(resume_id=resume_id).one_or_none()
    if stored is not None:
        ensure_original(db, resume, stored)
        db.commit()

    rows = db.query(CvVersion).filter_by(resume_id=resume_id).all()
    rows.sort(key=lambda r: (not r.is_original, -r.created_at.timestamp()))
    return [_version_out(r) for r in rows]


@router.get("/versions/{version_id}", response_model=VersionOut)
def get_version(version_id: str, db: Session = Depends(get_db)) -> VersionOut:
    return _version_out(_owned_version(db, version_id))


@router.delete("/versions/{version_id}", status_code=204, response_class=Response)
def delete_version(version_id: str, db: Session = Depends(get_db)) -> Response:
    row = _owned_version(db, version_id)
    if row.is_original:
        raise HTTPException(
            409,
            "The original is the CV itself. To remove it, delete the CV — that "
            "removes every version with it.",
        )
    db.delete(row)
    db.commit()
    return Response(status_code=204)
