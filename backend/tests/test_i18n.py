"""Arabic: the catalogue, the edge translation, and what reaches the model.

The strongest tests here run the code that writes messages -- every check,
deduction, note and error -- and fail on any that comes out of `tr` still in
English. A message added later without a translation fails them too.
"""
from __future__ import annotations

import ast
import pathlib
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.analyst import review as review_mod
from app.agents.analyst import scoring
from app.agents.analyst.fields import FieldCandidate, score_field
from app.agents.analyst.industries import PACKS
from app.agents.analyst.parser import ParseReport
from app.agents.analyst.profile import Contact, CvProfile, Experience, Project
from app.agents.analyst.provenance import introduced
from app.agents.analyst.review import ReviewCall, content_checks, contact_checks, layout_checks
from app.agents.analyst.schemas import (
    ExperienceFit, Fit, Importance, Requirement, Status, WritingReview,
)
from app.agents.analyst.tailor import Target, _label, scope_for
from app.agents.analyst.targeting import CAVEAT
from app.agents.scout.brief import _gap, _why
from app.agents.scout.intake import IntakeError, describe_failure
from app.agents.scout.matcher import Match
from app.agents.scout.policy import PolicyViolation, WallEncountered
from app.core.i18n import LANGUAGE_RULE_AR, _SENTENCE, tr, with_language
from app.core.safe_fetch import BlockedAddress
from app.sources.base import JobPosting

ARABIC = re.compile(r"[؀-ۿ]")
APP = pathlib.Path(__file__).parent.parent / "app"


def fully_arabic(text: str) -> bool:
    """Every sentence of the translation carries Arabic -- no English left over."""
    translated = tr(text, "ar")
    return all(ARABIC.search(part) for part in _SENTENCE.split(translated) if part.strip())


def assert_translated(*texts: str) -> None:
    missing = [t for t in texts if t and not fully_arabic(t)]
    assert not missing, "untranslated:\n" + "\n".join(missing)


# --- the mechanism ------------------------------------------------------------------

def test_english_is_left_alone():
    assert tr("Resume not found.", "en") == "Resume not found."


def test_an_exact_message_is_translated():
    assert tr("Resume not found.", "ar") == "لم يُعثر على السيرة الذاتية."


def test_a_composed_message_is_translated_sentence_by_sentence():
    assert tr("Resume not found. Upload it first.", "ar") == (
        "لم يُعثر على السيرة الذاتية. ارفعها أولًا."
    )


def test_a_message_inside_a_message_is_translated_too():
    out = tr("Google for Jobs: the request did not go through. Try again shortly.", "ar")
    assert out == "Google للوظائف: لم يكتمل الطلب. حاول مرة أخرى بعد قليل."


def test_an_unknown_message_comes_back_unchanged():
    assert tr("Something nobody has translated.", "ar") == "Something nobody has translated."


def test_a_quote_from_a_cv_is_never_rewritten():
    """Nested-only patterns like "{title} at {company}" must not touch a bullet."""
    for quote in ("Led the migration at Tamara", "Wrote 3 pages", "Payouts API"):
        assert tr(quote, "ar") == quote


def test_numbers_only_fill_number_slots():
    assert tr("3 pages", "ar") == "3 صفحات"
    assert tr("Several pages", "ar") == "Several pages"


# --- every error the code raises -----------------------------------------------------

RAISED = {"HTTPException", "IntakeError", "ProfileError", "PolicyViolation", "JSearchError",
          "ScoutModelError", "MissingCredentialsError", "ModelOutputError", "RefusalError",
          "BlockedAddress", "UnknownEdit", "PlaceholderError", "_with_fallback"}


