"""Reading a pasted job URL: the free rungs, the walls, and the aggregator.

No network and no model. What is tested is the order of the attempt -- free
first, the model last -- and that a page nobody may fetch can still be found
through Google for Jobs.
"""
from __future__ import annotations

import pytest

from app.agents.scout import intake as intake_mod
from app.agents.scout.browser import Page
from app.agents.scout.extract import (
    free_read, from_meta, from_page, looks_like_a_posting, readable_text,
)
from app.agents.scout.intake import IntakeError, fetch_one
from app.agents.scout.lookup import query_from, via_aggregator
from app.agents.scout.policy import looks_like_a_wall
from app.sources.base import JobPosting

BODY = (
    "<p>We are hiring a backend engineer in Riyadh.</p>"
    "<h2>Responsibilities</h2><ul><li>Build payment APIs</li><li>Own services</li></ul>"
    "<h2>Requirements</h2><ul><li>5 years experience with Python</li>"
    "<li>Strong skills in PostgreSQL</li></ul>"
    "<p>Apply by sending your CV. Full-time, competitive salary and benefits.</p>"
) * 3

PAGE_HTML = (
    "<html><head><title>Senior Backend Engineer - Tamara</title>"
    '<meta property="og:title" content="Senior Backend Engineer | Tamara">'
    '<meta property="og:site_name" content="Tamara Careers">'
    "</head><body><nav>Home Jobs About</nav>"
    f"<main>{BODY}</main><footer>Cookies and legal</footer></body></html>"
)

JSON_LD = (
    '<script type="application/ld+json">'
    '{"@type": "JobPosting", "title": "Backend Engineer",'
    ' "hiringOrganization": {"name": "Hala"},'
    ' "description": "<p>Build payment systems in Riyadh.</p>"}'
    "</script>"
)


# --- reading a page without the model ------------------------------------------------

def test_furniture_is_not_part_of_the_posting():
    text = readable_text(PAGE_HTML)
    assert "Responsibilities" in text
    assert "Cookies and legal" not in text and "Home Jobs About" not in text


def test_a_listing_of_two_lines_is_not_a_posting():
    assert not looks_like_a_posting("Backend Engineer. Apply now.")
    assert looks_like_a_posting(readable_text(PAGE_HTML))


def test_a_page_names_itself_in_its_metadata():
    job = from_meta(PAGE_HTML, "https://example.com/jobs/123")
    assert job is not None
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Tamara Careers"
    assert "payment APIs" in job.description
    assert job.source == "page"


def test_structured_data_wins_over_metadata():
    page = Page(url="https://example.com/jobs/1", title="x", text="")
    job = free_read(page, JSON_LD + PAGE_HTML)
    assert job is not None and job.company == "Hala"


def test_the_model_is_only_asked_when_the_free_rungs_fail():
    class Model:
        def __init__(self):
            self.calls = 0

        def complete_json(self, **kw):
            self.calls += 1
            raise AssertionError("the model should not have been called")

    page = Page(url="https://example.com/jobs/1", title="Senior Backend Engineer", text="")
    model = Model()
    assert from_page(page, model, html=PAGE_HTML) is not None
    assert model.calls == 0


def test_a_page_the_model_calls_a_listing_still_yields_its_text():
    """The model is one opinion about an unusual layout, not the last word."""
    class Says:
        def complete_json(self, *, schema, system, user, **kw):
            return schema.model_validate({"is_job_posting": False, "title": ""})

    page = Page(url="https://example.com/jobs/1", title="Backend Engineer", text="")
    job = from_page(page, Says(), html=PAGE_HTML)
    assert job is not None and job.source == "page"


# --- walls ----------------------------------------------------------------------------

@pytest.mark.parametrize("marker", [
    "Just a moment...",
    "https://x.example/job?__cf_chl_rt_tk=abc",
    "Checking your browser before accessing",
    "Please enable JavaScript and cookies to continue",
])
def test_a_bot_check_is_a_wall_not_a_page(marker):
    assert looks_like_a_wall(marker)


# --- the whole attempt ------------------------------------------------------------------

