"""A browser that can only read.

The security model is capability-based, not instruction-based. The agent cannot
apply for a job, log in, or submit a form because **no method exists that would
do it** -- not because a prompt asks it not to. That distinction is the whole
point: a job posting is attacker-controllable text, and an LLM told "never
submit" will submit if a page argues convincingly enough. A method that does not
exist cannot be argued into existence.

Three layers, each sufficient on its own:

  1. **Surface.** The public API is goto / read_text / read_tree / scroll. There
     is no click, type, fill, upload, or submit. `test_the_public_surface_is_read_only`
     asserts this by introspection, so adding a write method breaks the build.
  2. **Network.** A route handler aborts every non-GET request, so even a page
     that auto-submits a form on load cannot POST.
  3. **Policy.** Every navigation goes through `Policy.check` first (allowlist,
     hard-blocked paths, robots.txt, rate limit).

Also deliberately absent: cookie and profile loading, fingerprint spoofing,
proxy rotation and CAPTCHA solving. A wall raises `WallEncountered` and the run
stops. Working around bot detection is what converts a soft rate-limit into a
ban, and it is not a thing this agent does.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from types import TracebackType

from .policy import USER_AGENT, Policy, PolicyViolation, WallEncountered, looks_like_a_wall

log = logging.getLogger(__name__)

# Methods that mutate server state. Aborted at the network layer.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Not worth the bandwidth when we only read text.
BLOCKED_RESOURCES = frozenset({"image", "media", "font", "stylesheet"})
# When a screenshot is wanted the page has to look like itself, so styling and
# images are allowed through for that read only.
VISUAL_RESOURCES = frozenset({"media"})

DEFAULT_TIMEOUT_MS = 25_000


@dataclass
class Page:
    """What a read returns. Plain data -- no handle back to the live page."""

    url: str
    title: str
    text: str
    blocked_writes: int = 0
    # PNG bytes, only when a caller asked for one. A screenshot is a *read*:
    # it observes the page and changes nothing, so it does not widen the
    # capability surface the way a click or a form submission would.
    screenshot: bytes | None = None


class ReadOnlyBrowser:
    """Playwright, with every write capability removed.

    Used as a context manager:

        with ReadOnlyBrowser(policy) as browser:
            page = browser.read("https://example.com/careers")
    """

    def __init__(
        self,
        policy: Policy,
        *,
        headless: bool = True,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self._policy = policy
        self._headless = headless
        self._timeout = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._blocked_writes = 0
        self._want_visuals = False

    # --- lifecycle ----------------------------------------------------------

    def __enter__(self) -> ReadOnlyBrowser:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Playwright is not installed. Run:\n"
                "  ./.venv/bin/pip install playwright\n"
                "  ./.venv/bin/playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        # A fresh context every run: no stored cookies, no profile, no logged-in
        # session. The agent browses as an anonymous visitor and cannot act as
        # the user even by accident.
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            locale="en-SA",
            java_script_enabled=True,
        )
        self._context.set_default_timeout(self._timeout)
        self._context.route("**/*", self._gate)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:  # noqa: BLE001 - teardown must not mask the real error
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass

    # --- the network gate ---------------------------------------------------

    def _gate(self, route, request) -> None:
        """Abort anything that writes, and anything off the allowlist.

        This is the layer that holds even if a page tries to submit a form by
        itself on load, or beacons data to a third party.
        """
        if request.method.upper() in WRITE_METHODS:
            self._blocked_writes += 1
            log.info("blocked %s %s", request.method, request.url)
            route.abort()
            return
        blocked = VISUAL_RESOURCES if self._want_visuals else BLOCKED_RESOURCES
        if request.resource_type in blocked:
            route.abort()
            return
        if not self._policy.host_allowed(request.url):
            log.debug("blocked off-allowlist request to %s", request.url)
            route.abort()
            return
        route.continue_()

    # --- the only public capability -----------------------------------------

    def read(self, url: str, *, screenshot: bool = False) -> Page:
        """Navigate and return the page's text. The only way in.

        Raises PolicyViolation before any request is made, and WallEncountered
        if the page turns out to be a login wall or bot check.
        """
        # Policy first, always. A forbidden URL is refused regardless of whether
        # a browser was ever started, so the refusal cannot depend on state the
        # caller controls.
        self._policy.check(url)
        if self._context is None:
            raise RuntimeError("Use ReadOnlyBrowser as a context manager.")
        self._policy.throttle(url)

        self._want_visuals = screenshot
        before = self._blocked_writes
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            title = page.title() or ""
            text = page.inner_text("body") or ""

            marker = looks_like_a_wall(text, title=title)
            if marker:
                raise WallEncountered(
                    f"{url} is behind a wall ({marker!r}). Stopping -- this agent "
                    "does not work around login walls or bot checks."
                )

            shot = page.screenshot(full_page=False) if screenshot else None
            return Page(
                url=page.url, title=title, text=text,
                blocked_writes=self._blocked_writes - before,
                screenshot=shot,
            )
        finally:
            page.close()

    def read_many(self, urls: list[str]) -> list[Page]:
        """Read several pages, skipping the ones policy refuses.

        A blocked or walled URL is logged and skipped rather than ending the
        run: one bad link in a company registry must not lose the whole scan.
        """
        out: list[Page] = []
        for url in urls:
            try:
                out.append(self.read(url))
            except PolicyViolation as exc:
                log.info("skipped %s: %s", url, exc)
            except WallEncountered as exc:
                log.warning("skipped %s: %s", url, exc)
        return out
