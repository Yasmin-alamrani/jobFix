"""JSearch adapter. Recorded payloads only -- no live calls, no quota spent."""
from __future__ import annotations

import httpx
import pytest

from app.sources.jsearch import JSearch, JSearchError

# Shape mirrors a real Google-for-Jobs response: the same role is often carried
# by several publishers at once, which is why apply_options matters.
PAYLOAD = {
    "status": "OK",
    "data": {"cursor": "next-page-token", "jobs": [
        {
            "job_id": "abc123",
            "job_title": "Senior Backend Engineer",
            "employer_name": "Tamara",
            "job_publisher": "LinkedIn",
            "job_city": "Riyadh",
            "job_country": "SA",
            "job_description": "Build payment systems.",
            "job_apply_link": "https://www.linkedin.com/jobs/view/123456",
            "job_posted_at_timestamp": 1756000000,
            "job_is_remote": False,
            "apply_options": [
                {"publisher": "LinkedIn", "apply_link": "https://www.linkedin.com/jobs/view/123456"},
                {"publisher": "Bayt", "apply_link": "https://www.bayt.com/en/job/123"},
            ],
        },
        {
            "job_id": "def456",
            "job_title": "Data Analyst",
            "employer_name": "Rain",
            "job_publisher": "Bayt",
            "job_city": "Riyadh",
            "job_country": "SA",
            "job_description": "Dashboards.",
            "job_apply_link": "https://www.bayt.com/en/job/456",
            "job_is_remote": True,
            "apply_options": [{"publisher": "Bayt", "apply_link": "https://www.bayt.com/en/job/456"}],
        },
        {"job_id": "no-title", "employer_name": "Ghost"},  # must be skipped
    ]},
}


def _client(monkeypatch, *, payload=PAYLOAD, status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        # Page 2 onward is empty, so pagination terminates.
        if request.url.params.get("cursor"):
            return httpx.Response(200, json={"data": {"jobs": [], "cursor": None}})
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*a, **kw):
        kw["transport"] = transport
        return real_client(*a, **kw)

    monkeypatch.setattr(httpx, "Client", fake_client)
    return JSearch("test-key")


def test_missing_key_fails_with_a_usable_message():
    with pytest.raises(JSearchError) as exc:
        JSearch("")
    assert "openwebninja.com" in str(exc.value)


def test_maps_fields_and_skips_untitled_rows(monkeypatch):
    jobs = _client(monkeypatch).search("backend engineer in Riyadh")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Senior Backend Engineer"
    assert j.company == "Tamara"
    assert j.location == "Riyadh, SA"
    assert j.publisher == "LinkedIn"
    assert j.source == "jsearch"
    assert j.posted_at is not None


def test_linkedin_filter_keeps_only_linkedin_roles(monkeypatch):
    jobs = _client(monkeypatch).linkedin_only("backend engineer in Riyadh")
    assert [j.company for j in jobs] == ["Tamara"]


def test_filter_also_matches_secondary_apply_options(monkeypatch):
    """A role published on Bayt but also listed on LinkedIn should still match."""
    jobs = _client(monkeypatch).search("x", publishers={"bayt"})
    assert {j.company for j in jobs} == {"Tamara", "Rain"}


def test_publisher_match_is_case_insensitive(monkeypatch):
    assert _client(monkeypatch).search("x", publishers={"LINKEDIN"})


def test_apply_options_are_captured(monkeypatch):
    j = _client(monkeypatch).search("x")[0]
    assert ("Bayt", "https://www.bayt.com/en/job/123") in j.apply_options


def test_apply_url_points_back_to_the_real_posting(monkeypatch):
    """We never scrape LinkedIn -- but we must send the user to it to apply."""
    j = _client(monkeypatch).search("x")[0]
    assert j.apply_url.startswith("https://www.linkedin.com/jobs/view/")


def test_country_defaults_to_saudi(monkeypatch):
    calls: list[httpx.Request] = []
    _client(monkeypatch, calls=calls).search("engineer")
    assert calls[0].url.params["country"] == "sa"


def test_bad_key_raises_rather_than_returning_empty(monkeypatch):
    with pytest.raises(JSearchError):
        _client(monkeypatch, status=401).search("engineer")


def test_quota_exhaustion_returns_what_it_has(monkeypatch):
    """A 429 mid-scan must not lose the pages already fetched."""
    assert _client(monkeypatch, status=429).search("engineer") == []


def test_pagination_follows_the_cursor_then_stops(monkeypatch):
    """search-v2 pages by cursor, not page number.

    The second response returns no cursor, so the scan stops there rather than
    burning all five requests from a 200/month quota.
    """
    calls: list[httpx.Request] = []
    jobs = _client(monkeypatch, calls=calls).search("engineer", pages=5)
    assert len(jobs) == 2
    assert len(calls) == 2
    assert calls[1].url.params["cursor"] == "next-page-token"


def test_a_null_cursor_stops_after_one_request(monkeypatch):
    payload = {"data": {"jobs": PAYLOAD["data"]["jobs"], "cursor": None}}
    calls: list[httpx.Request] = []
    _client(monkeypatch, payload=payload, calls=calls).search("engineer", pages=5)
    assert len(calls) == 1


def test_network_failure_does_not_propagate(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down")

    real_client = httpx.Client  # capture before patching, or this recurses

    def fake_client(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real_client(*a, **kw)

    monkeypatch.setattr(httpx, "Client", fake_client)
    assert JSearch("k").search("engineer") == []


# --- regressions from the first live call ------------------------------------

def test_v2_nests_jobs_under_data():
    """search-v2 returns data as a dict, not a list.

    Coding against the documented v1 shape crashed on the first real call:
    every element of `data` was a string, not a job.
    """
    assert isinstance(PAYLOAD["data"], dict)
    assert "jobs" in PAYLOAD["data"]


def test_english_is_requested_by_default(monkeypatch):
    """Without it, a Saudi search returns Arabic locations and null timestamps."""
    calls: list[httpx.Request] = []
    _client(monkeypatch, calls=calls).search("engineer")
    assert calls[0].url.params["language"] == "en"


def test_the_via_publisher_suffix_is_stripped():
    """Google appends ' • via LinkedIn' to its display location."""
    from app.sources.jsearch import _to_posting
    for raw in ("Riyadh  \u2022  via LinkedIn", "\u0627\u0644\u0631\u064a\u0627\u0636  \u2022  \u0639\u0628\u0631 LinkedIn"):
        job = _to_posting({"job_title": "X", "job_location": raw})
        assert "via" not in job.location.lower()
        assert "\u0639\u0628\u0631" not in job.location


def test_a_403_is_reported_as_a_key_problem(monkeypatch):
    """The first live call returned 403, not 401, and it was swallowed."""
    with pytest.raises(JSearchError, match="JSEARCH_API_KEY"):
        _client(monkeypatch, status=403).search("engineer")


def test_string_entries_in_jobs_are_skipped(monkeypatch):
    real = httpx.Client
    def handler(request):
        return httpx.Response(200, json={"data": {"jobs": ["garbage", None], "cursor": None}})
    monkeypatch.setattr(httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}))
    assert JSearch("k").search("engineer") == []
