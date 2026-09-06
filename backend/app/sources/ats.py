"""Tier 0: public ATS job boards.

These are the same JSON endpoints each platform's own careers page is built
from. No key, no scraping, no browser -- and they are the backbone of discovery,
because every company reachable here is one the browser agent never has to
visit.

Verified live during planning:
  Greenhouse  tamara -> 35 jobs (11 Riyadh)
  Ashby       rain   -> 47 jobs
  Greenhouse  hala   -> 14 jobs
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from .base import JobPosting, strip_html

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0)
HEADERS = {"User-Agent": "job-scout/0.1 (personal job search)"}


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _get(url: str, **kw: Any) -> Any | None:
    """Fetch JSON, returning None rather than raising.

    One dead board must never take down a whole scan -- companies delete
    boards, rename tokens, and go private without warning.
    """
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as c:
            r = c.get(url, **kw)
        if r.status_code != 200:
            log.info("board %s returned %s", url, r.status_code)
            return None
        return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("board %s failed: %s", url, exc)
        return None


class Greenhouse:
    name = "greenhouse"

    def fetch(self, token: str) -> list[JobPosting]:
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        if not data:
            return []
        out = []
        for j in data.get("jobs", []):
            out.append(
                JobPosting(
                    title=j.get("title", ""),
                    company=j.get("company_name") or token,
                    location=(j.get("location") or {}).get("name", "").strip(),
                    description=strip_html(j.get("content", "")),
                    apply_url=j.get("absolute_url", ""),
                    source=self.name,
                    external_id=str(j.get("id", "")),
                    posted_at=_parse_dt(j.get("first_published") or j.get("updated_at")),
                )
            )
        return out


class Ashby:
    name = "ashby"

    def fetch(self, token: str) -> list[JobPosting]:
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
        if not data:
            return []
        out = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            # Ashby gives clean plain text -- no HTML stripping needed.
            body = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))
            out.append(
                JobPosting(
                    title=j.get("title", ""),
                    company=token,
                    location=j.get("location", "") or "",
                    description=body,
                    apply_url=j.get("applyUrl") or j.get("jobUrl", ""),
                    source=self.name,
                    external_id=str(j.get("id", "")),
                    posted_at=_parse_dt(j.get("publishedAt")),
                    remote=bool(j.get("isRemote")),
                )
            )
        return out


class Lever:
    name = "lever"

    def fetch(self, token: str) -> list[JobPosting]:
        data = _get(f"https://api.lever.co/v0/postings/{token}?mode=json")
        if not isinstance(data, list):
            return []
        out = []
        for j in data:
            cats = j.get("categories") or {}
            posted = j.get("createdAt")
            out.append(
                JobPosting(
                    title=j.get("text", ""),
                    company=token,
                    location=cats.get("location", "") or "",
                    description=strip_html(j.get("descriptionPlain") or j.get("description", "")),
                    apply_url=j.get("hostedUrl", ""),
                    source=self.name,
                    external_id=str(j.get("id", "")),
                    posted_at=(
                        datetime.fromtimestamp(posted / 1000) if isinstance(posted, int) else None
                    ),
                )
            )
        return out


SOURCES = {s.name: s() for s in (Greenhouse, Ashby, Lever)}
