"""Matcher, brief and runner. The model is stubbed -- no key, no spend."""
from __future__ import annotations

import json

import httpx
import pytest

from app.agents.analyst.schemas import ExperienceFit, Fit, Importance, Requirement, Status
from app.agents.scout import brief as brief_mod
from app.agents.scout import runner as runner_mod
from app.agents.scout.brief import WORTH_IT, build
from app.agents.scout.llm import OpenRouter, OpenRouterError
from app.agents.scout.matcher import MATCH_MAX, Match, match_all, match_one
from app.agents.scout.prefilter import Candidate
from app.agents.scout.runner import ScoutRequest
from app.sources.base import JobPosting

CV = "Senior Backend Engineer. Python, PostgreSQL, Django, Kafka. Payments at Tamara since 2022."


def _job(title="Backend Engineer", company="Tamara",
         description="Python and PostgreSQL required.", **kw):
    return JobPosting(title=title, company=company, location="Riyadh, Saudi Arabia",
                      description=description, **kw)


def _cand(job=None, sim=0.5):
    return Candidate(job=job or _job(), similarity=sim, overlap=("python",))


def _req(skill, importance=Importance.CRITICAL, status=Status.PRESENT, evidence="x"):
    return Requirement(skill=skill, importance=importance, status=status, evidence=evidence)


STRONG = {
    "requirements": [
        {"skill": "Python", "importance": "critical", "status": "present",
         "evidence": "Python", "note": ""},
        {"skill": "PostgreSQL", "importance": "critical", "status": "present",
         "evidence": "PostgreSQL", "note": ""},
    ],
    "experience": {
        "jd_seniority": "Senior", "resume_seniority": "Senior",
        "years_required": 5, "years_evidenced": 5, "fit": "match",
        "gaps": [], "evidence": ["since 2022"],
    },
}

WEAK = {
    "requirements": [
        {"skill": "Kubernetes", "importance": "critical", "status": "missing",
         "evidence": "", "note": "absent"},
        {"skill": "Go", "importance": "critical", "status": "missing",
         "evidence": "", "note": "absent"},
    ],
    "experience": {
        "jd_seniority": "Staff", "resume_seniority": "Mid",
        "years_required": 8, "years_evidenced": 4, "fit": "far_under",
        "gaps": ["no distributed systems"], "evidence": [],
    },
}


