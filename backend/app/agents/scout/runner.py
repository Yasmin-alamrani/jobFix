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
from .llm import ScoutModel
from .matcher import Match, match_all
from .prefilter import rank

log = logging.getLogger(__name__)


# Pages of aggregator results per search. One page is ten roles, which is
# too few to show a range of employers; each page costs one request of the
# 200 a month the free plan allows.
JSEARCH_PAGES = 2


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


def collect(
    request: ScoutRequest,
    *,
    jsearch_key: str = "",
    notes: list[str] | None = None,
) -> list[JobPosting]:
    """Gather postings from every configured source.

    Tier 0 (ATS boards) is free and always runs. Tier 1 (Google for Jobs, which
    is how LinkedIn roles reach us) costs a request and is opt-in.

    `notes`, when given, receives what the user should know about a source they
    asked for that did not deliver -- no key, a spent quota, no results. In the
    log alone, each of those reads to the user as "Google has nothing".
    """
    notes = [] if notes is None else notes
    jobs = scan_ats(industries=request.industries, verified_only=True)
    log.info("tier 0: %s jobs from ATS boards", len(jobs))

    if request.include_jsearch and not jsearch_key:
        notes.append(
            "Google for Jobs was not searched: there is no JSEARCH_API_KEY in backend/.env."
        )
    elif request.include_jsearch:
        from app.sources.jsearch import JSearch

        query = request.jsearch_query or request.title_hint or "software engineer"
        try:
            client = JSearch(jsearch_key)
            found = (
                client.linkedin_only(query, pages=JSEARCH_PAGES)
                if request.linkedin_only
                else client.search(query, pages=JSEARCH_PAGES)
            )
            log.info("tier 1: %s jobs from Google for Jobs", len(found))
            jobs += found
            if client.last_problem:
                notes.append(f"Google for Jobs: {client.last_problem}")
            elif not found:
                where = " on LinkedIn" if request.linkedin_only else ""
                notes.append(f"Google for Jobs found no roles{where} for “{query}”.")
        except Exception as exc:  # noqa: BLE001 -- one dead source must not end a scan
            log.warning("jsearch unavailable: %s", exc)
            notes.append(f"Google for Jobs could not be searched: {exc}")

    # Deduplicate across sources: the same role often appears on a company's own
    # board and again through the aggregator -- and aggregators repeat it under
    # slightly different titles and places, which the exact key cannot see. So a
    # second key collapses one employer's near-identical titles too.
    seen: set[str] = set()
    out: list[JobPosting] = []
    for job in jobs:
        rough = " ".join(f"{job.company} {job.title}".lower().split())[:48]
        if job.dedupe_key in seen or rough in seen:
            continue
        seen.update({job.dedupe_key, rough})
        out.append(job)
    return out


def run(
    request: ScoutRequest,
    *,
    client: ScoutModel,
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
