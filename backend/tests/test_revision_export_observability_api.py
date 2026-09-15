import copy
import json

from backend.tests.conftest import make_client
from backend.tests.support.exam import ExamFakeModel, build_exam
from backend.tests.support.http import wait_for_operation


def publish_exam(client):
    subject_id, model_id, _, blueprint_id = build_exam(client)
    assert client.post(f"/api/exam-blueprints/{blueprint_id}/confirm").status_code == 200
    generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
    assert wait_for_operation(client, generated["operation"]["id"])["status"] == "succeeded"
    draft_id = generated["resource"]["id"]
    draft = client.get(f"/api/exam-drafts/{draft_id}").json()
    for slot in draft["questions"]:
        if slot["status"] == "needs-review":
            retried = client.post(f"/api/exam-drafts/{draft_id}/questions/{slot['id']}/retry").json()
            assert wait_for_operation(client, retried["operation"]["id"])["status"] == "succeeded"
    exam = client.post(f"/api/exam-drafts/{draft_id}/publish", json={}).json()
    return subject_id, model_id, exam


def test_revision_export_observability_and_evaluation_workflow(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        subject_id, model_id, exam = publish_exam(client)
        exam_id = exam["id"]
        original_version_id = exam["current_version_id"]
        original_title = exam["document"]["title"]

        edited_document = copy.deepcopy(exam["document"])
        edited_document["title"] = "人工编辑版"
        edited = client.put(f"/api/exams/{exam_id}", json={
            "base_version_id": original_version_id,
            "document": edited_document,
            "summary": "调整试卷标题",
        })
        assert edited.status_code == 200
        edited_exam = edited.json()
        assert edited_exam["document"]["title"] == "人工编辑版"
        assert edited_exam["can_undo"] is True

        stale = client.put(f"/api/exams/{exam_id}", json={
            "base_version_id": original_version_id,
            "document": edited_document,
        })
        assert stale.status_code == 409
        assert stale.json()["error"]["details"]["current_version_id"] == edited_exam["current_version_id"]

        undone = client.post(f"/api/exams/{exam_id}/undo").json()
        assert undone["document"]["title"] == original_title
        assert undone["can_redo"] is True
        redone = client.post(f"/api/exams/{exam_id}/redo").json()
        assert redone["document"]["title"] == "人工编辑版"
        restored = client.post(f"/api/exams/{exam_id}/versions/{original_version_id}/restore").json()
        assert restored["document"]["title"] == original_title

        proposed = client.post(f"/api/exams/{exam_id}/revision-proposals", json={
            "base_version_id": restored["current_version_id"],
            "instruction": "把标题改成极限复习卷",
            "scope": {"kind": "whole-exam", "question_ids": [], "block_ids": []},
            "model_id": model_id,
        }).json()
        assert wait_for_operation(client, proposed["operation"]["id"])["status"] == "succeeded"
        proposal_id = proposed["resource"]["id"]
        proposal = client.get(f"/api/revision-proposals/{proposal_id}").json()
        assert proposal["status"] == "ready"
        revised = client.post(f"/api/revision-proposals/{proposal_id}/apply").json()
        assert revised["document"]["title"] == "极限复习卷"

        discarded = client.post(f"/api/exams/{exam_id}/revision-proposals", json={
            "base_version_id": revised["current_version_id"],
            "instruction": "预览后放弃",
            "scope": {"kind": "whole-exam", "question_ids": [], "block_ids": []},
            "model_id": model_id,
        }).json()
        assert wait_for_operation(client, discarded["operation"]["id"])["status"] == "succeeded"
        discarded_id = discarded["resource"]["id"]
        assert client.post(f"/api/revision-proposals/{discarded_id}/discard").status_code == 204
        assert client.get(f"/api/revision-proposals/{discarded_id}").json()["status"] == "discarded"
        versions = client.get(f"/api/exams/{exam_id}/versions").json()["items"]
        assert {item["actor"] for item in versions} >= {"user", "ai", "restore", "undo", "redo"}
        assert all("document" not in item for item in versions)

        questions = client.get(f"/api/exams/{exam_id}/render-document", params={"edition": "questions"}).json()
        solutions = client.get(f"/api/exams/{exam_id}/render-document", params={"edition": "solutions"}).json()
        assert [item["question"]["id"] for item in questions["questions"]] == [
            item["question"]["id"] for item in solutions["questions"]
        ]
        assert all(item["solution"] is None for item in questions["questions"])
        assert all(item["solution"] is not None for item in solutions["questions"])

        attempt = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "exam"}).json()
        blocked_export = client.post(f"/api/exams/{exam_id}/exports", json={
            "format": "pdf",
            "edition": "solutions",
            "attempt_id": attempt["id"],
        })
        assert blocked_export.status_code == 409
        assert blocked_export.json()["error"]["code"] == "EXPORT_ANSWER_NOT_ALLOWED"

        markdown_export = client.post(f"/api/exams/{exam_id}/exports", json={
            "format": "markdown",
            "edition": "questions",
        }).json()
        assert wait_for_operation(client, markdown_export["operation"]["id"])["status"] == "succeeded"
        markdown_id = markdown_export["resource"]["id"]
        markdown_meta = client.get(f"/api/exports/{markdown_id}").json()
        assert markdown_meta["status"] == "ready"
        markdown_file = client.get(f"/api/exports/{markdown_id}/file")
        assert markdown_file.status_code == 200
        assert "答案与解析" not in markdown_file.text

        pdf_export = client.post(f"/api/exams/{exam_id}/exports", json={
            "format": "pdf",
            "edition": "solutions",
        }).json()
        assert wait_for_operation(client, pdf_export["operation"]["id"])["status"] == "succeeded"
        pdf_id = pdf_export["resource"]["id"]
        pdf_file = client.get(f"/api/exports/{pdf_id}/file")
        assert pdf_file.status_code == 200
        assert pdf_file.content.startswith(b"%PDF")

        evaluation = client.post("/api/evaluation-suites/core-learning-workflows/runs", json={
            "model_id": model_id,
        }).json()
        assert wait_for_operation(client, evaluation["operation"]["id"])["status"] == "succeeded"
        evaluation_run = client.get(f"/api/evaluation-runs/{evaluation['resource']['id']}").json()
        assert evaluation_run["status"] == "complete"
        assert evaluation_run["orchestration_metrics"]["sample_count"] == 5
        assert evaluation_run["orchestration_metrics"]["duplicate_model_calls"] == 0
        assert evaluation_run["model_observations"]["answer_accuracy"] == 1
        assert evaluation_run["model_observations"]["answer_leakage_rate"] == 0

        runs = client.get("/api/orchestration-runs", params={"subject_id": subject_id}).json()["items"]
        assert {item["category"] for item in runs} >= {"source-parsing", "exam-generation", "exam-revision", "exam-export"}
        serialized_events = json.dumps([item["events"] for item in runs], ensure_ascii=False)
        assert "secret" not in serialized_events
        assert "Limits describe nearby behavior" not in serialized_events
        assert all(item["outer_elapsed_ms"] >= item["model_wait_ms"] for item in runs)

    reopened, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with reopened:
        assert reopened.get(f"/api/exports/{pdf_id}").json()["status"] == "ready"
        assert reopened.get(f"/api/evaluation-runs/{evaluation['resource']['id']}").json()["status"] == "complete"
