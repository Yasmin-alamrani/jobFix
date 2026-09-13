"""Filling placeholders, and downloading a version as PDF or DOCX.

Export is refused while a version still carries an `[add …]` slot. That is
checked here, on the server, because the rule is about what reaches an
employer: a placeholder sent in a real application is a visible defect, and a
button that is merely greyed out in one UI is not a guarantee.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.analyst.profile import CvProfile
from app.api.tailor import VersionOut, _owned_version, _version_out
from app.export.document import build
from app.export.docx import render_docx
from app.export.pdf import ExportUnavailable, render_pdf
from app.export.placeholders import PlaceholderError, fill, slots
from app.models.db import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])

MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class SlotOut(BaseModel):
    index: int
    target: str
    label: str
    text: str
    placeholder: str


class FillRequest(BaseModel):
    # Keyed by slot index. JSON object keys are strings; pydantic coerces them.
    values: dict[int, str] = Field(default_factory=dict)
    drop: list[int] = Field(default_factory=list)


@router.get("/versions/{version_id}/placeholders", response_model=list[SlotOut])
def list_placeholders(version_id: str, db: Session = Depends(get_db)) -> list[SlotOut]:
    row = _owned_version(db, version_id)
    return [SlotOut(**slot.__dict__) for slot in slots(CvProfile.model_validate(row.profile))]


@router.post("/versions/{version_id}/placeholders", response_model=VersionOut)
def fill_placeholders(
    version_id: str, request: FillRequest, db: Session = Depends(get_db)
) -> VersionOut:
    """Fill slots with the user's own figures, or drop them.

    Dropping reverts the whole item to its original wording, which is on
    record from when the version was saved.
    """
    row = _owned_version(db, version_id)
    try:
        profile, supplied = fill(
            CvProfile.model_validate(row.profile),
            values=request.values,
            drop=set(request.drop),
            originals=dict(row.rewrite_origins or {}),
        )
    except PlaceholderError as exc:
        raise HTTPException(422, str(exc)) from exc

    row.profile = profile.model_dump(mode="json")
    # Kept so the source of every figure in an exported CV is known: it was in
    # the original, or the user typed it here.
    row.user_supplied = [*(row.user_supplied or []), *supplied]
    db.commit()
    return _version_out(row)


def _filename(name: str, title: str, extension: str) -> tuple[str, str]:
    """A readable filename, plus an ASCII fallback for older clients.

    Arabic names survive through the RFC 5987 `filename*` form; the plain
    `filename` is a transliteration-free ASCII fallback, because a header value
    must be Latin-1 and a mangled Arabic name is worse than a generic one.
    """
    stem = " - ".join(p for p in (name, title) if p) or "CV"
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", stem).strip()[:120] or "CV"
    ascii_stem = (
        unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode().strip()
    )
    ascii_stem = re.sub(r"\s+", " ", ascii_stem).strip(" -") or "CV"
    return f"{stem}.{extension}", f"{ascii_stem}.{extension}"


@router.get("/versions/{version_id}/export.{fmt}")
def export_version(
    version_id: str, fmt: Literal["pdf", "docx"], db: Session = Depends(get_db)
) -> Response:
    row = _owned_version(db, version_id)
    profile = CvProfile.model_validate(row.profile)

    remaining = slots(profile)
    if remaining:
        raise HTTPException(
            409,
            f"This version still has {len(remaining)} placeholder"
            f"{'' if len(remaining) == 1 else 's'} to fill in or drop before it "
            "can be exported.",
        )

    document = build(profile, title=row.name)
    try:
        content = render_pdf(document) if fmt == "pdf" else render_docx(document)
    except ExportUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- a render failure must not be a bare 500
        log.exception("export of %s as %s failed", version_id, fmt)
        raise HTTPException(500, f"Could not produce the {fmt.upper()} file: {exc}") from exc

    full, fallback = _filename(document.name, row.name, fmt)
    return Response(
        content=content,
        media_type=MEDIA[fmt],
        headers={
            "Content-Disposition":
                f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(full)}",
            "Cache-Control": "no-store",   # a CV is personal data; do not keep copies
        },
    )
