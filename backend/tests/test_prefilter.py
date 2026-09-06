"""Stage-1 prefilter. Pure arithmetic -- no network, no model, no key."""
from __future__ import annotations

import pytest

from app.agents.scout.prefilter import Candidate, rank, tokenize
from app.sources.base import JobPosting

BACKEND_CV = """
Yasmin Al Amrani. Riyadh.
Senior Backend Engineer at Tamara, 2022 to present.
Built settlement reconciliation in Python and PostgreSQL handling 2M transactions monthly.
Designed the merchant payouts API on Django and Kafka, deployed with Docker on AWS.
BSc Computer Science, King Saud University.
"""


def _job(title, desc="", company="X", location="Riyadh, Saudi Arabia", remote=False):
    return JobPosting(title=title, description=desc, company=company,
                      location=location, remote=remote)


# --- tokenizer ---------------------------------------------------------------

def test_stopwords_and_resume_furniture_are_dropped():
    """Regression: CV section headings scored as highly distinctive terms.

    IDF runs over job descriptions, where 'education' and 'summary' are rare --
    so the maths rated them as strong signal and matched any posting that
    mentioned them. That ranked a Finance Operations manager third against a
    backend CV.
    """
    tokens = set(tokenize("Education Summary University Degree present the and python"))
    assert tokens == {"python"}


def test_synonyms_are_folded():
    assert "postgresql" in tokenize("Postgres experience")
    assert "kubernetes" in tokenize("k8s at scale")
    assert "javascript" in tokenize("strong JS skills")


def test_dotted_and_plus_tokens_survive():
    assert "c++" in tokenize("c++") or "c+" in tokenize("c++")
    assert "node" in tokenize("Node.js")


# --- ranking -----------------------------------------------------------------

def test_relevant_role_outranks_irrelevant_one():
    jobs = [
        _job("Customer Care Advisor", "Handle customer calls and email tickets politely."),
        _job("Backend Engineer", "Python, PostgreSQL, Django, Kafka. Build payment APIs."),
    ]
    ranked = rank(BACKEND_CV, jobs)
    assert ranked[0].job.title == "Backend Engineer"
    assert ranked[0].similarity > ranked[1].similarity


def test_results_are_sorted_descending():
    jobs = [
        _job("Backend Engineer", "Python PostgreSQL Kafka Django payments"),
        _job("Auditor", "Audit financial statements and internal controls"),
        _job("Platform Engineer", "Docker AWS Kubernetes Python infrastructure"),
    ]
    sims = [c.similarity for c in rank(BACKEND_CV, jobs)]
    assert sims == sorted(sims, reverse=True)


def test_title_boost_lifts_a_matching_title():
    """A title match should outrank a body that merely mentions the same words."""
    on_title = _job("Backend Engineer", "We need someone good.")
    in_body = _job("Operations Associate", "You will liaise with the backend engineer team.")
    ranked = rank(BACKEND_CV, [in_body, on_title])
    assert ranked[0].job.title == "Backend Engineer"


def test_title_hint_reorders_between_similar_jobs():
    jobs = [
        _job("Data Engineer", "Python PostgreSQL pipelines AWS Docker Kafka"),
        _job("Backend Engineer", "Python PostgreSQL pipelines AWS Docker Kafka"),
    ]
    hinted = rank(BACKEND_CV, jobs, title_hint="Backend Engineer")
    assert hinted[0].job.title == "Backend Engineer"


def test_location_filter_keeps_only_matching_places():
    jobs = [
        _job("Backend Engineer", "Python", location="Riyadh, Saudi Arabia"),
        _job("Backend Engineer", "Python", location="Berlin, Germany"),
        _job("Backend Engineer", "Python", location="Dubai, UAE"),
    ]
    kept = rank(BACKEND_CV, jobs, locations={"saudi"})
    assert [c.job.location for c in kept] == ["Riyadh, Saudi Arabia"]


def test_remote_roles_survive_a_remote_location_filter():
    jobs = [
        _job("Backend Engineer", "Python", location="Anywhere", remote=True),
        _job("Backend Engineer", "Python", location="Berlin, Germany"),
    ]
    assert len(rank(BACKEND_CV, jobs, locations={"remote"})) == 1


def test_limit_truncates_after_sorting():
    jobs = [_job(f"Engineer {i}", "Python PostgreSQL") for i in range(10)]
    assert len(rank(BACKEND_CV, jobs, limit=3)) == 3


def test_empty_inputs_do_not_explode():
    assert rank(BACKEND_CV, []) == []
    assert rank("", [_job("Backend Engineer", "Python")])[0].similarity == 0.0
    assert rank(BACKEND_CV, [_job("Backend Engineer", "Python")], locations={"tokyo"}) == []


def test_overlap_explains_the_match_without_boilerplate():
    job = _job("Backend Engineer", "Python PostgreSQL Kafka Django payments settlement")
    c = rank(BACKEND_CV, [job])[0]
    assert c.overlap, "a strong match should name shared terms"
    assert not {"education", "summary", "university"} & set(c.overlap)


def test_why_is_readable_and_handles_no_overlap():
    job = _job("Marine Biologist", "Study coral reefs and tidal ecosystems")
    c = rank(BACKEND_CV, [job])[0]
    assert isinstance(c.why, str) and c.why


def test_ranking_is_deterministic():
    jobs = [
        _job("Backend Engineer", "Python PostgreSQL Kafka"),
        _job("Data Scientist", "Python pandas modelling"),
        _job("Auditor", "Financial controls"),
    ]
    runs = {
        tuple((c.job.title, c.similarity) for c in rank(BACKEND_CV, jobs))
        for _ in range(10)
    }
    assert len(runs) == 1


def test_similarity_stays_in_range():
    jobs = [_job("Backend Engineer", BACKEND_CV)]   # identical text: the ceiling
    c = rank(BACKEND_CV, jobs)[0]
    assert 0.0 <= c.similarity <= 1.5   # title-hint lift can exceed 1.0
