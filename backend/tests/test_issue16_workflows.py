from backend.app.model_client import ModelClientError
from backend.tests.conftest import ImmediateFakeModelClient, WaitingFakeModelClient, make_client, wait_for
from backend.tests.support.bootstrap import create_subject_and_source, create_subject_with_current_model
from backend.tests.support.exam import ExamFakeModel, build_exam


class FailingFakeModelClient(ImmediateFakeModelClient):
    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        raise ModelClientError("模型暂时不可用", code="MODEL_CONNECTION_FAILED")


class RetryableGradingModel(ExamFakeModel):
    def __init__(self):
        super().__init__()
        self.fail_grading = False

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        content = messages[-1]["content"]
        if self.fail_grading and isinstance(content, str) and "根据评分点评估答案" in content:
            raise ModelClientError("模型暂时不可用", code="MODEL_CONNECTION_FAILED")
        return await super().chat(profile, messages, max_tokens, tools=tools)


def generation_call(model_client):
    for call in reversed(model_client.chat_calls):
        content = call["messages"][-1]["content"]
        text = content if isinstance(content, str) else ""
        if "起一个不超过12个字" not in text:
            return call
    raise AssertionError("missing generation call")


def test_model_api_format_and_session_chat_style_survive_restart(tmp_path):
    model_client = ImmediateFakeModelClient(answer="直接回答")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model = client.post("/api/models", json={
            "provider": "Looks like Ollama",
            "api_format": "openai-responses",
            "model": "local-model",
            "base_url": "http://localhost/v1",
        }).json()
        assert model["api_format"] == "openai-responses"
        client.put("/api/models/current", json={"model_id": model["id"]})

        session = client.post(f"/api/subjects/{subject_id}/sessions", json={
            "chat_style": "socratic",
        }).json()
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "content": "直接解释这道题",
            "chat_style": "crash-course",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")

        restored = client.get(f"/api/sessions/{session['id']}").json()
        assert restored["chat_style"] == "socratic"
        assert restored["messages"][-1]["chat_style"] == "crash-course"
        assert restored["messages"][-1]["model"]["api_format"] == "openai-responses"

    reopened, _ = make_client(tmp_path, model_client=model_client)
    with reopened:
        assert reopened.get(f"/api/models/{model['id']}").json()["api_format"] == "openai-responses"
        restored = reopened.get(f"/api/sessions/{session['id']}").json()
        assert restored["chat_style"] == "socratic"
        assert restored["messages"][-1]["chat_style"] == "crash-course"


def test_sessions_keep_explicit_source_scope_and_message_snapshot(tmp_path):
    model_client = ImmediateFakeModelClient(answer="依据资料")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
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

        source_id = client.get(f"/api/source-versions/{version_id}").json()["source_id"]
        changed = client.post(
            f"/api/sources/{source_id}/versions",
            files={"file": ("notes.md", b"# Limits\nUpdated content.", "text/markdown")},
        ).json()
        wait_for(lambda: client.get(f"/api/operations/{changed['operation']['id']}").json()["status"] == "succeeded")
        new_version_id = client.get(f"/api/sources/{source_id}").json()["current_version"]["id"]
        assert client.get(f"/api/sessions/{session['id']}").json()["source_version_ids"] == [version_id]

        updated = client.patch(
            f"/api/sessions/{session['id']}/sources/{version_id}",
            json={"source_version_id": new_version_id},
        ).json()
        assert updated["source_version_id"] == new_version_id
        second = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "空白会话"}).json()
        assert second["messages"] == []
        assert second["source_version_ids"] == []
        assert client.post(f"/api/sessions/{session['id']}/activate").json()["active"] is True

    reopened, _ = make_client(tmp_path, model_client=model_client)
    with reopened:
        restored = reopened.get(f"/api/sessions/{session['id']}").json()
        assert restored["source_version_ids"] == [new_version_id]
        assert restored["messages"][-1]["source_context"]["source_version_ids"] == [version_id]
        assert restored["messages"][-1]["model"]["model_id"] == model_id
        assert reopened.get(f"/api/sessions/{second['id']}").json()["messages"] == []
        renamed = reopened.patch(f"/api/sessions/{second['id']}", json={"title": "重命名会话"})
        assert renamed.json()["title"] == "重命名会话"
        assert reopened.delete(f"/api/sessions/{session['id']}/sources/{new_version_id}").status_code == 204
        assert reopened.get(f"/api/sessions/{session['id']}/sources").json()["items"] == []
        added = reopened.post(f"/api/sessions/{session['id']}/sources", json={
            "source_version_id": new_version_id,
        })
        assert added.status_code == 201
        assert reopened.delete(f"/api/sessions/{second['id']}").status_code == 204
        assert reopened.get(f"/api/sessions/{second['id']}").status_code == 404


