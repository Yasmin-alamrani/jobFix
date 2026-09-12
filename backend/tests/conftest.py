"""Shared fixtures.

The rate limiters are module-level singletons, so without this a test that
makes several requests would spend tokens the next test needs, and the suite
would fail differently depending on the order it ran in.
"""
from __future__ import annotations

import pytest

from app.core.ratelimit import reset_all


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    reset_all()
    yield
    reset_all()
