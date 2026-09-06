"""Agent 2 orchestration: scan → prefilter → match → brief.

The shape of the pipeline is the cost control. A scan returns roughly a hundred
jobs; the prefilter orders all of them for nothing, and only the shortlist
reaches the model. Scoring every job instead would multiply the bill by ten for
an answer nobody reads past the top eight.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from app.sources.base import JobPosting
from app.sources.registry import scan as scan_ats

from . import brief as brief_mod
from .brief import Brief
from .llm import OpenRouter
from .matcher import Match, match_all
from .prefilter import rank

log = logging.getLogger(__name__)


@dataclass
class ScoutRequest:
    resume_text: str
    title_hint: str = ""
    locations: set[str] = field(default_factory=lambda: {"saudi", "riyadh"})
    industries: set[str] | None = None
    # How many jobs reach the model. The only knob that costs money.
    shortlist: int = 12
    # How many appear in the brief.
    show: int = 8
    include_jsearch: bool = False
    jsearch_query: str = ""
    linkedin_only: bool = False


@dataclass
class ScoutResult:
    brief: Brief
    matches: list[Match]
    jobs_found: int
    jobs_scored: int


def collect(request: ScoutRequest, *, jsearch_key: str = "") -> list[JobPosting]:
    """Gather postings from every configured source.

    Tier 0 (ATS boards) is free and always runs. Tier 1 (Google for Jobs, which
    is how LinkedIn roles reach us) costs a request and is opt-in.
    """
    jobs = scan_ats(industries=request.industries, verified_only=True)
    log.info("tier 0: %s jobs from ATS boards", len(jobs))

    if request.include_jsearch and jsearch_key:
        from app.sources.jsearch import JSearch

        query = request.jsearch_query or request.title_hint or "software engineer"
        try:
            client = JSearch(jsearch_key)
            found = (
                client.linkedin_only(query)
                if request.linkedin_only
                else client.search(query)
            )
            log.info("tier 1: %s jobs from Google for Jobs", len(found))
            jobs += found
        except Exception as exc:  # noqa: BLE001 -- one dead source must not end a scan
            log.warning("jsearch unavailable: %s", exc)

    # Deduplicate across sources: the same role often appears on a company's own
    # board and again through the aggregator.
    seen: dict[str, JobPosting] = {}
    for job in jobs:
        seen.setdefault(job.dedupe_key, job)
    return list(seen.values())


def run(
    request: ScoutRequest,
    *,
    client: OpenRouter,
    jsearch_key: str = "",
    headline: bool = True,
) -> ScoutResult:
    jobs = collect(request, jsearch_key=jsearch_key)
    by_source = Counter(j.source for j in jobs)

    candidates = rank(
        request.resume_text,
        jobs,
        locations=request.locations or None,
        title_hint=request.title_hint,
    )
    log.info("prefilter: %s of %s jobs survived the location filter",
             len(candidates), len(jobs))

    matches = match_all(client, request.resume_text, candidates, limit=request.shortlist)

    return ScoutResult(
        brief=brief_mod.build(
            matches,
            total_found=len(jobs),
            by_source=dict(by_source),
            limit=request.show,
            client=client if headline else None,
        ),
        matches=matches,
        jobs_found=len(jobs),
        jobs_scored=len(matches),
    )
