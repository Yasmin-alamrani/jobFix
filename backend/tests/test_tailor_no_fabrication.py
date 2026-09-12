"""Acceptance criterion: a tailored CV contains no information absent from the original.

The checks below are written *independently* of `provenance.py`. Asserting that
the checker agrees with itself would prove nothing; these use their own plain
regexes to ask the question directly -- does the finished CV contain a figure,
a name, a posting term or a planted string that the original does not? -- and
would catch a bug in the checker rather than inherit it.

Three levels:

  1. Planted fabrications, each of a known kind, are all withheld, while the
     honest edits alongside them survive (so the property is not satisfied by
     refusing everything).
  2. A seeded random search: hundreds of proposals mixing honest phrasing,
     words from the wrong role, figures, posting terms, names, Arabic digits,
     broken reorders and unsupported skills. Every edit that survives is
     accepted, and the finished CV is checked.
  3. The whole path through the API: propose, accept every offered edit, save,
     read the stored version back.
"""
from __future__ import annotations

import random
import re

import pytest

from app.agents.analyst.profile import CvProfile
from app.agents.analyst.provenance import PHRASING
from app.agents.analyst.tailor import ProposedEdit, apply_edits, review
from tailor_fixtures import (  # noqa: F401 -- tailor_client is a fixture
    ARABIC,
    ARABIC_JD,
    CANARIES,
    CANARY_EDITS,
    JD,
    JD_ONLY_TERMS,
    LEGIT,
    ORIGINAL,
    call,
    propose,
    tailor_client,
    upload,
)

# --- the independent checks ----------------------------------------------------

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PLACEHOLDER = re.compile(r"\[add [^\]]*\]", re.I)


def _clean(text: str) -> str:
    return _PLACEHOLDER.sub(" ", text.translate(_ARABIC_DIGITS))


def figures(text: str) -> set[str]:
    return set(re.findall(r"\d+", _clean(text).replace(",", "")))


def capitalised_names(text: str) -> set[str]:
    """Acronyms and CamelCase -- the shape of tools, products and credentials."""
    return {m.lower() for m in re.findall(r"\b(?:[A-Z]{2,}\w*|[A-Za-z]*[a-z][A-Z]\w*)\b", _clean(text))}


def word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", _clean(text), re.I) is not None


def role_text(role) -> str:
    return "\n".join([role.title, role.company, role.location, role.start, role.end, *role.bullets])


def assert_adds_nothing(original: CvProfile, tailored: CvProfile, *, canaries=CANARIES,
                        job_terms=JD_ONLY_TERMS) -> None:
    before, after = original.all_text, tailored.all_text

    new_figures = figures(after) - figures(before)
    assert not new_figures, f"new figures: {new_figures}"

    new_names = capitalised_names(after) - capitalised_names(before)
    assert not new_names, f"new names: {new_names}"

    for term in job_terms:
        if not word_in(term, before):
            assert not word_in(term, after), f"posting term {term!r} got in"

    for canary in canaries:
        if word_in(canary, before) or (figures(canary) and figures(canary) <= figures(before)):
            continue
        assert not word_in(canary, after), f"planted {canary!r} got in"

    # Per role: nothing may move between jobs, even though it is "in the CV".
    for b_role, a_role in zip(original.experience, tailored.experience):
        b_text, a_text = role_text(b_role), role_text(a_role)
        assert figures(a_text) <= figures(b_text), \
            f"figure moved into {b_role.company}: {figures(a_text) - figures(b_text)}"
        assert capitalised_names(a_text) <= capitalised_names(b_text), \
            f"name moved into {b_role.company}: {capitalised_names(a_text) - capitalised_names(b_text)}"
        for other in original.experience:
            if other is not b_role and other.company and not word_in(other.company, b_text):
                assert not word_in(other.company, a_text), \
                    f"{other.company} appeared under {b_role.company}"

    # Facts tailoring may never touch.
    assert tailored.contact == original.contact
    assert tailored.education == original.education
    assert tailored.certifications == original.certifications
    assert tailored.languages == original.languages
    assert [(r.title, r.company, r.start, r.end) for r in tailored.experience] == \
           [(r.title, r.company, r.start, r.end) for r in original.experience]
    assert [len(r.bullets) for r in tailored.experience] == \
           [len(r.bullets) for r in original.experience]


def test_the_canaries_really_are_absent_from_the_original():
    """Otherwise every assertion about them below would pass vacuously."""
    for canary in CANARIES:
        assert not word_in(canary, ORIGINAL.all_text), canary
    for term in JD_ONLY_TERMS:
        assert not word_in(term, ORIGINAL.all_text), term


# --- level 1: planted fabrications ----------------------------------------------

@pytest.mark.parametrize("edit", CANARY_EDITS, ids=lambda e: f"{e.kind}:{e.target}:{e.after[:30]}")
def test_every_planted_fabrication_is_withheld(edit):
    result = review(ORIGINAL, call(edit), JD)
    assert result.edits == [], f"offered: {result.edits[0].after_text!r}"
    assert result.blocked and result.blocked[0].violations


def test_every_honest_edit_survives():
    """The property is only meaningful if the checker is not refusing everything."""
    result = review(ORIGINAL, call(*LEGIT), JD)
    assert len(result.edits) == len(LEGIT), [b.violations for b in result.blocked]


