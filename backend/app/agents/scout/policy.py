"""What the browser agent is allowed to touch.

This is the safety layer, and it is deliberately separate from the agent that
uses it. Every rule here is enforced before a request is made, so no prompt --
including one injected into a job posting -- can talk the agent past it.

Four independent gates, all of which must pass:

  0. The URL does not point at a private address. This runs first and offline:
     it inspects the URL rather than resolving it, because a gate that does DNS
     cannot be called freely. The matching resolve-time check -- for a *name*
     that points somewhere private -- lives in `core.safe_fetch.safe_get`, on
     the fetch itself, where it also re-checks after every redirect.
  1. The host is on the allowlist.
  2. The path is not one the site's robots.txt disallows, and not one of our
     own hard-blocked patterns.
  3. The per-domain rate limiter says enough time has passed.

Gate 2 carries the findings from planning: LinkedIn's search and guest
endpoints and Bayt's job listings are disallowed for every agent, so they are
blocked here by pattern as well as by robots.txt -- belt and braces, because a
robots.txt fetch can fail open and these must never be reached.
"""
from __future__ import annotations

import fnmatch
import logging
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.core.safe_fetch import BlockedAddress, assert_public_literal

log = logging.getLogger(__name__)

USER_AGENT = "job-scout/0.1 (personal job search; +https://github.com/local/job-scout)"

# Minimum seconds between requests to the same host. Human browsing pace, not
# a throttle to be tuned down: going faster is what turns a polite reader into
# something a site treats as an attack.
DEFAULT_DELAY = 4.0

# Paths we refuse regardless of what robots.txt says, because planning
# established they are disallowed and a failed robots fetch must not open them.
HARD_BLOCKED: dict[str, tuple[str, ...]] = {
    "linkedin.com": (
        "/jobs-guest/*",            # undocumented guest search endpoint
        "/jobs?runSearch*",         # search result pages
        "/api/jobPostings/jobs*",   # internal job API
        "/jobs/view/externalApply/*",
        "/enterprise-jobs/*",
        "/in/*",                    # member profiles: never our business
        "/checkpoint/*",            # auth walls
    ),
    "bayt.com": (
        "/en/jobs/",
        "/ar/jobs/",
        "/fr/jobs/",
        "/en/jobs/*-jobs/",
        "/ar/jobs/*-jobs/",
        "/*/login/*",
    ),
}

# Signals that we have hit a wall. The correct response is to stop and report,
# never to work around it.
WALL_MARKERS = (
    "captcha", "recaptcha", "hcaptcha", "cf-challenge", "are you a robot",
    "verify you are human", "unusual traffic", "access denied",
    "sign in to continue", "authwall", "please log in to continue",
    # Cloudflare's interstitial, by its text and by the token it puts in the
    # URL. Reading it as a page wastes a browser load and a model call on a
    # challenge that will never resolve for us.
    "just a moment", "__cf_chl", "checking your browser", "enable javascript and cookies",
)


class PolicyViolation(RuntimeError):
    """The request is not permitted. Never caught and retried -- it is a stop."""


