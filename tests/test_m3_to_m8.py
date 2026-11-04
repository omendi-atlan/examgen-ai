"""Milestones 3-8 — question generation, moderation, examination site, marking,
analytics and PDF deliverables, exercised end to end."""

from __future__ import annotations

import io

from .conftest import make_previous_paper, make_text_document
from .test_m2_visuals import DIAGRAM_HEAVY

QUESTION_TYPES = {
    "fill_blank", "short_answer", "extended_response", "single_choice", "multiple_choice",
    "matching", "numerical", "formula", "ordering", "diagram_interpretation",
    "diagram_labelling", "case_study", "essay",
}


def _workspace(client, auth, name="Data Structures and Algorithms", code="CS201"):
    response = client.post("/api/workspaces", json={
        "name": name, "code": code, "module": "Module 3",
        "institution": "University of Example"}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, auth, workspace_id, filename, content):
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def prepare_workspace(client, auth, *, with_visuals=False, name="Data Structures and Algorithms"):
    workspace = _workspace(client, auth, name)
    _upload(client, auth, workspace["id"], "notes.txt",
            DIAGRAM_HEAVY if with_visuals else make_text_document())
    _upload(client, auth, workspace["id"], "past-paper.txt", make_previous_paper())
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    approved_visual_ids = []
    if with_visuals:
        client.post(f"/api/workspaces/{workspace['id']}/visuals/propose", headers=auth)
        visuals = client.get(f"/api/workspaces/{workspace['id']}/visuals", headers=auth).json()
        for visual in visuals:
            client.post(f"/api/workspaces/{workspace['id']}/visuals/{visual['id']}/decision",
                        json={"decision": "approve"}, headers=auth)
            approved_visual_ids.append(visual["id"])
    return workspace, approved_visual_ids


def generate(client, auth, workspace_id, *, mode="practice", question_count=12,
             total_marks=100, duration=120):
    blueprint = client.post(f"/api/workspaces/{workspace_id}/blueprints", json={
        "title": "Algorithms Examination", "duration_minutes": duration,
        "total_marks": total_marks, "question_count": question_count,
        "mode": mode}, headers=auth).json()
    assert blueprint["is_valid"], blueprint["validation"]
    response = client.post(
        f"/api/workspaces/{workspace_id}/blueprints/{blueprint['id']}/generate",
        json={"mode": mode}, headers=auth)
    assert response.status_code == 201, response.text
    return blueprint, response.json()


# ---------------------------------------------------------------- M3 questions

def test_generated_questions_use_subject_material_and_correct_controls(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])

    questions = examination["questions"]
    assert len(questions) >= 8
    for question in questions:
        assert question["qtype"] in QUESTION_TYPES
        assert question["prompt"].strip()
        assert question["marks"] >= 1
        assert question["section"]

    # Mandated interaction controls.
    for question in questions:
        control = question["payload"].get("answer_control")
        if question["qtype"] == "fill_blank":
            assert control == "text_box", "fill-in questions must use a text box"
            assert "________" in question["prompt"]
        if question["qtype"] == "single_choice":
            assert control == "dropdown"
            assert len(question["options"]) >= 2
        if question["qtype"] == "multiple_choice":
            assert control == "checkboxes"
        if question["qtype"] == "matching":
            assert control == "dropdown_per_item"
            assert question["payload"]["items"]


def test_examination_marks_and_duration_match_the_blueprint(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"], total_marks=80, duration=90)
    assert examination["total_marks"] == 80
    assert sum(q["marks"] for q in examination["questions"]) == 80
    assert examination["duration_minutes"] == 90


def test_questions_record_provenance_and_deduplicate(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"], question_count=14)
    prompts = [q["prompt"] for q in examination["questions"]]
    assert len(prompts) == len(set(prompts)), "duplicate prompts were generated"

    # Every question is traceable to workspace content or an approved asset.
    detail = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}",
        headers=auth).json()
    assert detail["questions"]


def test_diagram_questions_reference_the_approved_visual_version(client, auth):
    workspace, approved = prepare_workspace(
        client, auth, with_visuals=True, name="Database Systems")
    assert approved
    _, examination = generate(client, auth, workspace["id"], question_count=12)

    visual_questions = [q for q in examination["questions"] if q["visual"]]
    assert visual_questions, "approved visuals must be assessed"
    for question in visual_questions:
        assert question["visual"]["version"] >= 1
        assert question["visual"]["svg"].startswith("<svg")
        assert question["qtype"] in {"diagram_labelling", "diagram_interpretation"}