def test_focused_source_is_retrieved_before_other_session_sources(tmp_path):
    model_client = ImmediateFakeModelClient()
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, first_version_id = create_subject_and_source(client)
        uploaded = client.post(
            f"/api/subjects/{subject_id}/sources",
            files={"file": ("focus.md", b"# Focus\nlimit", "text/markdown")},
        ).json()
        wait_for(lambda: client.get(f"/api/operations/{uploaded['operation']['id']}").json()["status"] == "succeeded")
        sources = client.get(f"/api/subjects/{subject_id}/sources").json()["items"]
        focused_version_id = next(source for source in sources if source["display_name"] == "focus.md")["current_version"]["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={
            "source_version_ids": [first_version_id, focused_version_id],
        }).json()
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "limit",
            "model_id": model_id,
            "source_version_ids": [focused_version_id],
            "focused_source_version_ids": [focused_version_id],
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        prompt = generation_call(model_client)["messages"][-1]["content"]
        assert prompt.index("[Focus]") < prompt.index("[Limits]")


def test_session_message_sends_attachment_and_grounding_rule_to_model(tmp_path):
    model_client = ImmediateFakeModelClient(answer="结合资料回答")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"source_version_ids": [version_id]},
        ).json()
        attachment = client.post(
            f"/api/subjects/{subject_id}/attachments",
            files={"file": ("question.txt", b"attachment evidence", "text/plain")},
        ).json()

        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "请解释",
            "model_id": model_id,
            "grounding_mode": "strict",
            "attachment_ids": [attachment["id"]],
        })
        operation_id = sent.json()["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")

        prompt = generation_call(model_client)["messages"][0]["content"]
        assert "attachment evidence" in prompt
        assert "只能依据" in prompt

        reused = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "再次解释",
            "model_id": model_id,
            "grounding_mode": "strict",
            "attachment_ids": [attachment["id"]],
        })
        assert reused.status_code == 409
        assert reused.json()["error"]["code"] == "RESOURCE_CONFLICT"

        follow_up = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "Limits 是什么？",
            "model_id": model_id,
            "grounding_mode": "general-knowledge",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{follow_up['operation']['id']}").json()["status"] == "succeeded")
        messages = model_client.chat_calls[-1]["messages"]
        assert any(message["role"] == "assistant" and message["content"] == "结合资料回答" for message in messages)
        assert "The limit of x is x." not in messages[-1]["content"]

    reopened, _ = make_client(tmp_path, model_client=model_client)
    with reopened:
        reused = reopened.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "重启后再次解释",
            "model_id": model_id,
            "grounding_mode": "strict",
            "attachment_ids": [attachment["id"]],
        })
        assert reused.status_code == 409
        assert reused.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_running_session_cannot_be_deleted(tmp_path):
    model_client = WaitingFakeModelClient()
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "物理"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "解释惯性",
            "model_id": model_id,
        }).json()
        wait_for(model_client.started.is_set)

        deleted = client.delete(f"/api/sessions/{session['id']}")
        assert deleted.status_code == 409
        assert deleted.json()["error"]["code"] == "OPERATION_IN_PROGRESS"

        client.post(f"/api/operations/{sent['operation']['id']}/cancel")
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "canceled")


