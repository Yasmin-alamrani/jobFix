"""Shared data contracts.

These serve double duty: they are the JSON schemas Claude must fill, and the
shapes the dashboard renders. Keeping them in one place means a model response
that would break the UI fails validation at the boundary instead.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Importance(str, Enum):
    CRITICAL = "critical"
    PREFERRED = "preferred"


class Status(str, Enum):
    PRESENT = "present"
    WEAK = "weak"
    MISSING = "missing"


class Fit(str, Enum):
    OVER = "over"
    MATCH = "match"
    UNDER = "under"
    FAR_UNDER = "far_under"


# --- What the model returns -------------------------------------------------


class Requirement(BaseModel):
    """One requirement lifted from the job description."""

    skill: str = Field(description="The requirement, as a short noun phrase.")
    importance: Importance = Field(
        description="critical if the JD lists it as required/must-have, else preferred."
    )
    status: Status = Field(
        description=(
            "present only when the resume gives direct evidence; weak when it is "
            "implied or adjacent; missing when there is no evidence at all."
        )
    )
    evidence: str = Field(
        default="",
        description=(
            "Verbatim quote from the resume supporting 'present' or 'weak'. "
            "Must be empty when status is missing. Never paraphrase."
        ),
    )
    note: str = Field(default="", description="One line on why this status was assigned.")


class RequirementList(BaseModel):
    requirements: list[Requirement]


class ExperienceFit(BaseModel):
    jd_seniority: str
    resume_seniority: str
    years_required: float | None = None
    years_evidenced: float | None = None
    fit: Fit
    gaps: list[str] = Field(default_factory=list, description="Concrete experience gaps.")
    evidence: list[str] = Field(
        default_factory=list, description="Verbatim resume quotes backing the assessment."
    )


class WritingIssue(BaseModel):
    """A single proposed edit, presented to the user as a redline."""

    section: str
    original: str = Field(description="Verbatim text currently in the resume.")
    suggested: str = Field(
        description=(
            "The replacement. Rephrase, quantify, or reorder only. Never introduce "
            "an employer, title, date, credential or metric not already present."
        )
    )
    why: str
    severity: Severity


class WritingReview(BaseModel):
    issues: list[WritingIssue]
    summary_verdict: str = Field(description="Two sentences on the resume's overall quality.")


# --- What we compute --------------------------------------------------------


class Deduction(BaseModel):
    rule: str
    title: str
    evidence: str
    fix: str
    points: float
    severity: Severity


class SubScore(BaseModel):
    key: str
    label: str
    earned: float
    max_points: float
    deductions: list[Deduction] = Field(default_factory=list)

    @property
    def pct(self) -> float:
        return round(100 * self.earned / self.max_points, 1) if self.max_points else 0.0


class AnalysisResult(BaseModel):
    overall_score: float
    sub_scores: list[SubScore]
    requirements: list[Requirement]
    experience: ExperienceFit
    writing: WritingReview
    top_fixes: list[Deduction]
    parse_facts: dict