def test_a_plain_page_is_read_without_a_browser_or_a_model(monkeypatch):
    monkeypatch.setattr(intake_mod, "_plain_get", lambda url: PAGE_HTML)
    monkeypatch.setattr(intake_mod.Policy, "check", lambda self, url: None)

    class NoBrowser:
        def __init__(self, *a, **kw):
            raise AssertionError("a browser should not have been started")

    monkeypatch.setattr(intake_mod, "ReadOnlyBrowser", NoBrowser)
    job = fetch_one("https://example.com/jobs/12345", client=None)
    assert job.title == "Senior Backend Engineer" and job.source == "pasted"


def test_a_page_without_an_id_is_not_trusted_on_its_text_alone(monkeypatch):
    """A listing index uses the same words; the URL is the second signal."""
    monkeypatch.setattr(intake_mod, "_plain_get", lambda url: PAGE_HTML)
    monkeypatch.setattr(intake_mod.Policy, "check", lambda self, url: None)
    monkeypatch.setattr(intake_mod, "ReadOnlyBrowser", _browser_raising(RuntimeError("no")))
    with pytest.raises(IntakeError):
        fetch_one("https://example.com/jobs", client=None, allow_browser=True)


def _browser_raising(exc):
    class Browser:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            raise exc

        def __exit__(self, *a):
            return False
    return Browser


def test_a_browser_that_cannot_open_the_page_says_so(monkeypatch):
    monkeypatch.setattr(intake_mod, "_plain_get", lambda url: "")
    monkeypatch.setattr(intake_mod.Policy, "check", lambda self, url: None)
    monkeypatch.setattr(intake_mod, "ReadOnlyBrowser", _browser_raising(TimeoutError("slow")))
    with pytest.raises(IntakeError, match="could not be opened in time"):
        fetch_one("https://example.com/jobs/1", client=None)


# --- the aggregator ----------------------------------------------------------------------

def test_a_url_spells_out_what_to_search_for():
    words, ident = query_from(
        "https://sa.linkedin.com/jobs/view/backend-engineer-at-fluidai-medical-4467880962"
    )
    assert "backend engineer" in words and "fluidai" in words
    assert ident == "4467880962"


def test_a_url_with_only_an_id_cannot_be_looked_up():
    words, ident = query_from("https://www.linkedin.com/jobs/view/4468385432/")
    assert words == "" and ident == "4468385432"


def _search_returning(*jobs):
    class Fake:
        def __init__(self, key, **kw):
            self.last_problem = ""

        def search(self, query, **kw):
            self.query = query
            return list(jobs)
    return Fake


def test_the_posting_is_found_by_its_id_in_an_apply_link(monkeypatch):
    import app.agents.scout.lookup as lookup_mod
    wanted = JobPosting(title="Backend Engineer", company="FluidAI Medical",
                        description="Build integrations.",
                        apply_options=[("LinkedIn", "https://www.linkedin.com/jobs/view/4467880962")])
    other = JobPosting(title="Chef", company="Kitchen")
    monkeypatch.setattr(lookup_mod, "JSearch", _search_returning(other, wanted))
    found = via_aggregator(
        "https://sa.linkedin.com/jobs/view/backend-engineer-at-fluidai-medical-4467880962",
        api_key="k",
    )
    assert found is not None and found.company == "FluidAI Medical"
    assert found.source == "google-jobs"


def test_an_unrelated_result_is_not_offered_as_the_posting(monkeypatch):
    import app.agents.scout.lookup as lookup_mod
    monkeypatch.setattr(lookup_mod, "JSearch", _search_returning(JobPosting(title="Chef", company="Kitchen")))
    assert via_aggregator("https://x.example/jobs/pastry-chef-role-123456", api_key="k") is None


def test_without_a_key_there_is_no_lookup(monkeypatch):
    import app.agents.scout.lookup as lookup_mod

    class Boom:
        def __init__(self, *a, **kw):
            raise AssertionError("no key means no request")

    monkeypatch.setattr(lookup_mod, "JSearch", Boom)
    assert via_aggregator("https://x.example/jobs/engineer-123456", api_key="") is None
