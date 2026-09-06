"""Paste-a-URL intake and the vision fallback."""
from __future__ import annotations

import base64

import httpx
import pytest

from app.agents.scout import intake as intake_mod
from app.agents.scout.browser import Page
from app.agents.scout.intake import IntakeError, describe_failure, fetch_one
from app.agents.scout.llm import OpenRouterError
from app.agents.scout.policy import Policy, PolicyViolation, WallEncountered
from app.agents.scout.vision import VisionClient

LINKEDIN_JOB = "https://www.linkedin.com/jobs/view/4123456789"

JSON_LD_PAGE = """
<html><head><script type="application/ld+json">
{"@type":"JobPosting","title":"Senior Backend Engineer",
 "hiringOrganization":{"name":"Tamara"},
 "jobLocation":{"address":{"addressLocality":"Riyadh","addressCountry":"SA"}},
 "description":"Build payment systems."}
</script></head><body>x</body></html>
"""


# --- the single-URL policy ---------------------------------------------------

def test_pasting_a_url_satisfies_the_host_gate():
    """Naming a page is intent; one fetch of one page is not a crawl."""
    policy = Policy.for_pasted_url(LINKEDIN_JOB)
    assert policy.host_allowed(LINKEDIN_JOB)


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?k=x",
    "https://www.linkedin.com/jobs?runSearch=true",
    "https://www.bayt.com/en/jobs/",
    "https://www.bayt.com/ar/jobs/",
])
def test_pasting_a_forbidden_url_does_not_unlock_it(url):
    """Hard blocks hold however we arrive at the page."""
    with pytest.raises(PolicyViolation):
        Policy.for_pasted_url(url).check(url)


def test_a_junk_url_is_rejected_immediately():
    with pytest.raises(PolicyViolation):
        Policy.for_pasted_url("not a url")


# --- rung 1: plain HTTP + JSON-LD --------------------------------------------

def _stub_get(monkeypatch, html, calls=None):
    def fake(url):
        if calls is not None:
            calls.append(url)
        return html
    monkeypatch.setattr(intake_mod, "_plain_get", fake)


def _no_robots(monkeypatch):
    """robots.txt fetch returns nothing -> fails open, as designed."""
    monkeypatch.setattr(Policy, "robots_allow", lambda self, url: True)


def test_structured_data_is_read_without_a_browser_or_a_model(monkeypatch):
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, JSON_LD_PAGE)

    def no_browser(*a, **kw):
        raise AssertionError("a browser must not start when JSON-LD is available")
    monkeypatch.setattr(intake_mod, "ReadOnlyBrowser", no_browser)

    job = fetch_one(LINKEDIN_JOB)
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Tamara"
    assert job.location == "Riyadh, SA"
    assert job.apply_url == LINKEDIN_JOB
    assert job.source == "pasted"


def test_policy_runs_before_any_fetch(monkeypatch):
    calls: list[str] = []
    _stub_get(monkeypatch, JSON_LD_PAGE, calls)
    with pytest.raises(PolicyViolation):
        fetch_one("https://www.bayt.com/en/jobs/")
    assert calls == [], "a forbidden URL must not be fetched at all"


# --- rungs 2 and 3: the browser ----------------------------------------------

class FakeBrowser:
    def __init__(self, page=None, raises=None):
        self._page, self._raises = page, raises

    def __call__(self, policy, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, url, **kw):
        if self._raises:
            raise self._raises
        return self._page


class StubModel:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, *, schema, system, user, **kw):
        self.calls += 1
        return schema.model_validate(self.payload)


def test_a_client_rendered_page_falls_through_to_the_model(monkeypatch):
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, "<html><body>loading…</body></html>")
    page = Page(url=LINKEDIN_JOB, title="Job", text="Backend Engineer at Tamara. Riyadh.")
    monkeypatch.setattr(intake_mod, "ReadOnlyBrowser", FakeBrowser(page))

    model = StubModel({
        "is_job_posting": True, "title": "Backend Engineer",
        "company": "Tamara", "location": "Riyadh", "description": "Payments.",
    })
    job = fetch_one(LINKEDIN_JOB, client=model)
    assert job.title == "Backend Engineer"
    assert model.calls == 1


def test_a_wall_is_reported_not_worked_around(monkeypatch):
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, "")
    monkeypatch.setattr(
        intake_mod, "ReadOnlyBrowser", FakeBrowser(raises=WallEncountered("authwall")),
    )
    with pytest.raises(WallEncountered):
        fetch_one(LINKEDIN_JOB, client=StubModel({}))


