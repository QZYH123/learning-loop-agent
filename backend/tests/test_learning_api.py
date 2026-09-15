import json

from backend.tests.conftest import ImmediateFakeModelClient, make_client
from backend.tests.support.bootstrap import create_subject_and_model
from backend.tests.support.http import upload_source, wait_for_operation


class LearningFakeModel(ImmediateFakeModelClient):
    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.chat_calls.append({"profile": profile, "messages": messages})
        text = messages[-1]["content"]
        if isinstance(text, str) and "章节速成目录" in text:
            return {
                "text": json.dumps({
                    "title": "极限速成",
                    "knowledge_points": [{
                        "title": "极限定义",
                        "explanation": "极限描述函数在某点附近的行为。",
                        "key_points": ["关注附近行为", "不要求点上取值"],
                        "self_test": {"prompt": "极限关注什么？", "answer": "函数在目标点附近的行为。"},
                    }],
                }),
                "provider": profile["provider"],
                "model": profile["model"],
            }
        return {"text": "依据资料回答。", "provider": profile["provider"], "model": profile["model"]}


def configure_socratic_chat(client):
    subject_id, model_id = create_subject_and_model(client)
    uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
    version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
    client.patch(f"/api/subjects/{subject_id}/chat", json={
        "chat_style": "socratic",
        "goal": "学习 Limits",
        "grounding_mode": "strict",
        "source_version_ids": [version_id],
    })
    client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})
    return subject_id


def test_grounded_chat_strict_supplemental_and_citation_lifecycle(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = create_subject_and_model(client)
        model = client.get(f"/api/models/{model_id}").json()
        assert "api_key" not in model
        assert model["has_api_key"] is True

        uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
        parsed = wait_for_operation(client, uploaded.json()["operation"]["id"])
        version_id = parsed["result"]["id"]
        source_id = uploaded.json()["resource"]["id"]

        configured = client.patch(f"/api/subjects/{subject_id}/chat", json={
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        })
        assert configured.status_code == 200
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})

        covered = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "What does a limit describe?",
        })
        operation = wait_for_operation(client, covered.json()["operation"]["id"])
        assert operation["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        answer = chat["messages"][-1]
        assert answer["grounding_result"] == "covered"
        assert len(answer["citations"]) >= 1
        citation_id = answer["citations"][0]["id"]
        assert client.get(f"/api/citations/{citation_id}").json()["available"] is True

        missed = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "How does photosynthesis work?",
        })
        wait_for_operation(client, missed.json()["operation"]["id"])
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["messages"][-1]["grounding_result"] == "not-covered"
        assert len(fake.chat_calls) == 1

        supplemental = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "How does photosynthesis work?",
            "grounding_mode": "supplemental",
        })
        wait_for_operation(client, supplemental.json()["operation"]["id"])
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["messages"][-1]["grounding_result"] == "supplemental"
        assert len(fake.chat_calls) == 2

        assert client.delete(f"/api/sources/{source_id}").status_code == 204
        assert client.get(f"/api/citations/{citation_id}").json()["available"] is False


def test_image_source_requires_vision_capability(tmp_path):
    from backend.tests.support.media import image_bytes

    client, _ = make_client(tmp_path)
    with client:
        subject_id, model_id = create_subject_and_model(client, vision=False)
        uploaded = upload_source(client, subject_id, "diagram.png", image_bytes(), "image/png")
        parsed = wait_for_operation(client, uploaded.json()["operation"]["id"])
        version_id = parsed["result"]["id"]
        client.patch(f"/api/subjects/{subject_id}/chat", json={
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        })
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})

        response = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "ask",
            "content": "解释这张图",
        })
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "IMAGE_INPUT_UNSUPPORTED"


def test_socratic_style_is_prompt_only_and_accepts_freeform_messages(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)
        first = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "content": "我先试试：极限关注点附近的行为。",
        })
        assert wait_for_operation(client, first.json()["operation"]["id"])["status"] == "succeeded"

        follow_up = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "self-test-answer",
            "content": "Please explain the limit directly.",
        })
        assert wait_for_operation(client, follow_up.json()["operation"]["id"])["status"] == "succeeded"

        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["chat_style"] == "socratic"
        assert chat["socratic_state"] is None
        assert chat["messages"][-1]["content"][0]["text"] == "依据资料回答。"
        prompt = fake.chat_calls[-1]["messages"][-1]["content"]
        assert "使用苏格拉底式交流" in prompt
        assert "先让学习者尝试作答" in prompt
        assert "直接讲解" in prompt
        assert '"assessment"' not in prompt


def test_crash_course_message_override_keeps_session_default(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)
        sent = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "content": "Teach me the limit in ten minutes.",
            "chat_style": "crash-course",
        })
        assert wait_for_operation(client, sent.json()["operation"]["id"])["status"] == "succeeded"

        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["chat_style"] == "socratic"
        assert chat["messages"][-1]["chat_style"] == "crash-course"
        assert "使用章节速成风格" in fake.chat_calls[-1]["messages"][-1]["content"]


def test_crash_course_artifact_persists_as_compatibility_endpoint(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = create_subject_and_model(client)
        uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
        version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
        configured = client.patch(f"/api/subjects/{subject_id}/chat", json={
            "chat_style": "socratic",
            "goal": "学习 Limits",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        }).json()
        assert configured["socratic_state"] is None
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})

        generated = client.post(f"/api/subjects/{subject_id}/chat/crash-course", json={
            "goal": "学习 Limits",
            "source_version_ids": [version_id],
            "grounding_mode": "strict",
        })
        operation = wait_for_operation(client, generated.json()["operation"]["id"])
        assert operation["status"] == "succeeded"
        artifact_id = operation["result"]["id"]
        artifact = client.get(f"/api/artifacts/{artifact_id}").json()
        assert artifact["knowledge_points"][0]["self_test"]["prompt"]
        assert artifact_id in client.get(f"/api/subjects/{subject_id}/chat").json()["artifact_ids"]

    reopened, _ = make_client(tmp_path, model_client=fake)
    with reopened:
        assert reopened.get(f"/api/artifacts/{artifact_id}").status_code == 200


def test_unpinned_session_uses_library_sources_for_grounded_chat(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = create_subject_and_model(client)
        uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
        version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={"title": "未钉选"}).json()
        assert session["source_version_ids"] == []
        sent = client.post(
            f"/api/sessions/{session['id']}/messages",
            json={
                "intent": "ask",
                "content": "What does a limit describe?",
                "model_id": model_id,
                "grounding_mode": "supplemental",
            },
        )
        assert sent.status_code == 202
        assert wait_for_operation(client, sent.json()["operation"]["id"])["status"] == "succeeded"
        message = client.get(f"/api/sessions/{session['id']}").json()["messages"][-1]
        assert message["status"] == "complete"
        assert version_id in message["source_context"]["source_version_ids"]
