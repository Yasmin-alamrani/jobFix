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
from app.agents.scout.lookup import via_aggregator
from app.agents.scout.policy import PolicyViolation, WallEncountered
from app.api.resumes import model_errors, owned_resume, text_of
from app.core.config import get_settings
from app.core.i18n import Lang, ui_lang
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
def fetch_job(request: FetchRequest, lang: Lang = Depends(ui_lang)) -> FetchedJob:
    """Read one posting. Free when the page publishes structured data.

    A site may refuse to be read -- LinkedIn's robots.txt forbids it, and some
    pages are walled or simply will not load. The posting is then looked up
    through Google for Jobs, which is where such sites publish it on purpose,
    so a pasted link still turns into a posting rather than an apology.
    """
    settings = get_settings()
    url = request.url.strip()
    model = available_model()

    def from_aggregator():
        return via_aggregator(
            url, api_key=settings.jsearch_api_key, country=settings.jsearch_country
        )

    try:
        job = fetch_one(url, client=model, budget=25.0)
    except (BlockedAddress, PolicyViolation, WallEncountered, IntakeError) as exc:
        job = from_aggregator()
        if job is None:
            raise HTTPException(422, _with_fallback(describe_failure(exc))) from exc
    except Exception as exc:  # noqa: BLE001 -- any failure has the same way forward
        log.exception("job fetch failed for %s", url)
        job = from_aggregator()
        if job is None:
            raise HTTPException(502, _with_fallback("That page could not be read.")) from exc

    if len(job.description.strip()) < MIN_POSTING:
        fuller = from_aggregator()
        if fuller is not None and len(fuller.description.strip()) >= MIN_POSTING:
            job = fuller
        else:
            raise HTTPException(
                422,
                _with_fallback("That page had too little text to be a full job posting."),
            )

    return FetchedJob(
        title=job.title, company=job.company, location=job.location,
        description=job.description, apply_url=job.apply_url or url,
        source=job.source,
    )


@router.post("/targeting", response_model=Targeting, dependencies=[Depends(analysis_limit)])
def company_targeting(
    request: TargetingRequest, db: Session = Depends(get_db), lang: Lang = Depends(ui_lang)
) -> Targeting:
    """What the posting shows the employer values, labelled stated or inferred."""
    if len(request.job_description.strip()) < 50:
        raise HTTPException(
            422, "Paste the full job description -- a snippet does not say enough."
        )
    resume_text = text_of(owned_resume(db, request.resume_id)) if request.resume_id else ""

    with model_errors("company targeting"):
        return target(
            job_description=request.job_description, title=request.title,
            company=request.company, resume_text=resume_text, lang=lang,
        )
