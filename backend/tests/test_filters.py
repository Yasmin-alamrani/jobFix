"""Search filters. Everything here is read from what a posting states."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.scout.filters import (
    Filters,
    age_in_days,
    apply,
    seniority_of,
    work_mode_of,
)
from app.sources.base import JobPosting

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def job(title="Backend Engineer", location="Riyadh", *, days=None, remote=False) -> JobPosting:
    return JobPosting(
        title=title, company="Tamara", location=location, remote=remote,
        posted_at=None if days is None else NOW - timedelta(days=days),
    )


# --- seniority -----------------------------------------------------------------

@pytest.mark.parametrize("title,level", [
    ("Software Engineering Intern", "intern"),
    ("Graduate Trainee, Payments", "intern"),
    ("Junior Backend Developer", "junior"),
    ("Associate Data Analyst", "junior"),
    ("Mid-level Frontend Engineer", "mid"),
    ("Software Engineer II", "mid"),
    ("Senior Backend Engineer", "senior"),
    ("Sr. Data Engineer", "senior"),
    ("Software Engineer III", "senior"),
    ("Lead Platform Engineer", "lead"),
    ("Senior Engineering Manager", "lead"),       # the decisive word wins
    ("Associate Director, Risk", "lead"),
    ("Principal Architect", "lead"),
    ("مهندس برمجيات أول", "senior"),
    ("مدير تطوير الأعمال", "lead"),
    ("متدرب هندسة برمجيات", "intern"),
    ("Backend Engineer", "unknown"),              # most titles say nothing
])
def test_seniority_is_read_from_title_words(title, level):
    assert seniority_of(title) == level


def test_a_word_containing_a_level_word_is_not_that_level():
    """"Leadership" in a product name, "Seniorita" -- whole words only."""
    assert seniority_of("Backend Engineer, Leadership Tools") == "unknown"


# --- work arrangement ------------------------------------------------------------

@pytest.mark.parametrize("title,location,remote,mode", [
    ("Backend Engineer", "Riyadh", False, "onsite"),
    ("Backend Engineer", "Remote - Saudi Arabia", False, "remote"),
    ("Backend Engineer", "Riyadh", True, "remote"),           # the source's flag
    ("Backend Engineer (Hybrid)", "Riyadh", False, "hybrid"),
    ("Backend Engineer", "الرياض - عن بعد", False, "remote"),
    ("Backend Engineer", "", False, "unknown"),
])
def test_work_arrangement_comes_from_flag_and_wording(title, location, remote, mode):
    assert work_mode_of(job(title, location, remote=remote)) == mode


def test_hybrid_wins_over_a_remote_flag():
    """A hybrid role flagged remote by a source is still not fully remote."""
    assert work_mode_of(job("Engineer", "Riyadh — Hybrid", remote=True)) == "hybrid"


# --- dates -----------------------------------------------------------------------

def test_age_is_measured_in_days():
    assert age_in_days(job(days=3), now=NOW) == pytest.approx(3.0)


def test_no_date_means_no_age():
    assert age_in_days(job(), now=NOW) is None


def test_a_naive_date_is_treated_as_utc():
    naive = JobPosting(title="x", company="y", posted_at=datetime(2026, 9, 10, 12, 0))
    assert age_in_days(naive, now=NOW) == pytest.approx(3.0)


# --- applying ----------------------------------------------------------------------

JOBS = [
    job("Senior Backend Engineer", "Riyadh", days=2),
    job("Backend Engineer", "Remote", days=40),
    job("Junior Developer", "Riyadh"),                  # no date
    job("Engineering Manager", "Riyadh — Hybrid", days=5),
    job("Data Engineer", ""),                           # no place, no flag, no date
]


def titles(result) -> list[str]:
    return [j.title for j in result.kept]


def test_no_filters_keep_everything():
    result = apply(JOBS, Filters(), now=NOW)
    assert len(result.kept) == len(JOBS) and not result.hidden
    assert not Filters().active


def test_work_arrangement_filter_counts_what_it_hid():
    result = apply(JOBS, Filters(work_mode="remote", include_unstated=False), now=NOW)
    assert titles(result) == ["Backend Engineer"]
    assert result.hidden == {"work_mode": 3, "work_mode_unstated": 1}


def test_unstated_postings_are_kept_when_asked():
    result = apply(JOBS, Filters(work_mode="remote", include_unstated=True), now=NOW)
    assert "Data Engineer" in titles(result)
    assert "work_mode_unstated" not in result.hidden


def test_seniority_filter_with_and_without_unstated_titles():
    kept_unstated = apply(JOBS, Filters(seniority=frozenset({"senior"})), now=NOW)
    assert titles(kept_unstated) == ["Senior Backend Engineer", "Backend Engineer", "Data Engineer"]
    assert kept_unstated.hidden == {"seniority": 2}

    strict = apply(JOBS, Filters(seniority=frozenset({"senior"}), include_unstated=False), now=NOW)
    assert titles(strict) == ["Senior Backend Engineer"]
    assert strict.hidden == {"seniority": 2, "seniority_unstated": 2}


def test_date_filter_hides_old_and_optionally_undated_postings():
    result = apply(JOBS, Filters(posted_within_days=7, include_unstated=False), now=NOW)
    assert titles(result) == ["Senior Backend Engineer", "Engineering Manager"]
    assert result.hidden == {"posted": 1, "posted_unstated": 2}


def test_filters_combine():
    """"Data Engineer" states no place, level or date. With unstated postings
    kept (the default) it passes all three filters; without, it passes none."""
    kept = apply(JOBS, Filters(work_mode="onsite", seniority=frozenset({"senior", "junior"}),
                               posted_within_days=30), now=NOW)
    assert titles(kept) == ["Senior Backend Engineer", "Junior Developer", "Data Engineer"]

    strict = apply(JOBS, Filters(work_mode="onsite", seniority=frozenset({"senior", "junior"}),
                                 posted_within_days=30, include_unstated=False), now=NOW)
    assert titles(strict) == ["Senior Backend Engineer"]


def test_each_posting_is_counted_once_under_the_first_filter_it_fails():
    result = apply(JOBS, Filters(work_mode="remote", seniority=frozenset({"lead"}),
                                 posted_within_days=1, include_unstated=False), now=NOW)
    assert sum(result.hidden.values()) + len(result.kept) == len(JOBS)
