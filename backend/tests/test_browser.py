"""ReadOnlyBrowser.

The security claim is that the agent *cannot* write, not that it is told not
to. These tests hold that claim: the surface tests fail the build if anyone
adds a write method, and the gate tests prove the network layer stops writes a
page starts by itself.
"""
from __future__ import annotations

import inspect

import pytest

from app.agents.scout.browser import BLOCKED_RESOURCES, WRITE_METHODS, Page, ReadOnlyBrowser
from app.agents.scout.policy import Policy, PolicyViolation, WallEncountered

ALLOWED = {"example.com", "linkedin.com", "bayt.com"}


@pytest.fixture
def policy():
    return Policy(ALLOWED, delay=0.0, respect_robots=False)


# --- layer 1: the capability surface -----------------------------------------

FORBIDDEN = (
    "click", "type", "fill", "press", "submit", "upload", "set_input_files",
    "check", "select_option", "tap", "drag", "dispatch_event", "evaluate",
    "add_cookies", "set_extra_http_headers", "login", "apply",
)


def test_the_public_surface_is_read_only():
    """If someone adds a write method, this fails -- which is the point.

    The agent cannot apply for a job or log in because no method exists that
    would. A prompt injected into a job posting cannot conjure one.
    """
    public = {
        name for name, _ in inspect.getmembers(ReadOnlyBrowser, callable)
        if not name.startswith("_")
    }
    assert public == {"read", "read_many"}, f"unexpected public methods: {public}"


@pytest.mark.parametrize("name", FORBIDDEN)
def test_no_write_capability_is_exposed(name):
    assert not hasattr(ReadOnlyBrowser, name)


def test_read_returns_plain_data_not_a_live_handle():
    """A Page must not carry anything the agent could act through."""
    fields = set(Page.__dataclass_fields__)
    assert fields == {"url", "title", "text", "blocked_writes", "screenshot"}
    for value in Page(url="u", title="t", text="x").__dict__.values():
        assert value is None or isinstance(value, (str, int, bytes))


def test_a_screenshot_is_a_read_not_a_write():
    """Capturing pixels observes the page; it does not act on it.

    The vision fallback needs an image, and adding it does not widen the
    capability surface: there is still no method that clicks, types or submits.
    The bytes are inert -- no handle back to the live page travels with them.
    """
    public = {
        name for name, _ in inspect.getmembers(ReadOnlyBrowser, callable)
        if not name.startswith("_")
    }
    assert public == {"read", "read_many"}, "screenshot must not add a public method"

    page = Page(url="u", title="t", text="x", screenshot=b"\x89PNG")
    assert isinstance(page.screenshot, bytes)


def test_screenshots_are_off_by_default():
    """Images cost money at the vision rung, so they are never captured idly."""
    import inspect as _i
    sig = _i.signature(ReadOnlyBrowser.read)
    assert sig.parameters["screenshot"].default is False
    assert sig.parameters["screenshot"].kind is _i.Parameter.KEYWORD_ONLY


# --- layer 2: the network gate -----------------------------------------------

class FakeRoute:
    def __init__(self):
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class FakeRequest:
    def __init__(self, url, method="GET", resource_type="document"):
        self.url = url
        self.method = method
        self.resource_type = resource_type


def _gate(policy, request):
    browser = ReadOnlyBrowser(policy)
    route = FakeRoute()
    browser._gate(route, request)
    return route, browser


@pytest.mark.parametrize("method", sorted(WRITE_METHODS))
def test_every_write_method_is_aborted(policy, method):
    """Even a page that submits a form on load cannot POST."""
    route, browser = _gate(policy, FakeRequest("https://example.com/apply", method))
    assert route.aborted and not route.continued
    assert browser._blocked_writes == 1


def test_a_normal_get_is_allowed(policy):
    route, _ = _gate(policy, FakeRequest("https://example.com/jobs"))
    assert route.continued and not route.aborted


def test_requests_to_other_hosts_are_aborted(policy):
    """Blocks beacons and third-party exfiltration from a loaded page."""
    route, _ = _gate(policy, FakeRequest("https://tracker.evil.com/collect"))
    assert route.aborted


