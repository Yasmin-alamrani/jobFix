"""The new resume endpoints: paste, profile, fields, delete.

Separate from `test_api.py` because these stub different collaborators. The
model is stubbed throughout, so nothing here spends or reaches the network.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.analyst.fields import FieldCandidate, score_field
from app.agents.analyst.profile import Contact, CvProfile, Experience, ProfileError

FIXTURES = Path(__file__).parent / "fixtures"

PROFILE = CvProfile(
    contact=Contact(name="Yasmin Alamrani", email="y@example.com", location="Riyadh"),
    summary="Backend engineer.",
    experience=[Experience(title="Backend Engineer", company="Tamara",
                           start="2021", start_year=2021, current=True,
                           bullets=["Built the payouts API"])],
    skills=["Python", "PostgreSQL"],
)

FIELDS = [
    score_field(FieldCandidate(
        key="fintech", matched_skills=["payments"], missing_skills=[],
        years_in_field=5.0, title_alignment="direct",
        justification="Payment rails experience.",
    ))
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    settings.upload_dir = tmp_path / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    import app.models.db as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path}/test.db",
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal",
                        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))

    from app.api import resumes as resumes_mod

    calls = {"profile": 0, "fields": 0}

    def fake_extract(text: str) -> CvProfile:
        calls["profile"] += 1
        return PROFILE

    def fake_fields(text: str, **kw):
        calls["fields"] += 1
        return FIELDS

    monkeypatch.setattr(resumes_mod, "extract_profile", fake_extract)
    monkeypatch.setattr(resumes_mod, "suggest_fields", fake_fields)

    from app.main import app
    with TestClient(app) as c:
        c.calls = calls
        yield c

    get_settings.cache_clear()


def _upload(client) -> str:
    with (FIXTURES / "clean_single_column.pdf").open("rb") as fh:
        response = client.post(
            "/api/resumes",
            files={"file": ("cv.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _paste(client, text: str):
    return client.post("/api/resumes/text", data={"text": text, "filename": "pasted"})


CV_TEXT = (
    "Yasmin Alamrani\nBackend Engineer, Riyadh\n"
    "Tamara — Jan 2021 to Present\n- Built the payouts API\n"
    "Education: BSc Computer Science, King Saud University, 2020\n"
    "Skills: Python, PostgreSQL, Django\n"
)


# --- paste -------------------------------------------------------------------

def test_a_pasted_cv_becomes_a_resume(client):
    response = _paste(client, CV_TEXT)
    assert response.status_code == 200
    assert response.json()["filename"] == "pasted"


def test_a_short_paste_is_refused(client):
    assert _paste(client, "Yasmin, engineer").status_code == 422


def test_a_pasted_cv_keeps_its_own_text(client):
    """Rendering to PDF and reading back would lose anything the font cannot draw."""
    arabic = "مهندس برمجيات\nخبرة في تطوير الأنظمة الخلفية\n" * 6
    resume_id = _paste(client, arabic).json()["id"]

    from app.models.db import SessionLocal
    from app.models.entities import Resume
    db = SessionLocal()
    stored = db.get(Resume, resume_id)
    assert stored.source_text.strip() == arabic.strip()
    db.close()


def test_a_pasted_cv_still_gets_a_pdf_for_the_visual_review(client):
    resume_id = _paste(client, CV_TEXT).json()["id"]

    from app.models.db import SessionLocal
    from app.models.entities import Resume
    db = SessionLocal()
    stored = db.get(Resume, resume_id)
    assert Path(stored.stored_path).exists()
    assert Path(stored.stored_path).suffix == ".pdf"
    db.close()


# --- profile -----------------------------------------------------------------

def test_the_profile_comes_back_structured(client):
    resume_id = _upload(client)
    body = client.get(f"/api/resumes/{resume_id}/profile").json()
    assert body["profile"]["contact"]["name"] == "Yasmin Alamrani"
    assert body["profile"]["skills"] == ["Python", "PostgreSQL"]
    assert body["prompt_version"] == "profile_v1"


def test_the_profile_is_extracted_once_and_then_cached(client):
    """Extraction is a model call; asking twice must not pay twice."""
    resume_id = _upload(client)
    client.get(f"/api/resumes/{resume_id}/profile")
    client.get(f"/api/resumes/{resume_id}/profile")
    client.get(f"/api/resumes/{resume_id}/profile")
    assert client.calls["profile"] == 1


def test_missing_sections_are_reported(client):
    resume_id = _upload(client)
    body = client.get(f"/api/resumes/{resume_id}/profile").json()
    assert "education" in body["sections_missing"]
    assert "experience" in body["sections_present"]


def test_an_unknown_resume_has_no_profile(client):
    assert client.get("/api/resumes/nope/profile").status_code == 404


def test_a_document_that_is_not_a_cv_is_reported_not_forced(client, monkeypatch):
    from app.api import resumes as resumes_mod

    def refuses(text: str):
        raise ProfileError("That document does not read as a CV.")

    monkeypatch.setattr(resumes_mod, "extract_profile", refuses)
    resume_id = _upload(client)
    response = client.get(f"/api/resumes/{resume_id}/profile")
    assert response.status_code == 422
    assert "does not read as a CV" in response.json()["detail"]


# --- fields ------------------------------------------------------------------

def test_matching_fields_come_back_scored(client):
    resume_id = _upload(client)
    body = client.get(f"/api/resumes/{resume_id}/fields").json()
    assert body["fields"][0]["key"] == "fintech"
    assert body["fields"][0]["score"] == 100.0
    assert body["fields"][0]["justification"]


def test_fields_are_cached_once_a_profile_exists(client):
    resume_id = _upload(client)
    client.get(f"/api/resumes/{resume_id}/profile")   # creates the row to cache into
    client.get(f"/api/resumes/{resume_id}/fields")
    client.get(f"/api/resumes/{resume_id}/fields")
    assert client.calls["fields"] == 1


def test_every_field_score_is_explained_by_its_components(client):
    resume_id = _upload(client)
    body = client.get(f"/api/resumes/{resume_id}/fields").json()
    for fit in body["fields"]:
        assert fit["score"] == pytest.approx(sum(c["earned"] for c in fit["components"]))


# --- delete ------------------------------------------------------------------

def test_deleting_a_resume_removes_the_file_from_disk(client):
    resume_id = _upload(client)

    from app.models.db import SessionLocal
    from app.models.entities import Resume
    db = SessionLocal()
    path = Path(db.get(Resume, resume_id).stored_path)
    db.close()
    assert path.exists()

    assert client.delete(f"/api/resumes/{resume_id}").status_code == 204
    assert not path.exists(), "the CV file survived the delete"


def test_deleting_a_resume_takes_its_profile_with_it(client):
    """A CV is personal data. Leaving the extracted entities behind keeps it."""
    resume_id = _upload(client)
    client.get(f"/api/resumes/{resume_id}/profile")

    from app.models.db import SessionLocal
    from app.models.entities import StoredProfile
    db = SessionLocal()
    assert db.query(StoredProfile).filter_by(resume_id=resume_id).count() == 1
    db.close()

    client.delete(f"/api/resumes/{resume_id}")

    db = SessionLocal()
    assert db.query(StoredProfile).filter_by(resume_id=resume_id).count() == 0
    db.close()


def test_deleting_a_resume_takes_its_analyses_with_it(client, monkeypatch):
    from app.agents.analyst.schemas import (
        AnalysisResult, ExperienceFit, Fit, SubScore, WritingReview,
    )
    from app.api import resumes as resumes_mod

    monkeypatch.setattr(resumes_mod, "analyze", lambda **kw: AnalysisResult(
        overall_score=80.0,
        sub_scores=[SubScore(key="ats", label="ATS", earned=25.0, max_points=25.0)],
        requirements=[],
        experience=ExperienceFit(jd_seniority="Senior", resume_seniority="Senior",
                                 fit=Fit.MATCH),
        writing=WritingReview(issues=[], summary_verdict="ok"),
        top_fixes=[], parse_facts={},
    ))

    resume_id = _upload(client)
    client.post("/api/analyses", data={
        "resume_id": resume_id, "job_description": "x" * 80,
        "industry": "tech", "job_title": "Backend Engineer",
    })

    from app.models.db import SessionLocal
    from app.models.entities import Analysis
    db = SessionLocal()
    assert db.query(Analysis).filter_by(resume_id=resume_id).count() == 1
    db.close()

    client.delete(f"/api/resumes/{resume_id}")

    db = SessionLocal()
    assert db.query(Analysis).filter_by(resume_id=resume_id).count() == 0
    db.close()


def test_deleting_an_unknown_resume_is_a_404(client):
    assert client.delete("/api/resumes/nope").status_code == 404


def test_a_deleted_resume_is_gone_from_every_endpoint(client):
    resume_id = _upload(client)
    client.delete(f"/api/resumes/{resume_id}")
    assert client.get(f"/api/resumes/{resume_id}/profile").status_code == 404
    assert client.get(f"/api/resumes/{resume_id}/fields").status_code == 404


def test_a_concurrent_extraction_is_absorbed_rather_than_a_500(client, monkeypatch):
    """The race: another request stores the profile while this one waits on the
    model. `resume_id` is unique, so the second insert fails -- which used to
    surface as a 500 on the first visit to the page in React's development mode,
    where every component mounts twice."""
    from app.api import resumes as resumes_mod
    from app.models.db import SessionLocal
    from app.models.entities import StoredProfile

    resume_id = _upload(client)

    def racing_extract(text: str) -> CvProfile:
        other = SessionLocal()
        other.add(StoredProfile(user_id="local", resume_id=resume_id,
                                profile=PROFILE.model_dump(mode="json"),
                                prompt_version="profile_v1"))
        other.commit()
        other.close()
        return PROFILE

    monkeypatch.setattr(resumes_mod, "extract_profile", racing_extract)
    response = client.get(f"/api/resumes/{resume_id}/profile")
    assert response.status_code == 200, response.text

    db = SessionLocal()
    assert db.query(StoredProfile).filter_by(resume_id=resume_id).count() == 1
    db.close()


# --- surviving a wiped disk ----------------------------------------------------
#
# A free host hands the container a new filesystem on every deploy. The row
# describing a CV outlives the file it points at, and parseability is measured
# from the PDF itself, so without the bytes in the database every CV uploaded
# before a restart would become unanalysable.

def _stored(resume_id: str):
    from app.models.db import SessionLocal
    from app.models.entities import Resume
    with SessionLocal() as db:
        row = db.get(Resume, resume_id)
        return row.stored_path, (row.file.content if row.file else None)


def test_the_document_is_kept_in_the_database(client):
    resume_id = _paste(client, CV_TEXT).json()["id"]
    path, content = _stored(resume_id)
    assert content, "the upload should have been stored in resume_files"
    assert content == Path(path).read_bytes()


def test_a_missing_file_is_restored_from_the_database(client):
    """The disk is wiped; the next read puts the file back rather than failing."""
    from app.api.resumes import ensure_local
    from app.models.db import SessionLocal
    from app.models.entities import Resume

    resume_id = _paste(client, CV_TEXT).json()["id"]
    path, original = _stored(resume_id)

    Path(path).unlink()                      # the deploy that loses the disk
    assert not Path(path).exists()

    with SessionLocal() as db:
        restored = ensure_local(db.get(Resume, resume_id))

    assert restored.exists()
    assert restored.read_bytes() == original


def test_the_visual_review_survives_the_disk_being_wiped(client):
    """Through the API rather than the helper: the case that used to break."""
    resume_id = _paste(client, CV_TEXT).json()["id"]
    path, _ = _stored(resume_id)
    Path(path).unlink()

    assert client.get(f"/api/resumes/{resume_id}/profile").status_code == 200


def test_a_cv_with_no_stored_bytes_reports_itself_gone(client):
    """A row predating this table has no file to restore, and must say so."""
    from fastapi import HTTPException
    from app.api.resumes import ensure_local
    from app.models.db import SessionLocal
    from app.models.entities import Resume

    resume_id = _paste(client, CV_TEXT).json()["id"]
    path, _ = _stored(resume_id)
    Path(path).unlink()
    with SessionLocal() as db:
        row = db.get(Resume, resume_id)
        row.file = None                      # as an older row would be
        db.commit()

    with SessionLocal() as db, pytest.raises(HTTPException) as caught:
        ensure_local(db.get(Resume, resume_id))
    assert caught.value.status_code == 410
