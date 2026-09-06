"""Analyzer wiring, exercised without touching the API."""
from pathlib import Path

import pytest

from app.agents.analyst import analyzer
from app.agents.analyst.schemas import (
    ExperienceFit, Fit, Importance, Requirement, Severity, Status,
    WritingIssue, WritingReview,
)

FIXTURES = Path(__file__).parent / "fixtures"

JD = """Senior Backend Engineer - Riyadh
Required: 5+ years Python, PostgreSQL, distributed systems, payments experience.
Preferred: Kafka, Kubernetes, Arabic language."""


class StubClaude:
    """Stands in for the model, returning fixed evidence."""

    def __init__(self):
        self.calls = []

    def call_structured(self, *, schema, system, content, **kw):
        self.calls.append({"schema": schema.__name__, "system": system, "content": content})
        if schema is WritingReview:
            return WritingReview(
                issues=[
                    WritingIssue(
                        section="Experience",
                        original="Responsible for the payouts API",
                        suggested="Designed the merchant payouts API used by 8,000 restaurants",
                        why="Unquantified duty; the number appears elsewhere in the resume.",
                        severity=Severity.MAJOR,
                    )
                ],
                summary_verdict="Solid but under-quantified.",
            )
        return schema(
            requirements=[
                Requirement(skill="Python", importance=Importance.CRITICAL,
                            status=Status.PRESENT, evidence="Built services in Python"),
                Requirement(skill="Kubernetes", importance=Importance.PREFERRED,
                            status=Status.MISSING),
            ],
            experience=ExperienceFit(
                jd_seniority="Senior", resume_seniority="Senior", fit=Fit.MATCH,
                years_required=5.0, years_evidenced=4.0, evidence=["2020 - Present"],
            ),
        )


@pytest.fixture
def stub(monkeypatch):
    s = StubClaude()
    monkeypatch.setattr(analyzer, "get_claude", lambda: s)
    return s


def test_full_analysis_produces_a_scored_result(stub):
    result = analyzer.analyze(
        resume_path=FIXTURES / "clean_single_column.pdf",
        job_description=JD, industry="fintech", job_title="Senior Backend Engineer",
    )
    assert 0 < result.overall_score <= 100
    assert len(result.sub_scores) == 4
    assert {s.key for s in result.sub_scores} == {"ats", "keywords", "experience", "formatting"}
    # The score is the sum of its parts -- nothing is added or hidden.
    assert result.overall_score == pytest.approx(sum(s.earned for s in result.sub_scores), abs=0.1)


def test_every_deduction_carries_evidence_and_a_fix(stub):
    """No unexplained point losses -- the core promise of the dashboard."""
    result = analyzer.analyze(
        resume_path=FIXTURES / "clean_single_column.pdf",
        job_description=JD, industry="tech",
    )
    for sub in result.sub_scores:
        for d in sub.deductions:
            assert d.rule and d.title, d
            assert d.evidence.strip(), f"{d.rule} has no evidence"
            assert d.fix.strip(), f"{d.rule} has no fix"
            assert d.points > 0, d


def test_both_prompts_forbid_fabrication(stub):
    analyzer.analyze(resume_path=FIXTURES / "clean_single_column.pdf",
                     job_description=JD, industry="tech")
    assert len(stub.calls) == 2
    for call in stub.calls:
        assert "never invent" in call["system"].lower()


def test_writing_prompt_does_not_ask_for_photo_or_iqama(stub):
    """The user corrected this: Saudi CVs follow international norms."""
    analyzer.analyze(resume_path=FIXTURES / "clean_single_column.pdf",
                     job_description=JD, industry="banking")
    writing_prompt = next(c["system"] for c in stub.calls if "writing" in c["system"].lower()
                          or "visual structure" in c["system"].lower())
    assert "do not suggest adding a" in writing_prompt.lower()
    for banned in ["photograph", "Iqama", "date of birth", "marital status"]:
        assert banned in writing_prompt


def test_writing_call_receives_the_actual_pdf(stub):
    """Layout can only be judged from the rendered document."""
    analyzer.analyze(resume_path=FIXTURES / "clean_single_column.pdf",
                     job_description=JD, industry="tech")
    writing_call = [c for c in stub.calls if c["schema"] == "WritingReview"][0]
    assert any(b.get("type") == "document" for b in writing_call["content"])


def test_arabic_resume_gets_bilingual_handling(stub):
    analyzer.analyze(resume_path=FIXTURES / "arabic.pdf",
                     job_description=JD, industry="government")
    writing_call = [c for c in stub.calls if c["schema"] == "WritingReview"][0]
    assert "do not treat" in writing_call["system"].lower()


def test_scanned_resume_short_circuits_without_calling_the_model(stub):
    """No text layer means nothing to reason over -- don't spend a request on it."""
    result = analyzer.analyze(resume_path=FIXTURES / "scanned.pdf",
                              job_description=JD, industry="tech")
    assert stub.calls == []
    assert result.sub_scores[0].earned == 0.0
    assert "no machine-readable text" in result.writing.summary_verdict


def test_top_fixes_are_capped_and_ranked(stub):
    result = analyzer.analyze(resume_path=FIXTURES / "two_column.pdf",
                              job_description=JD, industry="tech")
    assert len(result.top_fixes) <= 5
    assert result.top_fixes == sorted(result.top_fixes, key=lambda d: d.points, reverse=True)


def test_unreadable_resume_scores_zero_not_a_comfortable_number(stub):
    """Regression: an image-only CV once scored 61/100.

    Every dimension except parseability was silently awarded full marks --
    'no requirements extracted' read as 'matched everything'. A resume that
    reaches recruiters blank must not report a passing score.
    """
    result = analyzer.analyze(resume_path=FIXTURES / "scanned.pdf",
                              job_description=JD, industry="tech")
    assert result.overall_score == 0.0
    assert all(s.earned == 0.0 for s in result.sub_scores)
    # And every zeroed dimension explains itself.
    for sub in result.sub_scores:
        assert sub.deductions, f"{sub.key} scored 0 with no reason given"
        for d in sub.deductions:
            assert d.evidence.strip() and d.fix.strip()
