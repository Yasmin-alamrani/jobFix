"""The Gemini client, exercised without a key or a network.

Most tests hand the client a stand-in for the SDK. One goes a layer lower and
checks the request the real SDK puts on the wire, so a wrong field name fails
here rather than on the first real CV.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from fastapi import HTTPException
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.agents.analyst.analyzer import _MatchCall
from app.agents.analyst.fields import FieldCandidates
from app.agents.analyst.profile import CvProfile
from app.agents.analyst.schemas import WritingReview
from app.agents.analyst.tailor import TailorCall
from app.agents.analyst.targeting import Targeting
from app.api.resumes import model_errors
from app.core.gemini import (
    MAX_OUTPUT_TOKENS,
    GeminiClient,
    MissingCredentialsError,
    ModelOutputError,
    RefusalError,
    gemini_schema,
    pdf_block,
    text_block,
)


class Pick(BaseModel):
    skill: str
    years: int


GOOD = '{"skill": "Python", "years": 5}'


def reply(text=None, *, finish="STOP", thought=None, block=None):
    if block:
        return types.GenerateContentResponse.model_validate(
            {"prompt_feedback": {"block_reason": block}}
        )
    parts = []
    if thought:
        parts.append({"text": thought, "thought": True})
    if text is not None:
        parts.append({"text": text})
    return types.GenerateContentResponse.model_validate({
        "candidates": [{"content": {"role": "model", "parts": parts}, "finish_reason": finish}]
    })


class FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self.replies.pop(0)


class FakeSdk:
    def __init__(self, *replies):
        self.models = FakeModels(replies)


def client_with(*replies, thinking="high"):
    sdk = FakeSdk(*replies)
    client = GeminiClient(api_key="test-key", model="gemini-3.8-flash", thinking=thinking,
                          client=sdk)
    return client, sdk.models


def ask(client, **kw):
    return client.call_structured(schema=Pick, system="Extract.",
                                  content=[text_block("CV")], **kw)


# --- schemas ------------------------------------------------------------------------

def keys_in(node, found=None):
    """Every schema keyword in the tree -- property names excluded."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key == "properties":
                for sub in value.values():
                    keys_in(sub, found)
            else:
                keys_in(value, found)
    elif isinstance(node, list):
        for item in node:
            keys_in(item, found)
    return found


@pytest.mark.parametrize("schema", [
    CvProfile, FieldCandidates, _MatchCall, WritingReview, Targeting, TailorCall,
])
def test_every_analyst_schema_is_sent_flat(schema):
    keys = keys_in(gemini_schema(schema))
    assert not keys & {"$ref", "$defs", "default"}
    assert "properties" in keys


def test_a_field_named_default_is_kept():
    class Odd(BaseModel):
        default: str = "x"

    assert "default" in gemini_schema(Odd)["properties"]


def test_a_recursive_schema_fails_with_a_clear_message():
    class Node(BaseModel):
        children: list[Node] = []

    with pytest.raises(ValueError, match="refers to itself"):
        gemini_schema(Node)


# --- replies ------------------------------------------------------------------------

def test_the_reply_is_validated_into_the_schema():
    client, models = client_with(reply(GOOD))
    assert ask(client) == Pick(skill="Python", years=5)

    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.system_instruction == "Extract."
    assert config.thinking_config.thinking_level == types.ThinkingLevel.HIGH
    assert config.max_output_tokens == MAX_OUTPUT_TOKENS


def test_thought_parts_are_not_part_of_the_answer():
    client, _ = client_with(reply(GOOD, thought="Let me think about the CV..."))
    assert ask(client).skill == "Python"


def test_invalid_json_is_retried_with_the_error_shown():
    client, models = client_with(reply('{"skill": "Python"}'), reply(GOOD))
    assert ask(client).years == 5

    retry = models.calls[1]["contents"]
    assert [c.role for c in retry] == ["user", "model", "user"]
    assert retry[1].parts[0].text == '{"skill": "Python"}'
    assert "did not validate" in retry[2].parts[0].text


def test_it_gives_up_after_the_retry():
    client, models = client_with(reply("{}"), reply("not json"))
    with pytest.raises(ModelOutputError, match="valid Pick after 2 attempts"):
        ask(client)
    assert len(models.calls) == 2


def test_a_blocked_prompt_is_a_refusal():
    client, _ = client_with(reply(block="PROHIBITED_CONTENT"))
    with pytest.raises(RefusalError, match="PROHIBITED_CONTENT"):
        ask(client)


