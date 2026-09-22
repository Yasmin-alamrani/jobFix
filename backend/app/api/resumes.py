"""Resume upload and analysis endpoints."""
from __future__ import annotations

import contextlib
import logging
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.analyst.analyzer import analyze
from app.agents.analyst.fields import suggest_fields
from app.agents.analyst.industries import PACKS
from app.agents.analyst.parser import parse_pdf
from app.agents.analyst.profile import CvProfile, ProfileError, extract_profile
from app.agents.analyst.review import review_cv
from app.core.gemini import FAILURES, explain
from app.core.i18n import Lang, tr, ui_lang
from app.core.config import get_settings
from app.core.ratelimit import analysis_limit, upload_limit
from app.models.db import get_db
from app.models.entities import Analysis, Resume, StoredProfile, StoredReview
from app.prompts import profile_v1, review_v1

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resumes"])

ALLOWED = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
MAX_BYTES = 15 * 1024 * 1024


@contextlib.contextmanager
def model_errors(what: str) -> Iterator[None]:
    """Map model failures onto status codes that mean something to the caller.

    Every endpoint that calls Gemini needs the same mapping. Inlining it per
    endpoint is how one of them quietly ends up reporting an auth failure as a
    500 and sending the user to debug the wrong thing.
    """
    try:
        yield
    except FAILURES as exc:
        status, message = explain(exc)
        if status == 502:
            log.exception("model call failed during %s", what)
        raise HTTPException(status, message) from exc
    except ProfileError as exc:
        raise HTTPException(422, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 -- surface a usable message, log the rest
        log.exception("%s failed", what)
        raise HTTPException(500, f"{what.capitalize()} failed: {exc}") from exc


class ResumeOut(BaseModel):
    id: str
    filename: str


class AnalysisOut(BaseModel):
    id: str
    resume_id: str
    overall_score: float
    result: dict


@router.get("/industries")
def list_industries(lang: Lang = Depends(ui_lang)) -> list[dict]:
    return [{"key": p.key, "label": tr(p.label, lang)} for p in PACKS.values()]


@router.post("/resumes", response_model=ResumeOut, dependencies=[Depends(upload_limit)])
def upload_resume(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ResumeOut:
    if file.content_type not in ALLOWED:
        raise HTTPException(415, f"Upload a PDF or DOCX (got {file.content_type}).")

    settings = get_settings()
    suffix = ALLOWED[file.content_type]
    stored = settings.upload_dir / f"{uuid.uuid4()}{suffix}"

    with stored.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)

    if stored.stat().st_size > MAX_BYTES:
        stored.unlink(missing_ok=True)
        raise HTTPException(413, "Resume must be under 15 MB.")

    if suffix == ".docx":
        stored = _docx_to_pdf(stored)

    row = Resume(
        user_id=settings.default_user_id,
        filename=file.filename or "resume",
        stored_path=str(stored),
        content_type=file.content_type,
    )
    db.add(row)
    db.commit()
    return ResumeOut(id=row.id, filename=row.filename)


@router.post("/analyses", response_model=AnalysisOut, dependencies=[Depends(analysis_limit)])
def create_analysis(
    resume_id: str = Form(...),
    job_description: str = Form(...),
    industry: str = Form("other"),
    job_title: str = Form(""),
    db: Session = Depends(get_db),
    lang: Lang = Depends(ui_lang),
) -> AnalysisOut:
    settings = get_settings()
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != settings.default_user_id:
        raise HTTPException(404, "Resume not found.")
    if len(job_description.strip()) < 50:
        raise HTTPException(
            422, "Paste the full job description -- a short snippet can't be matched meaningfully."
        )

    with model_errors("analysis"):
        result = analyze(
            resume_path=Path(resume.stored_path),
            job_description=job_description,
            industry=industry,
            job_title=job_title,
            lang=lang,
        )

    row = Analysis(
        user_id=settings.default_user_id,
        resume_id=resume_id,
        job_title=job_title,
        industry=industry,
        job_description=job_description,
        overall_score=result.overall_score,
        result=result.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    return AnalysisOut(
        id=row.id, resume_id=resume_id,
        overall_score=row.overall_score, result=row.result,
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db)) -> AnalysisOut:
    row = db.get(Analysis, analysis_id)
    if row is None or row.user_id != get_settings().default_user_id:
        raise HTTPException(404, "Analysis not found.")
    return AnalysisOut(
        id=row.id, resume_id=row.resume_id,
        overall_score=row.overall_score, result=row.result,
    )


class ProfileOut(BaseModel):
    resume_id: str
    profile: dict
    prompt_version: str
    sections_present: list[str]
    sections_missing: list[str]


class FieldsOut(BaseModel):
    resume_id: str
    fields: list[dict]


# Sections a CV is expected to carry. Absence is reported, never filled in.
EXPECTED_SECTIONS = ("summary", "experience", "education", "skills")


def owned_resume(db: Session, resume_id: str) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != get_settings().default_user_id:
        raise HTTPException(404, "Resume not found.")
    return resume


def text_of(resume: Resume) -> str:
    """The CV's text, preferring the original over anything re-extracted.

    A pasted CV keeps its own text: laying it into a PDF and reading it back
    would drop every glyph the render font lacks, which for an Arabic CV is all
    of them. Uploaded files have no original, so they are parsed.
    """
    if resume.source_text.strip():
        return resume.source_text

    report = parse_pdf(Path(resume.stored_path))
    if not report.has_extractable_text:
        raise HTTPException(
            422,
            "That file has no machine-readable text, so there is nothing to read. "
            "Re-export it as a text PDF rather than a scan, or paste the text "
            "instead.",
        )
    return report.text


def ensure_profile(db: Session, resume: Resume) -> StoredProfile:
    """The CV's structured profile, extracted on first use and cached.

    Shared by the profile endpoint and by tailoring, so a CV is only ever read
    into entities once, and both see the same entities.
    """
    stored = db.query(StoredProfile).filter_by(resume_id=resume.id).one_or_none()
    if stored is not None:
        return stored

    with model_errors("profile extraction"):
        parsed = extract_profile(text_of(resume))
    stored = StoredProfile(
        user_id=resume.user_id,
        resume_id=resume.id,
        profile=parsed.model_dump(mode="json"),
        prompt_version=profile_v1.VERSION,
    )
    db.add(stored)
    try:
        db.commit()
    except IntegrityError:
        # Another request extracted the same CV while this one was waiting on
        # the model -- a double click, a second tab, or React's development mode
        # mounting the page twice. `resume_id` is unique, so the second insert
        # fails; the first profile is as good as this one, so use it.
        db.rollback()
        stored = db.query(StoredProfile).filter_by(resume_id=resume.id).one()
    return stored


@router.post("/resumes/text", response_model=ResumeOut,
             dependencies=[Depends(upload_limit)])
def upload_resume_text(
    text: str = Form(...),
    filename: str = Form("pasted-cv"),
    db: Session = Depends(get_db),
) -> ResumeOut:
    """Accept a CV as pasted text rather than a file.

    Laid out into a PDF on the way in, because the writing review reads the
    actual document to judge layout. A paste has no layout to judge, and a
    plain single-column render is an honest representation of that -- it scores
    the words on their own terms rather than inventing a design to critique.
    """
    body = text.strip()
    if len(body) < 100:
        raise HTTPException(
            422, "That is too short to be a CV. Paste the whole document."
        )

    settings = get_settings()
    stored = settings.upload_dir / f"{uuid.uuid4()}.pdf"
    _text_to_pdf(body, stored)

    row = Resume(
        user_id=settings.default_user_id,
        filename=filename or "pasted-cv",
        stored_path=str(stored),
        content_type="text/plain",
        source_text=body,
    )
    db.add(row)
    db.commit()
    return ResumeOut(id=row.id, filename=row.filename)


@router.get("/resumes/{resume_id}/profile", response_model=ProfileOut,
            dependencies=[Depends(upload_limit)])
def get_profile(resume_id: str, db: Session = Depends(get_db)) -> ProfileOut:
    """The CV as structured entities, extracted once and cached.

    Deliberately not done during upload. Extraction is a model call of several
    seconds, and upload currently fires the moment a file is chosen -- putting it
    there would freeze the picker before the user has said what they want. The
    same CV always yields the same profile, so computing it on first request and
    storing it costs one call either way.
    """
    resume = owned_resume(db, resume_id)
    stored = ensure_profile(db, resume)

    # Derived from the stored profile rather than persisted beside it, so the
    # two can never disagree.
    present = set(CvProfile.model_validate(stored.profile).sections_present)

    return ProfileOut(
        resume_id=resume_id,
        profile=stored.profile,
        prompt_version=stored.prompt_version,
        sections_present=sorted(present),
        sections_missing=[s for s in EXPECTED_SECTIONS if s not in present],
    )


@router.get("/resumes/{resume_id}/fields", response_model=FieldsOut,
            dependencies=[Depends(analysis_limit)])
def get_fields(
    resume_id: str, db: Session = Depends(get_db), lang: Lang = Depends(ui_lang)
) -> FieldsOut:
    """Fields this CV fits, best first. Cached alongside the profile, per
    language -- the justifications are the model's own sentences."""
    resume = owned_resume(db, resume_id)
    # "fields" is English, as it was before there was a choice of language.
    key = "fields" if lang == "en" else f"fields_{lang}"

    stored = db.query(StoredProfile).filter_by(resume_id=resume_id).one_or_none()
    if stored is not None and stored.fields and key in stored.fields:
        return FieldsOut(resume_id=resume_id, fields=stored.fields[key])

    with model_errors("field matching"):
        fits = suggest_fields(text_of(resume), lang=lang)

    payload = [fit.model_dump(mode="json") for fit in fits]
    if stored is not None:
        # A new dict, not an update in place: the JSON column only notices
        # being assigned to.
        stored.fields = {**(stored.fields or {}), key: payload}
        db.commit()
    return FieldsOut(resume_id=resume_id, fields=payload)


class ReviewOut(BaseModel):
    resume_id: str
    review: dict


def _reviews_by_lang(stored: StoredReview | None) -> dict[str, dict]:
    """The stored reviews, keyed by language.

    A review saved before there was a choice of language is the review itself
    rather than a dict of them, and it was written in English.
    """
    data = (stored.review or {}) if stored is not None else {}
    return {"en": data} if "verdict" in data else dict(data)


@router.get("/resumes/{resume_id}/review", response_model=ReviewOut,
            dependencies=[Depends(analysis_limit)])
def get_review(
    resume_id: str, db: Session = Depends(get_db), lang: Lang = Depends(ui_lang)
) -> ReviewOut:
    """Weak areas and how to fix them, with no job in mind. Cached per CV and
    per language.

    A review stored under an older prompt is redone, since it would otherwise
    keep showing advice the current prompt no longer gives.
    """
    resume = owned_resume(db, resume_id)
    stored = db.query(StoredReview).filter_by(resume_id=resume_id).one_or_none()
    current = stored is not None and stored.prompt_version == review_v1.VERSION
    by_lang = _reviews_by_lang(stored) if current else {}
    if lang in by_lang:
        return ReviewOut(resume_id=resume_id, review=by_lang[lang])

    text = text_of(resume)
    profile = CvProfile.model_validate(ensure_profile(db, resume).profile)
    # A pasted CV's PDF is our own plain render of it; its layout says nothing.
    report = None if resume.source_text.strip() else parse_pdf(Path(resume.stored_path))

    with model_errors("CV review"):
        review = review_cv(text, profile=profile, report=report, lang=lang)

    payload = review.model_dump(mode="json")
    if stored is None:
        db.add(StoredReview(user_id=resume.user_id, resume_id=resume.id,
                            review={lang: payload}, prompt_version=review_v1.VERSION))
    else:
        stored.review = {**by_lang, lang: payload}
        stored.prompt_version = review_v1.VERSION
    try:
        db.commit()
    except IntegrityError:
        # Another request reviewed the same CV first -- a second tab, or
        # React's development mode mounting twice. Its review is as good.
        db.rollback()
        again = db.query(StoredReview).filter_by(resume_id=resume_id).one()
        payload = _reviews_by_lang(again).get(lang, payload)
    return ReviewOut(resume_id=resume_id, review=payload)


@router.delete("/resumes/{resume_id}", status_code=204, response_class=Response)
def delete_resume(resume_id: str, db: Session = Depends(get_db)) -> Response:
    """Delete a CV, its file, and everything derived from it.

    A CV is personal data -- name, phone, address, employment history -- so this
    removes the stored file from disk as well as the rows. The cascade takes the
    analyses and the extracted profile with it; leaving those behind would keep
    the contents of a document the user asked us to forget.
    """
    resume = owned_resume(db, resume_id)

    path = Path(resume.stored_path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        # The row still goes. A file we cannot unlink is worth reporting, but
        # refusing the delete would leave the user with no way to remove the data.
        log.warning("could not remove %s: %s", path, exc)

    db.delete(resume)
    db.commit()
    return Response(status_code=204)


# A4 text frame with ~20mm margins, in points.
_TEXT_BOX = (56, 56, 539, 785)
_FONT_SIZE = 10


def _text_to_pdf(text: str, target: Path) -> Path:
    """Lay plain text out as a single-column PDF with a real text layer.

    Paginated rather than truncated: `insert_textbox` silently drops whatever
    does not fit and returns a negative number, so a long CV would lose its
    later roles with no error and nothing visible in the UI.
    """
    import fitz

    doc = fitz.open()
    remaining = text
    while True:
        fitted = _fitting_prefix(remaining)
        if not fitted:
            # A single line taller than the frame. Draw it and let it clip --
            # looping again with the same input would never terminate.
            fitted = remaining
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(*_TEXT_BOX), fitted, fontsize=_FONT_SIZE, fontname="helv"
        )
        remaining = remaining[len(fitted):].lstrip("\n")
        if not remaining.strip():
            break

    doc.save(target)
    doc.close()
    return target


def _fits_on_a_page(text: str) -> bool:
    """Whether `text` draws inside one page frame.

    Measured on a throwaway document rather than on the real one. PyMuPDF only
    answers this by trying to draw, and deleting the page it drew on raises
    ("kid not found in parent's kids array") -- so the probe gets its own doc.
    """
    import fitz

    probe = fitz.open()
    page = probe.new_page()
    fits = page.insert_textbox(
        fitz.Rect(*_TEXT_BOX), text, fontsize=_FONT_SIZE, fontname="helv"
    ) >= 0
    probe.close()
    return fits


def _fitting_prefix(text: str) -> str:
    """The longest run of whole lines from `text` that fits on one page."""
    lines = text.split("\n")
    low, high, best = 0, len(lines), ""
    while low < high:
        mid = (low + high + 1) // 2
        candidate = "\n".join(lines[:mid])
        if _fits_on_a_page(candidate):
            best, low = candidate, mid
        else:
            high = mid - 1
    return best


def _docx_to_pdf(path: Path) -> Path:
    """The visual review needs a PDF; convert on ingest.

    Tries LibreOffice for a faithful render, and falls back to laying the
    extracted text out with PyMuPDF so a missing soffice never blocks an upload.
    """
    import subprocess

    target = path.with_suffix(".pdf")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir",
                 str(path.parent), str(path)],
                check=True, capture_output=True, timeout=90,
            )
            if target.exists():
                return target
        except (subprocess.SubprocessError, OSError):
            log.warning("LibreOffice conversion failed; falling back to text layout.")

    import fitz
    from docx import Document

    text = "\n".join(p.text for p in Document(str(path)).paragraphs)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(56, 56, 539, 785), text, fontsize=10, fontname="helv")
    doc.save(target)
    doc.close()
    return target