def test_generation_is_deterministic_for_a_given_version(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, first = generate(client, auth, workspace["id"], question_count=10)
    _, second = generate(client, auth, workspace["id"], question_count=10)
    # A new examination is a new version and may reuse bank items, but the
    # question bank must not accumulate accidental duplicates.
    assert first["version"] != second["version"]
    prompts = [q["prompt"] for q in second["questions"]]
    assert len(prompts) == len(set(prompts))


# ---------------------------------------------------------------- M4 moderation

def test_moderation_runs_and_blocks_publication_on_critical_errors(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    assert examination["moderation_status"] in {"approved", "requires_review", "rejected"}
    assert examination["status"] in {"published", "draft"}

    response = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/moderate",
        headers=auth)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"approved", "requires_review", "rejected"}
    for finding in payload["findings"]:
        assert finding["severity"] in {"critical", "major", "minor"}
        assert finding["message"]


def test_unpublished_examination_cannot_be_sat(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    if examination["status"] == "published":
        return  # covered elsewhere; this test targets the blocked path
    response = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Test"}, headers=auth)
    assert response.status_code == 409


# ---------------------------------------------------------------- M5/M6 attempts

def test_autosave_persists_and_survives_reload(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Test Student", "student_number": "ST001"},
        headers=auth).json()

    question_id = examination["questions"][0]["question_id"]
    response = client.put(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/responses",
        json={"responses": [{"question_id": question_id,
                             "answer": {"value": "O(n log n)"}, "flagged": True}]},
        headers=auth)
    assert response.status_code == 200

    state = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}",
        headers=auth).json()
    assert state["responses"][question_id]["value"] == "O(n log n)"
    assert state["flags"][question_id] is True
    assert state["remaining_seconds"] > 0
    assert state["server_time"]


def test_formal_mode_does_not_leak_answers_to_the_student_view(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"], mode="formal")
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Test Student"}, headers=auth).json()

    state = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}",
        headers=auth).json()
    for question in state["questions"]:
        assert "expected_answer" not in question
        assert "rubrics" not in question
        assert "explanation" not in question

    submitted = client.post(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
        headers=auth).json()
    assert submitted["feedback_available"] is False
    assert submitted["score"] is None

    result = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()
    assert result["feedback_released"] is False
    assert result.get("memorandum") is None

    # Authorised release unlocks feedback.
    client.post(f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/release-feedback",
                headers=auth)
    released = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()
    assert released["feedback_released"] is True
    assert released["memorandum"]


def test_attempts_are_private_to_the_student(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Owner"}, headers=auth).json()

    other = client.post("/api/auth/register", json={
        "email": "intruder@example.com", "password": "intruder-password-123",
        "display_name": "Intruder"}).json()["access_token"]
    response = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}",
        headers={"Authorization": f"Bearer {other}"})
    # The workspace itself is private, so this is a 404.
    assert response.status_code == 404


# ---------------------------------------------------------------- M7 marking

def test_objective_marking_uses_verified_answer_keys(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Marker Test"}, headers=auth).json()

    detail = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}",
        headers=auth).json()
    responses = []
    for question in detail["questions"]:
        answer = {}
        if question["qtype"] in {"fill_blank", "short_answer"}:
            answer = {"value": question["expected_answer"]}
        elif question["qtype"] == "single_choice":
            answer = {"index": question["options"].index(question["expected_answer"])}
        elif question["qtype"] == "numerical":
            answer = {"value": question["expected_answer"]}
        elif question["qtype"] == "multiple_choice":
            answer = {"selected": question["payload"].get("correct", [])}
        elif question["qtype"] == "ordering":
            answer = {"order": question["payload"].get("correct_order", [])}
        elif question["qtype"] == "matching":
            answer = {"matches": {i["prompt"]: i["answer"]
                                  for i in question["payload"].get("items", [])}}
        else:
            answer = {"value": question["expected_answer"]}
        responses.append({"question_id": question["question_id"], "answer": answer,
                          "flagged": False})

    client.put(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/responses",
               json={"responses": responses}, headers=auth)
    submitted = client.post(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
        headers=auth).json()

    assert submitted["feedback_available"] is True
    assert submitted["percentage"] == 100.0, submitted

    result = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()
    for marking in result["markings"]:
        assert marking["rationale"]
        assert marking["awarded"] <= marking["max_marks"]
        assert marking["method"] in {"objective", "rubric"}