def test_a_withheld_reply_is_a_refusal():
    client, _ = client_with(reply(GOOD, finish="SAFETY"))
    with pytest.raises(RefusalError, match="SAFETY"):
        ask(client)


def test_running_out_of_room_is_reported_not_retried():
    client, models = client_with(reply('{"skill": "Pyth', finish="MAX_TOKENS"))
    with pytest.raises(ModelOutputError, match="ran out of room"):
        ask(client)
    assert len(models.calls) == 1


def test_an_empty_reply_is_reported():
    client, _ = client_with(reply(thought="only thinking"))
    with pytest.raises(ModelOutputError, match="empty"):
        ask(client)


def test_effort_overrides_the_default_thinking_level():
    client, models = client_with(reply(GOOD))
    ask(client, effort="low")
    assert models.calls[0]["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW


def test_no_key_means_no_request():
    client = GeminiClient(api_key="", model="gemini-3.8-flash", thinking="high")
    assert not client.has_credentials
    with pytest.raises(MissingCredentialsError, match="GEMINI_API_KEY"):
        ask(client)


def test_an_unknown_thinking_level_is_caught_at_startup():
    with pytest.raises(ValueError, match="GEMINI_THINKING"):
        GeminiClient(api_key="k", model="m", thinking="extreme")


def test_the_suite_never_sees_a_real_key():
    """conftest blanks the key, so no test can reach the API by accident."""
    from app.core.config import get_settings
    from app.core.gemini import get_gemini

    get_settings.cache_clear()
    assert get_settings().gemini_api_key == ""
    assert not get_gemini().has_credentials


# --- the wire -------------------------------------------------------------------------

def test_the_request_the_sdk_sends(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "candidates": [{
                "content": {"role": "model", "parts": [{"text": GOOD}]},
                "finishReason": "STOP",
            }],
        })

    sdk = genai.Client(api_key="test-key", http_options=types.HttpOptions(
        httpx_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ))
    client = GeminiClient(api_key="test-key", model="gemini-3.8-flash", thinking="high",
                          client=sdk)
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4 not really")

    result = client.call_structured(schema=Pick, system="Extract.",
                                    content=[pdf_block(pdf), text_block("The CV above.")])

    assert result == Pick(skill="Python", years=5)
    assert seen["url"].endswith("/models/gemini-3.8-flash:generateContent")
    assert seen["key"] == "test-key"

    body = seen["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "Extract."
    pdf_part, text_part = body["contents"][0]["parts"]
    assert pdf_part["inlineData"]["mimeType"] == "application/pdf"
    assert base64.b64decode(pdf_part["inlineData"]["data"]) == b"%PDF-1.4 not really"
    assert text_part["text"] == "The CV above."

    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["properties"]["years"]["type"] == "integer"
    # The SDK (2.23) spells this one field in snake_case inside an otherwise
    # camelCase body. Google's JSON parsing accepts either spelling of a proto
    # field name, so both are fine -- what matters is that the level arrives.
    thinking = config["thinkingConfig"]
    assert thinking.get("thinkingLevel", thinking.get("thinking_level")) == "HIGH"
    assert config["maxOutputTokens"] == MAX_OUTPUT_TOKENS


# --- what the user is told --------------------------------------------------------------

def api_error(cls, code, status, message):
    return cls(code, {"error": {"code": code, "status": status, "message": message}})


@pytest.mark.parametrize("exc,status", [
    (RefusalError("blocked"), 422),
    (MissingCredentialsError("no key"), 503),
    (api_error(errors.ClientError, 400, "INVALID_ARGUMENT",
               "API key not valid. Please pass a valid API key."), 503),
    (api_error(errors.ClientError, 403, "PERMISSION_DENIED", "Permission denied."), 503),
    (api_error(errors.ClientError, 429, "RESOURCE_EXHAUSTED", "Quota exceeded."), 429),
    (api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "Invalid JSON payload."), 502),
    (api_error(errors.ServerError, 503, "UNAVAILABLE", "The model is overloaded."), 503),
    (api_error(errors.ServerError, 500, "INTERNAL", "Internal error."), 502),
    (httpx.ConnectError("no route"), 503),
    (ModelOutputError("cut off"), 502),
])
def test_failures_reach_the_user_as_status_codes(exc, status):
    with pytest.raises(HTTPException) as caught:
        with model_errors("analysis"):
            raise exc
    assert caught.value.status_code == status
    assert "Anthropic" not in caught.value.detail