class StubClient:
    """Stands in for OpenRouter. Returns queued payloads in order."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def complete_json(self, *, schema, system, user, **kw):
        self.calls.append({"system": system, "user": user})
        payload = self.payloads.pop(0) if self.payloads else STRONG
        if isinstance(payload, Exception):
            raise payload
        return schema.model_validate(payload)


# --- matcher -----------------------------------------------------------------

def test_strong_match_scores_high():
    m = match_one(StubClient(STRONG), CV, _cand())
    assert m.ok
    assert m.score > 90
    assert set(m.matched) == {"Python", "PostgreSQL"}


def test_weak_match_scores_low_and_names_the_gaps():
    m = match_one(StubClient(WEAK), CV, _cand())
    assert m.score < 40
    assert set(m.missing_critical) == {"Kubernetes", "Go"}


def test_score_is_normalised_to_100():
    """Only the two CV-vs-JD dimensions count, rescaled from 55 to 100."""
    assert MATCH_MAX == 55.0
    assert match_one(StubClient(STRONG), CV, _cand()).score <= 100.0


def test_score_agrees_with_the_analyst_engine():
    """The brief must never disagree with the resume audit about the same job."""
    from app.agents.analyst import scoring

    m = match_one(StubClient(WEAK), CV, _cand())
    reqs = [
        _req("Kubernetes", status=Status.MISSING, evidence=""),
        _req("Go", status=Status.MISSING, evidence=""),
    ]
    fit = ExperienceFit(jd_seniority="Staff", resume_seniority="Mid",
                        years_required=8, years_evidenced=4, fit=Fit.FAR_UNDER,
                        gaps=["no distributed systems"])
    expected = scoring.score_keywords(reqs).earned + scoring.score_experience(fit).earned
    assert m.score == pytest.approx(round(100 * expected / MATCH_MAX, 1))


def test_prompt_forbids_fabrication():
    c = StubClient(STRONG)
    match_one(c, CV, _cand())
    assert "never invent" in c.calls[0]["system"].lower()


def test_a_failed_job_does_not_end_the_scan():
    c = StubClient(OpenRouterError("boom"), STRONG)
    matches = match_all(c, CV, [_cand(_job("A")), _cand(_job("B"))], limit=2)
    assert len(matches) == 2
    assert sum(m.ok for m in matches) == 1
    assert matches[0].ok, "successful matches must sort above failures"


def test_shortlist_limit_caps_model_calls():
    """The limit is the cost control -- it must actually bind."""
    c = StubClient(*([STRONG] * 20))
    match_all(c, CV, [_cand(_job(f"J{i}")) for i in range(20)], limit=5)
    assert len(c.calls) == 5


def test_long_descriptions_are_truncated():
    c = StubClient(STRONG)
    match_one(c, CV, _cand(_job(description="x" * 20000)))
    assert "truncated" in c.calls[0]["user"]
    assert len(c.calls[0]["user"]) < 20000


# --- brief -------------------------------------------------------------------

def _match(score, title="Backend Engineer", missing=(), fit=Fit.MATCH,
           yrs_req=None, yrs_ev=None, matched=("Python",)):
    reqs = [_req(s) for s in matched]
    reqs += [_req(s, status=Status.MISSING, evidence="") for s in missing]
    return Match(
        job=_job(title=title), score=score, requirements=reqs,
        experience=ExperienceFit(jd_seniority="Senior", resume_seniority="Senior",
                                 fit=fit, years_required=yrs_req, years_evidenced=yrs_ev),
        deductions=[],
    )


def test_brief_counts_only_roles_worth_the_time():
    b = build([_match(85), _match(70), _match(30)], total_found=50)
    assert f"{sum(1 for m in (85, 70, 30) if m >= WORTH_IT)} worth your time" in b.render()
    assert "50 roles found" in b.render()


def test_brief_names_matched_skills_and_missing_requirements():
    out = build([_match(62, missing=["Kubernetes"])], total_found=1).render()
    assert "Matched: Python" in out
    assert "Missing required: Kubernetes" in out


def test_brief_reports_a_years_shortfall():
    out = build([_match(55, yrs_req=6, yrs_ev=4)], total_found=1).render()
    assert "Asks 6 yrs, your CV evidences 4" in out


def test_brief_is_honest_when_nothing_matches():
    out = build([], total_found=40).render()
    assert "0 worth your time" in out
    assert "Nothing matched" in out


def test_brief_shows_the_publisher_when_it_came_via_an_aggregator():
    m = _match(80)
    m.job.publisher = "LinkedIn"
    assert "[via LinkedIn]" in build([m], total_found=1).render()


def test_brief_reports_failures_rather_than_hiding_them():
    failed = Match(job=_job(), score=0.0, requirements=[],
                   experience=ExperienceFit(jd_seniority="?", resume_seniority="?", fit=Fit.UNDER),
                   deductions=[], error="timeout")
    assert "1 role(s) could not be scored" in build([_match(80), failed], total_found=2).render()


def test_brief_respects_the_display_limit():
    b = build([_match(90 - i) for i in range(20)], total_found=20, limit=5)
    assert len(b.lines) == 5


def test_brief_costs_nothing_without_a_client():
    assert build([_match(80)], total_found=1).headline == ""


def test_headline_failure_leaves_the_brief_usable():
    class Boom:
        def complete_json(self, **kw):
            raise OpenRouterError("no credit")
    b = build([_match(80)], total_found=1, client=Boom())
    assert b.headline == ""
    assert "Backend Engineer" in b.render()


# --- llm client --------------------------------------------------------------

def _http(monkeypatch, content, status=200):
    def handler(request):
        if status != 200:
            return httpx.Response(status, text="err")
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    return OpenRouter("k")


class _Shape(brief_mod._Headline):
    pass


def test_json_wrapped_in_a_code_fence_is_recovered(monkeypatch):
    c = _http(monkeypatch, '```json\n{"headline": "thin batch"}\n```')
    assert c.complete_json(schema=_Shape, system="s", user="u").headline == "thin batch"


def test_json_with_leading_prose_is_recovered(monkeypatch):
    c = _http(monkeypatch, 'Sure! {"headline": "ok"}')
    assert c.complete_json(schema=_Shape, system="s", user="u").headline == "ok"


def test_missing_key_fails_with_a_usable_message():
    with pytest.raises(OpenRouterError) as exc:
        OpenRouter("")
    assert "openrouter.ai/keys" in str(exc.value)


@pytest.mark.parametrize("status,expected", [
    (401, "rejected the API key"), (402, "out of credit"), (429, "Rate limited"),
])
def test_http_errors_are_translated(monkeypatch, status, expected):
    c = _http(monkeypatch, "", status=status)
    with pytest.raises(OpenRouterError) as exc:
        c.complete_json(schema=_Shape, system="s", user="u")
    assert expected in str(exc.value)


def test_unparseable_output_retries_then_gives_up(monkeypatch):
    c = _http(monkeypatch, "not json at all")
    with pytest.raises(OpenRouterError):
        c.complete_json(schema=_Shape, system="s", user="u", retries=1)


# --- runner ------------------------------------------------------------------

def test_collect_deduplicates_across_sources(monkeypatch):
    dupe = _job()
    monkeypatch.setattr(runner_mod, "scan_ats", lambda **kw: [dupe, _job(), _job("Other")])
    assert len(runner_mod.collect(ScoutRequest(resume_text=CV))) == 2


def test_jsearch_is_skipped_without_a_key(monkeypatch):
    monkeypatch.setattr(runner_mod, "scan_ats", lambda **kw: [_job()])
    req = ScoutRequest(resume_text=CV, include_jsearch=True)
    assert len(runner_mod.collect(req, jsearch_key="")) == 1


def test_run_produces_a_brief_end_to_end(monkeypatch):
    monkeypatch.setattr(
        runner_mod, "scan_ats",
        lambda **kw: [_job("Backend Engineer"), _job("Auditor", description="Audit controls")],
    )
    result = runner_mod.run(
        ScoutRequest(resume_text=CV, title_hint="Backend Engineer", shortlist=2),
        client=StubClient(STRONG, WEAK), headline=False,
    )
    assert result.jobs_found == 2
    assert result.jobs_scored == 2
    assert "roles found" in result.brief.render()
    # Best first.
    assert result.matches[0].score > result.matches[1].score
