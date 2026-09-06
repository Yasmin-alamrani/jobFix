"""Tier 0 source tests. Recorded fixtures only -- no live calls in CI."""
from __future__ import annotations

import datetime

import pytest

from app.sources import ats
from app.sources.base import JobPosting, strip_html
from app.sources.registry import Company, load_registry, scan

# --- strip_html --------------------------------------------------------------

def test_greenhouse_escaped_html_is_unescaped_then_stripped():
    """Regression: unescaping after stripping is a no-op that leaks raw markup.

    Greenhouse delivers `content` HTML-escaped. Stripping tags first matches
    nothing, and the later unescape then turns &lt;p&gt; into visible '<p>'.
    """
    escaped = "&lt;p&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;/p&gt;&lt;li&gt;Python &amp;amp; SQL&lt;/li&gt;"
    out = strip_html(escaped)
    assert "<" not in out and ">" not in out
    assert "About" in out and "Python & SQL" in out


def test_raw_html_is_stripped_and_scripts_removed():
    out = strip_html("<p>Hi</p><script>evil()</script><li>Go &amp; Rust</li>")
    assert "evil" not in out
    assert "Go & Rust" in out


def test_list_items_become_bullets():
    assert "- one" in strip_html("<ul><li>one</li><li>two</li></ul>")


def test_strip_html_handles_empty():
    assert strip_html("") == ""


# --- dedupe ------------------------------------------------------------------

def test_same_role_from_two_sources_collapses():
    a = JobPosting(title="Backend Engineer", company="Tamara", location="Riyadh", source="greenhouse")
    b = JobPosting(title="backend  engineer", company="TAMARA", location="riyadh!", source="ashby")
    assert a.dedupe_key == b.dedupe_key


def test_different_roles_stay_separate():
    a = JobPosting(title="Backend Engineer", company="Tamara", location="Riyadh")
    b = JobPosting(title="Frontend Engineer", company="Tamara", location="Riyadh")
    assert a.dedupe_key != b.dedupe_key


# --- adapters ----------------------------------------------------------------

GREENHOUSE_PAYLOAD = {
    "jobs": [{
        "id": 123, "title": "Backend Engineer", "company_name": "Tamara",
        "location": {"name": "Riyadh, Saudi Arabia"},
        "content": "&lt;p&gt;Build payments&lt;/p&gt;",
        "absolute_url": "https://boards.greenhouse.io/tamara/jobs/123",
        "first_published": "2026-08-01T10:00:00Z",
    }]
}

ASHBY_PAYLOAD = {
    "jobs": [
        {"id": "a1", "title": "Platform Engineer", "location": "Riyadh",
         "descriptionPlain": "Run the platform", "applyUrl": "https://jobs.ashbyhq.com/rain/a1",
         "publishedAt": "2026-08-02T10:00:00Z", "isRemote": True, "isListed": True},
        {"id": "a2", "title": "Hidden role", "isListed": False},
    ]
}

LEVER_PAYLOAD = [{
    "id": "l1", "text": "Data Engineer", "categories": {"location": "Riyadh"},
    "descriptionPlain": "Pipelines", "hostedUrl": "https://jobs.lever.co/x/l1",
    "createdAt": 1754035200000,
}]


@pytest.fixture
def no_network(monkeypatch):
    """Any adapter reaching the network in a unit test is a bug."""
    def boom(*a, **kw):
        raise AssertionError("adapter attempted a live request")
    monkeypatch.setattr(ats, "_get", boom)


def test_greenhouse_maps_fields(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: GREENHOUSE_PAYLOAD)
    job = ats.Greenhouse().fetch("tamara")[0]
    assert job.title == "Backend Engineer"
    assert job.company == "Tamara"
    assert job.location == "Riyadh, Saudi Arabia"
    assert job.description == "Build payments"      # unescaped and stripped
    assert job.external_id == "123"
    assert job.posted_at is not None


def test_ashby_skips_unlisted_roles(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: ASHBY_PAYLOAD)
    jobs = ats.Ashby().fetch("rain")
    assert [j.title for j in jobs] == ["Platform Engineer"]
    assert jobs[0].remote is True


def test_lever_converts_epoch_millis(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: LEVER_PAYLOAD)
    job = ats.Lever().fetch("x")[0]
    assert job.title == "Data Engineer"
    expected = datetime.datetime.fromtimestamp(1754035200000 / 1000)
    assert job.posted_at == expected


def test_a_dead_board_returns_empty_not_an_exception(monkeypatch):
    """Companies delete boards without warning; one 404 must not end a scan."""
    monkeypatch.setattr(ats, "_get", lambda url, **kw: None)
    for source in ats.SOURCES.values():
        assert source.fetch("gone") == []


def test_lever_tolerates_unexpected_shape(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: {"error": "nope"})
    assert ats.Lever().fetch("x") == []


# --- registry ----------------------------------------------------------------

def test_shipped_registry_loads_and_is_valid():
    reg = load_registry()
    assert reg, "registry is empty"
    assert all(c.source in ats.SOURCES for c in reg)
    assert any(c.verified for c in reg)


def test_registry_skips_unknown_sources(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "- company: Good\n  industry: tech\n  source: greenhouse\n  token: g\n"
        "- company: Bad\n  industry: tech\n  source: nonsense\n  token: b\n"
    )
    assert [c.company for c in load_registry(p)] == ["Good"]


def test_scan_uses_registry_display_name_over_board_token(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: GREENHOUSE_PAYLOAD)
    jobs = scan([Company("Tamara Financial", "fintech", "greenhouse", "tamara", True)])
    assert jobs[0].company == "Tamara Financial"


def test_scan_filters_by_industry_and_verified(monkeypatch):
    monkeypatch.setattr(ats, "_get", lambda url, **kw: GREENHOUSE_PAYLOAD)
    companies = [
        Company("A", "fintech", "greenhouse", "a", True),
        Company("B", "banking", "greenhouse", "b", True),
        Company("C", "fintech", "greenhouse", "c", False),
    ]
    # Company name is part of the dedupe key, so identical payloads from two
    # different companies are two distinct jobs -- which is what we want.
    assert {j.company for j in scan(companies, industries={"fintech"})} == {"A", "C"}
    assert {j.company for j in scan(companies, verified_only=True)} == {"A", "B"}
    assert scan(companies, industries={"energy"}) == []