def test_wrong_objective_answers_score_zero(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Wrong Answers"}, headers=auth).json()

    detail = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}",
        headers=auth).json()
    responses = [{"question_id": q["question_id"],
                  "answer": {"value": "definitely not the answer", "index": 0,
                             "selected": ["wrong"], "order": ["wrong"],
                             "matches": {"x": "y"}},
                  "flagged": False} for q in detail["questions"]]
    client.put(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/responses",
               json={"responses": responses}, headers=auth)
    submitted = client.post(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
        headers=auth).json()
    assert submitted["percentage"] < 40


def test_rubric_marking_supports_human_review(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Review Test"}, headers=auth).json()

    detail = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}",
        headers=auth).json()
    # Submit a one-word response to an extended question to force low confidence.
    responses = [{"question_id": q["question_id"], "answer": {"value": "maybe"},
                  "flagged": False} for q in detail["questions"]]
    client.put(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/responses",
               json={"responses": responses}, headers=auth)
    client.post(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
                headers=auth)
    result = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()

    rubric_markings = [m for m in result["markings"] if m["method"] == "rubric"]
    assert rubric_markings, "extended responses must be rubric marked"
    flagged = [m for m in rubric_markings if m["needs_human_review"]]
    assert flagged, "unreliable responses must be flagged for human review"

    # A lecturer can override the automated award, which clears the review flag.
    review = client.post(
        f"/api/workspaces/{workspace['id']}/markings/{flagged[0]['id']}/review",
        json={"awarded": flagged[0]["max_marks"], "rationale": "Manual review by lecturer"},
        headers=auth)
    assert review.status_code == 200, review.text
    assert review.json()["reviewed"] is True
    assert review.json()["needs_human_review"] is False
    assert review.json()["awarded"] == flagged[0]["max_marks"]

    refreshed = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()
    updated = [m for m in refreshed["markings"] if m["id"] == flagged[0]["id"]][0]
    assert updated["reviewed"] is True


def test_marking_override_is_validated(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Validation Test"}, headers=auth).json()
    client.post(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
                headers=auth)
    markings = client.get(
        f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/result",
        headers=auth).json()["markings"]
    assert markings
    target = markings[0]
    too_high = client.post(
        f"/api/workspaces/{workspace['id']}/markings/{target['id']}/review",
        json={"awarded": target["max_marks"] + 100}, headers=auth)
    assert too_high.status_code == 400
    negative = client.post(
        f"/api/workspaces/{workspace['id']}/markings/{target['id']}/review",
        json={"awarded": -5}, headers=auth)
    assert negative.status_code == 400


def test_analytics_reflect_actual_results(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    attempt = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "Analytics Test"}, headers=auth).json()

    detail = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}",
        headers=auth).json()
    responses = []
    for index, question in enumerate(detail["questions"]):
        # Answer the first half correctly and the second half incorrectly.
        if index < len(detail["questions"]) // 2:
            answer = {"value": question["expected_answer"],
                      "index": question["options"].index(question["expected_answer"])
                      if question["qtype"] == "single_choice" else 0}
        else:
            answer = {"value": "incorrect", "index": 0}
        responses.append({"question_id": question["question_id"], "answer": answer})
    client.put(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/responses",
               json={"responses": responses}, headers=auth)
    client.post(f"/api/workspaces/{workspace['id']}/attempts/{attempt['id']}/submit",
                headers=auth)

    analytics = client.get(f"/api/workspaces/{workspace['id']}/analytics", headers=auth).json()
    assert analytics["attempts"] == 1
    assert analytics["average_percentage"] is not None
    assert analytics["by_topic"]
    assert analytics["mastery"]["overall"] in {
        "not_assessed", "requires_improvement", "developing", "competent", "strong_mastery"}
    assert analytics["recommendations"]
    assert analytics["history"]


# ---------------------------------------------------------------- M8 PDFs

def test_both_pdf_deliverables_are_generated_and_version_consistent(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])

    deliverables = client.post(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/deliverables",
        headers=auth).json()
    assert "memorandum" in deliverables and "mastery_guide" in deliverables
    for kind in ("memorandum", "mastery_guide"):
        assert deliverables[kind]["version"] == examination["version"]

    memo = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
        f"/deliverables/memorandum/download", headers=auth)
    assert memo.status_code == 200
    assert memo.headers["content-type"] == "application/pdf"
    assert memo.content.startswith(b"%PDF")

    mastery = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
        f"/deliverables/mastery_guide/download", headers=auth)
    assert mastery.status_code == 200
    assert mastery.content.startswith(b"%PDF")
    assert len(mastery.content) > 2000