def test_attempt_completion_does_not_start_grading_and_can_resume(tmp_path):
    model_client = RetryableGradingModel()
    client, _ = make_client(tmp_path, model_client=model_client)
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
        subjective = next(question for question in attempt["paper"]["questions"] if question["type"] == "short-answer")
        client.put(f"/api/attempts/{attempt['id']}/answers/{subjective['id']}", json={
            "answer": {"kind": "text", "text": "It describes nearby behavior."},
        })
        completed = client.post(f"/api/attempts/{attempt['id']}/complete").json()
        assert completed["completion_status"] == "completed"
        assert completed["grading_status"] == "not-requested"
        assert completed["unanswered_question_ids"]

        model_client.fail_grading = True
        failed_grading = client.post(f"/api/attempts/{attempt['id']}/grade").json()
        wait_for(lambda: client.get(f"/api/operations/{failed_grading['operation']['id']}").json()["status"] == "failed")
        failed = client.get(f"/api/attempts/{attempt['id']}").json()
        assert failed["completion_status"] == "completed"
        assert failed["grading_status"] == "failed"

        model_client.fail_grading = False
        grading = client.post(f"/api/attempts/{attempt['id']}/grade").json()
        wait_for(lambda: client.get(f"/api/operations/{grading['operation']['id']}").json()["status"] == "succeeded")
        graded = client.get(f"/api/attempts/{attempt['id']}").json()
        assert graded["completion_status"] == "completed"
        assert graded["grading_status"] == "completed"

        continued = client.post(f"/api/attempts/{attempt['id']}/continue").json()
        assert continued["completion_status"] == "in-progress"
        choice = next(question for question in continued["paper"]["questions"] if question["type"] == "single-choice")
        client.put(f"/api/attempts/{attempt['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["A"]},
        })
        assert client.get(f"/api/attempts/{attempt['id']}").json()["grading_status"] == "stale"

        exam_attempt = client.post(f"/api/exams/{published.json()['id']}/attempts", json={"mode": "exam"}).json()
        choice = next(question for question in exam_attempt["paper"]["questions"] if question["type"] == "single-choice")
        client.put(f"/api/attempts/{exam_attempt['id']}/answers/{choice['id']}", json={
            "answer": {"kind": "choice", "option_ids": ["A"]},
        })
        grading = client.post(f"/api/attempts/{exam_attempt['id']}/grade").json()
        wait_for(lambda: client.get(f"/api/operations/{grading['operation']['id']}").json()["status"] == "succeeded")
        graded = client.get(f"/api/attempts/{exam_attempt['id']}").json()
        assert graded["completion_status"] == "in-progress"
        assert graded["feedback"] == []
        assert client.get(f"/api/attempts/{exam_attempt['id']}/review").status_code == 409
        client.post(f"/api/attempts/{exam_attempt['id']}/complete")
        assert client.get(f"/api/attempts/{exam_attempt['id']}").json()["feedback"]
        assert client.get(f"/api/attempts/{exam_attempt['id']}/review").status_code == 200

    reopened, _ = make_client(tmp_path, model_client=model_client)
    with reopened:
        restored = reopened.get(f"/api/attempts/{attempt['id']}").json()
        assert restored["completion_status"] == "in-progress"
        assert restored["grading_status"] == "stale"
        assert reopened.get(f"/api/attempts/{exam_attempt['id']}/review").status_code == 200


def test_model_discovery_failure_keeps_manual_fallback(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/models/discover", json={
            "api_format": "ollama",
            "base_url": "http://127.0.0.1:1",
            "manual_model_name": "qwen2.5:7b",
        })
        assert response.status_code == 200
        assert response.json()["manual_model_allowed"] is True
        assert response.json()["models"] == []


