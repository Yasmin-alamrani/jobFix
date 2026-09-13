"""Search filters: work arrangement, seniority, and how recently a role was posted.

Every value is read from what a posting states -- a remote flag its source sets,
a date it publishes, a word in its title. Nothing is guessed. A posting that
does not say is "unknown", and what happens to unknowns is the user's call
(`include_unstated`), not the filter's: most titles name no level at all, so
silently dropping them would empty the results, and silently keeping them would
make the filter look stricter than it is. Either way the numbers hidden are
counted and returned, so the user sees what a filter removed and why.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.sources.base import JobPosting

SENIORITY_LEVELS = ("intern", "junior", "mid", "senior", "lead")
WORK_MODES = ("remote", "hybrid", "onsite")

# First match wins, most decisive first: "Senior Engineering Manager" is a lead
# role, "Associate Director" is a director. Arabic titles are covered for the
# common level words. Python's \b is Unicode-aware, so it bounds Arabic too.
_SENIORITY_RULES: list[tuple[str, re.Pattern]] = [
    ("intern", re.compile(r"\b(intern|internship|trainee|co-?op|apprentice|متدرب|تدريب)\b", re.I)),
    ("lead", re.compile(
        r"\b(lead|principal|staff|head|director|manager|vp|chief|architect|رئيس|مدير|قائد)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr|iii|iv|أول|خبير)\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr|entry[- ]level|graduate|associate|مبتدئ)\b", re.I)),
    ("mid", re.compile(r"\b(mid|mid-level|intermediate|ii)\b", re.I)),
]

_REMOTE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b|عن بعد", re.I)
_HYBRID = re.compile(r"\bhybrid\b|هجين", re.I)


def seniority_of(title: str) -> str:
    """The level a title states, or "unknown". Inferred from wording, so shown as such."""
    for level, pattern in _SENIORITY_RULES:
        if pattern.search(title or ""):
            return level
    return "unknown"


def work_mode_of(job: JobPosting) -> str:
    """Remote, hybrid or onsite, from what the posting says.

    "onsite" means the posting names a place and says nothing about remote or
    hybrid work -- the reading every job board uses. With no place and no flag,
    the answer is "unknown".
    """
    text = f"{job.title} {job.location}"
    if _HYBRID.search(text):
        return "hybrid"
    if job.remote or _REMOTE.search(text):
        return "remote"
    if job.location.strip():
        return "onsite"
    return "unknown"


def age_in_days(job: JobPosting, *, now: datetime | None = None) -> float | None:
    if job.posted_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - posted) / timedelta(days=1))


@dataclass
class Filters:
    work_mode: str = "any"                         # any | remote | hybrid | onsite
    seniority: frozenset[str] = frozenset()        # empty means any
    posted_within_days: int | None = None
    include_unstated: bool = True

    @property
    def active(self) -> bool:
        return self.work_mode != "any" or bool(self.seniority) or self.posted_within_days is not None


@dataclass
class Filtered:
    kept: list[JobPosting]
    # reason -> count. "<filter>" is a posting that states a value that does not
    # match; "<filter>_unstated" is one that states nothing, hidden only when
    # include_unstated is off.
    hidden: Counter = field(default_factory=Counter)


def apply(jobs: Iterable[JobPosting], filters: Filters, *, now: datetime | None = None) -> Filtered:
    result = Filtered(kept=[])
    for job in jobs:
        reason = _rejection(job, filters, now=now)
        if reason:
            result.hidden[reason] += 1
        else:
            result.kept.append(job)
    return result


def _rejection(job: JobPosting, filters: Filters, *, now: datetime | None) -> str:
    """The first filter this job fails, or "" if it passes them all."""
    if filters.work_mode != "any":
        mode = work_mode_of(job)
        if mode == "unknown":
            if not filters.include_unstated:
                return "work_mode_unstated"
        elif mode != filters.work_mode:
            return "work_mode"

    if filters.seniority:
        level = seniority_of(job.title)
        if level == "unknown":
            if not filters.include_unstated:
                return "seniority_unstated"
        elif level not in filters.seniority:
            return "seniority"

    if filters.posted_within_days is not None:
        age = age_in_days(job, now=now)
        if age is None:
            if not filters.include_unstated:
                return "posted_unstated"
        elif age > filters.posted_within_days:
            return "posted"

    return ""
