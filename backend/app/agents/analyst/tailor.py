"""Tailoring: specific, reviewable edits to a CV for one job.

The model proposes; this module decides what the user is allowed to see.

  1. The CV is shown to the model with an ID before every editable item. The
     model refers to items by ID and supplies only the new text -- the *before*
     side of every diff is read from the profile here, so a misquoted original
     can never reach the screen.
  2. `review` resolves each proposal, then checks it with `provenance`. An edit
     that introduces a figure, a named thing, a job-description term or a
     leadership claim the edited item does not contain is moved to `blocked`,
     with the reason. Blocked edits are reported rather than silently dropped,
     because a user who is told "we withheld a suggestion that would have added
     Kubernetes" learns something true about their CV.
  3. `apply_edits` applies only accepted IDs, in a fixed order, to a copy of the
     profile the proposal was generated from. The client sends IDs and nothing
     else, so no text a client supplies can end up in a saved CV.
  4. Before a version is stored, `introduced_into` and `untouchable_changes`
     check the finished document against the original as a whole. Every edit
     was already checked; this is the backstop that makes the guarantee hold for
     the document rather than for each piece of it.

What tailoring may change: the summary, bullet wording, project descriptions,
and the order of bullets, skills and projects; and it may add to the skills list
a skill the CV already demonstrates elsewhere. It never touches titles,
employers, dates, education, certifications, languages or contact details.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.core.gemini import get_gemini, text_block
from app.prompts import data_block, tailor_v1

from .profile import CvProfile
from .provenance import PLACEHOLDER, Finding, introduced, quoted_in, vocabulary
from .schemas import Importance

log = logging.getLogger(__name__)

MAX_JD_CHARS = 12_000
MAX_EDITS = 12
# Past these lengths a "rewrite" is no longer an edit of that item.
MAX_TEXT = {"summary": 900, "bullet": 400, "desc": 700}
MAX_SKILL = 60

Kind = Literal["rewrite", "reorder", "add_skill"]


# --- what the model returns ---------------------------------------------------


class ProposedEdit(BaseModel):
    kind: Kind
    target: str = Field(description="An item ID from the CV, e.g. 'exp0.b2' or 'skills'.")
    after: str = Field(default="", description="New text for rewrite; the skill for add_skill.")
    order: list[int] = Field(default_factory=list, description="New index order, for reorder.")
    evidence: str = Field(default="", description="Verbatim CV quote, for add_skill.")
    why: str = ""
    requirement: str = ""


class Gap(BaseModel):
    requirement: str
    importance: Importance = Importance.PREFERRED
    advice: str = ""


class TailorCall(BaseModel):
    edits: list[ProposedEdit] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)


# --- what the user sees -------------------------------------------------------


class DiffOp(BaseModel):
    op: Literal["equal", "insert", "delete"]
    text: str


class Edit(BaseModel):
    id: str
    kind: Kind
    target: str
    label: str = ""
    before_text: str = ""
    after_text: str = ""
    before_items: list[str] = Field(default_factory=list)
    after_items: list[str] = Field(default_factory=list)
    order: list[int] = Field(default_factory=list)
    diff: list[DiffOp] = Field(default_factory=list)
    evidence: str = ""
    why: str = ""
    requirement: str = ""
    has_placeholder: bool = False
    violations: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    edits: list[Edit]
    blocked: list[Edit]
    gaps: list[Gap]


class UnknownEdit(ValueError):
    """An accepted ID that is not an approved edit in this proposal."""


# --- addressing items in a profile ---------------------------------------------

_TARGET = re.compile(
    r"^(?:(summary)|(skills)|(projects)|exp(\d+)\.b(\d+)|exp(\d+)\.bullets|proj(\d+)\.desc)$"
)


@dataclass(frozen=True)
class Target:
    kind: str           # summary | skills | projects | bullet | bullets | desc
    i: int = -1
    j: int = -1


# Which item kinds each edit kind may touch.
_ALLOWED = {
    "rewrite": {"summary", "bullet", "desc"},
    "reorder": {"bullets", "skills", "projects"},
    "add_skill": {"skills"},
}


def parse_target(raw: str) -> Target | None:
    match = _TARGET.match((raw or "").strip())
    if not match:
        return None
    summary, skills, projects, bi, bj, oi, pi = match.groups()
    if summary:
        return Target("summary")
    if skills:
        return Target("skills")
    if projects:
        return Target("projects")
    if bi is not None:
        return Target("bullet", int(bi), int(bj))
    if oi is not None:
        return Target("bullets", int(oi))
    return Target("desc", int(pi))


def _role_ok(profile: CvProfile, t: Target) -> bool:
    return 0 <= t.i < len(profile.experience)


def _text_at(profile: CvProfile, t: Target) -> str | None:
    if t.kind == "summary":
        return profile.summary
    if t.kind == "bullet" and _role_ok(profile, t):
        bullets = profile.experience[t.i].bullets
        return bullets[t.j] if 0 <= t.j < len(bullets) else None
    if t.kind == "desc" and 0 <= t.i < len(profile.projects):
        return profile.projects[t.i].description
    return None


def _set_text(profile: CvProfile, t: Target, value: str) -> None:
    if t.kind == "summary":
        profile.summary = value
    elif t.kind == "bullet":
        profile.experience[t.i].bullets[t.j] = value
    elif t.kind == "desc":
        profile.projects[t.i].description = value


def _items_at(profile: CvProfile, t: Target) -> list[str] | None:
    if t.kind == "skills":
        return list(profile.skills)
    if t.kind == "projects":
        return [p.name or f"Project {k + 1}" for k, p in enumerate(profile.projects)]
    if t.kind == "bullets" and _role_ok(profile, t):
        return list(profile.experience[t.i].bullets)
    return None


def _reorder(profile: CvProfile, t: Target, order: list[int]) -> None:
    if t.kind == "skills":
        profile.skills = [profile.skills[k] for k in order]
    elif t.kind == "projects":
        profile.projects = [profile.projects[k] for k in order]
    elif t.kind == "bullets":
        role = profile.experience[t.i]
        role.bullets = [role.bullets[k] for k in order]


def _who(profile: CvProfile, i: int) -> str:
    role = profile.experience[i]
    return " at ".join(x for x in (role.title, role.company) if x) or f"Role {i + 1}"


def _label(profile: CvProfile, t: Target, kind: str, after: str = "") -> str:
    if t.kind == "summary":
        return "Summary"
    if t.kind == "bullet":
        return f"{_who(profile, t.i)} — bullet {t.j + 1}"
    if t.kind == "bullets":
        return f"{_who(profile, t.i)} — bullet order"
    if t.kind == "desc":
        name = profile.projects[t.i].name
        return f"Project “{name}” — description" if name else f"Project {t.i + 1} — description"
    if t.kind == "skills":
        return f"Skills — add “{after}”" if kind == "add_skill" else "Skills — order"
    return "Projects — order"


def scope_for(profile: CvProfile, t: Target) -> tuple[str, str]:
    """The text an edit is checked against, and how to name it to the user.

    A bullet is checked against its own role, not the whole CV. A figure or tool
    from a different job is real, but claiming it here would be false.
    """
    if t.kind in ("bullet", "bullets"):
        role = profile.experience[t.i]
        text = "\n".join([role.title, role.company, role.location, role.start,
                          role.end, *role.bullets])
        return text, (f"your role at {role.company}" if role.company else "this role")
    if t.kind == "desc":
        project = profile.projects[t.i]
        text = "\n".join([project.name, project.description, project.link,
                          *project.technologies])
        return text, (f"the project “{project.name}”" if project.name else "this project")
    return profile.all_text, "your CV"


def editable_texts(profile: CvProfile) -> list[tuple[str, str, str]]:
    """Every free-text item tailoring can rewrite, as (target, label, text).

    Public because export needs the same addressing to find and fill the
    placeholders a rewrite left behind.
    """
    items = [("summary", "Summary", profile.summary)]
    for i, role in enumerate(profile.experience):
        for j, bullet in enumerate(role.bullets):
            t = Target("bullet", i, j)
            items.append((f"exp{i}.b{j}", _label(profile, t, "rewrite"), bullet))
    for i, project in enumerate(profile.projects):
        items.append((f"proj{i}.desc", _label(profile, Target("desc", i), "rewrite"),
                      project.description))
    return items


def set_text(profile: CvProfile, target: str, value: str) -> None:
    """Replace one free-text item, addressed the way `editable_texts` names it."""
    parsed = parse_target(target)
    if parsed is None or parsed.kind not in _ALLOWED["rewrite"] or _text_at(profile, parsed) is None:
        raise ValueError(f"{target!r} is not an editable text item.")
    _set_text(profile, parsed, value)


# --- diffs --------------------------------------------------------------------


def word_diff(before: str, after: str) -> list[DiffOp]:
    """A word-level diff, whitespace preserved, adjacent runs merged.

    Joining the non-insert ops reproduces `before` exactly, and joining the
    non-delete ops reproduces `after` -- the UI relies on that to render one
    redline instead of two blocks the reader has to compare by eye.
    """
    a = re.findall(r"\s+|\S+", before)
    b = re.findall(r"\s+|\S+", after)
    ops: list[DiffOp] = []

    def push(op: str, text: str) -> None:
        if not text:
            return
        if ops and ops[-1].op == op:
            ops[-1].text += text
        else:
            ops.append(DiffOp(op=op, text=text))

    raw: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            raw.append(DiffOp(op="equal", text="".join(a[i1:i2])))
        else:
            if i2 > i1:
                raw.append(DiffOp(op="delete", text="".join(a[i1:i2])))
            if j2 > j1:
                raw.append(DiffOp(op="insert", text="".join(b[j1:j2])))

    # A lone space that matched between two changed words is not a meaningful
    # anchor -- keeping it splits one change into a stutter of struck and added
    # fragments. Fold it into the change on both sides, so each changed run
    # reads as one deletion followed by one insertion.
    pending_delete = pending_insert = ""
    for k, op in enumerate(raw):
        between_changes = (
            op.op == "equal" and not op.text.strip()
            and 0 < k < len(raw) - 1
            and raw[k - 1].op != "equal" and raw[k + 1].op != "equal"
        )
        if between_changes:
            pending_delete += op.text
            pending_insert += op.text
        elif op.op == "delete":
            pending_delete += op.text
        elif op.op == "insert":
            pending_insert += op.text
        else:
            push("delete", pending_delete)
            push("insert", pending_insert)
            pending_delete = pending_insert = ""
            push("equal", op.text)
    push("delete", pending_delete)
    push("insert", pending_insert)
    return ops


# --- review -------------------------------------------------------------------


class _Unusable(Exception):
    def __init__(self, reason: str, label: str = "") -> None:
        super().__init__(reason)
        self.label = label


def _squash(text: str) -> str:
    return " ".join(text.split())


def _resolve(profile: CvProfile, proposed: ProposedEdit, edit_id: str) -> tuple[Edit, Target]:
    t = parse_target(proposed.target)
    if t is None or t.kind not in _ALLOWED[proposed.kind]:
        raise _Unusable(
            f"“{proposed.target}” is not a part of the CV that this kind of edit can change."
        )

    edit = Edit(
        id=edit_id, kind=proposed.kind, target=proposed.target.strip(),
        evidence=proposed.evidence.strip(), why=proposed.why.strip(),
        requirement=proposed.requirement.strip(),
    )

    if proposed.kind == "rewrite":
        before = _text_at(profile, t)
        if before is None:
            raise _Unusable("That points at a part of the CV that does not exist.")
        after = _squash(proposed.after) if t.kind == "bullet" else proposed.after.strip()
        edit.label = _label(profile, t, proposed.kind)
        edit.before_text, edit.after_text = before, after
        edit.diff = word_diff(before, after)
        edit.has_placeholder = bool(PLACEHOLDER.search(after))
        return edit, t

    if proposed.kind == "reorder":
        items = _items_at(profile, t)
        if items is None:
            raise _Unusable("That points at a list that does not exist.")
        edit.label = _label(profile, t, proposed.kind)
        order = list(proposed.order)
        if sorted(order) != list(range(len(items))):
            raise _Unusable(
                "The new order is not a rearrangement of the existing items — it "
                "drops, repeats or invents one.",
                label=edit.label,
            )
        edit.before_items, edit.after_items = items, [items[k] for k in order]
        edit.order = order
        return edit, t

    skill = _squash(proposed.after)
    edit.label = _label(profile, t, proposed.kind, skill)
    edit.after_text = skill
    edit.before_items = list(profile.skills)
    edit.after_items = [*profile.skills, skill]
    return edit, t


def _is_noop(edit: Edit) -> bool:
    if edit.kind == "rewrite":
        return _squash(edit.before_text) == _squash(edit.after_text)
    if edit.kind == "reorder":
        return edit.order == sorted(edit.order)
    return False


def _violations(profile: CvProfile, edit: Edit, t: Target, job_vocab: set[str]) -> list[str]:
    if edit.kind == "reorder":
        return []   # a permutation was verified in _resolve; it cannot add anything

    if edit.kind == "rewrite":
        if not edit.after_text.strip():
            return ["The suggested text is empty."]
        limit = MAX_TEXT[t.kind]
        if len(edit.after_text) > limit:
            return [f"At {len(edit.after_text)} characters it is too long for this part of a CV."]
        scope, where = scope_for(profile, t)
        return [f.message for f in introduced(
            edit.after_text, scope=scope, whole=profile.all_text,
            job_terms=job_vocab, where=where,
        )]

    skill = edit.after_text
    if not skill or len(skill) > MAX_SKILL:
        return ["That is not a skill name."]
    if skill.casefold() in {s.casefold() for s in profile.skills}:
        return ["It is already in your skills list."]
    if not edit.evidence or not quoted_in(edit.evidence, profile.all_text):
        return ["No quote from your CV was given to show this skill, so it cannot be added."]
    unsupported = introduced(skill, scope=edit.evidence, strict=True, where="the quoted line")
    if unsupported:
        return [f.message for f in unsupported]
    return []


def _dedupe_gaps(gaps: list[Gap]) -> list[Gap]:
    seen, out = set(), []
    for gap in gaps:
        key = _squash(gap.requirement).casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(gap)
    return out


def review(profile: CvProfile, call: TailorCall, job_description: str) -> Proposal:
    """Turn a model's proposals into edits the user may see, and ones they may not.

    Pure: no model call, no I/O. That is what makes the no-fabrication guarantee
    testable -- any proposal, however adversarial, can be fed straight in.
    """
    job_vocab = vocabulary(job_description)
    edits: list[Edit] = []
    blocked: list[Edit] = []
    claimed: set[tuple[str, str, str]] = set()

    # Read a little past MAX_EDITS: a model that over-proposes should still have
    # its best dozen *usable* edits shown, not its first dozen of any kind.
    for n, proposed in enumerate(call.edits[: MAX_EDITS * 3], start=1):
        edit_id = f"e{n}"
        try:
            edit, t = _resolve(profile, proposed, edit_id)
        except _Unusable as exc:
            blocked.append(Edit(
                id=edit_id, kind=proposed.kind, target=proposed.target,
                label=exc.label or proposed.target, after_text=proposed.after,
                why=proposed.why, requirement=proposed.requirement,
                violations=[str(exc)],
            ))
            continue

        if _is_noop(edit):
            continue

        # One change per spot. Two rewrites of the same bullet cannot both be
        # accepted coherently, so the second is withheld rather than offered.
        spot = (edit.kind, edit.target,
                edit.after_text.casefold() if edit.kind == "add_skill" else "")
        violations = (
            ["Another suggestion already changes this."]
            if spot in claimed
            else _violations(profile, edit, t, job_vocab)
        )
        if violations:
            edit.violations = violations
            blocked.append(edit)
            continue

        claimed.add(spot)
        edits.append(edit)
        if len(edits) >= MAX_EDITS:
            break

    return Proposal(edits=edits, blocked=blocked, gaps=_dedupe_gaps(call.gaps))


# --- apply --------------------------------------------------------------------


def apply_edits(profile: CvProfile, edits: list[Edit], accepted_ids: list[str]) -> CvProfile:
    """Apply the accepted edits to a copy of `profile`.

    Order is fixed -- rewrites, then reorders, then additions -- because indices
    refer to the original positions. Rewrites do not move anything, so a reorder
    applied after them still means what it meant when it was proposed.
    """
    known = {e.id for e in edits}
    unknown = sorted(set(accepted_ids) - known)
    if unknown:
        raise UnknownEdit(
            f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not "
            "among the suggestions that can be accepted."
        )

    chosen = [e for e in edits if e.id in set(accepted_ids)]
    out = profile.model_copy(deep=True)

    for edit in (e for e in chosen if e.kind == "rewrite"):
        _set_text(out, parse_target(edit.target), edit.after_text)
    for edit in (e for e in chosen if e.kind == "reorder"):
        _reorder(out, parse_target(edit.target), edit.order)
    for edit in (e for e in chosen if e.kind == "add_skill"):
        if edit.after_text.casefold() not in {s.casefold() for s in out.skills}:
            out.skills.append(edit.after_text)
    return out


def introduced_into(original: CvProfile, tailored: CvProfile, job_description: str) -> list[Finding]:
    """The whole-document backstop: anything the tailored CV says that the original did not."""
    return introduced(
        tailored.all_text, scope=original.all_text,
        job_terms=vocabulary(job_description), where="the original CV",
    )


def untouchable_changes(original: CvProfile, tailored: CvProfile) -> list[str]:
    """Fields tailoring must never alter. Any entry here means something went wrong."""
    problems = []
    if tailored.contact != original.contact:
        problems.append("contact details")
    if tailored.education != original.education:
        problems.append("education")
    if tailored.certifications != original.certifications:
        problems.append("certifications")
    if tailored.languages != original.languages:
        problems.append("languages")
    if len(tailored.experience) != len(original.experience):
        problems.append("the number of roles")
    else:
        for before, after in zip(original.experience, tailored.experience):
            if (before.title, before.company, before.location, before.start, before.end,
                    before.current) != (after.title, after.company, after.location,
                                        after.start, after.end, after.current):
                problems.append(f"the role at {before.company or 'a company'}")
            # Bullets may be reworded and reordered, never added or removed.
            if len(before.bullets) != len(after.bullets):
                problems.append(f"the number of bullets at {before.company or 'a company'}")
    if sorted(p.name for p in tailored.projects) != sorted(p.name for p in original.projects):
        problems.append("the list of projects")
    return problems


# --- the model call -----------------------------------------------------------


def render_for_model(profile: CvProfile) -> str:
    """The CV with an ID before every editable item."""
    lines = [f"[summary] {profile.summary or '(the CV has no summary)'}"]

    for i, role in enumerate(profile.experience):
        dates = " – ".join(x for x in (role.start, "Present" if role.current else role.end) if x)
        head = " — ".join(x for x in (role.title, role.company, role.location) if x)
        lines.append(f"[exp{i}] {head}{f' ({dates})' if dates else ''}  <- not editable")
        for j, bullet in enumerate(role.bullets):
            lines.append(f"  [exp{i}.b{j}] {bullet}")

    for i, project in enumerate(profile.projects):
        tech = f" | technologies: {', '.join(project.technologies)}" if project.technologies else ""
        lines.append(f"[proj{i}] {project.name}{tech}  <- name not editable")
        lines.append(f"  [proj{i}.desc] {project.description or '(no description)'}")

    if profile.skills:
        lines.append("[skills] " + " | ".join(f"{k}: {s}" for k, s in enumerate(profile.skills)))
    if profile.projects:
        lines.append("[projects] " + " | ".join(
            f"{k}: {p.name or f'Project {k + 1}'}" for k, p in enumerate(profile.projects)))

    for edu in profile.education:
        lines.append(f"(education, not editable) {edu.degree} {edu.field_of_study} — "
                     f"{edu.institution} {edu.end}".strip())
    for cert in profile.certifications:
        lines.append(f"(certification, not editable) {cert.name} {cert.issuer} {cert.year}".strip())
    for lang in profile.languages:
        lines.append(f"(language, not editable) {lang.name} {lang.proficiency}".strip())

    return "\n".join(lines)


def propose(
    profile: CvProfile, *, job_title: str, company: str, job_description: str
) -> Proposal:
    """One model call, then `review`. Title and company travel inside the fence:
    they come from the same untrusted posting as the description does."""
    header = "\n".join(x for x in (
        f"Title: {job_title}" if job_title else "",
        f"Company: {company}" if company else "",
    ) if x)
    posting = (f"{header}\n\n" if header else "") + job_description[:MAX_JD_CHARS]

    call = get_gemini().call_structured(
        schema=TailorCall,
        system=tailor_v1.SYSTEM,
        content=[text_block(
            data_block("job_description", posting)
            + "\n\n"
            + data_block("resume_text", render_for_model(profile))
            + "\n\nPropose edits that tailor this CV to the job above."
        )],
    )
    return review(profile, call, posting)
