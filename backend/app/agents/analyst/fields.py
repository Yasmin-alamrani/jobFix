"""Which fields this CV fits, and how well.

The score is computed here, in Python, from evidence the model supplies. That is
the same split `scoring.py` uses against a single job posting, and it is here for
the same reasons: the number is reproducible, every point is traceable to a
named cause, and the model cannot flatter the candidate by inflating it.

The formula, out of 100:

    skills      50   how much of the field's core the CV evidences
    experience  30   evidenced years, saturating at SENIOR_YEARS
    titles      20   direct / adjacent / distant

Weights are deliberately skills-led. Someone with the skills and a short history
is a plausible hire into a field; someone with years in an adjacent field and
none of its skills is not, and a formula that let tenure dominate would tell
them otherwise.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.gemini import get_gemini, text_block
from app.prompts import data_block, fields_v1

from .industries import PACKS

log = logging.getLogger(__name__)

WEIGHTS = {"skills": 50.0, "experience": 30.0, "titles": 20.0}

# Years at which the experience component is full. Beyond this, more years do
# not make someone a better fit for the *field* -- they make them more senior
# within it, which is a different question and one the job-level audit asks.
SENIOR_YEARS = 5.0

TITLE_POINTS = {"direct": 20.0, "adjacent": 12.0, "distant": 4.0}

# A field is only worth showing if the CV gives some real purchase on it.
WORTH_SHOWING = 35.0


class FieldCandidate(BaseModel):
    """What the model reports for one field. No score -- that is computed."""

    key: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    years_in_field: float | None = None
    title_alignment: str = "distant"
    justification: str = ""


class FieldCandidates(BaseModel):
    fields: list[FieldCandidate]


class FieldComponent(BaseModel):
    key: str
    label: str
    earned: float
    max_points: float
    why: str


class FieldFit(BaseModel):
    """One field, scored, with the arithmetic left visible."""

    key: str
    label: str
    score: float
    components: list[FieldComponent]
    matched_skills: list[str]
    missing_skills: list[str]
    years_in_field: float | None
    title_alignment: str
    justification: str


def _catalogue() -> str:
    """The fields on offer, rendered for the prompt.

    Drawn from the existing industry packs rather than a second list, so the
    advice a user gets for a field ("these certifications matter here") comes
    from the same place the audit's tone and vocabulary already come from.
    """
    lines = []
    for pack in PACKS.values():
        if pack.key == "other":
            continue
        emphasis = "; ".join(pack.emphasis)
        lines.append(f"- {pack.key}: {pack.label}. Core signals: {emphasis}")
    return "\n".join(lines)


def _skills_component(candidate: FieldCandidate) -> FieldComponent:
    matched, missing = len(candidate.matched_skills), len(candidate.missing_skills)
    total = matched + missing
    maximum = WEIGHTS["skills"]

    if total == 0:
        # No signals either way is not evidence of a fit. Award nothing rather
        # than full marks -- "nothing to match means everything matched" is the
        # bug that would report a comfortable score for an empty CV.
        return FieldComponent(
            key="skills", label="Core skills", earned=0.0, max_points=maximum,
            why="The CV gives no evidence either way for this field's core skills.",
        )

    earned = round(maximum * matched / total, 1)
    return FieldComponent(
        key="skills", label="Core skills", earned=earned, max_points=maximum,
        why=f"Evidences {matched} of {total} core skills for this field.",
    )


def _experience_component(candidate: FieldCandidate) -> FieldComponent:
    maximum = WEIGHTS["experience"]
    years = candidate.years_in_field

    if years is None:
        # The model could not evidence a number from the dates. Half marks would
        # be inventing one; zero says plainly that the CV does not show it.
        return FieldComponent(
            key="experience", label="Evidenced experience", earned=0.0,
            max_points=maximum,
            why="The dates in the CV do not evidence time spent in this field.",
        )

    earned = round(maximum * min(years, SENIOR_YEARS) / SENIOR_YEARS, 1)
    return FieldComponent(
        key="experience", label="Evidenced experience", earned=earned,
        max_points=maximum,
        why=f"{years:g} year(s) evidenced, out of {SENIOR_YEARS:g} for full marks.",
    )


def _titles_component(candidate: FieldCandidate) -> FieldComponent:
    alignment = (candidate.title_alignment or "distant").lower()
    earned = TITLE_POINTS.get(alignment, TITLE_POINTS["distant"])
    reasons = {
        "direct": "Job titles in the CV are titles from this field.",
        "adjacent": "Titles are from a neighbouring discipline that transfers.",
        "distant": "Moving into this field would be a career change.",
    }
    return FieldComponent(
        key="titles", label="Title alignment", earned=earned,
        max_points=WEIGHTS["titles"],
        why=reasons.get(alignment, reasons["distant"]),
    )


def score_field(candidate: FieldCandidate) -> FieldFit | None:
    """Turn one candidate's evidence into a scored fit. None for unknown keys."""
    pack = PACKS.get(candidate.key)
    if pack is None:
        log.warning("model returned an unknown field key: %r", candidate.key)
        return None

    components = [
        _skills_component(candidate),
        _experience_component(candidate),
        _titles_component(candidate),
    ]
    return FieldFit(
        key=candidate.key,
        label=pack.label,
        score=round(sum(c.earned for c in components), 1),
        components=components,
        matched_skills=candidate.matched_skills,
        missing_skills=candidate.missing_skills,
        years_in_field=candidate.years_in_field,
        title_alignment=candidate.title_alignment,
        justification=candidate.justification,
    )


def suggest_fields(resume_text: str, *, limit: int = 5) -> list[FieldFit]:
    """The fields this CV fits, best first.

    Returns [] rather than raising when nothing clears `WORTH_SHOWING`. An empty
    result is an honest answer -- it means the CV does not yet read as belonging
    to any of these fields, which is exactly what its owner needs to know.
    """
    text = resume_text.strip()
    if not text:
        return []

    result = get_gemini().call_structured(
        schema=FieldCandidates,
        system=fields_v1.system(_catalogue()),
        content=[text_block(data_block("resume_text", text[:30_000]))],
    )

    scored = [fit for fit in map(score_field, result.fields) if fit is not None]
    scored = [fit for fit in scored if fit.score >= WORTH_SHOWING]
    scored.sort(key=lambda fit: fit.score, reverse=True)
    return scored[:limit]
