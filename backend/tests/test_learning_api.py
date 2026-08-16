import json

from backend.tests.conftest import ImmediateFakeModelClient, make_client
from backend.tests.test_sources_api import upload_source, wait_for_operation


class LearningFakeModel(ImmediateFakeModelClient):
    async def chat(self, profile, messages):
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


class SocraticAssessmentFake(LearningFakeModel):
    def __init__(self, assessment, response):
        super().__init__()
        self.assessment = assessment
        self.response = response

    async def chat(self, profile, messages):
        self.chat_calls.append({"profile": profile, "messages": messages})
        prompt = messages[-1]["content"]
        if isinstance(prompt, str) and '"assessment"' in prompt and '"response"' in prompt:
            text = json.dumps({"assessment": self.assessment, "response": self.response})
        else:
            text = self.response
        return {"text": text, "provider": profile["provider"], "model": profile["model"]}


def create_subject_and_model(client, *, vision=False):
    subject = client.post("/api/subjects", json={"name": "数学"}).json()
    model = client.post("/api/models", json={
        "provider": "Fake",
        "model": "fake-1",
        "base_url": "http://localhost/v1",
        "api_key": "secret",
        "capabilities": {"text": True, "vision": vision},
    }).json()
    return subject["id"], model["id"]


def configure_socratic_chat(client):
    subject_id, model_id = create_subject_and_model(client)
    uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
    version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
    client.patch(f"/api/subjects/{subject_id}/chat", json={
        "learning_mode": "socratic",
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
    from backend.tests.test_rich_sources_api import image_bytes

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


def test_socratic_correct_attempt_moves_to_self_test(tmp_path):
    fake = SocraticAssessmentFake("correct", "回答正确。请说明 x 趋近于 0 时 2x 的极限。")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)

        response = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "attempt",
            "content": "A limit describes nearby behavior.",
        })
        operation = wait_for_operation(client, response.json()["operation"]["id"])

        assert operation["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["socratic_state"]["stage"] == "self-testing"
        assert chat["messages"][-1]["content"][0]["text"] == "回答正确。请说明 x 趋近于 0 时 2x 的极限。"


def test_socratic_missing_prerequisite_returns_to_attempt(tmp_path):
    fake = SocraticAssessmentFake(
        "missing-prerequisite",
        "先回顾函数在一点附近取值的含义，再尝试说明极限关注什么。",
    )
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)

        response = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "attempt",
            "content": "A limit describes nearby behavior, but I do not understand a function.",
        })
        operation = wait_for_operation(client, response.json()["operation"]["id"])

        assert operation["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["socratic_state"] == {
            "stage": "awaiting-attempt",
            "hint_level": 0,
            "answer_revealed": False,
        }
        assert chat["messages"][-1]["content"][0]["text"].startswith("先回顾函数")


def test_socratic_incorrect_self_test_does_not_complete(tmp_path):
    fake = SocraticAssessmentFake("misunderstanding", "还需要区分函数值与附近行为，请修正后再试。")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)
        explanation = client.post(
            f"/api/subjects/{subject_id}/chat/messages",
            json={"intent": "request-explanation"},
        )
        wait_for_operation(client, explanation.json()["operation"]["id"])
        self_test = client.post(
            f"/api/subjects/{subject_id}/chat/messages",
            json={"intent": "request-self-test"},
        )
        wait_for_operation(client, self_test.json()["operation"]["id"])

        response = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "self-test-answer",
            "content": "A limit is the function value at the point.",
        })
        operation = wait_for_operation(client, response.json()["operation"]["id"])

        assert operation["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["socratic_state"]["stage"] == "self-testing"
        assert chat["messages"][-1]["content"][0]["text"].startswith("还需要区分")


def test_socratic_misunderstood_restate_requires_another_restate(tmp_path):
    fake = SocraticAssessmentFake("misunderstanding", "复述仍混淆了点上取值与附近行为，请重新组织。")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = configure_socratic_chat(client)
        attempt = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "attempt",
            "content": "A limit is the function value at the point.",
        })
        wait_for_operation(client, attempt.json()["operation"]["id"])

        restate = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
            "intent": "restate",
            "content": "A limit is only the value at that point.",
        })
        operation = wait_for_operation(client, restate.json()["operation"]["id"])

        assert operation["status"] == "succeeded"
        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["socratic_state"]["stage"] == "correcting"
        assert chat["messages"][-1]["content"][0]["text"].startswith("复述仍混淆")


def test_socratic_state_and_crash_course_artifact_persist(tmp_path):
    fake = LearningFakeModel()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = create_subject_and_model(client)
        uploaded = upload_source(client, subject_id, "limits.md", b"# Limits\n\nA limit describes nearby behavior.")
        version_id = wait_for_operation(client, uploaded.json()["operation"]["id"])["result"]["id"]
        configured = client.patch(f"/api/subjects/{subject_id}/chat", json={
            "learning_mode": "socratic",
            "goal": "学习 Limits",
            "grounding_mode": "strict",
            "source_version_ids": [version_id],
        }).json()
        assert configured["socratic_state"]["stage"] == "awaiting-attempt"
        client.post(f"/api/subjects/{subject_id}/chat/model", json={"model_id": model_id})

        hint = client.post(f"/api/subjects/{subject_id}/chat/messages", json={"intent": "request-hint"})
        wait_for_operation(client, hint.json()["operation"]["id"])
        state = client.get(f"/api/subjects/{subject_id}/chat").json()["socratic_state"]
        assert state == {"stage": "hinting", "hint_level": 1, "answer_revealed": False}

        explanation = client.post(
            f"/api/subjects/{subject_id}/chat/messages",
            json={"intent": "request-explanation"},
        )
        wait_for_operation(client, explanation.json()["operation"]["id"])
        state = client.get(f"/api/subjects/{subject_id}/chat").json()["socratic_state"]
        assert state["stage"] == "awaiting-restate"
        assert state["answer_revealed"] is True

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
