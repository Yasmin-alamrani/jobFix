"""Agent 1: the resume analyst.

Two model calls, deliberately split by what they need to see:

  A. Requirement extraction + seniority fit -- reasons over resume *text*
     against the job description.
  B. Writing review -- gets the actual PDF, because judging layout and
     visual hierarchy from extracted text is guesswork.

Neither call returns a score. They return evidence; `scoring.py` does the
arithmetic. That is what keeps the number reproducible and every deduction
traceable to a quoted span.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from app.core.claude import get_claude, pdf_block, text_block

from . import scoring
from .industries import prompt_fragment
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

# The single most important instruction in this application. A resume tool that
# invents experience produces a candidate who cannot answer for their own CV in
# an interview, and that is a worse outcome than a low score.
NO_FABRICATION = """
ABSOLUTE CONSTRAINT -- never violate this, whatever else is asked of you:
You must never invent, embellish, or imply experience the resume does not
already evidence. Specifically, you must not introduce an employer, job title,
date, degree, certification, tool, metric, or achievement that is not already
present in the resume text.

When a requirement is absent, say it is absent. A genuine gap, named plainly,
is useful to the candidate. A fabricated qualification is not -- they will be
asked about it in an interview and will not be able to answer.

Rewrites may only rephrase, quantify what is already stated, reorder, or align
existing wording with the job description's vocabulary.
""".strip()


class _MatchCall(BaseModel):
    """Combined result of call A -- both halves reason over the same context."""

    requirements: list[Requirement]
    experience: ExperienceFit


def _match_system(industry: str) -> str:
    return f"""You are an experienced technical recruiter screening a resume against a
specific job description for the Saudi Arabian market.

{prompt_fragment(industry)}

{NO_FABRICATION}

Your task has two parts.

1. Extract every distinct requirement from the job description. Mark each
   `critical` if the posting states it as required, essential, or a must-have;
   `preferred` otherwise. Then judge each against the resume:
     - `present`: the resume gives direct, specific evidence. Quote it verbatim
       in `evidence`.
     - `weak`: the resume implies it or shows something adjacent, but does not
       demonstrate it. Quote the closest evidence.
     - `missing`: no evidence at all. Leave `evidence` empty.
   Do not merge distinct requirements, and do not invent requirements the
   posting does not state.

2. Assess seniority fit. Use `years_evidenced` from actual dates in the resume;
   leave it null rather than guessing. Back the assessment with verbatim quotes.

Be accurate rather than generous. An inflated assessment costs the candidate a
real interview."""


def _writing_system(industry: str, report: ParseReport) -> str:
    bilingual = (
        "\nThis resume contains Arabic. Assess it on its own terms -- do not treat "
        "a non-English resume as a defect, and keep suggested text in the language "
        "of the span you are replacing."
        if report.is_bilingual or report.primary_language == "ar"
        else ""
    )
    return f"""You are reviewing the writing and visual structure of a resume for the
Saudi Arabian market. You can see the actual document, so judge layout,
hierarchy and readability as rendered.

{prompt_fragment(industry)}

{NO_FABRICATION}

Report concrete, actionable issues. For each, quote the current text verbatim
in `original` and give the replacement in `suggested`. Prefer weak, unquantified
bullets ("responsible for X") that can be sharpened using numbers already
present elsewhere in the resume.

Severity: `critical` if it would cost an interview, `major` if it visibly
weakens the application, `minor` for polish. Report at most 12 issues, best
first. If the resume is genuinely strong, return few issues -- do not invent
problems to seem thorough.

Resume conventions here follow international standards. Do NOT suggest adding a
photograph, national ID, Iqama number, date of birth, marital status or
nationality; none of these belong on a modern CV.{bilingual}"""


def analyze(
    *,
    resume_path: Path,
    job_description: str,
    industry: str = "other",
    job_title: str = "",
) -> AnalysisResult:
    """Run the full analysis and return a scored, evidence-backed result."""
    report = parse_pdf(resume_path)
    claude = get_claude()

    if not report.has_extractable_text:
        # No text layer means the model has nothing to reason over and the ATS
        # has nothing to read. Every dimension is unassessable, so the honest
        # result is zero -- not a partial score built from dimensions we simply
        # failed to test. Awarding full keyword marks here (nothing to match =
        # matched everything) would report a comfortable number for a resume
        # that reaches recruiters blank.
        return _unreadable_result(report)

    role = f"Target role: {job_title}\n\n" if job_title else ""
    match = claude.call_structured(
        schema=_MatchCall,
        system=_match_system(industry),
        content=[
            text_block(
                f"{role}JOB DESCRIPTION\n---\n{job_description}\n---\n\n"
                f"RESUME TEXT\n---\n{report.text}\n---"
            )
        ],
    )

    writing = claude.call_structured(
        schema=WritingReview,
        system=_writing_system(industry, report),
        content=[
            pdf_block(resume_path),
            text_block(
                "Review the resume above against this job description.\n\n"
                f"JOB DESCRIPTION\n---\n{job_description}\n---"
            ),
        ],
    )

    subs = [
        scoring.score_ats(report),
        scoring.score_keywords(match.requirements),
        scoring.score_experience(match.experience),
        scoring.score_formatting(report, writing),
    ]

    return AnalysisResult(
        overall_score=scoring.overall(subs),
        sub_scores=subs,
        requirements=match.requirements,
        experience=match.experience,
        writing=writing,
        top_fixes=scoring.top_fixes(subs),
        parse_facts=_facts(report),
    )


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
