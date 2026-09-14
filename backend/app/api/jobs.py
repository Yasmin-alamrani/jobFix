"""Job-link analysis: read a posting from a URL, and read what its employer values.

Reading a URL can fail for reasons the user cannot fix from here -- a login
wall, a bot check, a page that renders only in a browser, a site whose
robots.txt forbids it. Every one of those answers with the reason and the same
way forward: paste the description. The paste box sits directly under the URL
field, so a failed fetch is a detour of one step rather than a dead end.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.analyst.targeting import Targeting, target
from app.agents.scout.intake import IntakeError, describe_failure, fetch_one
from app.agents.scout.llm import available_model
from app.agents.scout.policy import PolicyViolation, WallEncountered
from app.api.resumes import model_errors, owned_resume, text_of
from app.core.ratelimit import analysis_limit, fetch_limit
from app.core.safe_fetch import BlockedAddress
from app.models.db import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Below this, what came back is a stub or a listing card, not a posting.
MIN_POSTING = 200
PASTE = "Paste the job description into the box below instead."


def _with_fallback(message: str) -> str:
    return message if "paste" in message.lower() else f"{message} {PASTE}"


class FetchRequest(BaseModel):
    url: str


class FetchedJob(BaseModel):
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    source: str


class TargetingRequest(BaseModel):
    job_description: str
    title: str = ""
    company: str = ""
    # Optional: with a CV, the actions are specific to it ("move this bullet
    # up"); without one, they are about the posting alone.
    resume_id: str = ""


@router.post("/fetch", response_model=FetchedJob, dependencies=[Depends(fetch_limit)])
def fetch_job(request: FetchRequest) -> FetchedJob:
    """Read one posting. Free when the page publishes structured data."""
    model = available_model()
    try:
        job = fetch_one(request.url.strip(), client=model)
    except (BlockedAddress, PolicyViolation, WallEncountered, IntakeError) as exc:
        raise HTTPException(422, _with_fallback(describe_failure(exc))) from exc
    except Exception as exc:  # noqa: BLE001 -- any failure has the same way forward
        log.exception("job fetch failed for %s", request.url)
        raise HTTPException(502, _with_fallback("That page could not be read.")) from exc

    if len(job.description.strip()) < MIN_POSTING:
        raise HTTPException(
            422,
            _with_fallback("That page had too little text to be a full job posting."),
        )

    return FetchedJob(
        title=job.title, company=job.company, location=job.location,
        description=job.description, apply_url=job.apply_url or request.url.strip(),
        source=job.source,
    )


@router.post("/targeting", response_model=Targeting, dependencies=[Depends(analysis_limit)])
def company_targeting(request: TargetingRequest, db: Session = Depends(get_db)) -> Targeting:
    """What the posting shows the employer values, labelled stated or inferred."""
    if len(request.job_description.strip()) < 50:
        raise HTTPException(
            422, "Paste the full job description -- a snippet does not say enough."
        )
    resume_text = text_of(owned_resume(db, request.resume_id)) if request.resume_id else ""

    with model_errors("company targeting"):
        return target(
            job_description=request.job_description, title=request.title,
            company=request.company, resume_text=resume_text,
        )
