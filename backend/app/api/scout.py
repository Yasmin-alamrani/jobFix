"""Agent 2 endpoints: find jobs, then score the shortlist.

Split into two calls on purpose. The prefilter is free and instant, so results
appear immediately and the user decides what is worth paying to score. Folding
both into one request would hide the cost behind a spinner and score jobs
nobody wanted.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.analyst.parser import parse_pdf
from app.agents.scout import brief as brief_mod
from app.agents.scout import filters as job_filters
from app.agents.scout.intake import IntakeError, describe_failure, fetch_one
from app.agents.scout.llm import ScoutModel, ScoutModelError, available_model
from app.agents.scout.policy import PolicyViolation, WallEncountered
from app.core.safe_fetch import BlockedAddress
from app.agents.scout.matcher import match_all
from app.agents.scout.prefilter import rank
from app.agents.scout.runner import ScoutRequest, collect
from app.core.config import get_settings
from app.core.i18n import Lang, tr, ui_lang
from app.core.ratelimit import fetch_limit, scoring_limit
from app.models.db import get_db
from app.models.entities import Resume, StoredProfile
from pathlib import Path

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scout", tags=["scout"])

# Ceiling on how many jobs one request may score, whatever the client asks for.
MAX_SHORTLIST = 20

# How many roles from one employer may appear in a result list.
MAX_PER_COMPANY = 3


class FindRequest(BaseModel):
    resume_id: str
    title_hint: str = ""
    locations: list[str] = Field(default_factory=lambda: ["saudi", "riyadh"])
    industries: list[str] = Field(default_factory=list)
    # On by default. The free ATS boards are a handful of companies; without
    # the aggregator a search shows the same few names every time.
    include_jsearch: bool = True
    linkedin_only: bool = False
    jsearch_query: str = ""
    # Filters. A value a posting does not state is "unknown"; whether those are
    # kept is the user's call, and what each filter hid is counted in the reply.
    work_mode: Literal["any", "remote", "hybrid", "onsite"] = "any"
    seniority: list[Literal["intern", "junior", "mid", "senior", "lead"]] = Field(
        default_factory=list)
    posted_within_days: int | None = Field(default=None, ge=1, le=365)
    include_unstated: bool = True


class CandidateOut(BaseModel):
    id: str
    title: str
    company: str
    location: str
    similarity: float
    # Share of this posting's distinctive terms the CV carries, 0..1. The
    # cosine above ranks; this one is the only number of the two that means
    # anything shown on its own to a person.
    coverage: float = 0.0
    overlap: list[str]
    apply_url: str
    source: str
    publisher: str = ""
    remote: bool = False
    # Read from the posting: seniority from title words, the arrangement from
    # its flags and location, the date as published. "unknown" when unstated.
    seniority: str = "unknown"
    work_mode: str = "unknown"
    posted_at: datetime | None = None


class FindResponse(BaseModel):
    total_found: int
    by_source: dict[str, int]
    candidates: list[CandidateOut]
    # reason -> how many postings the filters hid for it.
    hidden: dict[str, int] = Field(default_factory=dict)
    # What the user should know about the sources: Google not searched and
    # why, or what it was searched for.
    notes: list[str] = Field(default_factory=list)


class CachedJob(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    source: str


class ScoreRequest(BaseModel):
    resume_id: str
    job_ids: list[str]
    headline: bool = True


class LineOut(BaseModel):
    # The search result this line scores, so tailoring can resolve the posting
    # from the server's cache instead of the client sending it back.
    id: str = ""
    score: float
    title: str
    company: str
    location: str
    why: str
    gap: str
    url: str
    publisher: str = ""
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    seniority: str = "unknown"
    work_mode: str = "unknown"
    posted_at: datetime | None = None


class ScoreResponse(BaseModel):
    headline: str
    rendered: str
    worth_it: int
    failures: int
    lines: list[LineOut]


# Jobs are held between the two calls so the client sends ids, not whole
# postings back. Single-user, so a process-local cache is enough; this becomes
# a table if the app ever serves more than one person.
_CACHE: dict[str, dict] = {}


def _resume_text(db: Session, resume_id: str) -> str:
    settings = get_settings()
    row = db.get(Resume, resume_id)
    if row is None or row.user_id != settings.default_user_id:
        raise HTTPException(404, "Resume not found. Upload it first.")
    report = parse_pdf(Path(row.stored_path))
    if not report.has_extractable_text:
        raise HTTPException(
            422,
            "That resume has no machine-readable text, so it cannot be matched "
            "against anything. Re-export it as a text PDF.",
        )
    return report.text


def _latest_title(db: Session, resume_id: str) -> str:
    """The CV's most recent job title, from its stored profile if it has one.

    What Google for Jobs is searched for when the user types no role -- a better
    guess than a fixed "software engineer" for a CV that is not one. Read from
    the cache only, so a search never waits on a model call for it.
    """
    stored = db.query(StoredProfile).filter_by(resume_id=resume_id).one_or_none()
    if stored is None:
        return ""
    roles = (stored.profile or {}).get("experience") or []
    return next((str(r.get("title") or "").strip() for r in roles
                 if str(r.get("title") or "").strip()), "")


@router.post("/find", response_model=FindResponse, dependencies=[Depends(fetch_limit)])
def find(
    request: FindRequest, db: Session = Depends(get_db), lang: Lang = Depends(ui_lang)
) -> FindResponse:
    """Scan sources and rank against the CV. Free -- no model call."""
    settings = get_settings()
    resume_text = _resume_text(db, request.resume_id)

    notes: list[str] = []
    google_query = request.jsearch_query or request.title_hint
    if request.include_jsearch and not google_query:
        google_query = _latest_title(db, request.resume_id)
        if google_query and settings.jsearch_api_key:
            notes.append(
                f"Google for Jobs was searched for “{google_query}”, the most recent "
                "title on your CV. Type a role to search for something else."
            )

    scout_request = ScoutRequest(
        resume_text=resume_text,
        title_hint=request.title_hint,
        locations={loc.lower() for loc in request.locations if loc.strip()},
        industries=set(request.industries) or None,
        include_jsearch=request.include_jsearch,
        linkedin_only=request.linkedin_only,
        jsearch_query=google_query,
    )

    jobs = collect(scout_request, jsearch_key=settings.jsearch_api_key, notes=notes)
    filtered = job_filters.apply(jobs, job_filters.Filters(
        work_mode=request.work_mode,
        seniority=frozenset(request.seniority),
        posted_within_days=request.posted_within_days,
        include_unstated=request.include_unstated,
    ))
    candidates = rank(
        resume_text, filtered.kept,
        locations=scout_request.locations or None,
        title_hint=request.title_hint,
    )

    # One employer with twenty openings would otherwise be the whole page.
    per_company: dict[str, int] = {}
    spread = []
    for candidate in candidates:
        name = candidate.job.company.strip().lower()
        if name and per_company.get(name, 0) >= MAX_PER_COMPANY:
            continue
        per_company[name] = per_company.get(name, 0) + 1
        spread.append(candidate)
    candidates = spread

    by_source: dict[str, int] = {}
    for job in jobs:
        by_source[job.source] = by_source.get(job.source, 0) + 1

    _CACHE[request.resume_id] = {c.job.dedupe_key: c for c in candidates}

    return FindResponse(
        total_found=len(jobs),
        by_source=by_source,
        hidden=dict(filtered.hidden),
        notes=[tr(note, lang) for note in notes],
        candidates=[
            CandidateOut(
                id=c.job.dedupe_key, title=c.job.title, company=c.job.company,
                location=c.job.location, similarity=c.similarity,
                coverage=c.coverage,
                overlap=list(c.overlap), apply_url=c.job.apply_url,
                source=c.job.source, publisher=c.job.publisher, remote=c.job.remote,
                seniority=job_filters.seniority_of(c.job.title),
                work_mode=job_filters.work_mode_of(c.job),
                posted_at=c.job.posted_at,
            )
            for c in candidates
        ],
    )


@router.get("/jobs/{resume_id}/{job_id}", response_model=CachedJob)
def cached_job(resume_id: str, job_id: str, lang: Lang = Depends(ui_lang)) -> CachedJob:
    """One result from the last search, in full.

    The search itself returns titles and places only. A description is several
    thousand characters, and thirty of them would be sent for the one the user
    opens -- so they stay here until then.
    """
    candidate = _CACHE.get(resume_id, {}).get(job_id)
    if candidate is None:
        raise HTTPException(409, "That search result has expired. Run the search again.")
    job = candidate.job
    return CachedJob(
        id=job_id, title=job.title, company=job.company, location=job.location,
        description=job.description, apply_url=job.apply_url, source=job.source,
    )


@router.post("/score", response_model=ScoreResponse, dependencies=[Depends(scoring_limit)])
def score(
    request: ScoreRequest, db: Session = Depends(get_db), lang: Lang = Depends(ui_lang)
) -> ScoreResponse:
    """Score the chosen shortlist with the model. This is the part that costs."""
    model = ScoutModel()
    if not model.has_credentials:
        raise HTTPException(
            503,
            "No Gemini API key. Add GEMINI_API_KEY to backend/.env and restart the server.",
        )
    if not request.job_ids:
        raise HTTPException(422, "Pick at least one job to score.")

    cached = _CACHE.get(request.resume_id)
    if not cached:
        raise HTTPException(409, "Run a search first — those results have expired.")

    chosen = [cached[jid] for jid in request.job_ids[:MAX_SHORTLIST] if jid in cached]
    if not chosen:
        raise HTTPException(404, "None of those jobs are in the last search.")

    resume_text = _resume_text(db, request.resume_id)

    try:
        matches = match_all(model, resume_text, chosen, limit=MAX_SHORTLIST)
        built = brief_mod.build(
            matches, total_found=len(cached), limit=len(chosen),
            client=model if request.headline else None, lang=lang,
        )
    except ScoutModelError as exc:
        raise HTTPException(502, str(exc)) from exc

    by_key = {m.job.dedupe_key: m for m in matches}
    lines = []
    for line in built.lines:
        match = next(
            (m for m in matches if m.job.title == line.title and m.job.company == line.company),
            None,
        )
        lines.append(
            LineOut(
                id=match.job.dedupe_key if match else "",
                score=line.score, title=line.title, company=line.company,
                location=line.location, why=tr(line.why, lang), gap=tr(line.gap, lang),
                url=line.url, publisher=line.publisher,
                matched=match.matched if match else [],
                missing=match.missing_critical if match else [],
                seniority=job_filters.seniority_of(line.title),
                work_mode=job_filters.work_mode_of(match.job) if match else "unknown",
                posted_at=match.job.posted_at if match else None,
            )
        )

    return ScoreResponse(
        headline=built.headline,
        rendered=built.render(),
        worth_it=sum(1 for line in built.lines if line.score >= brief_mod.WORTH_IT),
        failures=built.failures,
        lines=lines,
    )


class FromUrlRequest(BaseModel):
    url: str
    resume_id: str = ""      # when given, the role is scored against the CV


class FromUrlResponse(BaseModel):
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    source: str
    score: float | None = None
    why: str = ""
    gap: str = ""
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


@router.post("/from-url", response_model=FromUrlResponse, dependencies=[Depends(fetch_limit)])
def from_url(request: FromUrlRequest, db: Session = Depends(get_db)) -> FromUrlResponse:
    """Read one job posting the user pasted, and optionally score it.

    This is how a LinkedIn or Bayt role enters the app: the user names a
    specific page, we fetch that page once. Reading is free when the page
    publishes structured data; scoring costs one model call.
    """
    settings = get_settings()
    model = available_model()

    try:
        job = fetch_one(request.url.strip(), client=model)
    except (BlockedAddress, PolicyViolation, WallEncountered, IntakeError) as exc:
        raise HTTPException(422, describe_failure(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("intake failed for %s", request.url)
        raise HTTPException(502, f"Could not read that page: {exc}") from exc

    out = FromUrlResponse(
        title=job.title, company=job.company, location=job.location,
        description=job.description[:4000], apply_url=job.apply_url, source=job.source,
    )

    if not request.resume_id or model is None:
        return out

    from app.agents.scout.brief import _gap, _why
    from app.agents.scout.matcher import match_one
    from app.agents.scout.prefilter import Candidate

    resume_text = _resume_text(db, request.resume_id)
    match = match_one(model, resume_text, Candidate(job=job, similarity=0.0, overlap=()))
    if match.ok:
        out.score = match.score
        out.why = _why(match)
        out.gap = _gap(match)
        out.matched = match.matched
        out.missing = match.missing_critical
    return out