@pytest.mark.parametrize("kind", sorted(BLOCKED_RESOURCES))
def test_heavy_resources_are_skipped(policy, kind):
    route, _ = _gate(policy, FakeRequest("https://example.com/x", resource_type=kind))
    assert route.aborted


def test_method_check_is_case_insensitive(policy):
    route, _ = _gate(policy, FakeRequest("https://example.com/x", "post"))
    assert route.aborted


# --- layer 3: policy, before the network ------------------------------------

def test_policy_is_enforced_before_any_request(policy):
    """A refused URL must raise without a browser ever being started."""
    browser = ReadOnlyBrowser(policy)
    assert browser._context is None
    with pytest.raises(PolicyViolation):
        browser.read("https://evil.com/jobs")


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?q=x",
    "https://www.bayt.com/en/jobs/",
    "file:///etc/passwd",
    "https://tracker.evil.com/x",
])
def test_forbidden_urls_are_refused_without_starting_a_browser(policy, url):
    with pytest.raises(PolicyViolation):
        ReadOnlyBrowser(policy).read(url)


def test_using_it_outside_a_context_manager_is_an_error(policy):
    with pytest.raises(RuntimeError, match="context manager"):
        ReadOnlyBrowser(policy).read("https://example.com/ok")


# --- walls -------------------------------------------------------------------

class FakePage:
    def __init__(self, text, title="", url="https://example.com/x"):
        self._text, self._title, self.url = text, title, url
        self.closed = False

    def goto(self, url, **kw): pass
    def title(self): return self._title
    def inner_text(self, sel): return self._text
    def close(self): self.closed = True


class FakeContext:
    def __init__(self, page): self._page = page
    def new_page(self): return self._page
    def set_default_timeout(self, ms): pass
    def route(self, pattern, handler): pass


def _browser_with(policy, page):
    browser = ReadOnlyBrowser(policy)
    browser._context = FakeContext(page)
    return browser


def test_a_wall_stops_the_run_rather_than_being_worked_around(policy):
    page = FakePage("Please complete the CAPTCHA to continue", title="Security check")
    with pytest.raises(WallEncountered, match="does not work around"):
        _browser_with(policy, page).read("https://example.com/jobs")


def test_real_content_reads_normally(policy):
    page = FakePage("Senior Backend Engineer. Python, PostgreSQL. Riyadh.", title="Careers")
    result = _browser_with(policy, page).read("https://example.com/jobs")
    assert result.title == "Careers"
    assert "Backend Engineer" in result.text


def test_the_page_is_closed_even_when_a_wall_is_hit(policy):
    page = FakePage("verify you are human")
    with pytest.raises(WallEncountered):
        _browser_with(policy, page).read("https://example.com/x")
    assert page.closed, "pages must not leak on the error path"


def test_read_many_skips_bad_urls_without_losing_the_run(policy):
    page = FakePage("Backend Engineer at Tamara", title="Job")
    browser = _browser_with(policy, page)
    pages = browser.read_many([
        "https://evil.com/x",                # off allowlist
        "https://www.bayt.com/en/jobs/",     # hard blocked
        "https://example.com/good",          # fine
    ])
    assert len(pages) == 1
    assert pages[0].title == "Job"


def test_read_many_survives_a_wall(policy):
    browser = _browser_with(policy, FakePage("Access denied"))
    assert browser.read_many(["https://example.com/a"]) == []


# --- what must stay absent ---------------------------------------------------

def test_no_stealth_or_evasion_tooling_is_referenced():
    """Defeating bot detection is what turns a rate-limit into a ban."""
    import pathlib
    source = pathlib.Path(
        "app/agents/scout/browser.py"
    ).read_text().lower()
    for banned in ("stealth", "undetected", "proxy_rotat", "solve_captcha",
                   "anticaptcha", "2captcha", "fingerprint_spoof"):
        assert banned not in source, f"{banned!r} must not appear in the browser"


def test_no_persistent_profile_or_cookie_loading():
    source = inspect.getsource(ReadOnlyBrowser.__enter__).lower()
    assert "launch_persistent_context" not in source
    assert "storage_state" not in source
    assert "new_context" in source, "each run must get a fresh anonymous context"
