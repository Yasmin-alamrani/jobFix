"""Normalized job postings and the source protocol.

Every source -- an ATS API, a search index, a pasted URL -- produces the same
`JobPosting`, so ranking and the brief never need to know where a job came from.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, field_validator

# Applications are either a link the user follows or nothing at all. There is no
# 'email' channel any more: the outreach agent was dropped.
Channel = str


class JobPosting(BaseModel):
    title: str
    company: str
    location: str = ""
    description: str = ""
    apply_url: str = ""
    source: str = ""
    external_id: str = ""
    posted_at: datetime | None = None
    remote: bool = False

    # Which site originally published the role, when it reached us through an
    # aggregator -- "LinkedIn", "Bayt", "Indeed". `source` says how we got it;
    # `publisher` says where it lives. The brief shows the latter, because that
    # is where the user will actually click apply.
    publisher: str = ""
    # Every place the same role can be applied to, as (publisher, url). Google
    # for Jobs often lists a role on several boards at once.
    apply_options: list[tuple[str, str]] = Field(default_factory=list)

    @field_validator("title", "company", mode="after")
    @classmethod
    def _tidy(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("location", mode="after")
    @classmethod
    def _tidy_location(cls, value: str) -> str:
        """Collapse repeated place names.

        Sources report location as city/state/country independently, and for a
        city-state like Riyadh that yields "Riyadh, Riyadh, Saudi Arabia".
        Dropping consecutive duplicates keeps the brief readable without
        discarding genuinely different parts.
        """
        parts, out = [p.strip() for p in value.split(",")], []
        for part in parts:
            if part and (not out or part.lower() != out[-1].lower()):
                out.append(part)
        return ", ".join(out)

    @property
    def dedupe_key(self) -> str:
        """Stable identity across sources.

        The same role often appears on a company's ATS board and again in a
        search index, under slightly different titles. Normalising before
        hashing keeps those collapsed into one entry.
        """
        norm = " ".join(
            f"{self.company} {self.title} {self.location}".lower().split()
        )
        norm = re.sub(r"[^a-z0-9 ]", "", norm)
        return hashlib.sha256(norm.encode()).hexdigest()[:16]


class JobSource(Protocol):
    """A place jobs come from. Implementations must not raise on a bad board."""

    name: str

    def fetch(self, token: str) -> list[JobPosting]: ...


def strip_html(raw: str) -> str:
    """Flatten an HTML job description to readable text.

    Job descriptions arrive as HTML from most ATS APIs. The matcher reads plain
    text, and block-level tags need to become newlines or paragraphs run
    together into unreadable walls.
    """
    if not raw:
        return ""
    import html as html_mod

    # Unescape *first*. Greenhouse delivers its `content` HTML-escaped, so
    # stripping tags before unescaping is a no-op that then exposes raw markup
    # as body text. A second unescape afterwards catches entities that were
    # double-encoded or sit in text nodes (&amp;, &nbsp;).
    text = html_mod.unescape(raw)
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()
