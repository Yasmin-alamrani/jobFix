"""Arabic for everything the app writes itself.

Three kinds of text reach a user, and each is handled differently:

- **What the model writes** -- reviews, advice, verdicts, justifications. The
  prompt is told which language to write in (`with_language`). What it quotes
  stays in the language it was quoted from, or the check that it really is a
  quote would fail.
- **What the code writes** -- automatic checks, score deductions, search notes,
  error messages. These are written in English where they are made and
  translated on the way out by `tr`, from the catalogue in `i18n_ar.py`. One
  catalogue rather than an Arabic twin beside every English message: the code
  stays readable, and a test can check that no message escapes untranslated.
- **What the documents say** -- the CV, the posting. Never translated.

The page says which language it is in with a header of its own rather than
Accept-Language, which the browser fills in by itself: someone who picks English
on an Arabic browser must get English back.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeVar

from fastapi import Request
from pydantic import BaseModel

from app.core import i18n_ar

Lang = Literal["en", "ar"]
HEADER = "x-ui-lang"

M = TypeVar("M", bound=BaseModel)


def lang_of(request: Request) -> Lang:
    return "ar" if request.headers.get(HEADER, "").strip().lower().startswith("ar") else "en"


def ui_lang(request: Request) -> Lang:
    """FastAPI dependency: the language the page is being shown in."""
    return lang_of(request)


# --- the model ---------------------------------------------------------------------

LANGUAGE_RULE_AR = """OUTPUT LANGUAGE -- ARABIC
Write every sentence you compose yourself -- titles, explanations, problems,
advice, recommendations, verdicts, notes, justifications -- in clear Modern
Standard Arabic.

Never translate what you quote. A quote from the CV or the posting stays exactly
as written, in its own language; a translated quote is not a quote, and the
check that it appears in the document will reject it. A rewrite of CV text stays
in the language of the text it rewrites. Skill names, tools, job titles and
requirements taken from a document keep the document's own wording. Enum values
and field names stay exactly as the schema defines them."""


def with_language(system: str, lang: Lang) -> str:
    """The system prompt, told which language to write in."""
    return system if lang != "ar" else f"{system}\n\n{LANGUAGE_RULE_AR}"


# --- the code's own messages ----------------------------------------------------------

@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    arabic: str
    # Whether the English template is several sentences long. Only those may
    # match several sentences at once -- otherwise "Missing required: {x}."
    # swallows the sentences after it into {x} and leaves them in English.
    multi: bool


# Slots that only ever hold a number. Matching digits there rather than any
# text keeps "{n} pages" from rewriting a quoted bullet that ends in "pages".
_NUMERIC = frozenset({"n", "c", "p", "total", "full", "code", "cv", "jd"})


def _compile(template: str) -> re.Pattern[str]:
    """An English template with {name} slots, as a whole-string regex."""
    out, pos = [], 0
    for slot in re.finditer(r"\{(\w+)\}", template):
        name = slot.group(1)
        out.append(re.escape(template[pos:slot.start()]))
        out.append(rf"(?P<{name}>[\d.,]+)" if name in _NUMERIC else f"(?P<{name}>.+?)")
        pos = slot.end()
    out.append(re.escape(template[pos:]))
    return re.compile("".join(out), re.DOTALL)


# Where one sentence ends and the next begins, in messages composed of several.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def _pattern(en: str, ar: str) -> _Pattern:
    return _Pattern(_compile(en), ar, multi=len(_SENTENCE.split(en)) > 1)


_PATTERNS = [_pattern(en, ar) for en, ar in i18n_ar.PATTERNS]
# Only ever tried on a piece of a message -- a "{role} at {company}" inside a
# label -- never on a whole string, which might be a quote from a CV.
_NESTED = [_pattern(en, ar) for en, ar in i18n_ar.NESTED_PATTERNS]


def tr(text: str, lang: Lang) -> str:
    """A message the code wrote, in the page's language.

    A message with no translation comes back unchanged: English in an Arabic
    page is a gap to fill, not an error to show.
    """
    if lang != "ar" or not text or not text.strip():
        return text
    return _translate(text.strip(), nested=False)


def _translate(text: str, *, nested: bool) -> str:
    parts = _SENTENCE.split(text)
    whole = _one(text, nested=nested, several=len(parts) > 1)
    if whole is not None:
        return whole
    # Composed messages -- "Resume not found. Upload it first." -- one
    # sentence at a time.
    if len(parts) == 1:
        return text
    return " ".join(_one(part, nested=nested, several=False) or part for part in parts)


def _one(sentence: str, *, nested: bool, several: bool) -> str | None:
    if sentence in i18n_ar.EXACT:
        return i18n_ar.EXACT[sentence]
    if nested and sentence in i18n_ar.NESTED_EXACT:
        return i18n_ar.NESTED_EXACT[sentence]
    for pattern in (*_PATTERNS, *_NESTED) if nested else _PATTERNS:
        if several and not pattern.multi:
            continue
        match = pattern.regex.fullmatch(sentence)
        if match:
            # Slots named t_* hold a message of their own ("Google for Jobs:
            # <why>"), so they are translated too; the rest -- a URL, a skill,
            # a number -- are left as they are.
            values = {
                key: _translate(value, nested=True) if key.startswith("t_") else value
                for key, value in match.groupdict().items()
            }
            return pattern.arabic.format(**values)
    return None


def tr_fields(model: M, lang: Lang, *names: str) -> M:
    """A copy of `model` with the named string fields translated."""
    if lang != "ar":
        return model
    return model.model_copy(update={name: tr(getattr(model, name), lang) for name in names})
