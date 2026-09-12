"""Tailoring and version endpoints.

The model is stubbed in `tailor_client`, so every proposal here is the fixed mix
of honest and planted edits from `tailor_fixtures`.
"""
from __future__ import annotations

from app.agents.analyst.profile import CvProfile
from tailor_fixtures import (  # noqa: F401 -- tailor_client is a fixture
    JD,
    LEGIT,
    ORIGINAL,
    propose,
    tailor_client,
    upload,
)


def save(client, proposal_id: str, ids, name: str = ""):
    return client.post(f"/api/tailor/{proposal_id}/versions",
                       json={"accepted_ids": ids, "name": name})


# --- proposing -----------------------------------------------------------------

def test_a_proposal_lists_offered_withheld_and_gaps(tailor_client):
    resume_id = upload(tailor_client)
    body = propose(tailor_client, resume_id).json()

    assert len(body["edits"]) == len(LEGIT)
    assert body["blocked"] and all(b["violations"] for b in body["blocked"])
    assert [g["requirement"] for g in body["gaps"]] == ["Kubernetes", "SAMA compliance"]
    assert body["prompt_version"] == "tailor_v1"
    assert body["job_title"] == "Senior Backend Engineer" and body["company"] == "Hala"


def test_a_rewrite_carries_a_diff_the_ui_can_render(tailor_client):
    resume_id = upload(tailor_client)
    rewrite = next(e for e in propose(tailor_client, resume_id).json()["edits"]
                   if e["kind"] == "rewrite")
    ops = rewrite["diff"]
    assert "".join(o["text"] for o in ops if o["op"] != "insert") == rewrite["before_text"]
    assert "".join(o["text"] for o in ops if o["op"] != "delete") == rewrite["after_text"]


def test_a_short_posting_is_refused_before_any_model_call(tailor_client):
    resume_id = upload(tailor_client)
    response = propose(tailor_client, resume_id, description="Engineer wanted.")
    assert response.status_code == 422
    assert tailor_client.stub.calls == []


def test_saying_no_job_is_refused(tailor_client):
    resume_id = upload(tailor_client)
    assert tailor_client.post("/api/tailor", json={"resume_id": resume_id}).status_code == 422


def test_an_unknown_resume_is_a_404(tailor_client):
    assert propose(tailor_client, "nope").status_code == 404


def test_a_search_result_is_resolved_from_the_servers_cache(tailor_client, monkeypatch):
    """The client names the result; the posting text never makes the round trip."""
    from app.agents.scout.prefilter import Candidate
    from app.api import scout as scout_mod
    from app.sources.base import JobPosting

    resume_id = upload(tailor_client)
    posting = JobPosting(title="Payments Engineer", company="Rain", description=JD,
                         apply_url="https://jobs.example.com/rain/7", source="greenhouse")
    monkeypatch.setitem(scout_mod._CACHE, resume_id,
                        {"abc": Candidate(job=posting, similarity=0.1, overlap=())})

    response = tailor_client.post("/api/tailor",
                                  json={"resume_id": resume_id, "scout_job_id": "abc"})
    assert response.status_code == 200, response.text
    assert response.json()["company"] == "Rain"


def test_an_expired_search_result_says_so(tailor_client):
    resume_id = upload(tailor_client)
    response = tailor_client.post("/api/tailor",
                                  json={"resume_id": resume_id, "scout_job_id": "gone"})
    assert response.status_code == 409


def test_the_same_posting_is_one_job_not_two(tailor_client):
    resume_id = upload(tailor_client)
    first = propose(tailor_client, resume_id).json()
    second = propose(tailor_client, resume_id).json()
    assert first["job_id"] == second["job_id"]


# --- saving versions -----------------------------------------------------------

