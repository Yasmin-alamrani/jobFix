"""The `[add number]` slots a tailored version still carries, and filling them.

Tailoring may leave a placeholder where a bullet would be stronger with a figure
the CV does not give. That figure can only come from the user -- it is theirs to
state -- so this is the one place in the app where text typed by the user enters
a version. Two ways out for each slot, and nothing else:

  fill   replace the placeholder with the user's own figure. Recorded on the
         version as user-supplied, so the provenance of every figure in an
         exported CV is known: it was in the original, or the user typed it.
  drop   the user does not have the figure. The whole item reverts to its
         original wording. Deleting just the placeholder would leave "cutting run
         time by" hanging mid-sentence; putting the original back cannot.

A version with a slot left in it is never exported. That is enforced in the
export endpoints, not left to the user interface.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.analyst.profile import CvProfile
from app.agents.analyst.provenance import PLACEHOLDER
from app.agents.analyst.tailor import editable_texts, set_text

# A figure, a unit, a currency: "40%", "SAR 2.5M", "1,200 merchants". Long
# enough for that and too short for a sentence.
MAX_VALUE = 32
_HAS_DIGIT = re.compile(r"\d|[٠-٩]")


class PlaceholderError(ValueError):
    """A fill or drop request that cannot be applied as asked."""


@dataclass(frozen=True)
class Slot:
    index: int
    target: str
    label: str
    text: str
    placeholder: str


def slots(profile: CvProfile) -> list[Slot]:
    """Every placeholder left in the profile, numbered in reading order."""
    found: list[Slot] = []
    for target, label, text in editable_texts(profile):
        for match in PLACEHOLDER.finditer(text or ""):
            found.append(Slot(len(found), target, label, text, match.group(0)))
    return found


def clean_value(raw: str) -> str:
    """Validate one figure the user typed.

    It must look like a figure: a placeholder asks for a number, and accepting a
    sentence here would turn the one sanctioned opening for user text into a
    way to write anything into an exported CV.
    """
    value = " ".join((raw or "").split())
    if not value:
        raise PlaceholderError("A figure cannot be empty. Drop the edit instead if you do not have one.")
    if len(value) > MAX_VALUE:
        raise PlaceholderError(f"“{value[:40]}…” is too long for a figure.")
    if "[" in value or "]" in value:
        raise PlaceholderError("A figure cannot contain square brackets.")
    if not _HAS_DIGIT.search(value):
        raise PlaceholderError(f"“{value}” is not a figure. It needs at least one digit.")
    return value


def fill(
    profile: CvProfile,
    *,
    values: dict[int, str],
    drop: set[int],
    originals: dict[str, str],
) -> tuple[CvProfile, list[dict]]:
    """Apply fills and drops to a copy of `profile`.

    Returns the new profile and the list of user-supplied figures it now
    contains, as {"target", "value"} records. Dropping any slot in an item
    reverts the whole item, so a drop wins over a fill in the same item.
    """
    current = slots(profile)
    known = {slot.index for slot in current}
    unknown = sorted((set(values) | drop) - known)
    if unknown:
        raise PlaceholderError(
            f"There is no placeholder {', '.join(map(str, unknown))} in this version."
        )
    cleaned = {index: clean_value(value) for index, value in values.items()}

    out = profile.model_copy(deep=True)
    supplied: list[dict] = []
    by_target: dict[str, list[Slot]] = {}
    for slot in current:
        by_target.setdefault(slot.target, []).append(slot)

    for target, item_slots in by_target.items():
        text = item_slots[0].text
        if any(slot.index in drop for slot in item_slots):
            if target not in originals:
                raise PlaceholderError(
                    f"The original wording of “{item_slots[0].label}” is not on record, "
                    "so it cannot be restored. Fill in the figure instead."
                )
            set_text(out, target, originals[target])
            continue

        # Replace occurrences in order, leaving unfilled ones in place. Counting
        # matches rather than searching for the placeholder text is what makes
        # two identical "[add number]" slots in one bullet independently fillable.
        counter = iter(item_slots)

        def substitute(match: re.Match) -> str:
            slot = next(counter)
            if slot.index in cleaned:
                supplied.append({"target": target, "value": cleaned[slot.index]})
                return cleaned[slot.index]
            return match.group(0)

        set_text(out, target, PLACEHOLDER.sub(substitute, text))

    return out, supplied