def test_model_discovery_does_not_guess_vision_from_model_name(tmp_path, monkeypatch):
    class DiscoveryResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "visionary-text-model"}]}

    monkeypatch.setattr("backend.app.learning.httpx.get", lambda *args, **kwargs: DiscoveryResponse())
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/models/discover", json={
            "api_format": "openai-chat-completions",
            "base_url": "http://localhost/v1",
        })
        assert response.status_code == 200
        assert response.json()["models"][0]["capabilities"] == {"text": True, "vision": False}


def test_ollama_discovery_is_ephemeral_and_does_not_persist_credentials(tmp_path, monkeypatch):
    captured = {}

    class DiscoveryResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "qwen2.5:7b"}]}

    def fake_get(url, headers, timeout, **kwargs):
        captured.update({"url": url, "headers": headers, "timeout": timeout, **kwargs})
        return DiscoveryResponse()

    monkeypatch.setattr("backend.app.learning.httpx.get", fake_get)
    client, _ = make_client(tmp_path)
    with client:
        response = client.post("/api/models/discover", json={
            "api_format": "ollama",
            "base_url": "http://localhost:11434",
            "api_key": "temporary-secret",
        })
        assert response.status_code == 200
        assert response.json()["models"] == [{
            "name": "qwen2.5:7b",
            "capabilities": {"text": True, "vision": False},
        }]
        assert captured["url"] == "http://localhost:11434/api/tags"
        assert captured["headers"]["Authorization"] == "Bearer temporary-secret"
        assert captured["headers"]["X-Api-Key"] == "temporary-secret"
        assert captured["timeout"] == 15.0
        assert client.get("/api/models").json()["items"] == []

    workspace_file = tmp_path / "data" / "workspace.json"
    assert not workspace_file.exists() or "temporary-secret" not in workspace_file.read_text(encoding="utf-8")


def test_current_model_selection_applies_to_existing_chat(tmp_path):
    model_client = ImmediateFakeModelClient()
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        first_model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-a", "base_url": "http://localhost/v1"},
        ).json()["id"]
        second_model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-b", "base_url": "http://localhost/v1"},
        ).json()["id"]
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": first_model_id})
        client.put("/api/models/current", json={"model_id": second_model_id})

        sent = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "2 + 2 等于多少？",
            "grounding_mode": "general-knowledge",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        assert model_client.chat_calls[-1]["profile"]["id"] == second_model_id

        assert client.delete(f"/api/models/{second_model_id}").status_code == 204
        assert client.get("/api/models/current").json() is None


