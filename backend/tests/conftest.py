"""Shared fixtures.

The rate limiters are module-level singletons, so without this a test that
makes several requests would spend tokens the next test needs, and the suite
would fail differently depending on the order it ran in.

The Gemini key is blanked before anything reads settings. An environment
variable outranks backend/.env, so once a real key is in .env the suite still
cannot reach the API: a test that forgets to stub the model gets "no key"
instead of quietly sending a CV to Google and spending money.
"""
from __future__ import annotations

import os

os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402 -- the key must be blanked before app code loads

from app.core.ratelimit import reset_all  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    reset_all()
    yield
    reset_all()
