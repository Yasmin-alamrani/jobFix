"""Browser safety policy.

These are the tests that matter most in the scout agent. Everything else
decides how good the results are; these decide whether the agent can be talked
into fetching something it must not. Written before the browser that uses them.
"""
from __future__ import annotations

import httpx
import pytest

from app.agents.scout.policy import (
    HARD_BLOCKED,
    Policy,
    PolicyViolation,
    RateLimiter,
    host_of,
    looks_like_a_wall,
)

ALLOWED = {"boards-api.greenhouse.io", "api.ashbyhq.com", "linkedin.com", "bayt.com"}


@pytest.fixture
def policy():
    # robots disabled by default so each test isolates the gate it targets;
    # the robots gate has its own tests below.
    return Policy(ALLOWED, delay=0.0, respect_robots=False)


# --- gate 1: the allowlist ---------------------------------------------------

def test_allowed_host_passes(policy):
    policy.check("https://boards-api.greenhouse.io/v1/boards/tamara/jobs")


def test_unknown_host_is_refused(policy):
    with pytest.raises(PolicyViolation, match="allowlist"):
        policy.check("https://evil.example.com/jobs")


def test_subdomain_of_an_allowed_host_is_allowed(policy):
    policy.check("https://careers.linkedin.com/something")


def test_lookalike_suffix_does_not_slip_through(policy):
    """'linkedin.com.evil.com' must not match 'linkedin.com'."""
    for url in (
        "https://linkedin.com.evil.com/jobs",
        "https://notlinkedin.com/jobs",
        "https://evil-bayt.com/jobs",
    ):
        with pytest.raises(PolicyViolation):
            policy.check(url)


def test_www_prefix_is_ignored_on_both_sides(policy):
    policy.check("https://www.linkedin.com/jobs/view/123")
    Policy({"www.bayt.com"}, respect_robots=False).check("https://bayt.com/en/company/x")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,<script>x</script>",
    "ftp://linkedin.com/x",
    "//linkedin.com/jobs",
    "",
])
def test_non_http_schemes_are_refused(policy, url):
    with pytest.raises(PolicyViolation):
        policy.check(url)


# --- gate 2: hard-blocked paths ----------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=x",
    "https://www.linkedin.com/jobs?runSearch=true",
    "https://www.linkedin.com/api/jobPostings/jobs?x=1",
    "https://www.linkedin.com/in/someone",
    "https://www.linkedin.com/checkpoint/challenge",
    "https://www.bayt.com/en/jobs/",
    "https://www.bayt.com/ar/jobs/",
    "https://www.bayt.com/en/jobs/software-engineer-jobs/",
])
def test_paths_their_robots_txt_forbids_are_blocked(policy, url):
    """Verified against the live robots.txt during planning."""
    with pytest.raises(PolicyViolation, match="hard-blocked"):
        policy.check(url)


def test_an_individual_linkedin_posting_is_not_blocked(policy):
    """/jobs/view/{id} is public, carries JSON-LD, and Googlebot may index it."""
    policy.check("https://www.linkedin.com/jobs/view/4123456789")


def test_hard_blocks_survive_a_failed_robots_fetch(monkeypatch):
    """robots.txt fails open -- the hard blocks must not.

    If a robots fetch times out we fall back to permitting the host, so the
    paths planning established as forbidden have to be blocked independently
    or a network blip would open them.
    """
    def dead(*a, **kw):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "Client", dead)

    strict = Policy(ALLOWED, delay=0.0, respect_robots=True)
    with pytest.raises(PolicyViolation, match="hard-blocked"):
        strict.check("https://www.bayt.com/en/jobs/")


def test_hard_block_table_covers_both_sites():
    assert "linkedin.com" in HARD_BLOCKED and "bayt.com" in HARD_BLOCKED


# --- gate 3: robots.txt ------------------------------------------------------

def _robots(monkeypatch, body: str, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(status, text=body)

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )


def test_robots_disallow_is_obeyed(monkeypatch):
    _robots(monkeypatch, "User-agent: *\nDisallow: /private/")
    p = Policy({"example.com"}, delay=0.0)
    with pytest.raises(PolicyViolation, match="robots.txt"):
        p.check("https://example.com/private/thing")
    p.check("https://example.com/public/thing")


def test_robots_is_fetched_once_per_host(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, text="User-agent: *\nDisallow: /x/")

    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )
    p = Policy({"example.com"}, delay=0.0)
    for _ in range(4):
        p.check("https://example.com/ok")
    assert len(calls) == 1


def test_missing_robots_fails_open_for_allowed_hosts(monkeypatch):
    _robots(monkeypatch, "", status=404)
    Policy({"example.com"}, delay=0.0).check("https://example.com/anything")


# --- gate 4: rate limiting ---------------------------------------------------

def test_first_request_to_a_host_is_not_delayed():
    assert RateLimiter(delay=5.0).wait("a.com", sleep=lambda s: None, now=lambda: 100.0) == 0.0


def test_second_request_to_the_same_host_waits():
    clock = iter([100.0, 100.5])
    limiter = RateLimiter(delay=4.0)
    slept = []
    limiter.wait("a.com", sleep=slept.append, now=lambda: next(clock))
    pause = limiter.wait("a.com", sleep=slept.append, now=lambda: next(clock))
    assert pause == pytest.approx(3.5)
    assert slept == [0.0, pytest.approx(3.5)] or slept[-1] == pytest.approx(3.5)


def test_different_hosts_do_not_block_each_other():
    limiter = RateLimiter(delay=4.0)
    limiter.wait("a.com", sleep=lambda s: None, now=lambda: 100.0)
    assert limiter.wait("b.com", sleep=lambda s: None, now=lambda: 100.1) == 0.0


def test_default_pace_is_human():
    """A tighter default is what turns a polite reader into an attack."""
    from app.agents.scout.policy import DEFAULT_DELAY
    assert DEFAULT_DELAY >= 3.0


# --- walls: stop, never solve ------------------------------------------------

@pytest.mark.parametrize("text", [
    "Please complete the CAPTCHA to continue",
    "Verify you are human before proceeding",
    "We've detected unusual traffic from your network",
    "Sign in to continue to LinkedIn",
    "Access denied",
])
def test_walls_are_detected(text):
    assert looks_like_a_wall(text)


def test_real_content_is_not_mistaken_for_a_wall():
    assert not looks_like_a_wall(
        "Senior Backend Engineer at Tamara. Build payment systems in Python. "
        "Riyadh based. Apply through our careers page."
    )


def test_wall_detection_reads_the_title_too():
    assert looks_like_a_wall("Nothing here", title="Security Verification | CAPTCHA")


def test_host_of_normalises():
    assert host_of("https://WWW.LinkedIn.com/jobs/view/1") == "linkedin.com"
    assert host_of("not a url") == ""
