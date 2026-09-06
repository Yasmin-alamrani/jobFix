"""Scoring must be pure: same inputs, same number, no API involved."""
from pathlib import Path

import pytest

from app.agents.analyst.parser import ParseReport, parse_pdf
from app.agents.analyst.schemas import (
    ExperienceFit, Fit, Importance, Requirement, Severity, Status, WritingReview,
)
from app.agents.analyst import scoring

FIXTURES = Path(__file__).parent / "fixtures"


def _fit(**kw):
    base = dict(jd_seniority="Senior", resume_seniority="Senior", fit=Fit.MATCH)
    base.update(kw)
    return ExperienceFit(**base)


def _req(skill, importance, status, evidence=""):
    return Requirement(skill=skill, importance=importance, status=status, evidence=evidence)


# --- ATS ---------------------------------------------------------------------

def test_scanned_pdf_scores_zero_parseability():
    """Plan verification 2: an image-only CV must score near zero."""
    report = parse_pdf(FIXTURES / "scanned.pdf")
    sub = scoring.score_ats(report)
    assert sub.earned == 0.0
    assert sub.deductions[0].rule == "ats.no_text_layer"
    assert sub.deductions[0].severity is Severity.CRITICAL


def test_clean_pdf_scores_full_parseability():
    report = parse_pdf(FIXTURES / "clean_single_column.pdf")
    sub = scoring.score_ats(report)
    assert sub.earned == sub.max_points, [d.title for d in sub.deductions]


def test_two_column_is_penalised_but_not_zeroed():
    report = parse_pdf(FIXTURES / "two_column.pdf")
    sub = scoring.score_ats(report)
    assert "ats.multi_column" in {d.rule for d in sub.deductions}
    assert 0 < sub.earned < sub.max_points


# --- Keywords ----------------------------------------------------------------

def test_all_requirements_present_earns_full_marks():
    reqs = [
        _req("Python", Importance.CRITICAL, Status.PRESENT, "Built services in Python"),
        _req("Kafka", Importance.PREFERRED, Status.PRESENT, "Kafka pipelines"),
    ]
    assert scoring.score_keywords(reqs).earned == scoring.WEIGHTS["keywords"]


def test_critical_missing_costs_double_a_preferred_missing():
    crit = scoring.score_keywords([
        _req("Python", Importance.CRITICAL, Status.MISSING),
        _req("Kafka", Importance.PREFERRED, Status.PRESENT, "x"),
    ])
    pref = scoring.score_keywords([
        _req("Python", Importance.CRITICAL, Status.PRESENT, "x"),
        _req("Kafka", Importance.PREFERRED, Status.MISSING),
    ])
    assert crit.earned < pref.earned


def test_weak_status_earns_half_credit():
    weak = scoring.score_keywords([_req("Python", Importance.CRITICAL, Status.WEAK, "scripting")])
    assert weak.earned == pytest.approx(scoring.WEIGHTS["keywords"] / 2)


def test_missing_requirement_fix_does_not_tell_user_to_fabricate():
    """The agent must never suggest inventing experience."""
    sub = scoring.score_keywords([_req("Kubernetes", Importance.CRITICAL, Status.MISSING)])
    fix = sub.deductions[0].fix.lower()
    assert "genuine gap" in fix
    assert "if you don't" in fix


def test_no_requirements_does_not_punish():
    assert scoring.score_keywords([]).earned == scoring.WEIGHTS["keywords"]


# --- Experience --------------------------------------------------------------

def test_matching_seniority_loses_nothing():
    assert scoring.score_experience(_fit()).earned == scoring.WEIGHTS["experience"]


def test_far_under_is_penalised_hardest():
    under = scoring.score_experience(_fit(fit=Fit.UNDER)).earned
    far = scoring.score_experience(_fit(fit=Fit.FAR_UNDER)).earned
    over = scoring.score_experience(_fit(fit=Fit.OVER)).earned
    assert far < under < over < scoring.WEIGHTS["experience"]


def test_years_shortfall_is_capped():
    """A wild shortfall must not drive the sub-score negative."""
    sub = scoring.score_experience(
        _fit(fit=Fit.FAR_UNDER, years_required=30.0, years_evidenced=0.0)
    )
    assert sub.earned >= 0.0


# --- Formatting --------------------------------------------------------------

def test_local_saudi_number_without_country_code_is_flagged():
    report = ParseReport(
        page_count=2, detected_sections=["experience", "education", "skills"],
        has_saudi_phone=True, phone_e164_ok=False,
    )
    rules = {d.rule for d in scoring.score_formatting(report, WritingReview(issues=[], summary_verdict="")).deductions}
    assert "fmt.phone_not_e164" in rules


def test_two_pages_is_not_penalised():
    """2-3 pages is normal; only >3 should cost points."""
    report = ParseReport(page_count=2, detected_sections=["experience", "education", "skills"])
    rules = {d.rule for d in scoring.score_formatting(report, WritingReview(issues=[], summary_verdict="")).deductions}
    assert "fmt.too_long" not in rules


# --- Aggregate ---------------------------------------------------------------

def test_score_is_deterministic_across_runs():
    """Plan verification 3: fixed sub-signals produce a reproducible /100."""
    report = parse_pdf(FIXTURES / "clean_single_column.pdf")
    reqs = [
        _req("Python", Importance.CRITICAL, Status.PRESENT, "Python"),
        _req("Kubernetes", Importance.CRITICAL, Status.MISSING),
        _req("Kafka", Importance.PREFERRED, Status.WEAK, "queues"),
    ]
    writing = WritingReview(issues=[], summary_verdict="ok")

    runs = {
        scoring.overall([
            scoring.score_ats(report), scoring.score_keywords(reqs),
            scoring.score_experience(_fit()), scoring.score_formatting(report, writing),
        ])
        for _ in range(20)
    }
    assert len(runs) == 1


def test_overall_never_exceeds_100_or_drops_below_0():
    report = parse_pdf(FIXTURES / "scanned.pdf")
    reqs = [_req(f"s{i}", Importance.CRITICAL, Status.MISSING) for i in range(12)]
    writing = WritingReview(
        issues=[], summary_verdict="",
    )
    subs = [
        scoring.score_ats(report), scoring.score_keywords(reqs),
        scoring.score_experience(_fit(fit=Fit.FAR_UNDER, years_required=20.0, years_evidenced=0.0)),
        scoring.score_formatting(report, writing),
    ]
    assert 0.0 <= scoring.overall(subs) <= 100.0


def test_top_fixes_are_ordered_by_points_recovered():
    report = parse_pdf(FIXTURES / "two_column.pdf")
    subs = [scoring.score_ats(report)]
    fixes = scoring.top_fixes(subs)
    assert fixes == sorted(fixes, key=lambda d: d.points, reverse=True)
