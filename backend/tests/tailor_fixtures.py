"""CVs, postings and model proposals shared by the tailoring tests.

Not collected as a test module (no `test_` prefix); imported by the ones that are.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.analyst.profile import (
    Certification,
    Contact,
    CvProfile,
    Education,
    Experience,
    Language,
    Project,
)
from app.agents.analyst.tailor import Gap, ProposedEdit, TailorCall

FIXTURES = Path(__file__).parent / "fixtures"

ORIGINAL = CvProfile(
    contact=Contact(name="Yasmin Alamrani", email="y@example.com",
                    phone="+966501234567", location="Riyadh"),
    summary="Backend engineer focused on payment systems.",
    experience=[
        Experience(
            title="Backend Engineer", company="Tamara", location="Riyadh",
            start="Jan 2021", start_year=2021, current=True,
            bullets=[
                "Built the payouts API used by 8,000 merchants",
                "Migrated reporting to PostgreSQL",
                "Worked on payment reconciliation jobs",
            ],
        ),
        Experience(
            title="Software Engineer", company="Rain", location="Riyadh",
            start="Jun 2018", end="Dec 2020", start_year=2018, end_year=2020,
            bullets=[
                "Supported the onboarding team with 12 KYC checks per day using Django",
                "Wrote internal tooling",
            ],
        ),
    ],
    education=[Education(degree="BSc", field_of_study="Computer Science",
                         institution="King Saud University", end="2018", end_year=2018)],
    skills=["Python", "Docker", "Django"],
    certifications=[Certification(name="Scrum Foundations", issuer="Coursera", year="2019")],
    projects=[Project(name="Souq", description="A small marketplace side project",
                      technologies=["Redis"])],
    languages=[Language(name="Arabic", proficiency="Native"),
               Language(name="English", proficiency="Fluent")],
)

ARABIC = CvProfile(
    contact=Contact(name="ياسمين العمراني", location="الرياض"),
    summary="مهندسة برمجيات متخصصة في أنظمة الدفع",
    experience=[
        Experience(
            title="مهندسة برمجيات", company="تمارا", start="2021", start_year=2021,
            current=True,
            bullets=["بناء واجهة برمجية للمدفوعات تخدم 8000 تاجر",
                     "ترحيل التقارير إلى PostgreSQL"],
        )
    ],
    skills=["Python"],
)

JD = """Senior Backend Engineer — Payments
Requirements: 8+ years building scalable payment systems with Kubernetes, Kafka
and microservices. Experience with SAMA compliance. You will lead a small team.
AWS Certified preferred. A PhD is a plus."""

ARABIC_JD = "مطلوب مهندس خبرة في كوبرنيتس والخدمات المصغرة وأنظمة الدفع"

# Terms the posting asks for that the CV does not have. None may ever reach a
# tailored CV.
JD_ONLY_TERMS = ["kubernetes", "kafka", "microservices", "sama", "compliance", "aws", "phd"]

# Strings that must never appear in any tailored version of ORIGINAL. Checked
# at setup to be genuinely absent, so a pass means something.
CANARIES = [
    "Kubernetes", "Kafka", "microservices", "SAMA", "compliance", "AWS", "PhD",
    "Google", "Microsoft", "2015", "9,500", "73", "٧٣", "Led", "Tripled",
]

# Edits a careful editor might propose. Each must survive review.
LEGIT = [
    ProposedEdit(kind="rewrite", target="exp0.b0",
                 after="Designed and built the payouts API used by 8,000 merchants",
                 why="Leads with ownership of a payments API.", requirement="payment systems"),
    ProposedEdit(kind="rewrite", target="exp0.b2",
                 after="Built scalable payment reconciliation jobs, cutting run time by [add %]",
                 why="Uses the posting's language for existing work.", requirement="scalable systems"),
    ProposedEdit(kind="reorder", target="exp0.bullets", order=[2, 0, 1],
                 why="Payments work first."),
    ProposedEdit(kind="reorder", target="skills", order=[2, 0, 1], why="Framework first."),
    ProposedEdit(kind="add_skill", target="skills", after="PostgreSQL",
                 evidence="Migrated reporting to PostgreSQL", why="Shown in a bullet."),
    ProposedEdit(kind="rewrite", target="summary",
                 after="Backend engineer focused on payment systems, with a payouts API "
                       "used by 8,000 merchants.",
                 why="Summary names the strongest evidence."),
]

# Edits that would fabricate. Each must be withheld.
CANARY_EDITS = [
    ProposedEdit(kind="rewrite", target="exp0.b0", after="Built the payouts API on Kubernetes and Kafka"),
    ProposedEdit(kind="rewrite", target="exp0.b1", after="Migrated reporting to PostgreSQL across microservices"),
    ProposedEdit(kind="rewrite", target="exp0.b2", after="Led payment reconciliation for SAMA compliance"),
    ProposedEdit(kind="rewrite", target="exp1.b1", after="Wrote internal tooling at Google"),
    ProposedEdit(kind="rewrite", target="exp1.b1", after="Microsoft internal tooling, written by me"),
    ProposedEdit(kind="rewrite", target="exp1.b0",
                 after="Supported the onboarding team with 12 KYC checks per day using Django "
                       "for 8,000 merchants"),
    ProposedEdit(kind="rewrite", target="summary", after="Backend engineer with a PhD and 9,500 merchants"),
    ProposedEdit(kind="rewrite", target="proj0.desc", after="A small marketplace side project with ٧٣ users"),
    ProposedEdit(kind="rewrite", target="exp1.b1", after="Wrote internal tooling since 2015"),
    ProposedEdit(kind="rewrite", target="exp0.b1", after="Tripled reporting speed after moving to PostgreSQL"),
    ProposedEdit(kind="rewrite", target="exp0.b1", after="Rain migrated reporting to PostgreSQL"),
    ProposedEdit(kind="add_skill", target="skills", after="Kubernetes",
                 evidence="Built the payouts API used by 8,000 merchants"),
    ProposedEdit(kind="add_skill", target="skills", after="AWS", evidence=""),
    ProposedEdit(kind="reorder", target="exp0.bullets", order=[0, 0, 1]),
    ProposedEdit(kind="rewrite", target="exp0.title", after="Senior Backend Engineer"),
]

GAPS = [
    Gap(requirement="Kubernetes", importance="critical",
        advice="Deploy a side project to a managed Kubernetes cluster."),
    Gap(requirement="kubernetes", importance="critical", advice="duplicate, dropped"),
    Gap(requirement="SAMA compliance", importance="preferred",
        advice="If you have worked under SAMA rules, say so in your own words."),
]


def call(*edits: ProposedEdit, gaps=()) -> TailorCall:
    return TailorCall(edits=list(edits), gaps=list(gaps))


class StubModel:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict] = []

    def call_structured(self, *, schema, system, content, **kw):
        self.calls.append({"schema": schema.__name__, "system": system, "content": content})
        return self.result


@pytest.fixture
def tailor_client(tmp_path, monkeypatch):
    """An app on a throwaway database, with extraction and tailoring stubbed."""
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

    from app.agents.analyst import tailor as tailor_mod
    from app.api import resumes as resumes_mod

    monkeypatch.setattr(resumes_mod, "extract_profile", lambda text: ORIGINAL)
    stub = StubModel(call(*LEGIT, *CANARY_EDITS, gaps=GAPS))
    monkeypatch.setattr(tailor_mod, "get_gemini", lambda: stub)

    from app.main import app
    with TestClient(app) as client:
        client.stub = stub
        yield client

    get_settings.cache_clear()


def upload(client) -> str:
    with (FIXTURES / "clean_single_column.pdf").open("rb") as fh:
        response = client.post("/api/resumes", files={"file": ("cv.pdf", fh, "application/pdf")})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def propose(client, resume_id: str, **job):
    body = {"resume_id": resume_id, "job": {
        "title": "Senior Backend Engineer", "company": "Hala",
        "description": JD, "apply_url": "https://jobs.example.com/hala/1", **job,
    }}
    return client.post("/api/tailor", json=body)
