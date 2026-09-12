"""The fact checker every tailored edit passes through.

Each test names one way a rewrite could add something the CV does not say, or
one way an honest rewrite could be wrongly refused. Both directions matter: a
checker that refuses everything is as useless as one that refuses nothing.
"""
from __future__ import annotations

import pytest

from app.agents.analyst.provenance import (
    introduced,
    is_named,
    numbers,
    present,
    vocabulary,
)

ROLE = """Backend Engineer
Tamara
Jan 2021
Built the payouts API used by 8,000 merchants
Migrated reporting to PostgreSQL
Worked on payment reconciliation jobs"""

OTHER = "Rain\nSupported onboarding with 12 KYC checks per day using Django"
WHOLE = ROLE + "\n" + OTHER
JD = vocabulary("Kubernetes, microservices, compliance and scalable payment systems. Lead a team.")


def kinds(text: str, **kw) -> list[str]:
    kw.setdefault("scope", ROLE)
    kw.setdefault("whole", WHOLE)
    kw.setdefault("job_terms", JD)
    return [f.kind for f in introduced(text, **kw)]


# --- honest rewrites pass ------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Designed and built the payouts API used by 8,000 merchants",
    "Built scalable payment reconciliation jobs",
    "Migrated reporting to PostgreSQL",
    "Built the payouts APIs used by 8000 merchants",          # plural, no comma
    "Built payment reconciliation jobs and the payouts API",  # reordered words
    "Engineered the payouts API used by 8,000 merchants",     # verb outside PHRASING
    "Migrated reporting to PostgreSQL, improving performance by [add %]",
    "Rebuilt reporting on PostgreSQL",                        # irregular, prefixed
    "Rewrote the payouts API used by 8,000 merchants",
    "Co-designed the payouts API",
])
def test_honest_rewrites_are_not_refused(text):
    assert kinds(text) == []


# --- figures -------------------------------------------------------------------

def test_a_new_figure_is_caught():
    assert kinds("Built the payouts API used by 9,500 merchants") == ["number"]


def test_arabic_indic_digits_are_normalised_before_comparing():
    """A figure must not slip through by being written in another script."""
    assert kinds("Built the payouts API used by ٧٣ merchants") == ["number"]
    assert numbers("٨٠٠٠") == {"8000"}


def test_a_spelled_out_quantity_is_a_figure():
    assert "number" in kinds("Tripled payment reconciliation throughput")


def test_a_figure_from_another_role_is_caught_and_explained():
    """Real, but true of a different job. Moving it is fabrication."""
    found = introduced("Built the payouts API with 12 checks", scope=ROLE, whole=WHOLE)
    assert found[0].kind == "number"
    assert "elsewhere in your CV" in found[0].message


def test_the_placeholder_is_the_one_thing_allowed_in():
    assert kinds("Reduced payment reconciliation time by [add number]") == []


def test_comma_and_plain_figures_are_the_same_figure():
    assert numbers("8,000 and 1,200") == numbers("8000 and 1200")


# --- named things --------------------------------------------------------------

@pytest.mark.parametrize("token,expected", [
    ("PostgreSQL", True), ("AWS", True), ("iOS", True), ("C++", True), ("C#", True),
    ("Node.js", True), ("CI/CD", True), ("EC2", True),
    ("built", False), ("payments", False),
])
def test_named_shapes(token, expected):
    assert is_named(token, at_sentence_start=False) is expected


def test_a_capital_mid_sentence_marks_a_name():
    assert is_named("Google", at_sentence_start=False)
    assert not is_named("Google", at_sentence_start=True)   # decided by the next rule


def test_a_tool_the_role_never_mentions_is_caught():
    assert kinds("Built the payouts API on Kubernetes") == ["named"]


def test_an_employer_mid_sentence_is_caught():
    assert kinds("Built the payouts API, as at Google") == ["named"]


def test_an_employer_opening_a_sentence_is_caught():
    """Capitalisation proves nothing at the start of a sentence, so a word
    there has to be ordinary phrasing or verb-shaped to pass as prose."""
    assert kinds("Microsoft built the payouts API") == ["named"]


def test_another_roles_employer_opening_a_bullet_is_caught():
    found = introduced("Rain migrated reporting to PostgreSQL", scope=ROLE, whole=WHOLE)
    assert [f.kind for f in found] == ["named"]
    assert "elsewhere in your CV" in found[0].message


