"""Field matching, and the arithmetic behind the fit score.

Most of this file tests `score_field`, which takes model evidence and returns a
number. That function does not call the model at all, so these are ordinary
arithmetic tests -- which is the point of computing the score in Python.
"""
from __future__ import annotations

import pytest

from app.agents.analyst import fields as fields_mod
from app.agents.analyst.fields import (
    SENIOR_YEARS,
    WEIGHTS,
    WORTH_SHOWING,
    FieldCandidate,
    FieldCandidates,
    score_field,
    suggest_fields,
)


def candidate(**overrides) -> FieldCandidate:
    base = dict(
        key="fintech",
        matched_skills=["payments rails", "KYC/AML"],
        missing_skills=["SAMA licensing"],
        years_in_field=3.0,
        title_alignment="direct",
        justification="Worked on payment rails at a licensed provider.",
    )
    base.update(overrides)
    return FieldCandidate(**base)


class StubClaude:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def call_structured(self, *, schema, system, content, **kw):
        self.calls.append({"system": system, "content": content})
        return self.result


@pytest.fixture
def stub(monkeypatch):
    def install(*candidates) -> StubClaude:
        client = StubClaude(FieldCandidates(fields=list(candidates)))
        monkeypatch.setattr(fields_mod, "get_claude", lambda: client)
        return client

    return install


# --- the formula -------------------------------------------------------------

def test_a_perfect_fit_scores_one_hundred():
    fit = score_field(candidate(
        matched_skills=["a", "b", "c"], missing_skills=[],
        years_in_field=SENIOR_YEARS, title_alignment="direct",
    ))
    assert fit.score == 100.0


def test_the_components_sum_to_the_score():
    """The arithmetic must be visible and must add up, or it is not auditable."""
    fit = score_field(candidate())
    assert fit.score == pytest.approx(sum(c.earned for c in fit.components))


def test_no_evidence_either_way_scores_zero_on_skills():
    """The 'nothing to match means everything matched' bug, guarded.

    An empty requirement set must not award full marks -- that reports a
    comfortable number for a CV that evidences nothing.
    """
    fit = score_field(candidate(matched_skills=[], missing_skills=[]))
    skills = next(c for c in fit.components if c.key == "skills")
    assert skills.earned == 0.0


def test_half_the_core_skills_earns_half_the_skill_points():
    fit = score_field(candidate(matched_skills=["a", "b"], missing_skills=["c", "d"]))
    skills = next(c for c in fit.components if c.key == "skills")
    assert skills.earned == pytest.approx(WEIGHTS["skills"] / 2)


def test_unevidenced_years_score_zero_rather_than_half():
    """A null is 'the CV does not show it', not 'assume the middle'."""
    fit = score_field(candidate(years_in_field=None))
    experience = next(c for c in fit.components if c.key == "experience")
    assert experience.earned == 0.0
    assert "do not evidence" in experience.why


def test_experience_saturates_rather_than_running_away():
    at_ceiling = score_field(candidate(years_in_field=SENIOR_YEARS))
    far_past = score_field(candidate(years_in_field=SENIOR_YEARS * 6))
    assert at_ceiling.score == far_past.score


def test_title_alignment_is_ordered():
    scores = [
        score_field(candidate(title_alignment=alignment)).score
        for alignment in ("direct", "adjacent", "distant")
    ]
    assert scores == sorted(scores, reverse=True)


def test_an_unknown_alignment_is_treated_as_the_weakest():
    assert score_field(candidate(title_alignment="excellent")).score == \
           score_field(candidate(title_alignment="distant")).score


def test_skills_outweigh_tenure():
    """Someone with the skills and little time beats time with no skills.

    This is the weighting decision made explicit: a formula where tenure
    dominated would tell a career-changer with none of the skills that they fit.
    """
    skilled_newcomer = score_field(candidate(
        matched_skills=["a", "b", "c", "d"], missing_skills=[],
        years_in_field=0.5, title_alignment="adjacent",
    ))
    tenured_outsider = score_field(candidate(
        matched_skills=[], missing_skills=["a", "b", "c", "d"],
        years_in_field=SENIOR_YEARS * 2, title_alignment="adjacent",
    ))
    assert skilled_newcomer.score > tenured_outsider.score


def test_the_same_evidence_always_scores_the_same():
    assert len({score_field(candidate()).score for _ in range(20)}) == 1


def test_an_unknown_field_key_is_dropped_not_scored():
    assert score_field(candidate(key="underwater-basket-weaving")) is None


def test_the_label_comes_from_the_industry_pack():
    """Fields reuse the existing packs, so advice and audit share vocabulary."""
    assert score_field(candidate(key="fintech")).label == "Fintech"


# --- selection ---------------------------------------------------------------

def test_fields_come_back_best_first(stub):
    """Both clear the threshold, so ordering is what is under test here."""
    stub(
        candidate(key="fintech", matched_skills=["a", "b"], missing_skills=["c"],
                  years_in_field=2.0, title_alignment="adjacent"),
        candidate(key="tech", matched_skills=["a", "b", "c"], missing_skills=[],
                  years_in_field=SENIOR_YEARS, title_alignment="direct"),
    )
    results = suggest_fields("a cv")
    assert [f.key for f in results] == ["tech", "fintech"]
    assert results[0].score > results[1].score >= WORTH_SHOWING


def test_a_field_the_cv_barely_touches_is_not_shown(stub):
    stub(candidate(key="healthcare", matched_skills=[], missing_skills=["a", "b"],
                   years_in_field=None, title_alignment="distant"))
    assert suggest_fields("a cv") == []


def test_no_plausible_field_is_an_empty_list_not_an_error(stub):
    stub()
    assert suggest_fields("a cv") == []


def test_the_limit_is_honoured(stub):
    strong = [
        candidate(key=key, matched_skills=["a", "b"], missing_skills=[],
                  years_in_field=SENIOR_YEARS, title_alignment="direct")
        for key in ("tech", "fintech", "banking", "consulting", "energy")
    ]
    stub(*strong)
    assert len(suggest_fields("a cv", limit=2)) == 2


def test_everything_shown_clears_the_threshold(stub):
    stub(
        candidate(key="tech", matched_skills=["a", "b"], missing_skills=[],
                  years_in_field=SENIOR_YEARS, title_alignment="direct"),
        candidate(key="energy", matched_skills=[], missing_skills=["x"],
                  years_in_field=None, title_alignment="distant"),
    )
    assert all(f.score >= WORTH_SHOWING for f in suggest_fields("a cv"))


def test_an_empty_cv_costs_no_model_call(stub):
    client = stub(candidate())
    assert suggest_fields("   ") == []
    assert client.calls == []


def test_the_catalogue_in_the_prompt_lists_real_field_keys(stub):
    client = stub(candidate())
    suggest_fields("a cv")
    system = client.calls[0]["system"]
    assert "fintech: Fintech" in system
    # 'other' is a fallback for the audit, not a field anyone is told they fit.
    assert "\n- other:" not in system


def test_the_cv_reaches_the_model_as_delimited_data(stub):
    client = stub(candidate())
    suggest_fields("Yasmin Alamrani, backend engineer")
    sent = client.calls[0]["content"][0]["text"]
    assert sent.startswith("<resume_text>") and sent.endswith("</resume_text>")


def test_the_prompt_forbids_the_model_writing_its_own_score(stub):
    """The justification sits next to a computed number and must not contradict it."""
    client = stub(candidate())
    suggest_fields("a cv")
    system = client.calls[0]["system"]
    assert "do not write" in system.lower()
    assert "strong match" in system