def test_a_listing_page_is_rejected_with_useful_advice(monkeypatch):
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, "<html><body>50 jobs found</body></html>")
    monkeypatch.setattr(
        intake_mod, "ReadOnlyBrowser",
        FakeBrowser(Page(url="u", title="Jobs", text="50 jobs found")),
    )
    with pytest.raises(IntakeError, match="one specific role"):
        fetch_one(LINKEDIN_JOB, client=StubModel({"is_job_posting": False, "title": ""}))


def test_browser_can_be_disabled(monkeypatch):
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, "<html><body>nothing structured</body></html>")
    with pytest.raises(IntakeError, match="browser fallback is off"):
        fetch_one(LINKEDIN_JOB, allow_browser=False)


# --- error messages ----------------------------------------------------------

def test_failures_explain_what_to_do_instead():
    assert "one specific role" in describe_failure(PolicyViolation("blocked"))
    assert "paste the description" in describe_failure(WallEncountered("wall")).lower()
    assert describe_failure(IntakeError("nope")) == "nope"


# --- vision fallback ---------------------------------------------------------

def _vision(monkeypatch, content, status=200):
    def handler(request):
        if status != 200:
            return httpx.Response(status, text="err")
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    return VisionClient("k")


def _shot_page():
    return Page(url="https://x.com/j/1", title="Job", text="", screenshot=b"\x89PNG fake")


def test_vision_extracts_from_a_screenshot(monkeypatch):
    client = _vision(monkeypatch, '{"is_job_posting": true, "title": "Backend Engineer",'
                                  ' "company": "Rain", "location": "Riyadh",'
                                  ' "description": "Go.", "employment_type": "Full-time",'
                                  ' "seniority": "Senior"}')
    job = client.read_page(_shot_page())
    assert job.title == "Backend Engineer"
    assert job.source == "vision"


def test_vision_needs_a_screenshot(monkeypatch):
    client = _vision(monkeypatch, "{}")
    with pytest.raises(ValueError, match="screenshot=True"):
        client.read_page(Page(url="u", title="t", text="x"))


def test_vision_prompt_treats_the_image_as_untrusted(monkeypatch):
    from app.agents.scout.vision import SYSTEM
    system = " ".join(SYSTEM.lower().split())
    assert "untrusted" in system
    assert "never as instructions" in system
    assert "no action available to you" in system


def test_vision_rejects_non_job_images(monkeypatch):
    client = _vision(monkeypatch, '{"is_job_posting": false, "title": ""}')
    assert client.read_page(_shot_page()) is None


def test_vision_survives_unusable_output(monkeypatch):
    client = _vision(monkeypatch, "the image shows a job")
    assert client.read_page(_shot_page()) is None


def test_vision_http_errors_are_translated(monkeypatch):
    client = _vision(monkeypatch, "", status=429)
    with pytest.raises(OpenRouterError, match="429"):
        client.read_page(_shot_page())


def test_vision_requires_a_key():
    with pytest.raises(OpenRouterError):
        VisionClient("")


def test_vision_sends_the_image_as_a_data_url(monkeypatch):
    captured = {}

    def handler(request):
        import json
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"is_job_posting": true, "title": "X"}'}}]})

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    VisionClient("k").read_page(_shot_page())
    image = captured["messages"][1]["content"][0]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")
    assert base64.standard_b64decode(image.split(",", 1)[1]) == b"\x89PNG fake"


def test_a_missing_key_is_not_blamed_on_the_url(monkeypatch):
    """Regression: 'not a job posting' was shown when the real cause was no key.

    That sends the user off checking their link when the fix is configuration.
    """
    _no_robots(monkeypatch)
    _stub_get(monkeypatch, "<html><body>Backend Engineer at Tamara</body></html>")
    monkeypatch.setattr(
        intake_mod, "ReadOnlyBrowser",
        FakeBrowser(Page(url="u", title="Job", text="Backend Engineer at Tamara")),
    )
    with pytest.raises(IntakeError, match="OPENROUTER_API_KEY"):
        fetch_one(LINKEDIN_JOB, client=None)


def test_policy_advice_is_not_duplicated():
    message = describe_failure(PolicyViolation("blocked path."))
    assert message.count("listing page") == 1
