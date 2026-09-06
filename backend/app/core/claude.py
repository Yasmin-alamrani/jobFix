"""Shared Anthropic client.

Every agent call goes through `call_structured`, which pins the model, enables
adaptive thinking, and validates the response against a Pydantic schema. The
schema guarantee matters: the dashboard renders straight off these objects, so
a malformed model response must fail here rather than halfway up the UI.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class RefusalError(RuntimeError):
    """Claude declined the request (stop_reason == 'refusal')."""


class MissingCredentialsError(RuntimeError):
    """No Anthropic credentials could be resolved.

    The SDK raises a bare TypeError for this at request time, which reaches the
    user as an opaque 500. Detecting it up front lets the API return something
    they can act on.
    """


class ClaudeClient:
    def __init__(self) -> None:
        settings = get_settings()
        # A bare constructor also resolves `ant auth login` profiles, so an unset
        # ANTHROPIC_API_KEY is not necessarily an error.
        kwargs: dict[str, Any] = {}
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        self._client = anthropic.Anthropic(**kwargs)
        self._model = settings.claude_model
        self._effort = settings.claude_effort

    @property
    def has_credentials(self) -> bool:
        """True when the SDK resolved a credential from any source.

        An unset ANTHROPIC_API_KEY alone does not mean unauthenticated -- the
        SDK also reads ANTHROPIC_AUTH_TOKEN and `ant auth login` profiles, and
        folds whichever it finds into these attributes.
        """
        return bool(self._client.api_key or self._client.auth_token)

    def call_structured(
        self,
        *,
        schema: type[T],
        system: str,
        content: list[dict[str, Any]],
        max_tokens: int = 16000,
        effort: str | None = None,
    ) -> T:
        """One structured call. Returns a validated instance of `schema`."""
        if not self.has_credentials:
            raise MissingCredentialsError(
                "No Anthropic credentials found. Set ANTHROPIC_API_KEY in backend/.env "
                "(or run `ant auth login`) and restart the server."
            )

        response = self._client.messages.parse(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort or self._effort},
            output_format=schema,
        )

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise RefusalError(
                f"Claude declined this request: {getattr(detail, 'explanation', 'no detail')}"
            )

        parsed = response.parsed_output
        if parsed is None:
            raise RuntimeError("Structured output was empty despite a non-refusal stop reason.")
        return parsed


def pdf_block(path: Path) -> dict[str, Any]:
    """A resume PDF as a document content block.

    Sending the real PDF (rather than extracted text) is deliberate: the model
    needs to see the actual layout to judge visual formatting. Place this block
    *before* the text block in the content list.
    """
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
    }


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


_client: ClaudeClient | None = None


def get_claude() -> ClaudeClient:
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client
