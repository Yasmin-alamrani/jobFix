"""Shared Gemini client.

Every model call -- the analyst's, and the scout's through `scout/llm.py` --
goes through `call_structured`, which pins the model, sets the thinking level,
constrains the reply to the schema's JSON, and validates it
with Pydantic. The validation matters: the dashboard renders straight off these
objects, so a malformed response must fail here rather than halfway up the UI.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Thinking tokens count against this, so it is set well above the largest
# reply (a full CvProfile) to leave room for the reasoning before it.
MAX_OUTPUT_TOKENS = 32_768

# A CV analysis with a PDF attached and high thinking can take a while; the
# SDK retries 408/429/5xx on its own, with backoff, before giving up.
_HTTP = types.HttpOptions(timeout=180_000, retry_options=types.HttpRetryOptions(attempts=3))

# Finish reasons that mean the reply was withheld, not cut short or malformed.
_WITHHELD = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"}

THINKING_LEVELS = ("low", "medium", "high")


class RefusalError(RuntimeError):
    """Gemini withheld the reply (a safety or policy block)."""


class MissingCredentialsError(RuntimeError):
    """GEMINI_API_KEY is not set.

    Checked before any request so the API can say exactly what to fix, instead
    of surfacing an opaque SDK error as a 500.
    """


class ModelOutputError(RuntimeError):
    """The reply could not be turned into the schema: empty, cut off, or still
    invalid after a retry."""


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        thinking: str,
        client: Any = None,
    ) -> None:
        if thinking not in THINKING_LEVELS:
            raise ValueError(
                f"GEMINI_THINKING must be one of {', '.join(THINKING_LEVELS)}, not {thinking!r}."
            )
        self._model = model
        self._thinking = thinking
        # The SDK refuses to build without a key, so an unset key leaves no
        # client and every call reports the missing key instead.
        if client is not None:
            self._client = client
        elif api_key:
            self._client = genai.Client(api_key=api_key, http_options=_HTTP)
        else:
            self._client = None

    @property
    def has_credentials(self) -> bool:
        return self._client is not None

    def call_structured(
        self,
        *,
        schema: type[T],
        system: str,
        content: list[dict[str, Any]],
        max_tokens: int = MAX_OUTPUT_TOKENS,
        effort: str | None = None,
        retries: int = 1,
    ) -> T:
        """One structured call. Returns a validated instance of `schema`."""
        if self._client is None:
            raise MissingCredentialsError(
                "No Gemini API key. Get one at https://aistudio.google.com/apikey, set "
                "GEMINI_API_KEY in backend/.env and restart the server."
            )

        prompt = types.Content(role="user", parts=[_part(block) for block in content])
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=gemini_schema(schema),
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel((effort or self._thinking).upper())
            ),
            max_output_tokens=max_tokens,
            # No tools are offered, so there is nothing to call automatically;
            # left on, the SDK logs a warning about it on every request.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        contents = [prompt]
        last_error: ValidationError | None = None
        for attempt in range(retries + 1):
            response = self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
            text = _reply_text(response)
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                last_error = exc
                log.warning("attempt %s: %s did not validate", attempt + 1, schema.__name__)
                # Show the model its own output and what was wrong with it,
                # rather than repeating the prompt and hoping.
                contents = [
                    prompt,
                    types.Content(role="model", parts=[types.Part.from_text(text=text[:4000])]),
                    types.Content(role="user", parts=[types.Part.from_text(
                        text="That did not validate against the required schema: "
                        f"{str(exc)[:600]}\n\nReturn only the corrected JSON object."
                    )]),
                ]

        raise ModelOutputError(
            f"Gemini did not return a valid {schema.__name__} after {retries + 1} attempts: "
            f"{str(last_error)[:300]}"
        )


def _reply_text(response: types.GenerateContentResponse) -> str:
    """The answer text, or the reason there is none."""
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason:
        detail = getattr(feedback, "block_reason_message", None) or ""
        raise RefusalError(
            f"Gemini blocked this request ({_name(feedback.block_reason)}). {detail}".strip()
        )
    if not response.candidates:
        raise ModelOutputError("Gemini returned no reply.")

    candidate = response.candidates[0]
    reason = _name(candidate.finish_reason)
    if reason in _WITHHELD:
        raise RefusalError(f"Gemini withheld its reply ({reason}).")
    if reason == "MAX_TOKENS":
        raise ModelOutputError(
            "Gemini ran out of room before finishing its reply. Try a shorter document."
        )

    parts = (candidate.content.parts if candidate.content else None) or []
    text = "".join(p.text for p in parts if p.text and not p.thought)
    if not text.strip():
        raise ModelOutputError("Gemini returned an empty reply.")
    return text


def _name(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


# --- failures --------------------------------------------------------------------

# Every way a call can fail that should reach the user as a message, not a crash.
FAILURES = (
    RefusalError,
    MissingCredentialsError,
    ModelOutputError,
    errors.APIError,
    httpx.TransportError,
)


def explain(exc: BaseException) -> tuple[int, str]:
    """An HTTP status and a message the user can act on, for a failed call.

    Shared by the analyst's endpoints and the scout, so the same failure reads
    the same way wherever it happens. Google reports an invalid key as a 400,
    not a 401, so for its errors the message decides as much as the code does.
    """
    if isinstance(exc, RefusalError):
        return 422, str(exc)
    if isinstance(exc, MissingCredentialsError):
        return 503, str(exc)
    if isinstance(exc, ModelOutputError):
        return 502, str(exc)
    if isinstance(exc, httpx.TransportError):
        return 503, "Could not reach the Gemini API. Check your connection."
    if isinstance(exc, errors.APIError):
        message = (exc.message or "").strip()
        if exc.code in (401, 403) or "API key" in message:
            return 503, (
                f"Gemini rejected the API key ({message.rstrip('.')}). Check GEMINI_API_KEY "
                "in backend/.env and restart the server."
            )
        if exc.code == 429:
            return 429, "Gemini's rate limit or quota was reached. Try again shortly."
        if exc.code == 503:
            return 503, "Gemini is overloaded right now. Try again in a minute."
        return 502, f"The Gemini API returned an error ({exc.code})."
    return 500, str(exc)


# --- schemas ---------------------------------------------------------------------

_DROPPED = {"$defs", "default"}


def gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON Schema with every `$ref` inlined.

    Pydantic files nested models under `$defs` and points at them with `$ref`.
    Gemini's structured output takes a subset of JSON Schema and has rejected
    `$defs` before, so the references are resolved here instead. Defaults are
    dropped: they describe what Pydantic fills in, not what the reply must hold.
    """
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})

    def inline(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [inline(item, seen) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            if name in seen:
                raise ValueError(
                    f"{model.__name__} refers to itself through {name}; flatten it before "
                    "sending it to Gemini."
                )
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            return inline({**defs[name], **siblings}, seen | {name})
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _DROPPED:
                continue
            # Under "properties" the keys are field names, one of which may
            # well be "default" -- only the values are schemas.
            out[key] = (
                {field: inline(sub, seen) for field, sub in value.items()}
                if key == "properties" else inline(value, seen)
            )
        return out

    return inline(raw, frozenset())


# --- content blocks --------------------------------------------------------------

def pdf_block(path: Path) -> dict[str, Any]:
    """A resume PDF as a content block.

    Sending the real PDF (rather than extracted text) is deliberate: the model
    needs to see the actual layout to judge visual formatting. Place this block
    *before* the text block in the content list.
    """
    return {"type": "document", "mime_type": "application/pdf", "data": path.read_bytes()}


def image_block(data: bytes, mime_type: str = "image/png") -> dict[str, Any]:
    return {"type": "image", "mime_type": mime_type, "data": data}


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _part(block: dict[str, Any]) -> types.Part:
    if block["type"] == "text":
        return types.Part.from_text(text=block["text"])
    if block["type"] in ("document", "image"):
        return types.Part.from_bytes(data=block["data"], mime_type=block["mime_type"])
    raise ValueError(f"Unknown content block type {block['type']!r}.")


_client: GeminiClient | None = None


def get_gemini() -> GeminiClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            thinking=settings.gemini_thinking,
        )
    return _client
