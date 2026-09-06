"""The /100 score.

Deliberately pure and deterministic: same inputs, same number, every time.
The model supplies evidence (which requirements exist, what is weak); the
arithmetic happens here. That split is what lets every lost point carry a
rule, a quoted span and a fix -- and what makes the score reproducible in a
unit test without touching the API.
"""
from __future__ import annotations

from .parser import ParseReport
from .schemas import (
    Deduction,
    ExperienceFit,
    Fit,
    Importance,
    Requirement,
    Severity,
    Status,
    SubScore,
    WritingReview,
)

WEIGHTS = {"ats": 25.0, "keywords": 35.0, "experience": 20.0, "formatting": 20.0}

# A critical requirement counts double a preferred one.
_IMPORTANCE_WEIGHT = {Importance.CRITICAL: 2.0, Importance.PREFERRED: 1.0}
# Partial credit for a requirement the resume only gestures at.
_STATUS_CREDIT = {Status.PRESENT: 1.0, Status.WEAK: 0.5, Status.MISSING: 0.0}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def score_ats(report: ParseReport) -> SubScore:
    """Machine-parseability. Deterministic only -- no model input."""
    maximum = WEIGHTS["ats"]
    deductions: list[Deduction] = []

    if not report.has_extractable_text:
        # Nothing else matters: the ATS receives an empty document.
        deductions.append(
            Deduction(
                rule="ats.no_text_layer",
                title="Resume has no machine-readable text",
                evidence=(
                    f"Only {report.char_count} extractable characters across "
                    f"{report.page_count} page(s)"
                    + ("; pages are images." if report.is_scanned else ".")
                ),
                fix=(
                    "Export the resume directly to PDF from your editor rather than "
                    "scanning or exporting as an image. Most ATS will read this as blank."
                ),
                points=maximum,
                severity=Severity.CRITICAL,
            )
        )
        return SubScore(key="ats", label="ATS parseability", earned=0.0,
                        max_points=maximum, deductions=deductions)

    if report.multi_column_pages:
        pages = ", ".join(str(p) for p in report.multi_column_pages)
        deductions.append(
            Deduction(
                rule="ats.multi_column",
                title="Multi-column layout",
                evidence=f"Side-by-side text columns detected on page(s) {pages}.",
                fix=(
                    "Move to a single-column layout. Many parsers read across columns "
                    "and interleave the two, scrambling your job titles and dates."
                ),
                points=8.0,
                severity=Severity.CRITICAL,
            )
        )

    if report.table_pages:
        pages = ", ".join(str(p) for p in report.table_pages)
        deductions.append(
            Deduction(
                rule="ats.tables",
                title="Content laid out in tables",
                evidence=f"Table structures on page(s) {pages}.",
                fix="Replace tables with plain paragraphs or bullets; cell content is often dropped.",
                points=4.0,
                severity=Severity.MAJOR,
            )
        )

    if report.header_footer_text:
        sample = "; ".join(report.header_footer_text[:2])[:160]
        deductions.append(
            Deduction(
                rule="ats.header_footer",
                title="Text sits in the page header or footer",
                evidence=f'Found in the header/footer band: "{sample}"',
                fix=(
                    "Move this into the body of the page. If your contact details are "
                    "up there, an ATS may discard them entirely."
                ),
                points=5.0 if not report.has_email else 3.0,
                severity=Severity.MAJOR,
            )
        )

    if not report.has_email:
        deductions.append(
            Deduction(
                rule="ats.no_email",
                title="No email address found",
                evidence="No address matching an email pattern in the extracted text.",
                fix="Add a plain-text email in the body, not inside an image or header.",
                points=5.0,
                severity=Severity.CRITICAL,
            )
        )

    if not report.has_phone:
        deductions.append(
            Deduction(
                rule="ats.no_phone",
                title="No phone number found",
                evidence="No phone-shaped string in the extracted text.",
                fix="Add a contact number in the body of the resume.",
                points=3.0,
                severity=Severity.MAJOR,
            )
        )

    if report.non_embedded_fonts:
        fonts = ", ".join(report.non_embedded_fonts[:3])
        deductions.append(
            Deduction(
                rule="ats.fonts_not_embedded",
                title="Fonts are not embedded",
                evidence=f"Non-embedded: {fonts}",
                fix="Re-export with fonts embedded, or switch to a standard face, so text extracts reliably.",
                points=2.0,
                severity=Severity.MINOR,
            )
        )

    total = sum(d.points for d in deductions)
    return SubScore(key="ats", label="ATS parseability",
                    earned=_clamp(maximum - total, 0.0, maximum),
                    max_points=maximum, deductions=deductions)


