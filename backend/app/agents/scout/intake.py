"""Tier 2: read one job posting the user pasted.

This is how a LinkedIn or Bayt role enters the app. The user names a specific
page; we fetch that page once and parse it. One user action, one request --
not a crawl, which is what the sites' robots.txt forbid.

Escalation is cheapest-first, and usually stops at the first rung:

  1. **Plain HTTP + JSON-LD.** Free, no browser, no model. Most job pages
     publish schema.org JobPosting markup so search engines can index them --
     LinkedIn does this deliberately, which is why the individual posting is
     readable at all.
  2. **Browser + JSON-LD.** For pages that render their markup with JavaScript.
  3. **Browser + model.** Last resort, for pages with no structured data.

A login wall or bot check at any rung stops the attempt and reports it.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

import httpx

from app.core.safe_fetch import BlockedAddress, safe_get
from app.sources.base import JobPosting

from .browser import Page, ReadOnlyBrowser
from .extract import _meta, free_read, from_json_ld, model_read, readable_text
from .llm import ScoutModel
from .policy import USER_AGENT, Policy, PolicyViolation, WallEncountered, looks_like_a_wall

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(20.0)
# Below this, the page is almost certainly a shell that renders client-side.
MIN_USEFUL_TEXT = 400
# Past this, a model call is no longer worth the wait: the aggregator
# lookup behind this one is faster and usually knows the posting.
MODEL_BUDGET = 35.0


class IntakeError(RuntimeError):
    """The page could not be read as a job posting."""


def _plain_get(url: str) -> str:
    """Fetch the page, refusing any hop that lands on a private address.

    `safe_get` follows redirects by hand so the destination is checked again at
    every hop. A public URL that redirects to 169.254.169.254 is the whole point
    of that: the policy gate only ever saw the URL the user pasted.
    """
    response = safe_get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ar;q=0.8"},
        timeout=TIMEOUT,
    )
    if response is None:
        return ""
    return response.text if response.status_code == 200 else ""


# A posting's own address nearly always carries its id: /jobs/4468385432,
# /jdp/-52120917, /job/senior-backend-engineer-88421. A listing page does not.
_HAS_ID = re.compile(r"/[^/]*\d{4,}")


def _single_posting_page(url: str, html: str) -> bool:
    """Whether this page is one posting rather than a list of them.

    A listing page uses all the same words as a posting, so the free reader
    needs a second signal before it trusts the page's own text: an id in the
    URL, or a page that calls itself a job.
    """
    if _HAS_ID.search(urlparse(url).path):
        return True
    return "job" in (_meta(html, "og:type") or "").lower()


def fetch_one(
    url: str,
    *,
    client: ScoutModel | None = None,
    allow_browser: bool = True,
    budget: float = MODEL_BUDGET,
) -> JobPosting:
    """Read a single pasted job URL into a JobPosting.

    Cheapest first, and the model last: structured data, then the page's own
    text, then a rendered copy of both, and only then a model call -- which is
    skipped altogether once `budget` seconds have gone, because a user waiting
    on a slow page is better served by the aggregator lookup behind this.

    Raises PolicyViolation if the URL is forbidden, WallEncountered if the page
    is gated, and IntakeError if it simply is not a job posting.
    """
    started = time.monotonic()
    policy = Policy.for_pasted_url(url)
    policy.check(url)          # robots.txt and hard blocks still apply

    def done(job: JobPosting, how: str) -> JobPosting:
        job.apply_url = url
        job.source = "pasted"
        log.info("read %s %s in %.1fs", url, how, time.monotonic() - started)
        return job

    # --- rung 1: plain HTTP, no browser, no model --------------------------
    html = _plain_get(url)
    walled = bool(html) and bool(looks_like_a_wall(html))
    if walled:
        log.info("%s served a wall to a plain fetch; trying a browser", url)
    elif html:
        job = from_json_ld(html)
        if job:
            return done(job, "from JSON-LD")
        if _single_posting_page(url, html):
            page = Page(url=url, title="", text=readable_text(html))
            job = free_read(page, html)
            if job:
                return done(job, "from the page's own text")

    if not allow_browser:
        raise IntakeError(
            "That page publishes no structured job data, and browser fallback is off."
        )

    # --- rung 2: render it, still free -------------------------------------
    try:
        with ReadOnlyBrowser(policy, headless=True) as browser:
            page = browser.read(url)     # raises WallEncountered if gated
    except (WallEncountered, PolicyViolation):
        raise
    except Exception as exc:  # noqa: BLE001 -- a browser failure is not a crash
        log.warning("browser could not render %s: %s", url, exc)
        raise IntakeError(
            "That page could not be opened in time. It may be slow, or it may "
            "block automated readers."
        ) from exc

    rendered_html = html if len(html) > len(page.text) else ""
    job = from_json_ld(rendered_html)
    if job is None and _single_posting_page(url, rendered_html):
        job = free_read(page, rendered_html)
    if job:
        return done(job, "from the rendered page")

    # --- rung 3: the model -------------------------------------------------
    spent = time.monotonic() - started
    if client is not None and spent < budget:
        job = model_read(page, client)
        if job:
            return done(job, "with the model")
    elif client is not None:
        log.info("skipping the model for %s: %.0fs already spent", url, spent)

    if client is None:
        # Distinguish "we couldn't" from "you pasted the wrong thing". Blaming
        # the URL for a missing API key sends the user off fixing the wrong
        # problem.
        raise IntakeError(
            "That page publishes no structured job data, so reading it needs the "
            "model. Add GEMINI_API_KEY to backend/.env and restart the server, or "
            "paste the job description instead."
        )
    raise IntakeError(
        "That page does not look like a single job posting. Paste the link to "
        "one specific role rather than a search or listing page."
    )


def describe_failure(exc: Exception) -> str:
    """Turn an intake failure into something a person can act on."""
    if isinstance(exc, BlockedAddress):
        return (
            f"{exc} That link redirected somewhere on a private network, which "
            "this app will not follow."
        )
    if isinstance(exc, PolicyViolation):
        if "robots.txt" in str(exc):
            # The site's own rule, and the aggregator had nothing either --
            # naming robots.txt here would explain the machinery, not the fix.
            return (
                "That site does not allow automated reading of its pages. Open "
                "the posting, copy its description, and paste it below."
            )
        return (
            f"{exc} A link to one specific role usually works; a search or "
            "listing page will not."
        )
    if isinstance(exc, WallEncountered):
        return (
            "That page is behind a login wall or bot check, so it cannot be read "
            "automatically. Open it yourself and paste the description into the "
            "Match tab instead."
        )
    return str(exc)
