"""Reading a posting we may not fetch, through the aggregator it publishes to.

Some sites forbid automated reading of their pages -- LinkedIn above all -- and
that refusal is honoured: `policy.py` never lets the fetch happen. But those
same sites syndicate their postings to Google for Jobs deliberately, so the job
itself is public in a place that is meant to be read. When a pasted link cannot
be fetched, the posting is looked up there instead of scraping the page.

The lookup is by the words in the URL, and a result only counts when it is
recognisably the same posting: the site's own id in one of its apply links, or
enough of the title and company in common.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urlparse

from app.sources.base import JobPosting
from app.sources.jsearch import JSearch, JSearchError

log = logging.getLogger(__name__)

# A posting id in a path: LinkedIn's 4468385432, Bayt's 5123456.
_ID = re.compile(r"\d{6,}")

# Path words that say nothing about which job this is.
_NOISE = frozenset({
    "jobs", "job", "view", "jdp", "en", "ar", "sa", "ae", "careers", "career",
    "vacancy", "vacancies", "apply", "details", "detail", "listing", "posting",
    "at", "in", "the", "and", "of", "for", "com", "www", "p", "id",
})


def query_from(url: str) -> tuple[str, str]:
    """The words a URL spells out, and the posting id it carries."""
    path = unquote(urlparse(url).path)
    ident = (_ID.findall(path) or [""])[-1]
    words = [w for w in re.split(r"[^0-9A-Za-z؀-ۿ]+", path) if w]
    words = [w for w in words if not w.isdigit() and len(w) > 1 and w.lower() not in _NOISE]
    return " ".join(words[:12]), ident


def _is_same_posting(job: JobPosting, ident: str, words: str) -> bool:
    links = [job.apply_url, *(link for _, link in job.apply_options)]
    if ident and any(ident in (link or "") for link in links):
        return True
    wanted = {w.lower() for w in words.split()}
    if not wanted:
        return False
    have = {w.lower() for w in re.split(r"\W+", f"{job.title} {job.company}") if w}
    return len(have & wanted) >= max(2, len(wanted) // 2)


def via_aggregator(url: str, *, api_key: str, country: str = "sa") -> JobPosting | None:
    """The posting at `url`, read from Google for Jobs rather than from the page."""
    words, ident = query_from(url)
    if not api_key or not words:
        return None
    try:
        found = JSearch(api_key).search(words, country=country, date_posted="all")
    except JSearchError as exc:
        log.info("aggregator lookup failed for %s: %s", url, exc)
        return None

    for job in found:
        if _is_same_posting(job, ident, words):
            log.info("read %s through Google for Jobs", url)
            job.source = "google-jobs"
            return job
    log.info("Google for Jobs had nothing matching %s", url)
    return None