class WallEncountered(RuntimeError):
    """A login wall, CAPTCHA or bot check. Report it; do not attempt to solve it."""


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _registrable(host: str) -> str:
    """Crude eTLD+1. Good enough to match a hard-block key like 'linkedin.com'."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


@dataclass
class RateLimiter:
    """One request per host per `delay` seconds. Thread-safe."""

    delay: float = DEFAULT_DELAY
    _last: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def wait(self, host: str, *, sleep=time.sleep, now=time.monotonic) -> float:
        with self._lock:
            previous = self._last.get(host)
            current = now()
            pause = 0.0 if previous is None else max(0.0, self.delay - (current - previous))
            self._last[host] = current + pause
        if pause:
            sleep(pause)
        return pause


class Policy:
    """Decides whether a URL may be fetched."""

    def __init__(
        self,
        allowed_hosts: set[str],
        *,
        delay: float = DEFAULT_DELAY,
        respect_robots: bool = True,
    ) -> None:
        # Stored without 'www.' so the allowlist matches either spelling.
        self.allowed = {h.lower().removeprefix("www.") for h in allowed_hosts}
        self.limiter = RateLimiter(delay=delay)
        self.respect_robots = respect_robots
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    @classmethod
    def for_pasted_url(cls, url: str, *, delay: float = DEFAULT_DELAY) -> "Policy":
        """A policy scoped to one URL the user explicitly asked for.

        The host gate exists to stop the agent wandering. When a person pastes
        a specific link, that intent satisfies it -- they have named the page
        they want, and one fetch of one page is not a crawl.

        Everything else still applies. robots.txt is honoured, and the
        hard-blocked paths stay shut: pasting a link to LinkedIn's guest search
        endpoint or Bayt's job listings does not unlock them, because those are
        forbidden to automated access however we arrive at them.
        """
        host = host_of(url)
        if not host:
            raise PolicyViolation(f"Not a usable URL: {url!r}")
        return cls({host}, delay=delay, respect_robots=True)

    # --- gate 1 -------------------------------------------------------------

    def host_allowed(self, url: str) -> bool:
        host = host_of(url)
        if not host:
            return False
        # A subdomain of an allowed host is allowed; a lookalike suffix is not.
        return any(host == a or host.endswith("." + a) for a in self.allowed)

    # --- gate 2 -------------------------------------------------------------

    def hard_blocked(self, url: str) -> bool:
        parsed = urlparse(url)
        target = _registrable(host_of(url))
        patterns = HARD_BLOCKED.get(target, ())
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern + "*"):
                return True
        return False

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        key = f"{parsed.scheme}://{parsed.netloc}"
        if key in self._robots:
            return self._robots[key]

        parser: urllib.robotparser.RobotFileParser | None = None
        try:
            with httpx.Client(
                timeout=httpx.Timeout(10.0),
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(f"{key}/robots.txt")
            if response.status_code == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(response.text.splitlines())
        except httpx.HTTPError as exc:
            log.warning("robots.txt unavailable for %s: %s", key, exc)

        self._robots[key] = parser
        return parser

    def robots_allow(self, url: str) -> bool:
        """True when robots.txt permits us.

        Fails *open* on a missing or unreachable robots.txt, which is the
        convention -- but only ever for hosts already on the allowlist and
        outside HARD_BLOCKED, so the paths that actually matter stay shut.
        """
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    # --- combined -----------------------------------------------------------

    def check(self, url: str) -> None:
        """Raise PolicyViolation unless every gate passes."""
        if not url.lower().startswith(("http://", "https://")):
            raise PolicyViolation(f"Only http(s) URLs may be fetched: {url!r}")
        # Gate 0. Before the allowlist, because `for_pasted_url` builds the
        # allowlist *from the URL* -- the host gate cannot refuse an address the
        # user pasted, so something ahead of it has to.
        try:
            assert_public_literal(url)
        except BlockedAddress as exc:
            raise PolicyViolation(str(exc)) from exc
        if not self.host_allowed(url):
            raise PolicyViolation(f"{host_of(url)!r} is not on the allowlist.")
        if self.hard_blocked(url):
            raise PolicyViolation(
                f"{url} matches a hard-blocked path. This site's robots.txt "
                "forbids automated access to it."
            )
        if not self.robots_allow(url):
            raise PolicyViolation(f"robots.txt disallows {url}")

    def throttle(self, url: str) -> float:
        return self.limiter.wait(host_of(url))


def looks_like_a_wall(text: str, *, title: str = "") -> str:
    """Return the marker found, or '' when the page looks like real content."""
    haystack = f"{title}\n{text[:4000]}".lower()
    for marker in WALL_MARKERS:
        if marker in haystack:
            return marker
    return ""
