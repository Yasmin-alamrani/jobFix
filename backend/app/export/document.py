"""The CV as a layout: what goes on the page, in what order, in which direction.

Both renderers consume this and nothing else. Every decision that would
otherwise be made twice -- which sections appear, what they are called, how a
date range reads, whether the page runs right to left -- is made here once.

The layout is deliberately plain, because the point of the export is to survive
an applicant tracking system:

  - one column, top to bottom; no tables, no text boxes, no side panels
  - standard section headings, in the CV's own language
  - contact details in the body, never in a page header, which many parsers
    discard along with the page number
  - dates on the line after the role, not floated to the right margin, where a
    parser reading left to right would splice them into the title
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agents.analyst.profile import CvProfile

_ARABIC_LETTER = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")

SECTION_ORDER = ("summary", "experience", "education", "skills", "certifications",
                 "projects", "languages")

HEADINGS = {
    "en": {
        "summary": "Summary", "experience": "Experience", "education": "Education",
        "skills": "Skills", "certifications": "Certifications", "projects": "Projects",
        "languages": "Languages",
    },
    "ar": {
        "summary": "الملخص", "experience": "الخبرة العملية", "education": "التعليم",
        "skills": "المهارات", "certifications": "الشهادات", "projects": "المشاريع",
        "languages": "اللغات",
    },
}

_WORDS = {
    "en": {"present": "Present", "technologies": "Technologies", "list": ", "},
    "ar": {"present": "حتى الآن", "technologies": "التقنيات", "list": "، "},
}

SEPARATOR = " · "
DASH = " – "


@dataclass
class Entry:
    """One role, degree, certificate or project."""

    title: str
    detail: str = ""
    text: str = ""
    bullets: list[str] = field(default_factory=list)


@dataclass
class Section:
    key: str
    heading: str
    text: str = ""
    entries: list[Entry] = field(default_factory=list)


@dataclass
class Document:
    lang: str               # "en" | "ar"
    direction: str          # "ltr" | "rtl"
    name: str
    contact: list[str]
    sections: list[Section]
    title: str = ""         # document metadata, e.g. the version's name

    @property
    def text(self) -> str:
        """Everything a reader would see, in reading order. Used by tests to
        check that an export carries exactly the version's content."""
        parts = [self.name, SEPARATOR.join(self.contact)]
        for section in self.sections:
            parts += [section.heading, section.text]
            for entry in section.entries:
                parts += [entry.title, entry.detail, entry.text, *entry.bullets]
        return "\n".join(p for p in parts if p)


def language(profile: CvProfile) -> str:
    """Arabic when Arabic letters outnumber Latin ones, else English.

    Counted by letters rather than by words so that an Arabic CV full of tool
    names -- PostgreSQL, Kubernetes -- still reads as Arabic, which it is.
    """
    text = profile.all_text
    arabic = len(_ARABIC_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    return "ar" if arabic > latin else "en"


def _join(*parts: str, sep: str = SEPARATOR) -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())


def _dates(start: str, end: str, current: bool, lang: str) -> str:
    if not start and not end and not current:
        return ""
    finish = _WORDS[lang]["present"] if current and not end else end
    if start and finish:
        return f"{start}{DASH}{finish}"
    return start or finish


def build(profile: CvProfile, *, title: str = "", lang: str | None = None) -> Document:
    """Lay out a profile. Pure: the same profile always gives the same document."""
    lang = lang or language(profile)
    words, headings = _WORDS[lang], HEADINGS[lang]
    contact = [c for c in (profile.contact.email, profile.contact.phone,
                           profile.contact.location, *profile.contact.links) if c.strip()]

    sections: dict[str, Section] = {}

    if profile.summary.strip():
        sections["summary"] = Section("summary", headings["summary"], text=profile.summary.strip())

    if profile.experience:
        sections["experience"] = Section("experience", headings["experience"], entries=[
            Entry(
                title=_join(role.title, role.company, sep=" — "),
                detail=_join(role.location, _dates(role.start, role.end, role.current, lang)),
                bullets=[b.strip() for b in role.bullets if b.strip()],
            )
            for role in profile.experience
        ])

    if profile.education:
        sections["education"] = Section("education", headings["education"], entries=[
            Entry(
                title=_join(edu.degree, edu.field_of_study, sep=words["list"]),
                detail=_join(edu.institution, edu.location,
                             _dates(edu.start, edu.end, False, lang), edu.grade),
            )
            for edu in profile.education
        ])

    if profile.skills:
        sections["skills"] = Section("skills", headings["skills"],
                                     text=words["list"].join(s.strip() for s in profile.skills))

    if profile.certifications:
        sections["certifications"] = Section("certifications", headings["certifications"], entries=[
            Entry(title=cert.name, detail=_join(cert.issuer, cert.year))
            for cert in profile.certifications
        ])

    if profile.projects:
        sections["projects"] = Section("projects", headings["projects"], entries=[
            Entry(
                title=project.name,
                detail=_join(
                    project.link,
                    f"{words['technologies']}: {words['list'].join(project.technologies)}"
                    if project.technologies else "",
                ),
                text=project.description.strip(),
            )
            for project in profile.projects
        ])

    if profile.languages:
        sections["languages"] = Section("languages", headings["languages"], text=SEPARATOR.join(
            f"{lng.name} ({lng.proficiency})" if lng.proficiency else lng.name
            for lng in profile.languages if lng.name
        ))

    return Document(
        lang=lang,
        direction="rtl" if lang == "ar" else "ltr",
        name=profile.contact.name.strip(),
        contact=contact,
        sections=[sections[key] for key in SECTION_ORDER if key in sections],
        title=title,
    )