def test_accepting_everything_offered_still_adds_nothing():
    result = review(ORIGINAL, call(*LEGIT, *CANARY_EDITS), JD)
    tailored = apply_edits(ORIGINAL, result.edits, [e.id for e in result.edits])

    assert_adds_nothing(ORIGINAL, tailored)
    # ...and the honest edits did land.
    assert "Designed and built the payouts API" in tailored.all_text
    assert "PostgreSQL" in tailored.skills
    assert "[add %]" in tailored.all_text


# --- level 2: seeded random search ---------------------------------------------

REWRITE_TARGETS = ["summary", "exp0.b0", "exp0.b1", "exp0.b2", "exp1.b0", "exp1.b1",
                   "proj0.desc", "exp0.b9", "exp7.b0", "exp0.title", "education", "nonsense"]
REORDER_TARGETS = ["exp0.bullets", "exp1.bullets", "skills", "projects", "exp4.bullets"]
EXTRA_POISON = ["Kafka", "Oracle", "Harvard", "MBA", "CPA", "Scala", "fintech",
                "2012", "450", "99.9", "٥٠", "managed", "mentored", "hundreds",
                "Rain", "Tamara", "Django", "12", "8,000"]


def _cv_words(profile: CvProfile) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z؀-ۿ]+|\d[\d,]*", profile.all_text)))


def _random_call(rng: random.Random, profile: CvProfile) -> list[ProposedEdit]:
    words = _cv_words(profile)
    phrasing = sorted(PHRASING)
    bullets = [b for role in profile.experience for b in role.bullets]
    poison = CANARIES + EXTRA_POISON
    edits = []

    for _ in range(rng.randint(1, 15)):
        kind = rng.choice(["rewrite"] * 6 + ["reorder"] * 2 + ["add_skill"] * 2)
        if kind == "rewrite":
            parts = [rng.choice(words + phrasing) for _ in range(rng.randint(2, 12))]
            if rng.random() < 0.5:
                parts.insert(rng.randrange(len(parts) + 1), rng.choice(poison))
            if rng.random() < 0.2:
                parts.append("[add number]")
            if rng.random() < 0.3:
                parts[0] = parts[0].capitalize()
            edits.append(ProposedEdit(kind="rewrite", target=rng.choice(REWRITE_TARGETS),
                                      after=" ".join(parts)))
        elif kind == "reorder":
            n = rng.randint(1, 5)
            order = list(range(n))
            rng.shuffle(order)
            if rng.random() < 0.3:
                order[0] = order[-1]              # a broken permutation
            edits.append(ProposedEdit(kind="reorder", target=rng.choice(REORDER_TARGETS),
                                      order=order))
        else:
            skill = rng.choice(words + poison)
            evidence = rng.choice(bullets + ["", "Invented a sentence that is not in the CV"])
            edits.append(ProposedEdit(kind="add_skill", target="skills", after=skill,
                                      evidence=evidence))
    return edits


@pytest.mark.parametrize("profile,jd,label", [(ORIGINAL, JD, "english"),
                                              (ARABIC, ARABIC_JD, "arabic")])
def test_no_random_proposal_can_add_anything(profile, jd, label):
    offered_total = 0
    for seed in range(300):
        rng = random.Random(f"{label}-{seed}")
        result = review(profile, call(*_random_call(rng, profile)), jd)
        offered_total += len(result.edits)

        tailored = apply_edits(profile, result.edits, [e.id for e in result.edits])
        try:
            assert_adds_nothing(profile, tailored, canaries=CANARIES + EXTRA_POISON)
        except AssertionError as exc:
            offered = [(e.target, e.after_text) for e in result.edits]
            raise AssertionError(f"seed {label}-{seed}: {exc}\noffered: {offered}") from None

    # Guard against a vacuous pass: the search must have produced plenty of
    # edits that were offered and applied, not only ones that were refused.
    assert offered_total > 150, f"only {offered_total} edits were ever offered"


def test_an_arabic_posting_term_is_withheld_from_an_arabic_cv():
    edit = ProposedEdit(kind="rewrite", target="exp0.b0",
                        after="بناء واجهة برمجية للمدفوعات على كوبرنيتس تخدم 8000 تاجر")
    assert review(ARABIC, call(edit), ARABIC_JD).edits == []


def test_an_honest_arabic_rewrite_survives():
    edit = ProposedEdit(kind="rewrite", target="exp0.b0",
                        after="تطوير واجهة برمجية للمدفوعات تخدم 8000 تاجر")
    assert review(ARABIC, call(edit), ARABIC_JD).edits


# --- level 3: the whole path through the API -----------------------------------

def test_accepting_every_offered_edit_through_the_api_adds_nothing(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    assert proposal["blocked"], "the planted fabrications should have been withheld"

    every_id = [e["id"] for e in proposal["edits"]]
    saved = tailor_client.post(f"/api/tailor/{proposal['proposal_id']}/versions",
                               json={"accepted_ids": every_id})
    assert saved.status_code == 200, saved.text

    stored = tailor_client.get(f"/api/versions/{saved.json()['id']}").json()
    assert_adds_nothing(ORIGINAL, CvProfile.model_validate(stored["profile"]))


def test_a_withheld_edit_cannot_be_accepted_through_the_api(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    withheld = proposal["blocked"][0]["id"]

    response = tailor_client.post(f"/api/tailor/{proposal['proposal_id']}/versions",
                                  json={"accepted_ids": [withheld]})
    assert response.status_code == 422
    assert "withheld" in response.json()["detail"]
