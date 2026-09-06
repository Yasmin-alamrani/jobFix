"""Stage 2: score the shortlist against the CV, with evidence.

Reuses the analyst's scoring engine deliberately. The scout and the resume
audit must never disagree about how well a CV fits a posting -- if the brief
says 82 and opening the same job in the audit says 61, neither number is
trustworthy. So the model does the same job here as it does there (extract
requirements, judge seniority) and `analyst/scoring.py` does the arithmetic.

Only the two CV-vs-JD dimensions apply. ATS parseability and formatting are
properties of the resume, identical for every job, so including them would add
a constant to all scores and tell the user nothing about which role fits best.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from app.agents.analyst import scoring
from app.agents.analyst.schemas import Deduction, ExperienceFit, Fit, Requirement
from app.sources.base import JobPosting

from .llm import OpenRouter, OpenRouterError
from .prefilter import Candidate

log = logging.getLogger(__name__)

# Keywords (35) + experience (20). Normalised to 100 for display.
MATCH_MAX = scoring.WEIGHTS["keywords"] + scoring.WEIGHTS["experience"]

SYSTEM = """You are screening one job posting against one candidate's CV for the Saudi market.

ABSOLUTE CONSTRAINT: never invent, embellish, or imply experience the CV does not
already evidence. If the CV does not show something, mark it missing. A genuine
gap named plainly is useful; a fabricated qualification is not, because the
candidate will be asked about it in an interview.

Extract every distinct requirement from the posting. Mark `critical` if the
posting states it as required, essential, or a must-have; `preferred` otherwise.
Then judge each against the CV:
  - "present": the CV gives direct, specific evidence. Quote it verbatim in `evidence`.
  - "weak": implied or adjacent, but not demonstrated. Quote the closest evidence.
  - "missing": no evidence at all. Leave `evidence` empty.

Then assess seniority fit. Set `years_evidenced` from actual dates in the CV, or
null rather than guessing. `fit` is one of: over, match, under, far_under.

Return ONLY a JSON object of this exact shape:
{
  "requirements": [
    {"skill": str, "importance": "critical"|"preferred",
     "status": "present"|"weak"|"missing", "evidence": str, "note": str}
  ],
  "experience": {
    "jd_seniority": str, "resume_seniority": str,
    "years_required": number|null, "years_evidenced": number|null,
    "fit": "over"|"match"|"under"|"far_under",
    "gaps": [str], "evidence": [str]
  }
}

Be accurate rather than generous. An inflated match costs the candidate a real
interview when they apply to the wrong role."""


class _MatchCall(BaseModel):
    requirements: list[Requirement]
    experience: ExperienceFit


@dataclass
class Match:
    """One scored job, with every point traceable to a rule and a quote."""

    job: JobPosting
    score: float                      # out of 100
    requirements: list[Requirement]
    experience: ExperienceFit
    deductions: list[Deduction]
    prefilter_similarity: float = 0.0
    error: str = ""                   # set when the model call failed

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def missing_critical(self) -> list[str]:
        return [
            r.skill for r in self.requirements
            if r.status.value == "missing" and r.importance.value == "critical"
        ]

    @property
    def matched(self) -> list[str]:
        return [r.skill for r in self.requirements if r.status.value == "present"]


def _truncate(text: str, limit: int = 6000) -> str:
    """Job descriptions run long and the tail is usually boilerplate.

    Requirements appear early; equal-opportunity statements and benefits do not
    change the match. Cutting here keeps per-job cost predictable.
    """
    return text if len(text) <= limit else text[:limit] + "\n[...truncated]"


def match_one(client: OpenRouter, resume_text: str, candidate: Candidate) -> Match:
    """Score a single job. Never raises -- a failed job must not end the scan."""
    job = candidate.job
    user = (
        f"JOB POSTING\n---\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Location: {job.location}\n\n{_truncate(job.description)}\n---\n\n"
        f"CANDIDATE CV\n---\n{_truncate(resume_text, 8000)}\n---"
    )

    try:
        result = client.complete_json(schema=_MatchCall, system=SYSTEM, user=user)
    except OpenRouterError as exc:
        log.warning("match failed for %s @ %s: %s", job.title, job.company, exc)
        return Match(
            job=job, score=0.0, requirements=[],
            experience=ExperienceFit(jd_seniority="unknown", resume_seniority="unknown",
                                     fit=Fit.UNDER),
            deductions=[], prefilter_similarity=candidate.similarity, error=str(exc),
        )

    kw = scoring.score_keywords(result.requirements)
    exp = scoring.score_experience(result.experience)
    earned = kw.earned + exp.earned

    return Match(
        job=job,
        score=round(100 * earned / MATCH_MAX, 1),
        requirements=result.requirements,
        experience=result.experience,
        deductions=sorted(kw.deductions + exp.deductions, key=lambda d: d.points, reverse=True),
        prefilter_similarity=candidate.similarity,
    )


def match_all(
    client: OpenRouter,
    resume_text: str,
    candidates: list[Candidate],
    *,
    limit: int = 12,
) -> list[Match]:
    """Score the shortlist, best first.

    `limit` is the real cost control: the prefilter has already ordered every
    job for free, so this only pays for the ones plausibly worth reading.
    """
    matches = [match_one(client, resume_text, c) for c in candidates[:limit]]
    matches.sort(key=lambda m: (m.ok, m.score), reverse=True)
    return matches