def _sample(node: ast.expr) -> str | None:
    """The message with sample values -- 7 for any interpolation, so number
    slots fill -- or None when it is not a literal template."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                out.append(part.value)
            elif isinstance(part.value, ast.IfExp) and isinstance(part.value.orelse, ast.Constant):
                out.append(str(part.value.orelse.value))    # the plural of "placeholder{'s'}"
            else:
                out.append("7")
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _sample(node.left), _sample(node.right)
        return None if left is None or right is None else left + right
    return None


def raised_messages() -> list[tuple[str, str]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name not in RAISED:
                continue
            for arg in node.args:
                text = _sample(arg)
                if text and ARABIC.search(text) is None and re.search(r"[A-Za-z]{3}", text):
                    found.append((f"{path.relative_to(APP)}:{node.lineno}", text))
    return found


def test_the_scan_finds_the_messages():
    assert len(raised_messages()) > 40


@pytest.mark.parametrize("where,message", raised_messages(), ids=lambda x: x[:60])
def test_every_raised_message_has_an_arabic_translation(where, message):
    # Internal markers that never reach a page as they are.
    if message.startswith(("7 is behind a wall", "7 is not an editable")):
        pytest.skip("replaced by describe_failure / never shown")
    assert fully_arabic(message), f"{where}: {message!r} -> {tr(message, 'ar')!r}"


def test_intake_advice_is_translated_whole():
    assert_translated(
        describe_failure(PolicyViolation("robots.txt disallows https://x.example/job")),
        describe_failure(WallEncountered("authwall")),
        describe_failure(BlockedAddress("10.0.0.1 is a private or reserved address. Paste a public job URL.")),
        describe_failure(IntakeError("That page does not look like a single job posting.")),
        "That page could not be read. Paste the job description into the box below instead.",
    )


def test_model_failures_are_translated():
    from google.genai import errors
    from app.core.gemini import MissingCredentialsError, ModelOutputError, RefusalError, explain

    for exc in (
        MissingCredentialsError("No Gemini API key. Get one at https://aistudio.google.com/apikey, "
                                "set GEMINI_API_KEY in backend/.env and restart the server."),
        errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                           "message": "API key not valid. Please pass a valid API key."}}),
        errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "q"}}),
        errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "busy"}}),
        errors.ServerError(500, {"error": {"code": 500, "status": "INTERNAL", "message": "x"}}),
        httpx.ConnectError("no route"),
        ModelOutputError("Gemini ran out of room before finishing its reply. Try a shorter document."),
        RefusalError("Gemini withheld its reply (SAFETY)."),
    ):
        assert_translated(explain(exc)[1])


# --- every message the code composes ---------------------------------------------------

def deductions():
    bare = ParseReport(page_count=1, char_count=12, has_extractable_text=False, is_scanned=True)
    busy = ParseReport(page_count=4, char_count=900, multi_column_pages=[1], table_pages=[2],
                       header_footer_text=["Sara +966"], non_embedded_fonts=["Arial"],
                       has_email=False, has_phone=False, detected_sections=[],
                       nonstandard_headings=["My Journey"], has_saudi_phone=True,
                       phone_e164_ok=False)
    requirements = [
        Requirement(skill="Kafka", importance=Importance.CRITICAL, status=Status.MISSING),
        Requirement(skill="Go", importance=Importance.PREFERRED, status=Status.WEAK, evidence="Go"),
    ]
    subs = [scoring.score_ats(bare), scoring.score_ats(busy),
            scoring.score_keywords(requirements),
            scoring.score_formatting(busy, WritingReview(issues=[], summary_verdict=""))]
    for fit in (Fit.OVER, Fit.UNDER, Fit.FAR_UNDER):
        subs.append(scoring.score_experience(ExperienceFit(
            jd_seniority="Senior", resume_seniority="Mid", fit=fit,
            years_required=6, years_evidenced=3, gaps=["no people management"])))
    return subs


def test_every_deduction_is_translated():
    for sub in deductions():
        assert_translated(sub.label)
        for d in sub.deductions:
            assert_translated(d.title, d.fix)
            if not d.rule.startswith("exp.") or d.rule == "exp.years_short":
                assert_translated(d.evidence)


def test_the_review_checks_are_translated():
    empty = CvProfile(contact=Contact(name="Sara"),
                      experience=[Experience(title="Intern", company="Acme"),
                                  Experience(title="Analyst", company="Rain", start="2020",
                                             bullets=["Wrote reports", "Ran meetings", "Filed"])])
    report = ParseReport(page_count=4, char_count=900, multi_column_pages=[1],
                         has_email=False, has_phone=False, nonstandard_headings=["X"])
    for check in [*content_checks(empty), *contact_checks(empty), *layout_checks(report)]:
        assert_translated(check.title, check.fix)
        if check.rule not in {"content.few_numbers", "content.roles_without_bullets",
                              "content.roles_without_dates"}:     # these quote the CV
            assert_translated(check.evidence)


def test_every_field_and_its_arithmetic_is_translated():
    assert_translated(*(pack.label for pack in PACKS.values()))
    for alignment in ("direct", "adjacent", "distant"):
        for candidate in (
            FieldCandidate(key="tech", matched_skills=["Python"], missing_skills=["Go"],
                           years_in_field=3, title_alignment=alignment),
            FieldCandidate(key="tech", title_alignment=alignment),
        ):
            fit = score_field(candidate)
            for component in fit.components:
                assert_translated(component.label, component.why)


def _match(**experience) -> Match:
    return Match(
        job=JobPosting(title="Engineer", company="Rain"), score=50.0,
        requirements=[
            Requirement(skill=s, importance=Importance.CRITICAL, status=Status.PRESENT)
            for s in ("Python", "SQL", "Go", "Rust")
        ] + [
            Requirement(skill=s, importance=Importance.CRITICAL, status=Status.MISSING)
            for s in ("Kafka", "K8s", "Scala")
        ],
        experience=ExperienceFit(jd_seniority="Senior", resume_seniority="Mid", **experience),
        deductions=[],
    )


def test_the_search_brief_lines_are_translated():
    for fit in (Fit.OVER, Fit.UNDER, Fit.FAR_UNDER, Fit.MATCH):
        match = _match(fit=fit, years_required=6, years_evidenced=3)
        assert_translated(_why(match), _gap(match))
    empty = Match(job=JobPosting(title="x", company="y"), score=0.0, requirements=[],
                  experience=ExperienceFit(jd_seniority="?", resume_seniority="?", fit=Fit.MATCH),
                  deductions=[])
    assert_translated(_why(empty))


def test_the_search_notes_are_translated(monkeypatch):
    from app.agents.scout import runner as runner_mod
    from app.agents.scout.runner import ScoutRequest
    from app.sources import jsearch as jsearch_mod

    monkeypatch.setattr(runner_mod, "scan_ats", lambda **kw: [])
    notes: list[str] = []
    runner_mod.collect(ScoutRequest(resume_text="cv", include_jsearch=True), notes=notes)

    real_client = httpx.Client
    for status, body in ((429, {}), (500, {}), (200, {"data": {"jobs": []}})):
        def handler(request, status=status, body=body):
            return httpx.Response(status, json=body)
        monkeypatch.setattr(httpx, "Client", lambda *a, h=handler, **kw: real_client(
            *a, **{**kw, "transport": httpx.MockTransport(h)}))
        for linkedin in (False, True):
            runner_mod.collect(ScoutRequest(resume_text="cv", include_jsearch=True,
                                            jsearch_query="Backend Engineer",
                                            linkedin_only=linkedin),
                               jsearch_key="k", notes=notes)

    class Broken:
        def __init__(self, key):
            raise jsearch_mod.JSearchError(
                "JSearch rejected the API key. Check JSEARCH_API_KEY in backend/.env.")
    monkeypatch.setattr(jsearch_mod, "JSearch", Broken)
    runner_mod.collect(ScoutRequest(resume_text="cv", include_jsearch=True), jsearch_key="k",
                       notes=notes)

    notes.append("Google for Jobs was searched for “Backend Engineer”, the most recent "
                 "title on your CV. Type a role to search for something else.")
    assert len(notes) >= 6
    assert_translated(*notes)


def test_tailoring_labels_and_refusals_are_translated():
    profile = CvProfile(
        summary="Backend engineer.", skills=["Python"],
        experience=[Experience(title="Engineer", company="Tamara",
                               bullets=["Built the payouts API"]),
                    Experience(bullets=["Ran the ledger"])],
        projects=[Project(name="Ledger", description="A ledger."), Project(description="Tool.")],
    )
    labels = [
        _label(profile, Target("summary"), "rewrite"),
        _label(profile, Target("bullet", 0, 0), "rewrite"),
        _label(profile, Target("bullet", 1, 0), "rewrite"),
        _label(profile, Target("bullets", 0), "reorder"),
        _label(profile, Target("desc", 0), "rewrite"),
        _label(profile, Target("desc", 1), "rewrite"),
        _label(profile, Target("skills"), "add_skill", "Go"),
        _label(profile, Target("skills"), "reorder"),
        _label(profile, Target("projects"), "reorder"),
    ]
    assert_translated(*labels)

    messages = []
    for target in (Target("bullet", 0, 0), Target("bullet", 1, 0), Target("desc", 0),
                   Target("desc", 1), Target("summary")):
        scope, where = scope_for(profile, target)
        for text in ("Built the payouts API for 40 merchants at Google on Kubernetes",
                     "Led the ledger team", "Built the payouts API for fintech",
                     "Built the payouts API with throughput"):
            messages += [f.message for f in introduced(
                text, scope=scope, whole=profile.all_text + " 40 Kubernetes",
                job_terms={"fintech"}, where=where)]
    messages += [f.message for f in introduced("golang", scope="Go", strict=True,
                                               where="the quoted line")]

    # Every kind of refusal the checker writes, in every "where" it names.
    for kind in ("Adds the figure", "Adds “", "Brings in", "claims a leadership role",
                 "does not appear in", "It does appear elsewhere", "It is not in your CV",
                 "Tailoring can only reword"):
        assert any(kind in m for m in messages), f"no {kind!r} message was produced"
    for where in ("your role at Tamara", "this role", "the project “Ledger”", "this project",
                  "your CV", "the quoted line"):
        assert any(where in m for m in messages), f"no message names {where!r}"
    assert_translated(*messages)


def test_the_targeting_caveat_is_translated():
    assert_translated(CAVEAT)


# --- the model is told ---------------------------------------------------------------------

def test_the_language_rule_is_added_only_for_arabic():
    assert with_language("SYSTEM", "en") == "SYSTEM"
    assert with_language("SYSTEM", "ar").endswith(LANGUAGE_RULE_AR)
    assert "Never translate what you quote" in LANGUAGE_RULE_AR


class _Stub:
    def __init__(self):
        self.systems: list[str] = []

    def call_structured(self, *, schema, system, content, **kw):
        self.systems.append(system)
        if schema is CvProfile:
            return CvProfile(contact=Contact(name="Sara", email="s@example.com",
                                             phone="+966 5", links=["x"]),
                             summary="Engineer.", skills=["Python"],
                             experience=[Experience(title="Engineer", company="Rain",
                                                    start="2020", bullets=["Built 3 APIs"])])
        return schema.model_validate({"verdict": "جيدة.", "strengths": [], "weaknesses": []})


def test_an_arabic_review_asks_the_model_for_arabic(monkeypatch):
    stub = _Stub()
    monkeypatch.setattr(review_mod, "get_gemini", lambda: stub)
    profile = stub.call_structured(schema=CvProfile, system="", content=[])
    review = review_mod.review_cv("Engineer. Built 3 APIs", profile=profile, lang="ar")
    assert LANGUAGE_RULE_AR in stub.systems[-1]
    assert all(ARABIC.search(c.title) for c in review.checks)


# --- the endpoints ---------------------------------------------------------------------------

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
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "SessionLocal",
                        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


AR = {"X-UI-Lang": "ar"}


def test_errors_come_back_in_the_pages_language(client):
    assert client.get("/api/resumes/nope/review").json()["detail"] == "Resume not found."
    assert client.get("/api/resumes/nope/review", headers=AR).json()["detail"] == (
        "لم يُعثر على السيرة الذاتية."
    )


def test_the_browsers_own_language_header_is_ignored(client):
    """Accept-Language is the browser's; only the page's choice counts."""
    r = client.get("/api/resumes/nope/review", headers={"Accept-Language": "ar"})
    assert r.json()["detail"] == "Resume not found."


def test_industries_are_labelled_in_arabic(client):
    labels = {i["key"]: i["label"] for i in client.get("/api/industries", headers=AR).json()}
    assert labels["tech"] == "التقنية"


def _upload(client) -> str:
    fixture = pathlib.Path(__file__).parent / "fixtures" / "clean_single_column.pdf"
    with fixture.open("rb") as fh:
        return client.post("/api/resumes",
                           files={"file": ("cv.pdf", fh, "application/pdf")}).json()["id"]


def test_reviews_are_kept_per_language(client, monkeypatch):
    from app.agents.analyst import profile as profile_mod
    stub = _Stub()
    monkeypatch.setattr(review_mod, "get_gemini", lambda: stub)
    monkeypatch.setattr(profile_mod, "get_gemini", lambda: stub)
    resume_id = _upload(client)

    english = client.get(f"/api/resumes/{resume_id}/review").json()["review"]
    arabic = client.get(f"/api/resumes/{resume_id}/review", headers=AR).json()["review"]
    client.get(f"/api/resumes/{resume_id}/review", headers=AR)
    client.get(f"/api/resumes/{resume_id}/review")

    reviews = [s for s in stub.systems if "recruiter reviewing a CV" in s]
    assert len(reviews) == 2, "one review per language, each cached"
    assert LANGUAGE_RULE_AR in reviews[1] and LANGUAGE_RULE_AR not in reviews[0]
    assert english["checks"] and not ARABIC.search(english["checks"][0]["title"])
    assert ARABIC.search(arabic["checks"][0]["title"])


def test_a_review_stored_before_languages_is_read_as_english(client, monkeypatch):
    from app.agents.analyst import profile as profile_mod
    stub = _Stub()
    monkeypatch.setattr(review_mod, "get_gemini", lambda: stub)
    monkeypatch.setattr(profile_mod, "get_gemini", lambda: stub)
    resume_id = _upload(client)
    first = client.get(f"/api/resumes/{resume_id}/review").json()["review"]

    import app.models.db as db_mod
    from app.models.entities import StoredReview
    with db_mod.SessionLocal() as db:
        row = db.query(StoredReview).one()
        row.review = first                     # the old, flat shape
        db.commit()

    assert client.get(f"/api/resumes/{resume_id}/review").json()["review"] == first
    assert sum("recruiter reviewing a CV" in s for s in stub.systems) == 1


def test_review_checks_come_from_a_real_call_path(client, monkeypatch):
    """ReviewCall is what the endpoint asks for -- keep the stub honest."""
    assert ReviewCall.model_validate({"verdict": "x", "strengths": [], "weaknesses": []})