def test_a_tool_from_another_role_is_caught():
    assert kinds("Migrated reporting to PostgreSQL and Django") == ["named"]


def test_a_credential_is_caught():
    assert kinds("Built the payouts API while completing a PhD") == ["named"]


# --- terms lifted from the posting -------------------------------------------

def test_a_lowercase_job_term_is_caught():
    """The fabrication a tailoring model is most drawn to: the posting asks for
    microservices, so the bullet grows the word."""
    assert kinds("Built payouts microservices") == ["job_term"]


def test_a_domain_term_from_the_posting_is_caught():
    assert "job_term" in kinds("Built compliance checks for payment reconciliation")


def test_generic_words_from_the_posting_are_allowed():
    """'scalable' and 'systems' assert nothing on their own."""
    assert kinds("Built scalable payment systems for reconciliation") == []


# --- leadership claims -------------------------------------------------------

@pytest.mark.parametrize("verb", ["Led", "Managed", "Mentored", "Supervised", "Spearheaded",
                                  "Founded", "Owned"])
def test_leadership_the_role_does_not_describe_is_caught(verb):
    assert kinds(f"{verb} the payouts API work") == ["claim"]


def test_leadership_the_role_does_describe_is_allowed():
    scope = "Led a team of engineers on the payouts API"
    assert kinds("Leading the payouts API team", scope=scope, whole=scope) == []


def test_words_that_merely_start_like_a_claim_are_not_claims():
    """'ledger' is not 'led'; 'found and fixed' is not 'founded'."""
    scope = "Kept the ledger of payouts"
    assert kinds("Kept the payouts ledger", scope=scope, whole=scope) == []
    assert kinds("Found and fixed payment reconciliation bugs") == []


# --- strict mode, for skill names ----------------------------------------------

def test_strict_mode_refuses_ordinary_words_that_are_not_in_scope():
    """'project planning' is ordinary phrasing in a bullet, and a claim as a skill."""
    found = introduced("project planning", scope="Built the payouts API", strict=True)
    assert {f.kind for f in found} == {"unsupported"}
    assert {f.token for f in found} == {"project", "planning"}


def test_strict_mode_accepts_a_skill_the_quote_shows():
    assert introduced("PostgreSQL", scope="Migrated reporting to PostgreSQL", strict=True) == []


# --- presence ------------------------------------------------------------------

def test_plural_and_singular_count_as_the_same_word():
    vocab = vocabulary("Built one API and several libraries")
    assert present("apis", vocab)
    assert present("library", vocab)


def test_a_compound_is_present_when_its_parts_are():
    assert present("cross-functional", vocabulary("worked with cross functional teams"))


def test_a_prefix_does_not_launder_a_domain_word():
    """'reconciliation' minus 're' is not a phrasing word, so the prefix rule
    cannot turn a new domain term into phrasing."""
    scope = "Built the payouts API"
    assert kinds("Built the payouts API and reconciliation", scope=scope, whole=scope,
                 job_terms=set()) == ["new_term"]


def test_a_new_noun_is_a_new_fact_even_when_the_posting_never_said_it():
    """Found by the random search: 'fintech' was in neither the CV nor the
    posting, so neither the name rule nor the posting rule caught it."""
    assert kinds("Built fintech payment reconciliation jobs") == ["new_term"]


def test_a_new_verb_or_adverb_is_phrasing():
    assert kinds("Rapidly rebuilt and streamlined payment reconciliation jobs") == []


def test_an_arabic_word_with_a_different_prefix_is_the_same_word():
    scope = "بناء واجهة برمجية للمدفوعات"
    assert kinds("بناء واجهة برمجية المدفوعات", scope=scope, whole=scope, job_terms=set()) == []


def test_a_new_arabic_word_counts_as_new_content():
    scope = "بناء واجهة برمجية للمدفوعات"
    assert kinds("بناء واجهة برمجية للمدفوعات السحابية", scope=scope, whole=scope,
                 job_terms=set()) == ["new_term"]


def test_an_arabic_leadership_claim_is_caught():
    scope = "بناء واجهة برمجية للمدفوعات"
    assert kinds("قيادة بناء واجهة برمجية للمدفوعات", scope=scope, whole=scope,
                 job_terms=set()) == ["claim"]


def test_findings_are_not_repeated():
    found = introduced("Kubernetes and Kubernetes again", scope="Built things")
    assert len([f for f in found if f.token == "Kubernetes"]) == 1
