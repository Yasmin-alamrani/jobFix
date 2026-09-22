"""Company targeting, read from the posting and checked against it.

The model supplies a reading of the posting; this module decides which parts of
that reading may be presented as fact. The rule is mechanical:

  - A point may be labelled "stated" only if it carries a quote that appears in
    the posting. A "stated" point without one, or with a quote the posting does
    not contain, is relabelled "inferred". The model's own label is a claim;
    the quote is the evidence, and only the evidence counts.
  - A keyword survives only if the posting contains it. A term the model thinks
    an ATS "would also match" is exactly the kind of addition that ends up on a
    CV as a skill the candidate does not have.

What this cannot check is whether an inference is a *good* reading. That is why
inferences are labelled as such in the interface, and never dressed as facts.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.gemini import get_gemini, text_block
from app.core.i18n import Lang, tr, with_language
from app.prompts import data_block, targeting_v1

from .provenance import normalise, quoted_in

MAX_POSTING_CHARS = 12_000
MAX_KEYWORDS = 15

CAVEAT = (
    "Read from this job posting only -- there is no research on the company "
    "behind it. Points marked inferred are a reading of the posting, not facts "
    "about the employer."
)

Basis = Literal["stated", "inferred"]


class Signal(BaseModel):
    point: str
    basis: Basis = "inferred"
    quote: str = Field(default="", description="The posting's exact words, when stated.")


class Action(BaseModel):
    action: str
    why: str = ""
    basis: Basis = "inferred"
    quote: str = ""


class Targeting(BaseModel):
    values: list[Signal] = Field(default_factory=list)
    tone: Signal = Field(default_factory=lambda: Signal(point=""))
    keywords: list[str] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    caveat: str = ""
    prompt_version: str = ""


def _squash(text: str) -> str:
    return " ".join(text.split())


def _checked(item: Signal | Action, posting: str) -> Signal | Action:
    """Keep "stated" only when the quote is really in the posting."""
    quote = _squash(item.quote)
    if item.basis == "stated" and quote and quoted_in(quote, posting):
        return item.model_copy(update={"quote": quote})
    return item.model_copy(update={"basis": "inferred", "quote": ""})


def _in_posting(term: str, posting: str) -> bool:
    """Whole-word, case-insensitive: "Java" must not pass on "JavaScript"."""
    term = _squash(normalise(term))
    if not term:
        return False
    pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
    return re.search(pattern, _squash(normalise(posting)), re.IGNORECASE) is not None


def verify(result: Targeting, posting: str) -> Targeting:
    """Pure: apply the labelling rules to a model's answer."""
    keywords: list[str] = []
    seen: set[str] = set()
    for term in result.keywords:
        term = _squash(term)
        if term.casefold() not in seen and _in_posting(term, posting):
            seen.add(term.casefold())
            keywords.append(term)

    return Targeting(
        values=[_checked(v, posting) for v in result.values if v.point.strip()][:6],
        tone=_checked(result.tone, posting),
        keywords=keywords[:MAX_KEYWORDS],
        actions=[_checked(a, posting) for a in result.actions if a.action.strip()][:6],
        caveat=CAVEAT,
        prompt_version=targeting_v1.VERSION,
    )


def target(
    *, job_description: str, title: str = "", company: str = "", resume_text: str = "",
    lang: Lang = "en",
) -> Targeting:
    """One model call, then `verify`. Title and company go inside the fence,
    because they come from the same untrusted posting as the description."""
    header = "\n".join(x for x in (
        f"Title: {title}" if title else "", f"Company: {company}" if company else "",
    ) if x)
    posting = (f"{header}\n\n" if header else "") + job_description[:MAX_POSTING_CHARS]

    content = data_block("job_description", posting)
    if resume_text.strip():
        content += "\n\n" + data_block("resume_text", resume_text[:30_000])

    result = get_gemini().call_structured(
        schema=Targeting,
        system=with_language(targeting_v1.SYSTEM, lang),
        content=[text_block(content + "\n\nAnalyse how to target this employer.")],
    )
    checked = verify(result, posting)
    return checked.model_copy(update={"caveat": tr(checked.caveat, lang)})