def test_saving_applies_only_the_accepted_edits(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    chosen = proposal["edits"][0]

    version = save(tailor_client, proposal["proposal_id"], [chosen["id"]]).json()
    profile = CvProfile.model_validate(version["profile"])
    assert profile.experience[0].bullets[0] == chosen["after_text"]
    assert profile.experience[0].bullets[1] == ORIGINAL.experience[0].bullets[1]
    assert version["accepted_edit_ids"] == [chosen["id"]]


def test_a_version_is_named_after_its_job_by_default(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    version = save(tailor_client, proposal["proposal_id"], []).json()
    assert version["name"] == "Senior Backend Engineer — Hala"
    assert version["job_title"] == "Senior Backend Engineer"


def test_a_version_can_be_given_its_own_name(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    assert save(tailor_client, proposal["proposal_id"], [], "Hala — short").json()["name"] == \
        "Hala — short"


def test_accepting_nothing_saves_a_copy_of_the_original(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    version = save(tailor_client, proposal["proposal_id"], []).json()
    assert CvProfile.model_validate(version["profile"]) == ORIGINAL


def test_an_id_from_nowhere_is_refused(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    assert save(tailor_client, proposal["proposal_id"], ["e999"]).status_code == 422


def test_placeholders_left_to_fill_are_counted(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    with_placeholder = [e["id"] for e in proposal["edits"] if e["has_placeholder"]]
    assert with_placeholder
    assert save(tailor_client, proposal["proposal_id"], with_placeholder).json()["placeholders"] == 1


def test_an_unknown_proposal_is_a_404(tailor_client):
    assert save(tailor_client, "nope", []).status_code == 404


def test_a_tampered_proposal_fails_the_backstop_and_saves_nothing(tailor_client):
    """Defence in depth. If a stored edit were ever corrupted -- a bug, a bad
    migration, someone editing the database -- the whole-document check still
    refuses to produce a CV containing something the original does not."""
    from app.models.db import SessionLocal
    from app.models.entities import CvVersion, TailorProposal

    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()

    db = SessionLocal()
    row = db.get(TailorProposal, proposal["proposal_id"])
    edits = [dict(e) for e in row.edits]
    target = next(i for i, e in enumerate(edits) if e["kind"] == "rewrite" and
                  e["target"].startswith("exp0.b"))
    edits[target]["after_text"] = "Built the payouts API on Kubernetes"
    row.edits = edits
    db.commit()
    db.close()

    response = save(tailor_client, proposal["proposal_id"], [edits[target]["id"]])
    assert response.status_code == 500

    db = SessionLocal()
    assert db.query(CvVersion).filter_by(resume_id=resume_id, is_original=False).count() == 0
    db.close()


# --- listing and deleting ------------------------------------------------------

def test_the_original_is_listed_first_once_the_cv_has_been_read(tailor_client):
    resume_id = upload(tailor_client)
    assert tailor_client.get(f"/api/resumes/{resume_id}/versions").json() == []

    proposal = propose(tailor_client, resume_id).json()
    save(tailor_client, proposal["proposal_id"], [], "first")
    save(tailor_client, proposal["proposal_id"], [], "second")

    names = [v["name"] for v in tailor_client.get(f"/api/resumes/{resume_id}/versions").json()]
    assert names == ["Original", "second", "first"]


def test_a_tailored_version_can_be_deleted(tailor_client):
    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    version_id = save(tailor_client, proposal["proposal_id"], []).json()["id"]

    assert tailor_client.delete(f"/api/versions/{version_id}").status_code == 204
    assert tailor_client.get(f"/api/versions/{version_id}").status_code == 404


def test_the_original_cannot_be_deleted_on_its_own(tailor_client):
    resume_id = upload(tailor_client)
    propose(tailor_client, resume_id)
    original = tailor_client.get(f"/api/resumes/{resume_id}/versions").json()[0]
    assert original["is_original"]
    assert tailor_client.delete(f"/api/versions/{original['id']}").status_code == 409


def test_deleting_the_cv_deletes_every_proposal_and_version(tailor_client):
    """Tailored versions are copies of personal data; they go with the CV."""
    from app.models.db import SessionLocal
    from app.models.entities import CvVersion, TailorProposal

    resume_id = upload(tailor_client)
    proposal = propose(tailor_client, resume_id).json()
    save(tailor_client, proposal["proposal_id"], [e["id"] for e in proposal["edits"]])

    assert tailor_client.delete(f"/api/resumes/{resume_id}").status_code == 204

    db = SessionLocal()
    assert db.query(TailorProposal).filter_by(resume_id=resume_id).count() == 0
    assert db.query(CvVersion).filter_by(resume_id=resume_id).count() == 0
    db.close()
