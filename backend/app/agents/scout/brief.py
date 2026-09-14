"""The brief: what the scan found, short enough to scan in ten seconds.

The per-job lines are templated from the match data rather than written by the
model. The plan originally had DeepSeek generate them, but the matcher already
returns exactly what a summary needs -- which requirements matched, which
critical ones are missing, how the seniority compares -- and a template over
that data is free, identical between runs, and structurally incapable of
contradicting the score printed beside it. A model asked to summarise the same
facts can drift ("strong match" next to a 41), and that is the one failure a
brief cannot afford.

The model is used for one thing only: an optional opening line across the whole
scan, where genuine synthesis helps and no single number is at stake.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

from .llm import ScoutModel, ScoutModelError
from .matcher import Match

log = logging.getLogger(__name__)

# Below this, a role is not worth the user's attention.
WORTH_IT = 60.0


@dataclass
class BriefLine:
    score: float
    title: str
    company: str
    location: str
    why: str
    gap: str
    url: str
    publisher: str = ""

    def render(self) -> str:
        where = f"{self.company}, {self.location}" if self.location else self.company
        via = f"  [via {self.publisher}]" if self.publisher else ""
        out = [f"  {self.score:>3.0f}  {self.title} — {where}{via}"]
        if self.why:
            out.append(f"      {self.why}")
        if self.gap:
            out.append(f"      {self.gap}")
        return "\n".join(out)


@dataclass
class Brief:
    total_found: int
    shortlisted: int
    lines: list[BriefLine] = field(default_factory=list)
    by_source: dict[str, int] = field(default_factory=dict)
    headline: str = ""
    failures: int = 0

    def render(self) -> str:
        sources = " · ".join(f"{k} {v}" for k, v in sorted(self.by_source.items()))
        worth = sum(1 for line in self.lines if line.score >= WORTH_IT)

        head = f"{self.total_found} roles found · {worth} worth your time"
        if sources:
            head += f"   ({sources})"

        parts = [head]
        if self.headline:
            parts += ["", self.headline]
        parts.append("")

        if not self.lines:
            parts.append("  Nothing matched. Try widening the location filter or the role title.")
        else:
            parts += [line.render() for line in self.lines]

        if self.failures:
            parts += ["", f"  {self.failures} role(s) could not be scored — see the log."]
        return "\n".join(parts)


_FIT_NOTE = {
    "over": "You read as more senior than this role.",
    "under": "Reads a level above where your CV sits.",
    "far_under": "Substantial seniority gap.",
}


def _why(match: Match) -> str:
    matched = match.matched
    if not matched:
        return "No requirements clearly evidenced in your CV."
    shown = ", ".join(matched[:3])
    extra = f" +{len(matched) - 3} more" if len(matched) > 3 else ""
    return f"Matched: {shown}{extra}."


def _gap(match: Match) -> str:
    bits: list[str] = []

    missing = match.missing_critical
    if missing:
        shown = ", ".join(missing[:2])
        more = f" +{len(missing) - 2}" if len(missing) > 2 else ""
        bits.append(f"Missing required: {shown}{more}.")

    exp = match.experience
    note = _FIT_NOTE.get(exp.fit.value)
    if note:
        bits.append(note)
    if (
        exp.years_required is not None
        and exp.years_evidenced is not None
        and exp.years_evidenced < exp.years_required
    ):
        bits.append(
            f"Asks {exp.years_required:g} yrs, your CV evidences {exp.years_evidenced:g}."
        )

    return " ".join(bits)


class _Headline(BaseModel):
    headline: str


HEADLINE_SYSTEM = """You are writing ONE sentence at the top of a job-search brief.

You are given the roles already found and scored. Say what the batch looks like
as a whole -- the shape of the opportunity, or the pattern in what is missing.
Do not restate individual scores, do not list the jobs, and do not encourage or
congratulate. Be plain and specific.

If the results are weak, say so directly; a candidate is better served by
knowing the batch is thin than by being cheered along.

Return ONLY: {"headline": "<one sentence>"}"""


def build(
    matches: list[Match],
    *,
    total_found: int,
    by_source: dict[str, int] | None = None,
    limit: int = 8,
    client: ScoutModel | None = None,
) -> Brief:
    """Assemble the brief. Costs nothing unless `client` is given for a headline."""
    scored = [m for m in matches if m.ok]
    failures = len(matches) - len(scored)

    lines = [
        BriefLine(
            score=m.score,
            title=m.job.title,
            company=m.job.company,
            location=m.job.location,
            why=_why(m),
            gap=_gap(m),
            url=m.job.apply_url,
            publisher=m.job.publisher,
        )
        for m in scored[:limit]
    ]

    brief = Brief(
        total_found=total_found,
        shortlisted=len(scored),
        lines=lines,
        by_source=by_source or {},
        failures=failures,
    )

    if client and lines:
        digest = "\n".join(
            f"{line.score:.0f} | {line.title} at {line.company} | {line.why} {line.gap}"
            for line in lines
        )
        try:
            brief.headline = client.complete_json(
                schema=_Headline, system=HEADLINE_SYSTEM,
                user=f"Roles found:\n{digest}", effort="low",
            ).headline.strip()
        except ScoutModelError as exc:
            # A missing headline is cosmetic; the brief stands without it.
            log.info("headline unavailable: %s", exc)

    return brief
