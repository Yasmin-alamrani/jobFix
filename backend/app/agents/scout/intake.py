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

import httpx

from app.sources.base import JobPosting

from .browser import Page, ReadOnlyBrowser
from .extract import from_json_ld, from_page
from .llm import OpenRouter
from .policy import USER_AGENT, Policy, PolicyViolation, WallEncountered, looks_like_a_wall

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(20.0)
# Below this, the page is almost certainly a shell that renders client-side.
MIN_USEFUL_TEXT = 400


class IntakeError(RuntimeError):
    """The page could not be read as a job posting."""


def _plain_get(url: str) -> str:
    try:
        with httpx.Client(
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en,ar;q=0.8"},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
        return response.text if response.status_code == 200 else ""
    except httpx.HTTPError as exc:
        log.info("plain fetch failed for %s: %s", url, exc)
        return ""


def fetch_one(
    url: str,
    *,
    client: OpenRouter | None = None,
    allow_browser: bool = True,
) -> JobPosting:
    """Read a single pasted job URL into a JobPosting.

    Raises PolicyViolation if the URL is forbidden, WallEncountered if the page
    is gated, and IntakeError if it simply is not a job posting.
    """
    policy = Policy.for_pasted_url(url)
    policy.check(url)          # robots.txt and hard blocks still apply

    # --- rung 1: plain HTTP, structured data ------------------------------
    html = _plain_get(url)
    if html:
        if looks_like_a_wall(html):
            log.info("%s served a wall to a plain fetch; trying a browser", url)
        else:
            job = from_json_ld(html)
            if job:
                job.apply_url = url
                job.source = "pasted"
                log.info("read %s from JSON-LD without a browser or a model", url)
                return job

    if not allow_browser:
        raise IntakeError(
            "That page publishes no structured job data, and browser fallback is off."
        )

    # --- rungs 2 and 3: render it -----------------------------------------
    with ReadOnlyBrowser(policy, headless=True) as browser:
        page = browser.read(url)     # raises WallEncountered if gated

    rendered_html = html if len(html) > len(page.text) else ""
    job = from_page(page, client, html=rendered_html)

    if job is None and client is None:
        # Distinguish "we couldn't" from "you pasted the wrong thing". Blaming
        # the URL for a missing API key sends the user off fixing the wrong
        # problem.
        raise IntakeError(
            "That page publishes no structured job data, so reading it needs the "
            "model. Add OPENROUTER_API_KEY to backend/.env and restart the server."
        )
    if job is None:
        raise IntakeError(
            "That page does not look like a single job posting. Paste the link to "
            "one specific role rather than a search or listing page."
        )
    job.apply_url = url
    job.source = "pasted"
    return job


def describe_failure(exc: Exception) -> str:
    """Turn an intake failure into something a person can act on."""
    if isinstance(exc, PolicyViolation):
        return (
            f"{exc} A link to one specific role usually works; a search or "
            "listing page will not."
        )
    if isinstance(exc, WallEncountered):
        return (
            "That page is behind a login wall or bot check, so it cannot be read "
            "automatically. Open it yourself and paste the description into the "
            "audit tab instead."
        )
    return str(exc)
