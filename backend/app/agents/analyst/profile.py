"""The CV as structured entities.

`parser.py` already measures what an ATS trips over. This is the other half:
what the CV actually *says*, as fields rather than a wall of text.

It exists because everything downstream needs entities, not prose. Field
matching reasons over skills and titles; tailoring rewrites individual bullets
and has to put them back where they came from; export lays out sections in a
fixed order. All three would otherwise re-derive the same structure from the
same text, three times, differently.

One model call, schema-validated. Dates are kept exactly as the CV spells them,
with a parsed year alongside *only* where a real year appears -- the moment this
starts inferring "2021" from "three years ago", the profile stops being a record
of the document and becomes a guess about it.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.core.gemini import get_gemini, text_block
from app.prompts import data_block, profile_v1

log = logging.getLogger(__name__)

# Enough of the document to carry every section. Longer than this and we are
# almost certainly looking at a portfolio rather than a CV.
MAX_CHARS = 30_000


class Contact(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(
        default_factory=list, description="LinkedIn, GitHub, portfolio -- as written."
    )


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    start: str = Field(default="", description="As the CV spells it. Do not normalise.")
    end: str = Field(default="", description="Empty when the role is current.")
    start_year: int | None = Field(
        default=None, description="Only when a four-digit year is actually present."
    )
    end_year: int | None = None
    current: bool = False
    bullets: list[str] = Field(
        default_factory=list,
        description="One entry per bullet, verbatim. Never merged or rewritten.",
    )


class Education(BaseModel):
    degree: str = ""
    field_of_study: str = ""
    institution: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    end_year: int | None = None
    grade: str = Field(default="", description="GPA or classification, only if stated.")


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    year: str = Field(default="", description="Only if the CV states one.")


class Project(BaseModel):
    name: str = ""
    description: str = Field(default="", description="Verbatim. Do not summarise.")
    technologies: list[str] = Field(default_factory=list)
    link: str = ""


class Language(BaseModel):
    name: str = ""
    proficiency: str = Field(
        default="", description="Only as stated -- 'Native', 'B2'. Never inferred."
    )


class CvProfile(BaseModel):
    """What the CV says, as fields. The source of truth for tailoring and export."""

    is_resume: bool = True
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)

    @property
    def sections_present(self) -> list[str]:
        """Which sections the CV actually has. Drives the 'missing sections' advice."""
        present = []
        if self.summary.strip():
            present.append("summary")
        for name in ("experience", "education", "skills", "certifications",
                     "projects", "languages"):
            if getattr(self, name):
                present.append(name)
        return present

    @property
    def all_text(self) -> str:
        """Every string in the profile, for containment checks.

        The no-fabrication test for tailoring works by asking whether a proposed
        edit introduces a token that is not in here.
        """
        parts: list[str] = [self.summary, *self.skills]
        parts += [self.contact.name, self.contact.email, self.contact.phone,
                  self.contact.location, *self.contact.links]
        for role in self.experience:
            parts += [role.title, role.company, role.location, role.start, role.end,
                      *role.bullets]
        for edu in self.education:
            parts += [edu.degree, edu.field_of_study, edu.institution, edu.location,
                      edu.start, edu.end, edu.grade]
        for cert in self.certifications:
            parts += [cert.name, cert.issuer, cert.year]
        for project in self.projects:
            parts += [project.name, project.description, project.link,
                      *project.technologies]
        for language in self.languages:
            parts += [language.name, language.proficiency]
        return "\n".join(p for p in parts if p)


class ProfileError(RuntimeError):
    """The document could not be read as a CV."""


def extract_profile(resume_text: str) -> CvProfile:
    """Read a CV's text into entities.

    Takes text rather than a path so that a pasted CV and an uploaded file share
    one code path -- the caller runs `parse_pdf` when it has a file, and passes
    the paste straight through when it does not.
    """
    text = resume_text.strip()
    if not text:
        raise ProfileError(
            "There is no text to read. If this was a PDF, it has no text layer -- "
            "re-export it from your editor rather than as a scan."
        )

    profile = get_gemini().call_structured(
        schema=CvProfile,
        system=profile_v1.SYSTEM,
        content=[text_block(data_block("resume_text", text[:MAX_CHARS]))],
    )

    if not profile.is_resume:
        raise ProfileError(
            "That document does not read as a CV. Upload a resume rather than a "
            "cover letter, transcript or job description."
        )
    return _tidy(profile)


_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _year_in(value: str) -> int | None:
    match = _YEAR.search(value or "")
    return int(match.group(0)) if match else None


def _tidy(profile: CvProfile) -> CvProfile:
    """Repair what the model is systematically unreliable about.

    Two things, both checkable against the strings the model already returned,
    so neither invents anything:

    - A year it left null while writing one into the date string. Recovering it
      here is reading, not guessing -- and `years_evidenced` downstream depends
      on it.
    - `current` and a non-empty `end` both set. The CV says one or the other, so
      trusting the explicit end date and clearing the flag keeps the pair
      consistent without deciding anything the document did not.
    """
    for role in profile.experience:
        role.start_year = role.start_year or _year_in(role.start)
        role.end_year = role.end_year or _year_in(role.end)
        if role.current and role.end.strip() and role.end_year:
            role.current = False
        if not role.end.strip() and not role.end_year:
            # No end date at all reads as ongoing only when nothing contradicts it.
            role.current = role.current or bool(role.start.strip())

    for edu in profile.education:
        edu.end_year = edu.end_year or _year_in(edu.end)

    # Duplicate skills are a model artefact of a CV listing one twice; collapse
    # case-insensitively but keep the CV's own capitalisation.
    seen: dict[str, str] = {}
    for skill in profile.skills:
        key = skill.strip().lower()
        if key and key not in seen:
            seen[key] = skill.strip()
    profile.skills = list(seen.values())

    return profile
