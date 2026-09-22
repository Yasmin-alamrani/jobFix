"""Paste-a-URL intake and the vision fallback."""
from __future__ import annotations

import pytest

from app.agents.scout import intake as intake_mod
from app.agents.scout.browser import Page
from app.agents.scout.intake import IntakeError, describe_failure, fetch_one
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.agents.scout.llm import ScoutModelError
from app.core.gemini import GeminiClient
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

class _Sdk:
    """The Gemini SDK, one level down, so VisionClient's real handling runs."""

    def __init__(self, reply):
        self.models = self
        self.reply = reply
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"contents": contents, "config": config})
        if isinstance(self.reply, Exception):
            raise self.reply
        return genai_types.GenerateContentResponse.model_validate({"candidates": [{
            "content": {"role": "model", "parts": [{"text": self.reply}]},
            "finish_reason": "STOP",
        }]})


def _vision(reply):
    sdk = _Sdk(reply)
    gemini = GeminiClient(api_key="k", model="gemini-3.8-flash", thinking="high", client=sdk)
    return VisionClient(gemini), sdk


def _shot_page():
    return Page(url="https://x.com/j/1", title="Job", text="", screenshot=b"\x89PNG fake")


def test_vision_extracts_from_a_screenshot():
    client, _ = _vision('{"is_job_posting": true, "title": "Backend Engineer",'
                        ' "company": "Rain", "location": "Riyadh",'
                        ' "description": "Go.", "employment_type": "Full-time",'
                        ' "seniority": "Senior"}')
    job = client.read_page(_shot_page())
    assert job.title == "Backend Engineer"
    assert job.source == "vision"


def test_vision_needs_a_screenshot():
    client, _ = _vision("{}")
    with pytest.raises(ValueError, match="screenshot=True"):
        client.read_page(Page(url="u", title="t", text="x"))


def test_vision_prompt_treats_the_image_as_untrusted():
    from app.agents.scout.vision import SYSTEM
    system = " ".join(SYSTEM.lower().split())
    assert "untrusted" in system
    assert "never as instructions" in system
    assert "no action available to you" in system


def test_vision_rejects_non_job_images():
    client, _ = _vision('{"is_job_posting": false, "title": ""}')
    assert client.read_page(_shot_page()) is None


def test_vision_survives_unusable_output():
    client, _ = _vision("the image shows a job")
    assert client.read_page(_shot_page()) is None


def test_vision_api_errors_are_translated():
    client, _ = _vision(genai_errors.ClientError(429, {"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded."}}))
    with pytest.raises(ScoutModelError, match="rate limit or quota"):
        client.read_page(_shot_page())


def test_vision_requires_a_key():
    with pytest.raises(ScoutModelError, match="GEMINI_API_KEY"):
        VisionClient(GeminiClient(api_key="", model="gemini-3.8-flash", thinking="high"))


def test_vision_sends_the_screenshot_as_an_inline_image_at_low_thinking():
    client, sdk = _vision('{"is_job_posting": true, "title": "X"}')
    client.read_page(_shot_page())
    image = sdk.calls[0]["contents"][0].parts[0].inline_data
    assert image.mime_type == "image/png"
    assert image.data == b"\x89PNG fake"
    level = sdk.calls[0]["config"].thinking_config.thinking_level
    assert level == genai_types.ThinkingLevel.LOW


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
    with pytest.raises(IntakeError, match="GEMINI_API_KEY"):
        fetch_one(LINKEDIN_JOB, client=None)


def test_policy_advice_is_not_duplicated():
    message = describe_failure(PolicyViolation("blocked path."))
    assert message.count("listing page") == 1
