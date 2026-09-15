import io
import re
import zipfile

from backend.app.subject_transfer import export_zip_filename, sanitize_export_stem
from backend.tests.conftest import make_client
from backend.tests.support.exam import ExamFakeModel, build_exam, publish_ready_exam
from backend.tests.support.http import wait_for_operation


def _export_populated_subject(tmp_path):
    fake = ExamFakeModel()
    client, app = make_client(tmp_path / "source", model_client=fake)
    with client:
        subject_id, model_id, version_id, blueprint_id = build_exam(client)
        session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"title": "极限复习", "source_version_ids": [version_id]},
        ).json()
        sent = client.post(
            f"/api/sessions/{session['id']}/messages",
            json={"content": "What does a limit describe?", "model_id": model_id},
        )
        assert sent.status_code == 202
        assert wait_for_operation(client, sent.json()["operation"]["id"])["status"] == "succeeded"
        session = client.get(f"/api/sessions/{session['id']}").json()
        citations = session["messages"][-1].get("citations") or []
        assert citations
        exam = publish_ready_exam(client, blueprint_id)
        choice = next(question for question in exam["document"]["questions"] if question["type"] == "single-choice")
        attempt = client.post(f"/api/exams/{exam['id']}/attempts", json={"mode": "practice"}).json()
        saved = client.put(
            f"/api/attempts/{attempt['id']}/answers/{choice['id']}",
            json={"answer": {"kind": "choice", "option_ids": ["A"]}},
        )
        assert saved.status_code == 200
        exported = client.get(f"/api/subjects/{subject_id}/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/zip")
        disposition = exported.headers["content-disposition"]
        assert "filename*" in disposition
        assert re.search(r"-\d{8}\.zip", disposition)
        return {
            "zip_bytes": exported.content,
            "subject_id": subject_id,
            "version_id": version_id,
            "session_id": session["id"],
            "exam_id": exam["id"],
            "attempt_id": attempt["id"],
            "citation_id": citations[0]["id"],
            "query": "nearby behavior",
        }


def test_export_filename_sanitizes_unsafe_characters():
    assert sanitize_export_stem("数学/期中:复习") == "数学-期中-复习"
    assert export_zip_filename("a/b\\c:d", "20260820") == "a-b-c-d-20260820.zip"


def test_export_then_import_into_empty_workspace_restores_learning_state(tmp_path):
    fixture = _export_populated_subject(tmp_path)
    imported_client, imported_app = make_client(tmp_path / "empty", model_client=ExamFakeModel())
    with imported_client:
        assert imported_client.get("/api/subjects").json()["items"] == []
        response = imported_client.post(
            "/api/subjects/import",
            files={"file": ("math.zip", fixture["zip_bytes"], "application/zip")},
        )
        assert response.status_code == 201
        subject = response.json()
        assert subject["id"] == fixture["subject_id"]
        assert subject["counts"]["sources"] >= 1
        assert subject["counts"]["exams"] >= 1

        hits = imported_app.state.source_library.retrieve(fixture["query"], [fixture["version_id"]])
        assert hits

        session = imported_client.get(f"/api/sessions/{fixture['session_id']}").json()
        assert len(session["messages"]) >= 2
        assert any(item.get("role") == "user" for item in session["messages"])

        exam = imported_client.get(f"/api/exams/{fixture['exam_id']}")
        assert exam.status_code == 200
        assert exam.json()["id"] == fixture["exam_id"]

        attempt = imported_client.get(f"/api/attempts/{fixture['attempt_id']}")
        assert attempt.status_code == 200
        assert attempt.json()["answers"]

        citation = imported_client.get(f"/api/citations/{fixture['citation_id']}")
        assert citation.status_code == 200
        assert citation.json()["available"] is True

        new_attempt = imported_client.post(
            f"/api/exams/{fixture['exam_id']}/attempts",
            json={"mode": "practice"},
        )
        assert new_attempt.status_code == 201

        duplicate = imported_client.post(
            "/api/subjects/import",
            files={"file": ("math.zip", fixture["zip_bytes"], "application/zip")},
        )
        assert duplicate.status_code == 409
        assert "该科目已存在" in duplicate.json()["error"]["message"]
        assert len(imported_client.get("/api/subjects").json()["items"]) == 1


def test_import_rejects_broken_zip_without_partial_state(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        client.post("/api/subjects", json={"name": "已有科目"})
        before = client.get("/api/subjects").json()["items"]

        broken = client.post(
            "/api/subjects/import",
            files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
        )
        assert broken.status_code == 422
        assert broken.json()["error"]["message"]
        assert client.get("/api/subjects").json()["items"] == before

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "no manifest")
        missing = client.post(
            "/api/subjects/import",
            files={"file": ("empty.zip", buffer.getvalue(), "application/zip")},
        )
        assert missing.status_code == 422
        assert "manifest" in missing.json()["error"]["message"]
        assert client.get("/api/subjects").json()["items"] == before


def test_import_renames_when_only_subject_name_conflicts(tmp_path):
    fixture = _export_populated_subject(tmp_path)
    client, _ = make_client(tmp_path / "named", model_client=ExamFakeModel())
    with client:
        existing = client.post("/api/subjects", json={"name": "数学"}).json()
        imported = client.post(
            "/api/subjects/import",
            files={"file": ("math.zip", fixture["zip_bytes"], "application/zip")},
        )
        assert imported.status_code == 201
        assert imported.json()["id"] == fixture["subject_id"]
        assert imported.json()["name"] == "数学（导入）"
        assert existing["id"] != imported.json()["id"]
