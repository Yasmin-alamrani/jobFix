"""Phase 4 endpoints: reading a posting URL, company targeting, filtered search,
and requirement categories in the audit.

The fetcher, the model and the job sources are stubbed; no test reaches the
network or spends anything.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agents.analyst import analyzer
from app.agents.analyst import targeting as targeting_mod
from app.agents.analyst.schemas import (
    Category, ExperienceFit, Fit, Importance, Requirement, Status, WritingReview,
)
from app.agents.analyst.targeting import Signal, Targeting
from app.agents.scout.intake import IntakeError
from app.agents.scout.policy import PolicyViolation, WallEncountered
from app.core.safe_fetch import BlockedAddress
from app.sources.base import JobPosting
from tailor_fixtures import tailor_client, upload  # noqa: F401 -- tailor_client is a fixture

FIXTURES = Path(__file__).parent / "fixtures"
DESCRIPTION = ("We are hiring a backend engineer to build payment reconciliation in Python "
               "and PostgreSQL. You will own services end to end and work with SAMA rules. ") * 3


def posting(**overrides) -> JobPosting:
    base = dict(title="Senior Backend Engineer", company="Hala", location="Riyadh",
                description=DESCRIPTION, apply_url="https://jobs.example.com/hala/1",
                source="pasted")
    base.update(overrides)
    return JobPosting(**base)


# --- reading a posting URL ---------------------------------------------------------

@pytest.fixture
def fetcher(monkeypatch):
    from app.api import jobs as jobs_mod

    def install(outcome):
        def fake(url, client=None):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        monkeypatch.setattr(jobs_mod, "fetch_one", fake)
    return install


def test_a_readable_posting_fills_the_form(tailor_client, fetcher):
    fetcher(posting())
    body = tailor_client.post("/api/jobs/fetch", json={"url": "https://jobs.example.com/hala/1"}).json()
    assert body["title"] == "Senior Backend Engineer" and body["company"] == "Hala"
    assert body["description"].startswith("We are hiring")


@pytest.mark.parametrize("failure", [
    PolicyViolation("robots.txt disallows that page."),
    BlockedAddress("10.0.0.1 is a private or reserved address."),
    IntakeError("That page does not look like a single job posting."),
])
def test_every_refusal_points_to_the_paste_box(tailor_client, fetcher, failure):
    fetcher(failure)
    response = tailor_client.post("/api/jobs/fetch", json={"url": "https://x.example/job"})
    assert response.status_code == 422
    assert "Paste the job description into the box below instead." in response.json()["detail"]


def test_a_login_wall_says_paste_once_not_twice(tailor_client, fetcher):
    fetcher(WallEncountered("authwall"))
    detail = tailor_client.post("/api/jobs/fetch", json={"url": "https://x.example/job"}).json()["detail"]
    assert "login wall" in detail
    assert detail.lower().count("paste") == 1


def test_an_unexpected_failure_is_a_502_with_the_same_way_out(tailor_client, fetcher):
    fetcher(RuntimeError("browser crashed"))
    response = tailor_client.post("/api/jobs/fetch", json={"url": "https://x.example/job"})
    assert response.status_code == 502
    assert "Paste" in response.json()["detail"]


def test_a_page_with_too_little_text_is_not_treated_as_a_posting(tailor_client, fetcher):
    fetcher(posting(description="Apply now!"))
    response = tailor_client.post("/api/jobs/fetch", json={"url": "https://x.example/job"})
    assert response.status_code == 422 and "too little text" in response.json()["detail"]


# --- company targeting -------------------------------------------------------------

@pytest.fixture
def targeting_stub(monkeypatch):
    class Stub:
        calls: list = []

        def call_structured(self, *, schema, system, content, **kw):
            self.calls.append(content)
            return Targeting(
                values=[
                    Signal(point="Ownership", basis="stated", quote="own services end to end"),
                    Signal(point="Values diversity", basis="stated", quote="equal opportunity"),
                ],
                tone=Signal(point="Direct", basis="inferred"),
                keywords=["Python", "Kubernetes"],
            )

    stub = Stub()
    stub.calls = []
    monkeypatch.setattr(targeting_mod, "get_claude", lambda: stub)
    return stub


def test_targeting_labels_are_checked_before_they_reach_the_page(tailor_client, targeting_stub):
    body = tailor_client.post("/api/jobs/targeting", json={"job_description": DESCRIPTION}).json()
    assert [v["basis"] for v in body["values"]] == ["stated", "inferred"]
    assert body["keywords"] == ["Python"]
    assert "inferred" in body["caveat"]


def test_targeting_uses_the_cv_when_one_is_named(tailor_client, targeting_stub):
    resume_id = upload(tailor_client)
    tailor_client.post("/api/jobs/targeting",
                       json={"job_description": DESCRIPTION, "resume_id": resume_id})
    assert "<resume_text>" in targeting_stub.calls[-1][0]["text"]


def test_targeting_needs_a_real_posting(tailor_client, targeting_stub):
    response = tailor_client.post("/api/jobs/targeting", json={"job_description": "Engineer."})
    assert response.status_code == 422 and targeting_stub.calls == []


def test_targeting_for_an_unknown_cv_is_a_404(tailor_client, targeting_stub):
    response = tailor_client.post("/api/jobs/targeting",
                                  json={"job_description": DESCRIPTION, "resume_id": "nope"})
    assert response.status_code == 404


# --- filtered search ----------------------------------------------------------------

NOW = datetime.now(timezone.utc)
SEARCH_JOBS = [
    posting(title="Senior Backend Engineer", location="Riyadh", posted_at=NOW - timedelta(days=2),
            apply_url="https://jobs.example.com/1"),
    posting(title="Backend Engineer", company="Rain", location="Riyadh (Remote)",
            posted_at=NOW - timedelta(days=40), apply_url="https://jobs.example.com/2"),
    posting(title="Junior Developer", company="Lean", location="Riyadh", posted_at=None,
            apply_url="https://jobs.example.com/3"),
    posting(title="Engineering Manager", company="Tabby", location="Riyadh — Hybrid",
            posted_at=NOW - timedelta(days=5), apply_url="https://jobs.example.com/4"),
]


@pytest.fixture
def searchable(tailor_client, monkeypatch):
    from app.api import scout as scout_mod
    monkeypatch.setattr(scout_mod, "collect", lambda request, jsearch_key="": list(SEARCH_JOBS))
    return upload(tailor_client)


def find(client, resume_id, **filters):
    return client.post("/api/scout/find", json={"resume_id": resume_id, "locations": ["riyadh"],
                                                **filters})


def test_results_say_what_each_posting_states(tailor_client, searchable):
    body = find(tailor_client, searchable).json()
    by_title = {c["title"]: c for c in body["candidates"]}
    senior = by_title.get("Senior Backend Engineer")
    if senior:   # present unless the ranker scored it zero against this CV
        assert senior["seniority"] == "senior" and senior["work_mode"] == "onsite"
        assert senior["posted_at"] is not None
    assert body["hidden"] == {}


def test_a_work_arrangement_filter_reports_what_it_hid(tailor_client, searchable):
    body = find(tailor_client, searchable, work_mode="remote").json()
    assert {c["title"] for c in body["candidates"]} <= {"Backend Engineer"}
    assert body["hidden"] == {"work_mode": 3}


def test_a_date_filter_can_hide_undated_postings(tailor_client, searchable):
    body = find(tailor_client, searchable, posted_within_days=7, include_unstated=False).json()
    assert body["hidden"] == {"posted": 1, "posted_unstated": 1}
    assert {c["title"] for c in body["candidates"]} <= {"Senior Backend Engineer",
                                                        "Engineering Manager"}


def test_a_seniority_filter_keeps_unstated_titles_by_default(tailor_client, searchable):
    body = find(tailor_client, searchable, seniority=["senior"]).json()
    assert body["hidden"] == {"seniority": 2}


def test_filter_values_are_validated(tailor_client, searchable):
    assert find(tailor_client, searchable, work_mode="moon").status_code == 422
    assert find(tailor_client, searchable, seniority=["ceo"]).status_code == 422
    assert find(tailor_client, searchable, posted_within_days=0).status_code == 422


# --- requirement categories in the audit -------------------------------------------

def test_requirements_default_to_the_skill_category():
    """Analyses stored before categories existed must still load."""
    old = Requirement(skill="Python", importance=Importance.CRITICAL, status=Status.PRESENT)
    assert old.category == Category.SKILL


def test_the_audit_asks_for_categories_and_records_the_new_prompt(monkeypatch):
    calls = []

    class Stub:
        def call_structured(self, *, schema, system, content, **kw):
            calls.append(system)
            if schema is WritingReview:
                return WritingReview(issues=[], summary_verdict="ok")
            return schema(
                requirements=[Requirement(skill="Arabic", category=Category.LANGUAGE,
                                          importance=Importance.CRITICAL, status=Status.MISSING)],
                experience=ExperienceFit(jd_seniority="Senior", resume_seniority="Mid",
                                         fit=Fit.UNDER),
            )

    monkeypatch.setattr(analyzer, "get_claude", lambda: Stub())
    result = analyzer.analyze(resume_path=FIXTURES / "clean_single_column.pdf",
                              job_description=DESCRIPTION)
    assert "`certification`" in calls[0] and "visa" in calls[0]
    assert result.prompt_version == "analyst_v2"
    assert result.requirements[0].category == Category.LANGUAGE
