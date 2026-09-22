"""Agent 1: the resume analyst.

Two model calls, deliberately split by what they need to see:

  A. Requirement extraction + seniority fit -- reasons over resume *text*
     against the job description.
  B. Writing review -- gets the actual PDF, because judging layout and
     visual hierarchy from extracted text is guesswork.

Neither call returns a score. They return evidence; `scoring.py` does the
arithmetic. That is what keeps the number reproducible and every deduction
traceable to a quoted span.

The prompts themselves live in `app/prompts/analyst_v2.py` and are versioned,
because a change to their wording changes the evidence and therefore every
score produced afterwards. The version is recorded on each result.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from app.core.gemini import get_gemini, pdf_block, text_block
from app.core.i18n import Lang, tr, tr_fields, with_language
from app.prompts import analyst_v2, data_block

from . import scoring
from .parser import ParseReport, parse_pdf
from .schemas import (
    AnalysisResult,
    Deduction,
    ExperienceFit,
    Fit,
    Requirement,
    Severity,
    SubScore,
    WritingReview,
)

log = logging.getLogger(__name__)


class _MatchCall(BaseModel):
    """Combined result of call A -- both halves reason over the same context."""

    requirements: list[Requirement]
    experience: ExperienceFit


def analyze(
    *,
    resume_path: Path,
    job_description: str,
    industry: str = "other",
    job_title: str = "",
    lang: Lang = "en",
) -> AnalysisResult:
    """Run the full analysis and return a scored, evidence-backed result."""
    report = parse_pdf(resume_path)
    model = get_gemini()

    if not report.has_extractable_text:
        # No text layer means the model has nothing to reason over and the ATS
        # has nothing to read. Every dimension is unassessable, so the honest
        # result is zero -- not a partial score built from dimensions we simply
        # failed to test. Awarding full keyword marks here (nothing to match =
        # matched everything) would report a comfortable number for a resume
        # that reaches recruiters blank.
        return _localized(_unreadable_result(report), lang)

    role = f"Target role: {job_title}\n\n" if job_title else ""
    match = model.call_structured(
        schema=_MatchCall,
        system=with_language(analyst_v2.match_system(industry), lang),
        content=[
            text_block(
                role
                + data_block("job_description", job_description)
                + "\n\n"
                + data_block("resume_text", report.text)
            )
        ],
    )

    writing = model.call_structured(
        schema=WritingReview,
        system=with_language(analyst_v2.writing_system(
            industry,
            bilingual=report.is_bilingual or report.primary_language == "ar",
        ), lang),
        content=[
            pdf_block(resume_path),
            text_block(
                "Review the resume above against this job description.\n\n"
                + data_block("job_description", job_description)
            ),
        ],
    )

    subs = [
        scoring.score_ats(report),
        scoring.score_keywords(match.requirements),
        scoring.score_experience(match.experience),
        scoring.score_formatting(report, writing),
    ]

    result = AnalysisResult(
        overall_score=scoring.overall(subs),
        sub_scores=subs,
        requirements=match.requirements,
        experience=match.experience,
        writing=writing,
        top_fixes=scoring.top_fixes(subs),
        parse_facts=_facts(report),
        prompt_version=analyst_v2.VERSION,
    )
    return _localized(result, lang)


def _localized(result: AnalysisResult, lang: Lang) -> AnalysisResult:
    """The deductions' wording in the page's language.

    Scored first, translated after: the arithmetic never sees a translation,
    and a quote inside a deduction's evidence is left as the CV wrote it.
    """
    if lang != "ar":
        return result

    def deduction(d):
        return tr_fields(d, lang, "title", "evidence", "fix")

    return result.model_copy(update={
        "sub_scores": [
            s.model_copy(update={"label": tr(s.label, lang),
                                 "deductions": [deduction(d) for d in s.deductions]})
            for s in result.sub_scores
        ],
        "top_fixes": [deduction(d) for d in result.top_fixes],
        "writing": tr_fields(result.writing, lang, "summary_verdict"),
    })


def _facts(report: ParseReport) -> dict:
    """The measured facts, surfaced to the UI so the score is auditable."""
    return {
        "page_count": report.page_count,
        "char_count": report.char_count,
        "is_scanned": report.is_scanned,
        "has_extractable_text": report.has_extractable_text,
        "multi_column_pages": report.multi_column_pages,
        "table_pages": report.table_pages,
        "detected_sections": report.detected_sections,
        "nonstandard_headings": report.nonstandard_headings,
        "has_email": report.has_email,
        "has_phone": report.has_phone,
        "primary_language": report.primary_language,
        "is_bilingual": report.is_bilingual,
    }


def _unreadable_result(report: ParseReport) -> AnalysisResult:
    """Score for a document with no text layer: zero, with one clear reason."""
    ats = scoring.score_ats(report)
    reason = ats.deductions[0] if ats.deductions else None

    def blanked(key: str, label: str, maximum: float) -> SubScore:
        note = Deduction(
            rule="unreadable.not_assessable",
            title=f"{label} could not be assessed",
            evidence=(
                f"Only {report.char_count} extractable characters across "
                f"{report.page_count} page(s)."
            ),
            fix="Re-export the resume as a text PDF and run the audit again.",
            points=maximum,
            severity=Severity.CRITICAL,
        )
        return SubScore(key=key, label=label, earned=0.0, max_points=maximum,
                        deductions=[note])

    subs = [
        ats,
        blanked("keywords", "Keyword & skill match", scoring.WEIGHTS["keywords"]),
        blanked("experience", "Experience & seniority fit", scoring.WEIGHTS["experience"]),
        blanked("formatting", "Formatting & structure", scoring.WEIGHTS["formatting"]),
    ]
    writing = WritingReview(
        issues=[],
        summary_verdict=(
            "This file has no machine-readable text, so neither an applicant "
            "tracking system nor this audit can read it. Re-export it as a text "
            "PDF -- straight from your editor rather than as a scan or image -- "
            "and run it again."
        ),
    )
    return AnalysisResult(
        overall_score=scoring.overall(subs), sub_scores=subs, requirements=[],
        experience=ExperienceFit(jd_seniority="unknown", resume_seniority="unknown",
                                 fit=Fit.FAR_UNDER),
        writing=writing,
        top_fixes=[reason] if reason else [],
        parse_facts=_facts(report),
    )
