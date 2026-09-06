"""Resume upload and analysis endpoints."""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.analyst.analyzer import analyze
from app.agents.analyst.industries import PACKS
from app.core.claude import MissingCredentialsError, RefusalError
from app.core.config import get_settings
from app.models.db import get_db
from app.models.entities import Analysis, Resume

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["resumes"])

ALLOWED = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
MAX_BYTES = 15 * 1024 * 1024


class ResumeOut(BaseModel):
    id: str
    filename: str


class AnalysisOut(BaseModel):
    id: str
    resume_id: str
    overall_score: float
    result: dict


@router.get("/industries")
def list_industries() -> list[dict]:
    return [{"key": p.key, "label": p.label} for p in PACKS.values()]


@router.post("/resumes", response_model=ResumeOut)
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


@router.post("/analyses", response_model=AnalysisOut)
def create_analysis(
    resume_id: str = Form(...),
    job_description: str = Form(...),
    industry: str = Form("other"),
    job_title: str = Form(""),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    settings = get_settings()
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != settings.default_user_id:
        raise HTTPException(404, "Resume not found.")
    if len(job_description.strip()) < 50:
        raise HTTPException(
            422, "Paste the full job description -- a short snippet can't be matched meaningfully."
        )

    try:
        result = analyze(
            resume_path=Path(resume.stored_path),
            job_description=job_description,
            industry=industry,
            job_title=job_title,
        )
    except RefusalError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (MissingCredentialsError, anthropic.AuthenticationError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except anthropic.RateLimitError as exc:
        raise HTTPException(429, "Rate limited by the Anthropic API. Try again shortly.") from exc
    except anthropic.APIConnectionError as exc:
        raise HTTPException(503, "Could not reach the Anthropic API. Check your connection.") from exc
    except anthropic.APIStatusError as exc:
        log.exception("Anthropic returned %s for resume %s", exc.status_code, resume_id)
        raise HTTPException(502, f"The Anthropic API returned an error ({exc.status_code}).") from exc
    except Exception as exc:  # noqa: BLE001 -- surface a usable message, log the rest
        log.exception("Analysis failed for resume %s", resume_id)
        raise HTTPException(500, f"Analysis failed: {exc}") from exc

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
