"""Tier 1: LinkedIn and the rest of the open web, via Google for Jobs.

The problem this solves: LinkedIn has no third-party jobs API and its robots.txt
prohibits automated access, so we cannot query it directly. But LinkedIn
*deliberately* publishes schema.org `JobPosting` JSON-LD on `/jobs/view/{id}`
and permits Googlebot to index those pages -- it syndicates to Google on
purpose. Google for Jobs is therefore a legitimate place to read LinkedIn
listings from: the data is published for exactly this kind of aggregation, we
never touch linkedin.com, and the apply link points back to the real posting.

JSearch reads Google for Jobs and exposes it as JSON. Free tier is 200
requests/month, which is generous here because one request returns a page of
jobs, not a single job.

  https://www.openwebninja.com/api/jsearch   (direct; RapidAPI adds ~30%)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .base import JobPosting

log = logging.getLogger(__name__)

BASE_URL = "https://api.openwebninja.com/jsearch/search-v2"
TIMEOUT = httpx.Timeout(25.0)

# Gulf markets, for convenience at the call site.
SAUDI = "sa"
GULF = ("sa", "ae", "qa", "om")

# Google for Jobs localises its display strings to the requested country. Left
# to default, a Saudi search returns Arabic locations with the publisher glued
# on ("الرياض  •  عبر LinkedIn") and null timestamps. Asking for English gives a
# clean city and a real epoch, so it is the default here -- the *listings* are
# unaffected, only the metadata language.
DEFAULT_LANGUAGE = "en"

# Strips the " • via <publisher>" suffix Google appends to its display location,
# in either language, for the case where a caller overrides the language.
_VIA_SUFFIX = re.compile(r"\s*[•·]\s*(?:via|عبر)\s+.*$", re.I)


class JSearchError(RuntimeError):
    """The aggregator refused or failed the request."""


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _apply_options(job: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for opt in job.get("apply_options") or []:
        name, link = opt.get("publisher"), opt.get("apply_link")
        if name and link:
            out.append((name, link))
    return out


def _to_posting(job: dict) -> JobPosting | None:
    title = job.get("job_title")
    if not title:
        return None

    # search-v2 gives a preformatted `job_location`; fall back to assembling
    # it from the parts when it is absent.
    location = _VIA_SUFFIX.sub("", (job.get("job_location") or "")).strip()
    if not location:
        parts = (job.get("job_city"), job.get("job_state"), job.get("job_country"))
        location = ", ".join(p for p in parts if p)

    return JobPosting(
        title=title,
        company=job.get("employer_name") or "",
        location=location or ("Remote" if job.get("job_is_remote") else ""),
        description=job.get("job_description") or "",
        apply_url=job.get("job_apply_link") or "",
        source="jsearch",
        external_id=str(job.get("job_id") or ""),
        posted_at=_parse_dt(
            job.get("job_posted_at_timestamp") or job.get("job_posted_at_datetime_utc")
        ),
        remote=bool(job.get("job_is_remote")),
        publisher=job.get("job_publisher") or "",
        apply_options=_apply_options(job),
    )


class JSearch:
    """Google for Jobs, filtered to the publishers you care about."""

    name = "jsearch"

    def __init__(self, api_key: str, *, base_url: str = BASE_URL) -> None:
        if not api_key:
            raise JSearchError(
                "No JSearch API key. Get a free one (200 requests/month) at "
                "https://www.openwebninja.com/api/jsearch and set JSEARCH_API_KEY."
            )
        self._key = api_key
        self._base = base_url

    def search(
        self,
        query: str,
        *,
        country: str = SAUDI,
        pages: int = 1,
        date_posted: str = "month",
        publishers: set[str] | None = None,
        remote_only: bool = False,
        language: str = DEFAULT_LANGUAGE,
    ) -> list[JobPosting]:
        """Search Google for Jobs.

        `query` carries the role and, optionally, the place -- "backend engineer
        in Riyadh". `publishers` filters to specific origin sites, matched
        case-insensitively on a substring so that "linkedin" catches both
        "LinkedIn" and "LinkedIn Jobs".

        Costs one request per page. Returns [] rather than raising on a failed
        page, so a partial result still reaches the user.
        """
        wanted = {p.lower() for p in publishers} if publishers else None
        out: list[JobPosting] = []
        cursor: str | None = None

        for _ in range(max(1, pages)):
            params: dict[str, Any] = {
                "query": query,
                "country": country,
                "date_posted": date_posted,
                "language": language,
            }
            if remote_only:
                params["work_from_home"] = "true"
            if cursor:
                params["cursor"] = cursor

            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    r = client.get(
                        self._base, params=params, headers={"x-api-key": self._key}
                    )
            except httpx.HTTPError as exc:
                log.warning("jsearch request failed: %s", exc)
                break

            if r.status_code in (401, 403):
                raise JSearchError(
                    "JSearch rejected the API key. Check JSEARCH_API_KEY in backend/.env."
                )
            if r.status_code == 429:
                log.warning("jsearch quota exhausted")
                break
            if r.status_code != 200:
                log.warning("jsearch returned %s", r.status_code)
                break

            try:
                data = r.json().get("data") or {}
            except ValueError:
                log.warning("jsearch returned non-JSON")
                break

            # search-v2 nests the list under `data.jobs`; older shapes put a
            # list directly in `data`.
            jobs = data.get("jobs", []) if isinstance(data, dict) else data
            for raw in jobs:
                if not isinstance(raw, dict):
                    continue
                posting = _to_posting(raw)
                if posting is None:
                    continue
                if wanted and not self._matches(posting, wanted):
                    continue
                out.append(posting)

            cursor = data.get("cursor") if isinstance(data, dict) else None
            if not jobs or not cursor:
                break

        return out

    @staticmethod
    def _matches(posting: JobPosting, wanted: set[str]) -> bool:
        """True when the role is published on one of the wanted sites.

        Checked against `apply_options` too: Google often reports a role's
        primary publisher as one board while it is also listed on LinkedIn.
        """
        names = [posting.publisher, *(name for name, _ in posting.apply_options)]
        return any(w in (n or "").lower() for n in names for w in wanted)

    def linkedin_only(self, query: str, **kw: Any) -> list[JobPosting]:
        """Convenience: the same search, restricted to LinkedIn-published roles."""
        return self.search(query, publishers={"linkedin"}, **kw)
