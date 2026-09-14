"""API surface tests. The analyzer is stubbed -- no API key, no spend."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.analyst.schemas import (
    AnalysisResult, ExperienceFit, Fit, SubScore, WritingReview,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    from app.core.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    settings.upload_dir = tmp_path / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # Rebind the engine to the temp database.
    import app.models.db as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path}/test.db",
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal",
                        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))

    from app.api import resumes as resumes_mod

    def fake_analyze(**kw):
        subs = [
            SubScore(key="ats", label="ATS parseability", earned=25.0, max_points=25.0),
            SubScore(key="keywords", label="Keyword & skill match", earned=20.0, max_points=35.0),
            SubScore(key="experience", label="Experience & seniority fit", earned=18.0, max_points=20.0),
            SubScore(key="formatting", label="Formatting & structure", earned=17.0, max_points=20.0),
        ]
        return AnalysisResult(
            overall_score=80.0, sub_scores=subs, requirements=[],
            experience=ExperienceFit(jd_seniority="Senior", resume_seniority="Senior", fit=Fit.MATCH),
            writing=WritingReview(issues=[], summary_verdict="ok"),
            top_fixes=[], parse_facts={"page_count": 1},
        )

    monkeypatch.setattr(resumes_mod, "analyze", fake_analyze)

    from app.main import app
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()


def _upload(client) -> str:
    with (FIXTURES / "clean_single_column.pdf").open("rb") as fh:
        r = client.post("/api/resumes", files={"file": ("cv.pdf", fh, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_health_reports_model_and_key_status(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["model"] == "gemini-3.6-flash"
    assert "gemini_key_configured" in body
    assert "openrouter_key_configured" not in body


def test_industries_are_listed(client):
    keys = {i["key"] for i in client.get("/api/industries").json()}
    assert {"tech", "banking", "fintech", "government"} <= keys


def test_pdf_upload_succeeds(client):
    assert _upload(client)


def test_non_resume_upload_is_rejected(client):
    r = client.post("/api/resumes", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_analysis_round_trips(client):
    resume_id = _upload(client)
    r = client.post("/api/analyses", data={
        "resume_id": resume_id, "industry": "fintech", "job_title": "Backend Engineer",
        "job_description": "Senior Backend Engineer. Required: 5 years Python, PostgreSQL, "
                           "payments systems, distributed architecture. Riyadh based.",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall_score"] == 80.0
    assert len(body["result"]["sub_scores"]) == 4

    fetched = client.get(f"/api/analyses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["overall_score"] == 80.0


def test_short_job_description_is_rejected(client):
    resume_id = _upload(client)
    r = client.post("/api/analyses",
                    data={"resume_id": resume_id, "job_description": "backend dev"})
    assert r.status_code == 422


def test_unknown_resume_is_404(client):
    r = client.post("/api/analyses", data={
        "resume_id": "does-not-exist",
        "job_description": "A sufficiently long job description for the validator to accept it here.",
    })
    assert r.status_code == 404


def test_unknown_analysis_is_404(client):
    assert client.get("/api/analyses/nope").status_code == 404