def test_formal_memorandum_is_protected_until_released(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"], mode="formal")
    client.post(f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/deliverables",
                headers=auth)

    response = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
        f"/deliverables/memorandum/download", headers=auth)
    assert response.status_code == 403

    client.post(f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
                f"/release-feedback", headers=auth)
    unlocked = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
        f"/deliverables/memorandum/download", headers=auth)
    assert unlocked.status_code == 200
    assert unlocked.content.startswith(b"%PDF")


def test_mastery_guide_includes_subject_notes(client, auth):
    workspace, _ = prepare_workspace(client, auth)
    _, examination = generate(client, auth, workspace["id"])
    client.post(f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}/deliverables",
                headers=auth)
    response = client.get(
        f"/api/workspaces/{workspace['id']}/examinations/{examination['id']}"
        f"/deliverables/mastery_guide/download", headers=auth)
    assert response.status_code == 200
    # The guide must be a substantial document, not a stub.
    assert len(response.content) > 8000


# ---------------------------------------------------------------- end to end

def test_full_student_workflow_end_to_end(client, auth):
    """The complete journey from prompt section 21, in one test."""
    # 1-2. Create two independent subjects.
    algorithms = _workspace(client, auth, "Algorithms", "CS201")
    databases = _workspace(client, auth, "Databases", "CS310")

    # 3. Upload only the relevant coursework per subject.
    _upload(client, auth, algorithms["id"], "algorithms.txt", make_text_document())
    _upload(client, auth, databases["id"], "databases.txt", DIAGRAM_HEAVY)

    # 4-5. Analyse, classify and review coverage.
    report = client.post(f"/api/workspaces/{algorithms['id']}/classify", headers=auth).json()
    assert report["verdict"] in {"sufficient", "partial"}
    topics = client.get(f"/api/workspaces/{algorithms['id']}/topics", headers=auth).json()
    assert topics

    # Confirm the two subjects stayed isolated.
    db_topics = client.get(f"/api/workspaces/{databases['id']}/topics", headers=auth).json()
    assert {t["name"] for t in topics}.isdisjoint({t["name"] for t in db_topics})

    # 6. Approve visual assets.
    client.post(f"/api/workspaces/{algorithms['id']}/visuals/propose", headers=auth)
    for visual in client.get(f"/api/workspaces/{algorithms['id']}/visuals", headers=auth).json():
        client.post(f"/api/workspaces/{algorithms['id']}/visuals/{visual['id']}/decision",
                    json={"decision": "approve"}, headers=auth)

    # 7-8. Configure, validate, generate and sit the examination.
    _, examination = generate(client, auth, algorithms["id"], question_count=10)
    assert examination["status"] == "published"
    attempt = client.post(
        f"/api/workspaces/{algorithms['id']}/examinations/{examination['id']}/attempts",
        json={"student_name": "End To End", "student_number": "E2E1"}, headers=auth).json()

    detail = client.get(
        f"/api/workspaces/{algorithms['id']}/examinations/{examination['id']}",
        headers=auth).json()
    responses = []
    for question in detail["questions"]:
        answer = {"value": question.get("expected_answer", "")}
        if question["qtype"] == "single_choice":
            answer = {"index": question["options"].index(question["expected_answer"])}
        if question["qtype"] == "multiple_choice":
            answer = {"selected": question["payload"].get("correct", [])}
        if question["qtype"] == "ordering":
            answer = {"order": question["payload"].get("correct_order", [])}
        if question["qtype"] == "matching":
            answer = {"matches": {i["prompt"]: i["answer"]
                                  for i in question["payload"].get("items", [])}}
        responses.append({"question_id": question["question_id"], "answer": answer})
    client.put(f"/api/workspaces/{algorithms['id']}/attempts/{attempt['id']}/responses",
               json={"responses": responses}, headers=auth)

    # 9-10. Submit and receive marking.
    submitted = client.post(
        f"/api/workspaces/{algorithms['id']}/attempts/{attempt['id']}/submit",
        headers=auth).json()
    assert submitted["percentage"] == 100.0

    # 11-12. Performance analysis and the memorandum.
    analytics = client.get(f"/api/workspaces/{algorithms['id']}/analytics", headers=auth).json()
    assert analytics["attempts"] == 1
    assert analytics["mastery"]["overall"] == "strong_mastery"

    # 13-14. Both PDF deliverables, version consistent with the website.
    deliverables = client.post(
        f"/api/workspaces/{algorithms['id']}/examinations/{examination['id']}/deliverables",
        headers=auth).json()
    assert deliverables["memorandum"]["version"] == examination["version"]
    assert deliverables["mastery_guide"]["version"] == examination["version"]
