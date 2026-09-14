"""Per-client rate limiting for the endpoints that cost money or reach out.

Two kinds of endpoint need this for different reasons. An AI endpoint spends
real credit per call, so an accidental loop in the UI is a bill. A fetch
endpoint makes *us* the client of someone else's server, and hammering it from
a loop is how a polite reader becomes something a site blocks.

In-process and per-worker, which is the right size for the single-user app this
currently is: no Redis, no extra service. If this is ever deployed behind more
than one worker the buckets stop being shared, and this becomes the place to
swap in a shared store -- the dependency signature would not change.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class TokenBucket:
    """Classic token bucket: `capacity` burst, refilling at `per_second`.

    A bucket allows a burst up to its capacity and then settles to the refill
    rate, which suits this app -- a person legitimately scores several jobs in
    a row, then stops.
    """

    capacity: float
    per_second: float
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, key: str, *, now=time.monotonic) -> float:
        """Consume one token. Returns 0.0 when allowed, else seconds to wait."""
        with self._lock:
            current = now()
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=self.capacity - 1, updated=current)
                return 0.0

            elapsed = current - bucket.updated
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.per_second)
            bucket.updated = current

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return 0.0
            return (1 - bucket.tokens) / self.per_second

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def rate_limit(name: str, *, capacity: float, per_second: float):
    """Build a FastAPI dependency guarding one bucket of endpoints.

    A closure rather than a callable class on purpose. FastAPI resolves a
    dependency's annotations against its `__globals__`, which a class *instance*
    does not have -- so `request: Request` stays an unresolved string and FastAPI
    files it as a required query parameter, answering every call with a 422.
    A nested function carries the module globals and resolves correctly.

    Keyed on client IP. In single-user mode that is always the same address, so
    this is a runaway-loop guard rather than a defence against a crowd -- which
    is the threat that actually exists here.
    """
    bucket = TokenBucket(capacity=capacity, per_second=per_second)

    def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        wait = bucket.take(f"{name}:{client}")
        if wait > 0:
            raise HTTPException(
                429,
                f"Too many requests. Try again in {wait:.0f}s.",
                headers={"Retry-After": str(max(1, int(wait + 0.5)))},
            )

    # Exposed so tests can reset between cases, and so a future shared store has
    # one obvious place to be swapped in.
    dependency.bucket = bucket
    dependency.limit_name = name
    return dependency


# Analysis is two model calls with thinking enabled -- slow and the most
# expensive thing here, so the burst is small.
analysis_limit = rate_limit("analysis", capacity=5, per_second=1 / 20)

# Scoring a shortlist is cheaper per call but fans out over up to 20 jobs.
scoring_limit = rate_limit("scoring", capacity=10, per_second=1 / 10)

# Fetching a pasted URL reaches someone else's server. Paced closer to human.
fetch_limit = rate_limit("fetch", capacity=6, per_second=1 / 10)

# Upload plus profile extraction: one model call per upload.
upload_limit = rate_limit("upload", capacity=10, per_second=1 / 6)


ALL_LIMITS = (analysis_limit, scoring_limit, fetch_limit, upload_limit)


def reset_all() -> None:
    """Empty every bucket. For tests, which must not inherit each other's state."""
    for limit in ALL_LIMITS:
        limit.bucket.reset()
