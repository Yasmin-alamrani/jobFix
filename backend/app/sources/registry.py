"""Company registry and the Tier 0 scan."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from .ats import SOURCES
from .base import JobPosting

log = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).parent / "data" / "companies.yaml"


@dataclass(frozen=True)
class Company:
    company: str
    industry: str
    source: str
    token: str
    verified: bool = False


def load_registry(path: Path | None = None) -> list[Company]:
    raw = yaml.safe_load((path or REGISTRY_PATH).read_text()) or []
    out = []
    for entry in raw:
        if entry.get("source") not in SOURCES:
            log.warning("registry: unknown source %r for %s",
                        entry.get("source"), entry.get("company"))
            continue
        out.append(Company(**entry))
    return out


def scan(
    companies: list[Company] | None = None,
    *,
    industries: set[str] | None = None,
    verified_only: bool = False,
) -> list[JobPosting]:
    """Fetch every registered board and return deduplicated postings."""
    companies = companies if companies is not None else load_registry()
    if industries:
        companies = [c for c in companies if c.industry in industries]
    if verified_only:
        companies = [c for c in companies if c.verified]

    seen: dict[str, JobPosting] = {}
    for c in companies:
        for job in SOURCES[c.source].fetch(c.token):
            # Prefer the registry's display name over the board token.
            job.company = c.company
            seen.setdefault(job.dedupe_key, job)
    return list(seen.values())
