"""The token bucket, and that it is actually wired to the endpoints.

Time is injected rather than slept through -- a limiter test that waits for real
seconds is a limiter test nobody runs.
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.ratelimit import ALL_LIMITS, TokenBucket, rate_limit, reset_all
from app.main import app


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_a_burst_up_to_capacity_is_allowed():
    clock = Clock()
    bucket = TokenBucket(capacity=3, per_second=1)
    assert [bucket.take("k", now=clock) for _ in range(3)] == [0.0, 0.0, 0.0]


def test_the_next_request_past_capacity_is_told_how_long_to_wait():
    clock = Clock()
    bucket = TokenBucket(capacity=2, per_second=0.5)
    bucket.take("k", now=clock)
    bucket.take("k", now=clock)
    wait = bucket.take("k", now=clock)
    assert wait == pytest.approx(2.0)


def test_tokens_come_back_over_time():
    clock = Clock()
    bucket = TokenBucket(capacity=2, per_second=1)
    bucket.take("k", now=clock)
    bucket.take("k", now=clock)
    assert bucket.take("k", now=clock) > 0

    clock.advance(1.0)
    assert bucket.take("k", now=clock) == 0.0


def test_refill_never_exceeds_capacity():
    """An idle hour must not buy an unlimited burst."""
    clock = Clock()
    bucket = TokenBucket(capacity=2, per_second=1)
    bucket.take("k", now=clock)
    clock.advance(3600)
    assert [bucket.take("k", now=clock) for _ in range(2)] == [0.0, 0.0]
    assert bucket.take("k", now=clock) > 0


def test_clients_do_not_share_a_bucket():
    clock = Clock()
    bucket = TokenBucket(capacity=1, per_second=1)
    assert bucket.take("a", now=clock) == 0.0
    assert bucket.take("b", now=clock) == 0.0
    assert bucket.take("a", now=clock) > 0


def test_reset_empties_the_bucket():
    clock = Clock()
    bucket = TokenBucket(capacity=1, per_second=0.01)
    bucket.take("k", now=clock)
    assert bucket.take("k", now=clock) > 0
    bucket.reset()
    assert bucket.take("k", now=clock) == 0.0


def test_the_dependency_resolves_as_a_dependency_not_a_query_param():
    """Regression: a callable *class instance* has no `__globals__`.

    FastAPI resolves a dependency's annotations against that attribute, so
    `request: Request` stayed an unresolved string and became a required query
    parameter -- turning every guarded endpoint into a 422.
    """
    limit = rate_limit("probe", capacity=1, per_second=1)
    assert hasattr(limit, "__globals__")
    assert "Request" in limit.__globals__


def test_every_shipped_limit_has_a_positive_capacity():
    for limit in ALL_LIMITS:
        assert limit.bucket.capacity >= 1
        assert limit.bucket.per_second > 0


def test_a_guarded_endpoint_answers_429_with_a_retry_after():
    """The dependency refuses, and tells the client when to come back.

    Exercised against a throwaway endpoint rather than a real one: the first
    `capacity` requests are *allowed*, so pointing this at `/from-url` would
    make real network calls to whatever was pasted. The limiter is the unit
    under test; the handler behind it is not.
    """
    guard = rate_limit("probe", capacity=2, per_second=0.01)
    probe = FastAPI()

    @probe.get("/thing", dependencies=[Depends(guard)])
    def thing() -> dict:
        return {"ok": True}

    client = TestClient(probe)
    assert [client.get("/thing").status_code for _ in range(2)] == [200, 200]

    refused = client.get("/thing")
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1
    assert "Try again" in refused.json()["detail"]


def _rate_limited_routes() -> set[tuple[str, str]]:
    """Every (method, path) carrying a rate-limit dependency.

    Some routes -- the generated OpenAPI and docs endpoints -- have no
    `dependant` at all, so this cannot assume the attribute exists.
    """
    found = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        if not any(
            getattr(dep.call, "limit_name", None) for dep in dependant.dependencies
        ):
            continue
        for method in getattr(route, "methods", set()):
            found.add((method, route.path))
    return found


# The endpoints that must never be callable in a loop: each either spends API
# credit or makes us a client of someone else's server.
GUARDED = {
    ("POST", "/api/resumes"),
    ("POST", "/api/analyses"),
    ("POST", "/api/scout/find"),
    ("POST", "/api/scout/score"),
    ("POST", "/api/scout/from-url"),
    ("POST", "/api/tailor"),
    ("POST", "/api/jobs/fetch"),
    ("POST", "/api/jobs/targeting"),
}


def test_every_costly_endpoint_is_actually_guarded():
    """Asserts the wiring by introspection, so removing a limit breaks the build.

    A limiter nobody attached is the failure mode worth testing for -- the unit
    tests above would all still pass.
    """
    limited = _rate_limited_routes()
    assert GUARDED <= limited, f"unguarded: {GUARDED - limited}"


def test_reading_an_analysis_back_is_not_rate_limited():
    """The guard belongs on what costs, not on everything.

    A GET that reads a stored row spends nothing, and limiting it would make the
    UI fail while a user is simply re-reading their own result.
    """
    limited = _rate_limited_routes()
    assert ("GET", "/api/analyses/{analysis_id}") not in limited
    assert ("GET", "/api/industries") not in limited
    # Saving a version applies stored edits; it calls no model and fetches nothing.
    assert ("POST", "/api/tailor/{proposal_id}/versions") not in limited
