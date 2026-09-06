"""OpenRouter client for the scout agent.

DeepSeek v4 Flash is text-only and very cheap ($0.089/$0.177 per M against
Gemini 3.7 Flash's $0.75/$3.75), which is why the whole scout pipeline is built
to work from text rather than screenshots. Called through OpenRouter's
OpenAI-compatible endpoint with httpx -- already a dependency, so no SDK needed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = httpx.Timeout(90.0)

T = TypeVar("T", bound=BaseModel)


class OpenRouterError(RuntimeError):
    """The request could not be completed."""


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a reply that may be wrapped in prose or fences.

    Smaller models often return valid JSON inside a ```json block, or with a
    sentence before it. Rather than failing the whole batch on that, recover the
    object and let validation decide whether it is usable.
    """
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


class OpenRouter:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "deepseek/deepseek-v4-flash",
        base_url: str = BASE_URL,
        app_url: str = "https://github.com/local/job-scout",
        app_name: str = "job-scout",
    ) -> None:
        if not api_key:
            raise OpenRouterError(
                "No OpenRouter API key. Get one at https://openrouter.ai/keys "
                "and set OPENROUTER_API_KEY in backend/.env."
            )
        self._key = api_key
        self._model = model
        self._base = base_url
        # OpenRouter uses these for attribution on its leaderboards.
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": app_url,
            "X-Title": app_name,
        }

    def complete_json(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        max_tokens: int = 4000,
        temperature: float = 0.0,
        retries: int = 1,
    ) -> T:
        """One call returning a validated instance of `schema`.

        Temperature defaults to 0: this is an extraction task, and the same job
        description should yield the same requirements every run so that the
        score does not drift between scans.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    r = client.post(self._base, headers=self._headers, json=payload)
            except httpx.HTTPError as exc:
                raise OpenRouterError(f"Could not reach OpenRouter: {exc}") from exc

            if r.status_code == 401:
                raise OpenRouterError("OpenRouter rejected the API key.")
            if r.status_code == 402:
                raise OpenRouterError("OpenRouter account is out of credit.")
            if r.status_code == 429:
                raise OpenRouterError("Rate limited by OpenRouter. Try again shortly.")
            if r.status_code != 200:
                raise OpenRouterError(f"OpenRouter returned {r.status_code}: {r.text[:200]}")

            try:
                content = r.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError) as exc:
                raise OpenRouterError(f"Unexpected response shape: {exc}") from exc

            try:
                return schema.model_validate_json(_extract_json(content))
            except (ValidationError, ValueError) as exc:
                last_error = exc
                log.warning("attempt %s: model returned unusable JSON", attempt + 1)
                # Show the model its own bad output rather than repeating the
                # same prompt and hoping for a different result.
                payload["messages"] = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": content[:2000]},
                    {
                        "role": "user",
                        "content": (
                            "That did not validate against the required schema: "
                            f"{str(exc)[:400]}\n\nReturn only the corrected JSON object."
                        ),
                    },
                ]

        raise OpenRouterError(f"Model did not return valid JSON: {last_error}")