def score_keywords(requirements: list[Requirement]) -> SubScore:
    """Weighted coverage of JD requirements. A set intersection, not a judgement."""
    maximum = WEIGHTS["keywords"]
    if not requirements:
        return SubScore(key="keywords", label="Keyword & skill match",
                        earned=maximum, max_points=maximum)

    possible = sum(_IMPORTANCE_WEIGHT[r.importance] for r in requirements)
    achieved = sum(
        _IMPORTANCE_WEIGHT[r.importance] * _STATUS_CREDIT[r.status] for r in requirements
    )
    earned = maximum * (achieved / possible) if possible else maximum

    deductions: list[Deduction] = []
    for req in requirements:
        if req.status is Status.PRESENT:
            continue
        lost = maximum * (
            _IMPORTANCE_WEIGHT[req.importance] * (1 - _STATUS_CREDIT[req.status]) / possible
        )
        missing = req.status is Status.MISSING
        deductions.append(
            Deduction(
                rule=f"kw.{req.status.value}.{req.importance.value}",
                title=f"{'Missing' if missing else 'Weakly evidenced'}: {req.skill}",
                evidence=(
                    "Not found anywhere in the resume."
                    if missing
                    else f'Closest evidence: "{req.evidence[:200]}"'
                ),
                fix=(
                    f"The job description lists this as {req.importance.value}. "
                    + (
                        "If you have this experience, add it explicitly with the same wording "
                        "the posting uses. If you don't, treat it as a genuine gap to close "
                        "rather than something to add."
                        if missing
                        else "Make it explicit and quantify it, using the posting's wording."
                    )
                ),
                points=round(lost, 2),
                severity=(
                    Severity.CRITICAL
                    if missing and req.importance is Importance.CRITICAL
                    else Severity.MAJOR
                    if missing
                    else Severity.MINOR
                ),
            )
        )

    return SubScore(key="keywords", label="Keyword & skill match",
                    earned=round(_clamp(earned, 0.0, maximum), 2),
                    max_points=maximum, deductions=deductions)


_FIT_PENALTY = {Fit.MATCH: 0.0, Fit.OVER: 2.0, Fit.UNDER: 8.0, Fit.FAR_UNDER: 15.0}
_FIT_NOTE = {
    Fit.OVER: "You read as more senior than the posting. Frame your experience toward "
              "the scope of this role so you don't screen out as overqualified.",
    Fit.UNDER: "You read as less senior than the posting asks. Lead with your largest-scope "
               "work and make ownership explicit.",
    Fit.FAR_UNDER: "There is a substantial seniority gap. Worth applying only with a strong "
                   "referral, or targeting the level below.",
}


