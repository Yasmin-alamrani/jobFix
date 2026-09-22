"""A CV reviewed on its own terms: what is weak, and what to do about it.

The Match tab judges a CV against one job. This judges it against no job, the
way a recruiter skims it -- the review a user wants before they know where they
will apply.

Three sources, kept apart because they deserve different amounts of trust:

- **Layout checks**, from the PDF parser: measured, not judged. Two columns,
  tables, contact details in a page header. Uploaded files only -- a pasted CV
  has no layout, and checking the plain render we made of it would be checking
  our own typesetting.
- **Content checks**, from the structured profile: counted, not judged. How many
  bullets carry a number, which roles have no dates or no description.
- **The model's review**: judgement, so it is held to evidence. A weakness whose
  quote is not in the CV is withdrawn, and an example rewrite goes through the
  same provenance check as tailoring -- one that adds a number, a name or a new
  fact is withheld rather than shown.
"""
from __future__ import annotations

import logging
import re
from enum import Enum

from pydantic import BaseModel, Field

from app.core.gemini import get_gemini, text_block
from app.core.i18n import Lang, tr_fields, with_language
from app.prompts import data_block, review_v1

from . import scoring
from .parser import ParseReport
from .profile import CvProfile, Experience
from .provenance import introduced, normalise, quoted_in
from .schemas import Severity, WritingReview
from .tailor import Target, scope_for

log = logging.getLogger(__name__)

MAX_CHARS = 30_000

# Fewer than half the bullets carrying a figure reads as a list of duties.
QUANTIFIED_SHARE = 0.5
_DIGIT = re.compile(r"\d")

# The model writes placeholders longer than the 40 characters tailoring's
# pattern allows ("[add the business outcome this made possible]"). Read as
# words, their contents would look like new claims, so for the check they are
# shortened to one the pattern knows. The example shown keeps the original.
_PLACEHOLDER_LIKE = re.compile(r"\[add [^\[\]\n]{1,80}\]", re.IGNORECASE)

_RANK = {Severity.CRITICAL: 0, Severity.MAJOR: 1, Severity.MINOR: 2}


# --- What the model returns ------------------------------------------------------

class Area(str, Enum):
    IMPACT = "impact"
    CLARITY = "clarity"
    SUMMARY = "summary"
    SKILLS = "skills"
    STRUCTURE = "structure"
    CONSISTENCY = "consistency"
    LANGUAGE = "language"
    COMPLETENESS = "completeness"


class Weakness(BaseModel):
    area: Area
    severity: Severity
    title: str = Field(description="The problem, in under ten words.")
    evidence: str = Field(
        default="",
        description="Verbatim quote of the weak text. Empty only when something is absent.",
    )
    problem: str = Field(description="Why this hurts the CV, in one or two sentences.")
    recommendation: str = Field(description="Exactly what to change, specific to this CV.")
    example: str = Field(
        default="",
        description=(
            "Optional rewrite of the quoted text only. Anything it does not already "
            "say goes in a placeholder such as [add number]."
        ),
    )


class Strength(BaseModel):
    point: str = Field(description="What works, in under twelve words.")
    evidence: str = Field(description="Verbatim quote from the CV that shows it.")


class ReviewCall(BaseModel):
    verdict: str = Field(description="Two sentences on the CV overall.")
    strengths: list[Strength] = Field(default_factory=list)
    weaknesses: list[Weakness] = Field(default_factory=list)


# --- What the user gets ------------------------------------------------------------

class ReviewedWeakness(Weakness):
    # Set when the model's example stated something the CV does not, and was
    # removed. The finding and its advice stand; only the rewrite goes.
    example_withheld: bool = False


class Check(BaseModel):
    """A measured or counted problem -- no model involved."""

    rule: str
    title: str
    evidence: str
    fix: str
    severity: Severity


class CvReview(BaseModel):
    verdict: str
    strengths: list[Strength]
    weaknesses: list[ReviewedWeakness]
    checks: list[Check]
    # Model findings dropped because the text they quoted is not in the CV.
    withheld: int = 0
    # False for a pasted CV, which has no file whose layout could be checked.
    layout_checked: bool = True
    prompt_version: str = review_v1.VERSION


# --- Checks ----------------------------------------------------------------------

