"""The scout's model client: Gemini Flash, through the analyst's client.

The scout used to run on DeepSeek via OpenRouter. It now shares the analyst's
Gemini client, which means one key, one provider that sees the CV, and one
model reading requirements -- so the brief and the Match tab cannot disagree
because two different models read the same posting differently.

This adapter keeps the scout's own interface: one prompt string in, one
validated object out, and `ScoutModelError` for every kind of failure. Callers
catch that and carry on, because one job that fails to score must not end the
scan.

Temperature is left at Gemini's default. Google advises against lowering it for
Gemini 3 models, and what keeps the ranking steady here is the schema and the
Python scoring, not sampling.
"""
from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.core.gemini import FAILURES, GeminiClient, explain, get_gemini, text_block

T = TypeVar("T", bound=BaseModel)


class ScoutModelError(RuntimeError):
    """A model call failed. The message is written for the user."""


class ScoutModel:
    def __init__(self, client: GeminiClient | None = None) -> None:
        self._client = client or get_gemini()

    @property
    def has_credentials(self) -> bool:
        return self._client.has_credentials

    def complete_json(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        effort: str | None = None,
        retries: int = 1,
    ) -> T:
        """One call returning a validated instance of `schema`.

        `effort` is the thinking level for this call. Left unset it is the
        analyst's, which is what matching needs in order to agree with the
        Match tab; extraction and the headline ask for "low".
        """
        try:
            return self._client.call_structured(
                schema=schema, system=system, content=[text_block(user)],
                effort=effort, retries=retries,
            )
        except FAILURES as exc:
            raise ScoutModelError(explain(exc)[1]) from exc


def available_model() -> ScoutModel | None:
    """The model when a key is set, else None.

    None is a working answer: a page that publishes structured job data is read
    without any model, so a missing key only closes the fallback.
    """
    model = ScoutModel()
    return model if model.has_credentials else None