def score_experience(fit: ExperienceFit) -> SubScore:
    maximum = WEIGHTS["experience"]
    deductions: list[Deduction] = []

    penalty = _FIT_PENALTY[fit.fit]
    if penalty:
        deductions.append(
            Deduction(
                rule=f"exp.{fit.fit.value}",
                title=f"Seniority: resume reads {fit.resume_seniority}, posting asks {fit.jd_seniority}",
                evidence="; ".join(fit.evidence[:2])[:240] or "Based on titles and scope in the resume.",
                fix=_FIT_NOTE[fit.fit],
                points=penalty,
                severity=Severity.CRITICAL if fit.fit is Fit.FAR_UNDER else Severity.MAJOR,
            )
        )

    if (
        fit.years_required is not None
        and fit.years_evidenced is not None
        and fit.years_evidenced < fit.years_required
    ):
        shortfall = fit.years_required - fit.years_evidenced
        deductions.append(
            Deduction(
                rule="exp.years_short",
                title=f"{shortfall:.1f} years short of the stated requirement",
                evidence=f"Resume evidences ~{fit.years_evidenced:.1f} years; posting asks {fit.years_required:.1f}.",
                fix=(
                    "Check for relevant experience you haven't counted -- internships, "
                    "freelance, or in-role project work often go unlisted."
                ),
                points=_clamp(shortfall * 1.5, 0.0, 6.0),
                severity=Severity.MAJOR,
            )
        )

    for gap in fit.gaps[:3]:
        deductions.append(
            Deduction(
                rule="exp.gap", title=f"Experience gap: {gap}", evidence=gap,
                fix="Address directly in your cover letter rather than leaving it unexplained.",
                points=1.0, severity=Severity.MINOR,
            )
        )

    total = sum(d.points for d in deductions)
    return SubScore(key="experience", label="Experience & seniority fit",
                    earned=round(_clamp(maximum - total, 0.0, maximum), 2),
                    max_points=maximum, deductions=deductions)


_SEVERITY_COST = {Severity.CRITICAL: 4.0, Severity.MAJOR: 2.0, Severity.MINOR: 0.5}


def score_formatting(report: ParseReport, writing: WritingReview) -> SubScore:
    maximum = WEIGHTS["formatting"]
    deductions: list[Deduction] = []

    if report.page_count > 3:
        deductions.append(
            Deduction(
                rule="fmt.too_long", title=f"{report.page_count} pages",
                evidence=f"Document is {report.page_count} pages.",
                fix="Trim to at most 2-3 pages, keeping the most recent and most relevant roles.",
                points=3.0, severity=Severity.MAJOR,
            )
        )

    missing_core = {"experience", "education", "skills"} - set(report.detected_sections)
    if missing_core:
        names = ", ".join(sorted(missing_core))
        deductions.append(
            Deduction(
                rule="fmt.missing_sections", title=f"No clear section heading for: {names}",
                evidence=f"Headings found: {', '.join(report.detected_sections) or 'none'}",
                fix=(
                    "Use conventional headings (Experience, Education, Skills). Parsers key "
                    "off these to file your content into the right fields."
                ),
                points=2.0 * len(missing_core), severity=Severity.MAJOR,
            )
        )

    if report.nonstandard_headings:
        sample = ", ".join(report.nonstandard_headings[:3])
        deductions.append(
            Deduction(
                rule="fmt.nonstandard_headings", title="Unconventional section headings",
                evidence=f"Styled as headings but not recognised: {sample}",
                fix="Rename to the conventional equivalent so a parser knows what the section is.",
                points=1.5, severity=Severity.MINOR,
            )
        )

    # Saudi market: a local 05X number isn't dialable from outside the country.
    if report.has_saudi_phone and not report.phone_e164_ok:
        deductions.append(
            Deduction(
                rule="fmt.phone_not_e164", title="Phone number missing the +966 country code",
                evidence="Found a local-format Saudi mobile (05X) with no international prefix.",
                fix="Write it as +966 5X XXX XXXX so recruiters outside the Kingdom can dial it.",
                points=1.0, severity=Severity.MINOR,
            )
        )

    for issue in writing.issues:
        deductions.append(
            Deduction(
                rule="fmt.writing", title=f"{issue.section}: {issue.why[:80]}",
                evidence=issue.original[:200], fix=issue.suggested[:300],
                points=_SEVERITY_COST[issue.severity], severity=issue.severity,
            )
        )

    total = sum(d.points for d in deductions)
    return SubScore(key="formatting", label="Formatting & structure",
                    earned=round(_clamp(maximum - total, 0.0, maximum), 2),
                    max_points=maximum, deductions=deductions)


def overall(sub_scores: list[SubScore]) -> float:
    return round(sum(s.earned for s in sub_scores), 1)


def top_fixes(sub_scores: list[SubScore], limit: int = 5) -> list[Deduction]:
    """Highest-value fixes first -- what actually moves the score."""
    every = [d for s in sub_scores for d in s.deductions]
    return sorted(every, key=lambda d: d.points, reverse=True)[:limit]