def layout_checks(report: ParseReport) -> list[Check]:
    """What the parser measured: the ATS checks and the structural ones.

    Missing sections are left to `content_checks`, which reads them from the
    profile -- the parser only knows whether a heading was styled as one, and
    reporting both would name the same gap twice.
    """
    no_writing = WritingReview(issues=[], summary_verdict="")
    found = scoring.score_ats(report).deductions + [
        d for d in scoring.score_formatting(report, no_writing).deductions
        if d.rule != "fmt.missing_sections"
    ]
    return [
        Check(rule=d.rule, title=d.title, evidence=d.evidence, fix=d.fix, severity=d.severity)
        for d in found
    ]


_SECTIONS = {
    "summary": (
        "professional summary",
        Severity.MINOR,
        "Open with two or three lines on what you do, at what level, and what you "
        "are best at. It is the first thing a recruiter reads.",
    ),
    "experience": (
        "work experience",
        Severity.CRITICAL,
        "Add your roles -- internships, part-time and volunteer work count -- each "
        "with a title, employer, dates and what you did.",
    ),
    "education": (
        "education",
        Severity.MAJOR,
        "Add your highest qualification with the institution and the year. Many "
        "screens filter on it.",
    ),
    "skills": (
        "skills",
        Severity.MAJOR,
        "Add a short skills section naming the tools and methods you actually use. "
        "An ATS matches keywords against it.",
    ),
}


def _role(role: Experience) -> str:
    if role.title and role.company:
        return f"{role.title} at {role.company}"
    return role.title or role.company or "An untitled role"


def content_checks(profile: CvProfile) -> list[Check]:
    """What can be counted from the profile, without any judgement."""
    checks: list[Check] = []

    present = set(profile.sections_present)
    for key, (label, severity, fix) in _SECTIONS.items():
        if key not in present:
            checks.append(Check(
                rule=f"content.no_{key}", title=f"No {label} section",
                evidence=f"Nothing in the CV reads as a {label} section.",
                fix=fix, severity=severity,
            ))

    bullets = [b.strip() for role in profile.experience for b in role.bullets if b.strip()]
    plain = [b for b in bullets if not _DIGIT.search(normalise(b))]
    if len(bullets) >= 3 and (len(bullets) - len(plain)) / len(bullets) < QUANTIFIED_SHARE:
        checks.append(Check(
            rule="content.few_numbers",
            title=f"Only {len(bullets) - len(plain)} of {len(bullets)} bullet points include a number",
            evidence=plain[0][:200],
            fix=(
                "Recruiters skim for results. Where you know the figure -- people "
                "served, time saved, money, volume, team size -- add it. Where you "
                "do not, leave it out rather than guess."
            ),
            severity=Severity.MAJOR,
        ))

    bare = [role for role in profile.experience if not any(b.strip() for b in role.bullets)]
    if bare:
        checks.append(Check(
            rule="content.roles_without_bullets",
            title=f"{len(bare)} role{'s' if len(bare) > 1 else ''} with no description",
            evidence="; ".join(_role(r) for r in bare[:3]),
            fix=(
                "Add two to four bullet points under each role: what you did, and "
                "what changed because of it."
            ),
            severity=Severity.MAJOR,
        ))

    undated = [r for r in profile.experience if not r.start.strip() and not r.end.strip()]
    if undated:
        checks.append(Check(
            rule="content.roles_without_dates",
            title=f"{len(undated)} role{'s' if len(undated) > 1 else ''} with no dates",
            evidence="; ".join(_role(r) for r in undated[:3]),
            fix=(
                "Add a start and end date to each role, month and year. Recruiters "
                "and ATS use them to count your years of experience."
            ),
            severity=Severity.MAJOR,
        ))

    if not profile.contact.links:
        checks.append(Check(
            rule="content.no_links", title="No LinkedIn or portfolio link",
            evidence="The contact details list no web links.",
            fix=(
                "Add your LinkedIn profile URL, and a portfolio or GitHub link if your "
                "work is public. Recruiters look before they call."
            ),
            severity=Severity.MINOR,
        ))

    return checks


