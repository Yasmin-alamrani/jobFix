"""Which fields a CV fits.

The model's job here is evidence, not arithmetic. It reports which of a field's
core skills the CV demonstrates, how many years it evidences, and how close the
titles are -- `fields.py` turns that into a number.

That split is the same one the whole app runs on, and it matters most here. A
model asked directly for a "fit score out of 100" produces a number that moves
between runs, cannot be explained to the user, and drifts toward flattery. A
model asked "which of these skills does the CV evidence, and quote it" produces
something checkable.
"""
from __future__ import annotations

from app.prompts import NO_FABRICATION, untrusted_data_rule

VERSION = "fields_v1"


def system(catalogue: str) -> str:
    return f"""You assess which professional fields a CV fits, for the Saudi Arabian
job market.

{NO_FABRICATION}

{untrusted_data_rule("resume_text")}

These are the fields you may assess against. Use these keys exactly and invent
no others:

{catalogue}

Pick the fields this CV plausibly fits -- at most six, fewest is better. A CV
that fits two fields well should return two, not six padded with near-misses.

For each field you return:

- `matched_skills`: core skills of that field the CV gives **direct evidence**
  for. Quote or name only what is actually there.
- `missing_skills`: core skills of that field the CV does not evidence. Be
  honest and specific -- this list is what the user acts on, and a short list
  because you were being kind is worse than useless to them.
- `years_in_field`: years of experience the CV *evidences* in this field, from
  actual dates. Null when the dates do not support a number. Do not round up and
  do not count unrelated experience.
- `title_alignment`: `direct` when the CV's titles are titles from this field;
  `adjacent` when they are a neighbouring discipline that transfers; `distant`
  when a move into this field would be a career change.
- `justification`: ONE sentence on why this field fits, in plain language.
  Describe the evidence, not the strength -- do not write "strong match",
  "excellent fit", or any score, percentage or grade. A number is computed
  elsewhere and yours would contradict it.

Assess against what the CV demonstrates, not what it aspires to. A stated
interest in a field is not experience in it."""
