from backend.tests.conftest import ImmediateFakeModelClient, make_client, wait_for
from backend.tests.test_exam_workflow_api import ExamFakeModel, build_exam


def create_subject_and_source(client):
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
    response = client.post(
        f"/api/subjects/{subject_id}/sources",
        files={"file": ("notes.md", b"# Limits\nThe limit of x is x.", "text/markdown")},
    )
    operation_id = response.json()["operation"]["id"]
    wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
    source = client.get(f"/api/subjects/{subject_id}/sources").json()["items"][0]
    return subject_id, source["current_version"]["id"]


def test_sessions_keep_explicit_source_scope_and_message_snapshot(tmp_path):
    client, _ = make_client(tmp_path, model_client=ImmediateFakeModelClient(answer="依据资料"))
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"title": "极限复习", "source_version_ids": [version_id]},
        ).json()
        assert session["source_version_ids"] == [version_id]
        assert client.get(f"/api/source-versions/{version_id}/anchors").status_code == 200

        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "什么是极限？",
            "model_id": model_id,
            "focused_source_version_ids": [version_id],
            "only_use_specified_sources": True,
        })
        assert sent.status_code == 202
        operation_id = sent.json()["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
        current = client.get(f"/api/sessions/{session['id']}").json()
        assert current["messages"][-1]["source_context"]["only_use_specified_sources"] is True
        assert current["messages"][-1]["source_context"]["source_version_ids"] == [version_id]


def test_attempt_completion_does_not_start_grading_and_can_resume(tmp_path):
    client, _ = make_client(tmp_path, model_client=ExamFakeModel())
    with client:
        subject_id, _, _, blueprint_id = build_exam(client)
        client.patch(f"/api/exam-blueprints/{blueprint_id}", json={"total_score": 20})
        client.post(f"/api/exam-blueprints/{blueprint_id}/confirm")
        generated = client.post(f"/api/exam-blueprints/{blueprint_id}/generate").json()
        wait_for(lambda: client.get(f"/api/operations/{generated['operation']['id']}").json()["status"] == "succeeded")
        draft = client.get(f"/api/subjects/{subject_id}/exam-drafts").json()["items"][0]
        failed_question = next(item for item in draft["questions"] if item["status"] == "needs-review")
        retried = client.post(f"/api/exam-drafts/{draft['id']}/questions/{failed_question['id']}/retry").json()
        wait_for(lambda: client.get(f"/api/operations/{retried['operation']['id']}").json()["status"] == "succeeded")
        published = client.post(f"/api/exam-drafts/{draft['id']}/publish", json={})
        attempt = client.post(f"/api/exams/{published.json()['id']}/attempts", json={"mode": "practice"}).json()
        completed = client.post(f"/api/attempts/{attempt['id']}/complete").json()
        assert completed["completion_status"] == "completed"
        assert completed["grading_status"] == "not-requested"
        assert client.post(f"/api/attempts/{attempt['id']}/continue").json()["completion_status"] == "in-progress"


def test_model_discovery_failure_keeps_manual_fallback(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/models/discover", json={
            "provider": "ollama",
            "base_url": "http://127.0.0.1:1",
            "manual_model_name": "qwen2.5:7b",
        })
        assert response.status_code == 200
        assert response.json()["manual_model_allowed"] is True
        assert response.json()["models"] == []


def test_attachment_and_ai_document_lifecycle(tmp_path):
    client, _ = make_client(tmp_path, model_client=ImmediateFakeModelClient(answer="文档内容"))
    with client:
        subject_id = client.post("/api/subjects", json={"name": "物理"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        attachment = client.post(
            f"/api/subjects/{subject_id}/attachments",
            files={"file": ("figure.png", b"png-bytes", "image/png")},
        )
        assert attachment.status_code == 201
        attachment_id = attachment.json()["id"]
        assert client.get(f"/api/attachments/{attachment_id}/file").content == b"png-bytes"
        assert client.delete(f"/api/attachments/{attachment_id}").status_code == 204

        created = client.post(f"/api/subjects/{subject_id}/documents", json={
            "title": "电磁学摘要",
            "instruction": "整理核心概念",
            "source_version_ids": [],
            "grounding_mode": "general-knowledge",
            "model_id": model_id,
        }).json()
        operation_id = created["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
        document = client.get(f"/api/documents/{created['resource']['id']}").json()
        assert document["generated_by"] == "ai"
        proposal = client.post(f"/api/documents/{document['id']}/revision-proposals", json={
            "base_version_id": document["current_version_id"],
            "instruction": "补充一个例子",
            "model_id": model_id,
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{proposal['operation']['id']}").json()["status"] == "succeeded")
        assert client.get(f"/api/document-revision-proposals/{proposal['resource']['id']}").json()["status"] == "ready"
        applied = client.post(f"/api/document-revision-proposals/{proposal['resource']['id']}/apply")
        assert len(applied.json()["versions"]) == 2