def contact_checks(profile: CvProfile) -> list[Check]:
    """For a pasted CV, which has no file for the ATS checks to read these from."""
    checks: list[Check] = []
    if not profile.contact.email.strip():
        checks.append(Check(
            rule="content.no_email", title="No email address",
            evidence="The contact details have no email address.",
            fix="Add a professional email address at the top of the CV.",
            severity=Severity.CRITICAL,
        ))
    if not profile.contact.phone.strip():
        checks.append(Check(
            rule="content.no_phone", title="No phone number",
            evidence="The contact details have no phone number.",
            fix="Add a mobile number with the country code, such as +966 5X XXX XXXX.",
            severity=Severity.MAJOR,
        ))
    return checks


# --- The review --------------------------------------------------------------------

def review_cv(
    resume_text: str,
    *,
    profile: CvProfile,
    report: ParseReport | None = None,
    lang: Lang = "en",
) -> CvReview:
    """Checks first, then the model, told what the checks already found.

    In Arabic the model writes its findings in Arabic and the checks are
    translated; quotes and example rewrites stay in the CV's own language.
    """
    checks = layout_checks(report) if report is not None else contact_checks(profile)
    checks = sorted(checks + content_checks(profile), key=lambda c: _RANK[c.severity])

    already = "\n".join(f"- {c.title}" for c in checks) or "- (nothing)"
    call = get_gemini().call_structured(
        schema=ReviewCall,
        system=with_language(review_v1.SYSTEM, lang),
        content=[text_block(
            data_block("resume_text", resume_text[:MAX_CHARS])
            + "\n\nAlready reported by automatic checks -- do not repeat these:\n"
            + already
            + "\n\nReview this CV."
        )],
    )
    review = verify(call, resume_text, profile=profile, checks=checks,
                    layout_checked=report is not None)
    if lang == "ar":
        review = review.model_copy(update={"checks": [
            tr_fields(c, lang, "title", "evidence", "fix") for c in review.checks
        ]})
    return review


def scope_of(quote: str, profile: CvProfile, resume_text: str) -> str:
    """What an example rewrite of `quote` may draw on -- tailoring's rule.

    A bullet may use only what its own role says: a figure from another job is
    real, but claiming it here would be false. The summary and the skills may
    draw on the whole CV. A quote the profile does not place -- a heading, or a
    line extraction split differently -- is held to itself.
    """
    if not quote:
        return resume_text
    for i, role in enumerate(profile.experience):
        if quoted_in(quote, role.title) or any(quoted_in(quote, b) for b in role.bullets):
            return scope_for(profile, Target("bullet", i))[0]
    for i, project in enumerate(profile.projects):
        if quoted_in(quote, project.description):
            return scope_for(profile, Target("desc", i))[0]
    if quoted_in(quote, profile.summary) or quoted_in(quote, ", ".join(profile.skills)):
        return resume_text
    return quote


def verify(
    call: ReviewCall,
    resume_text: str,
    *,
    profile: CvProfile,
    checks: list[Check],
    layout_checked: bool,
) -> CvReview:
    """Hold the model's review to the CV it is about.

    A quote must be in the CV, or the finding is withdrawn. An example must not
    state anything its part of the CV does not (see `scope_of`), or it is
    withheld and the finding kept without it.
    """
    withheld = 0
    weaknesses: list[ReviewedWeakness] = []
    for weakness in call.weaknesses:
        quote = weakness.evidence.strip()
        if quote and not quoted_in(quote, resume_text):
            withheld += 1
            log.info("review finding withdrawn, quote not in CV: %r", quote[:80])
            continue

        example = weakness.example.strip()
        example_withheld = False
        if example and " ".join(example.split()).casefold() == " ".join(quote.split()).casefold():
            example = ""                    # a "rewrite" that changes nothing
        elif example and introduced(
            _PLACEHOLDER_LIKE.sub("[add detail]", example),
            scope=scope_of(quote, profile, resume_text),
            whole=resume_text,
        ):
            example, example_withheld = "", True

        weaknesses.append(ReviewedWeakness(
            **{**weakness.model_dump(), "evidence": quote, "example": example},
            example_withheld=example_withheld,
        ))

    strengths = []
    for strength in call.strengths:
        if strength.evidence.strip() and quoted_in(strength.evidence, resume_text):
            strengths.append(strength)
        else:
            withheld += 1

    weaknesses.sort(key=lambda w: _RANK[w.severity])
    return CvReview(
        verdict=call.verdict.strip(),
        strengths=strengths,
        weaknesses=weaknesses,
        checks=checks,
        withheld=withheld,
        layout_checked=layout_checked,
    )