def test_attachment_and_ai_document_lifecycle(tmp_path):
    model_client = ImmediateFakeModelClient(answer="电磁学摘要\n文档内容")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, source_version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
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
            "instruction": "整理 Limits 核心概念",
            "source_version_ids": [source_version_id],
            "grounding_mode": "strict",
            "model_id": model_id,
        }).json()
        operation_id = created["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
        document = client.get(f"/api/documents/{created['resource']['id']}").json()
        assert document["generated_by"] == "ai"
        assert "只能依据" in model_client.chat_calls[-1]["messages"][0]["content"]
        sources = client.get(f"/api/subjects/{subject_id}/sources").json()["items"]
        assert any(source["id"] == document["id"] for source in sources)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        added = client.post(f"/api/sessions/{session['id']}/sources", json={
            "source_version_id": document["current_version_id"],
        })
        assert added.status_code == 201
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "文档内容",
            "model_id": model_id,
            "grounding_mode": "strict",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        citations = client.get(f"/api/sessions/{session['id']}").json()["messages"][-1]["citations"]
        assert {citation["source_id"] for citation in citations} >= {document["id"]}
        assert any(citation["source_version_id"] == source_version_id for citation in citations)
        proposal = client.post(f"/api/documents/{document['id']}/revision-proposals", json={
            "base_version_id": document["current_version_id"],
            "instruction": "补充一个例子",
            "model_id": model_id,
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{proposal['operation']['id']}").json()["status"] == "succeeded")
        proposal_prompt = model_client.chat_calls[-1]["messages"][0]["content"]
        assert "当前文档内容" in proposal_prompt
        assert "文档内容" in proposal_prompt
        assert client.get(f"/api/document-revision-proposals/{proposal['resource']['id']}").json()["status"] == "ready"
        applied = client.post(f"/api/document-revision-proposals/{proposal['resource']['id']}/apply")
        assert len(applied.json()["versions"]) == 2
        source_versions = client.get(f"/api/sources/{document['id']}/versions").json()["items"]
        assert len(source_versions) == 2
        read_only = client.post(
            f"/api/sources/{document['id']}/versions",
            files={"file": ("override.md", b"direct edit", "text/markdown")},
        )
        assert read_only.status_code == 409
        assert read_only.json()["error"]["code"] == "AI_DOCUMENT_READ_ONLY"

        restored = client.post(
            f"/api/documents/{document['id']}/versions/{document['current_version_id']}/restore"
        ).json()
        assert len(restored["versions"]) == 3
        assert restored["versions"][-1]["content"] == document["versions"][0]["content"]
        source_versions = client.get(f"/api/sources/{document['id']}/versions").json()["items"]
        assert len(source_versions) == 3
        anchors = client.get(
            f"/api/source-versions/{restored['current_version_id']}/anchors"
        ).json()["items"]
        assert anchors[0]["location"]["label"].startswith("AI 生成：")

        discarded = client.post(f"/api/documents/{document['id']}/revision-proposals", json={
            "base_version_id": restored["current_version_id"],
            "instruction": "改写标题",
            "model_id": model_id,
        }).json()
        wait_for(lambda: client.get(
            f"/api/operations/{discarded['operation']['id']}"
        ).json()["status"] == "succeeded")
        assert client.post(
            f"/api/document-revision-proposals/{discarded['resource']['id']}/discard"
        ).status_code == 204
        proposal = client.get(
            f"/api/document-revision-proposals/{discarded['resource']['id']}"
        ).json()
        assert proposal["status"] == "discarded"
        assert client.delete(f"/api/documents/{document['id']}").status_code == 204
        assert client.get(f"/api/documents/{document['id']}").status_code == 404
        remaining = client.get(f"/api/subjects/{subject_id}/sources").json()["items"]
        assert all(item["id"] != document["id"] for item in remaining)


def test_failed_ai_document_generation_does_not_leave_ready_document(tmp_path):
    client, _ = make_client(tmp_path, model_client=FailingFakeModelClient())
    with client:
        subject_id = client.post("/api/subjects", json={"name": "化学"}).json()["id"]
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        created = client.post(f"/api/subjects/{subject_id}/documents", json={
            "title": "反应速率",
            "instruction": "整理概念",
            "source_version_ids": [],
            "grounding_mode": "general-knowledge",
            "model_id": model_id,
        }).json()
        operation_id = created["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "failed")

        assert client.get(f"/api/documents/{created['resource']['id']}").status_code == 404
        assert client.get(f"/api/subjects/{subject_id}/documents").json()["items"] == []


def test_context_id_lists_reject_duplicates_and_images_require_vision(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        subject_id, version_id = create_subject_and_source(client)
        model_id = client.post(
            "/api/models",
            json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
        ).json()["id"]
        duplicate_session = client.post(
            f"/api/subjects/{subject_id}/sessions",
            json={"source_version_ids": [version_id, version_id]},
        )
        assert duplicate_session.status_code == 422

        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        image = client.post(
            f"/api/subjects/{subject_id}/attachments",
            files={"file": ("diagram.png", b"png-bytes", "image/png")},
        ).json()
        unsupported = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "解释图片",
            "model_id": model_id,
            "attachment_ids": [image["id"]],
        })
        assert unsupported.status_code == 409
        assert unsupported.json()["error"]["code"] == "IMAGE_INPUT_UNSUPPORTED"

        duplicate_attachments = client.post(f"/api/sessions/{session['id']}/messages", json={
            "intent": "ask",
            "content": "解释图片",
            "model_id": model_id,
            "attachment_ids": [image["id"], image["id"]],
        })
        assert duplicate_attachments.status_code == 422


def test_retry_session_message_after_failure(tmp_path):
    from backend.app.model_client import ObservedModelClient

    failing = FailingFakeModelClient()
    success = ImmediateFakeModelClient(answer="重试成功")
    client, app = make_client(tmp_path, model_client=failing)
    with client:
        subject_id, _ = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()

        failed = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "第一问"}).json()
        wait_for(lambda: client.get(f"/api/operations/{failed['operation']['id']}").json()["status"] == "failed")
        assistant_id = failed["resource"]["id"]
        session_state = client.get(f"/api/sessions/{session['id']}").json()
        assert session_state["messages"][-1]["status"] == "error"

        app.state.learning_service.model_client = ObservedModelClient(success, app.state.observability_service)
        retried = client.post(f"/api/sessions/{session['id']}/messages/{assistant_id}/retry").json()
        wait_for(lambda: client.get(f"/api/operations/{retried['operation']['id']}").json()["status"] == "succeeded")
        restored = client.get(f"/api/sessions/{session['id']}").json()
        assert restored["messages"][-1]["status"] == "complete"
        assert restored["messages"][-1]["content"][0]["text"] == "重试成功"


def test_retry_session_message_rejects_non_failed_message(tmp_path):
    client, _ = make_client(tmp_path, model_client=ImmediateFakeModelClient(answer="完成"))
    with client:
        subject_id, _ = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "你好"}).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        assistant_id = sent["resource"]["id"]

        blocked = client.post(f"/api/sessions/{session['id']}/messages/{assistant_id}/retry")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_retry_session_message_blocks_while_generation_in_progress(tmp_path):
    from backend.app.model_client import ObservedModelClient

    failing = FailingFakeModelClient()
    waiting = WaitingFakeModelClient()
    client, app = make_client(tmp_path, model_client=failing)
    with client:
        subject_id, _ = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()

        failed = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "失败题"}).json()
        wait_for(lambda: client.get(f"/api/operations/{failed['operation']['id']}").json()["status"] == "failed")
        failed_assistant_id = failed["resource"]["id"]

        app.state.learning_service.model_client = ObservedModelClient(waiting, app.state.observability_service)
        in_flight = client.post(f"/api/sessions/{session['id']}/messages", json={"content": "进行中"}).json()
        wait_for(lambda: client.get(f"/api/sessions/{session['id']}").json()["messages"][-1]["status"] == "generating")

        blocked = client.post(f"/api/sessions/{session['id']}/messages/{failed_assistant_id}/retry")
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "OPERATION_IN_PROGRESS"

        waiting.release.set()
        wait_for(lambda: client.get(f"/api/operations/{in_flight['operation']['id']}").json()["status"] == "succeeded")


