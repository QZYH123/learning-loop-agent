from fastapi.testclient import TestClient

from backend.tests.conftest import make_client
from backend.tests.test_exam_workflow_api import ExamFakeModel, build_exam, publish_ready_exam


SUMMARY_FIELDS = {
    "id",
    "exam_id",
    "exam_version_id",
    "mode",
    "status",
    "completion_status",
    "answered_count",
    "question_count",
    "has_feedback",
    "created_at",
    "updated_at",
}
LEAK_KEYS = {"answers", "paper", "feedback", "unanswered_question_ids", "show_suggested_score"}


def _publish_exam(client):
    _, _, _, blueprint_id = build_exam(client)
    return publish_ready_exam(client, blueprint_id)


def test_list_exam_attempts_sorts_and_exposes_summary_fields(tmp_path):
    fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        exam = _publish_exam(client)
        exam_id = exam["id"]
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        clock = {"now": 1_700_000_000_000}
        app.state.exam_service._now = lambda: clock["now"]

        first = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "practice"}).json()
        clock["now"] += 1000
        second = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "exam"}).json()
        clock["now"] += 1000
        saved = client.put(
            f"/api/attempts/{first['id']}/answers/{choice['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["A"]}},
        )
        assert saved.status_code == 200

        listed = client.get(f"/api/exams/{exam_id}/attempts")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert [item["id"] for item in items] == [first["id"], second["id"]]
        assert all(set(item) == SUMMARY_FIELDS for item in items)
        assert items[0]["mode"] == "practice"
        assert items[0]["answered_count"] == 1
        assert items[0]["question_count"] == len(exam["document"]["questions"])
        assert items[0]["has_feedback"] is True
        assert items[1]["mode"] == "exam"
        assert items[1]["answered_count"] == 0
        assert items[1]["has_feedback"] is False


def test_list_exam_attempts_hides_exam_mode_answers_before_complete(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        exam = _publish_exam(client)
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        attempt = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "exam"}).json()
        saved = client.put(
            f"/api/attempts/{attempt['id']}/answers/{choice['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["A"]}},
        )
        assert saved.status_code == 200

        listed = client.get(f"/api/exams/{exam['id']}/attempts")
        assert listed.status_code == 200
        item = listed.json()["items"][0]
        assert set(item) == SUMMARY_FIELDS
        assert LEAK_KEYS.isdisjoint(item)
        payload = listed.text
        assert "option_ids" not in payload
        assert '"answers"' not in payload
        assert '"paper"' not in payload
        assert '"feedback"' not in payload
        assert item["has_feedback"] is False
        assert item["answered_count"] == 1


def test_list_exam_attempts_visible_to_new_client(tmp_path):
    fake = ExamFakeModel()
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        exam = _publish_exam(client)
        created = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "practice"}).json()
        exam_id = exam["id"]
        attempt_id = created["id"]
        other = TestClient(app)
        same_process = other.get(f"/api/exams/{exam_id}/attempts")
        assert same_process.status_code == 200
        assert any(item["id"] == attempt_id for item in same_process.json()["items"])

    reopened, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with reopened:
        listed = reopened.get(f"/api/exams/{exam_id}/attempts")
        assert listed.status_code == 200
        assert any(item["id"] == attempt_id for item in listed.json()["items"])


def test_delete_exam_cascades_attempts_and_lists_404(tmp_path):
    fake = ExamFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        exam = _publish_exam(client)
        exam_id = exam["id"]
        attempt = client.post(f"/api/exams/{exam_id}/attempts", json={"mode": "practice"}).json()
        versions = client.get(f"/api/exams/{exam_id}/versions").json()["items"]
        assert versions

        deleted = client.delete(f"/api/exams/{exam_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/exams/{exam_id}").status_code == 404
        assert client.get(f"/api/exams/{exam_id}/attempts").status_code == 404
        assert client.get(f"/api/attempts/{attempt['id']}").status_code == 404
        assert client.get(f"/api/exams/{exam_id}/revision-proposals").status_code == 404
        assert client.get(f"/api/exams/{exam_id}/versions").status_code == 404