class SequenceTitleModel(ImmediateFakeModelClient):
    def __init__(self, answer, title):
        super().__init__(answer=answer)
        self.title = title

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.chat_calls.append({"profile": profile, "messages": messages, "max_tokens": max_tokens, "tools": tools})
        text = self.title if max_tokens is not None else self.answer
        return {"text": text, "provider": profile["provider"], "model": profile["model"], "tool_calls": []}


class NamingErrorModel(ImmediateFakeModelClient):
    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        if max_tokens is not None:
            self.chat_calls.append({"profile": profile, "messages": messages, "max_tokens": max_tokens, "tools": tools})
            raise RuntimeError("naming failed")
        return await super().chat(profile, messages, max_tokens, tools=tools)


def test_session_notes_append_and_validate(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        subject_id, _ = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        user_note = client.post(
            f"/api/sessions/{session['id']}/notes",
            json={"role": "user", "content": "/组卷 考考我TCP"},
        )
        assert user_note.status_code == 201
        assert user_note.json()["role"] == "user"
        assert user_note.json()["status"] == "complete"
        assert user_note.json()["content"][0]["text"] == "/组卷 考考我TCP"
        system_note = client.post(
            f"/api/sessions/{session['id']}/notes",
            json={"role": "system", "content": "已生成蓝图「TCP」，请在组卷区确认题型与总分"},
        )
        assert system_note.status_code == 201
        messages = client.get(f"/api/sessions/{session['id']}").json()["messages"]
        assert [item["role"] for item in messages] == ["user", "system"]
        assert messages[1]["status"] == "complete"
        invalid_role = client.post(
            f"/api/sessions/{session['id']}/notes",
            json={"role": "assistant", "content": "不行"},
        )
        assert invalid_role.status_code == 422
        missing = client.post(
            "/api/sessions/session-missing/notes",
            json={"role": "user", "content": "你好"},
        )
        assert missing.status_code == 404


def test_ai_document_title_from_first_line(tmp_path):
    model_client = ImmediateFakeModelClient(answer="计网大纲\n# 第一章 概述\n传输层")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, model_id = create_subject_with_current_model(client)
        created = client.post(f"/api/subjects/{subject_id}/documents", json={
            "instruction": "整理计网",
            "source_version_ids": [],
            "grounding_mode": "general-knowledge",
            "model_id": model_id,
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{created['operation']['id']}").json()["status"] == "succeeded")
        document = client.get(f"/api/documents/{created['resource']['id']}").json()
        assert document["title"] == "计网大纲"
        body = document["versions"][0]["content"][0]["text"]
        assert "计网大纲" not in body
        assert "第一章" in body


def test_ai_document_title_fallback_when_unformatted(tmp_path):
    model_client = ImmediateFakeModelClient(answer="   \n")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, model_id = create_subject_with_current_model(client)
        created = client.post(f"/api/subjects/{subject_id}/documents", json={
            "instruction": "整理笔记",
            "source_version_ids": [],
            "grounding_mode": "general-knowledge",
            "model_id": model_id,
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{created['operation']['id']}").json()["status"] == "succeeded")
        document = client.get(f"/api/documents/{created['resource']['id']}").json()
        assert document["title"] == "学习笔记"


def test_session_auto_title_from_naming_call(tmp_path):
    model_client = SequenceTitleModel(answer="TCP 通过三次握手建立连接。", title="TCP 三次握手")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, model_id = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "content": "请解释 TCP 三次握手",
            "model_id": model_id,
            "grounding_mode": "general-knowledge",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        restored = client.get(f"/api/sessions/{session['id']}").json()
        assert restored["title"] == "TCP 三次握手"
        assert len(model_client.chat_calls) == 2
        assert model_client.chat_calls[1]["max_tokens"] == 24
        assert "起一个不超过12个字" in model_client.chat_calls[1]["messages"][0]["content"]


def test_session_auto_title_keeps_fallback_when_naming_fails(tmp_path):
    model_client = NamingErrorModel(answer="这是兜底回答")
    client, _ = make_client(tmp_path, model_client=model_client)
    with client:
        subject_id, model_id = create_subject_with_current_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        content = "请解释 TCP 三次握手"
        sent = client.post(f"/api/sessions/{session['id']}/messages", json={
            "content": content,
            "model_id": model_id,
            "grounding_mode": "general-knowledge",
        }).json()
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "succeeded")
        restored = client.get(f"/api/sessions/{session['id']}").json()
        assert restored["title"] == content[:60]
        assert restored["messages"][-1]["status"] == "complete"
        assert restored["messages"][-1]["content"][0]["text"] == "这是兜底回答"
