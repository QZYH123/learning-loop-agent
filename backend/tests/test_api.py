from backend.tests.conftest import ImmediateFakeModelClient, WaitingFakeModelClient, make_client, wait_for


def workspace(client):
    return client.get("/api/workspace").json()


def create_model(client, **overrides):
    payload = {"provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1", **overrides}
    return client.post("/api/models", json=payload).json()["id"]


def send_message(client, subject_id, content, model_id):
    return client.post(f"/api/subjects/{subject_id}/chat/messages", json={
        "intent": "ask",
        "content": content,
        "model_id": model_id,
    })


def test_subject_lifecycle_api(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        math = client.post("/api/subjects", json={"name": "数学"})
        assert math.status_code == 201
        math_id = math.json()["id"]
        english_id = client.post("/api/subjects", json={"name": "英语"}).json()["id"]

        renamed = client.patch(f"/api/subjects/{english_id}", json={"name": "大学英语"})
        assert renamed.json()["name"] == "大学英语"
        assert client.post(f"/api/subjects/{math_id}/activate").json()["active_subject_id"] == math_id

        assert client.delete(f"/api/subjects/{math_id}").status_code == 204
        assert [item["id"] for item in client.get("/api/subjects").json()["items"]] == [english_id]

        duplicate = client.post("/api/subjects", json={"name": " 大学英语 "})
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "SUBJECT_NAME_DUPLICATE"


def test_workspace_persists_between_app_restarts(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]

    reopened, _ = make_client(tmp_path)
    with reopened:
        state = workspace(reopened)
        assert state["active_subject_id"] == subject_id
        assert [item["name"] for item in state["subjects"]] == ["数学"]


def test_model_verify_and_chat_message_metadata_api(tmp_path):
    fake = ImmediateFakeModelClient()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = create_model(client, provider="FakeAI", api_key="secret")

        verified = client.post(f"/api/models/{model_id}/verify")
        assert verified.status_code == 202
        operation_id = verified.json()["operation"]["id"]
        wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
        assert client.get(f"/api/models/{model_id}").json()["validation"]["status"] == "ok"

        sent = send_message(client, subject_id, "你好", model_id)
        assert sent.status_code == 202
        wait_for(lambda: client.get(f"/api/subjects/{subject_id}/chat").json()["messages"][-1]["status"] == "complete")

        chat = client.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["messages"][0]["content"][0]["text"] == "你好"
        assert chat["messages"][1]["content"][0]["text"] == "这是通用知识模式下的回答。"
        assert chat["messages"][1]["grounding_result"] == "general-knowledge"
        assert chat["messages"][1]["model"]["provider"] == "FakeAI"
        assert len(fake.chat_calls) == 1
        assert "你好" in fake.chat_calls[0]["messages"][0]["content"]


def test_chat_history_and_model_config_restore_after_restart(tmp_path):
    fake = ImmediateFakeModelClient(answer="持久化回答")
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = create_model(client)
        send_message(client, subject_id, "会保存吗？", model_id)
        wait_for(lambda: client.get(f"/api/subjects/{subject_id}/chat").json()["messages"][-1]["status"] == "complete")

    reopened, _ = make_client(tmp_path)
    with reopened:
        assert workspace(reopened)["models"][0]["model"] == "fake-1"
        chat = reopened.get(f"/api/subjects/{subject_id}/chat").json()
        assert chat["messages"][0]["content"][0]["text"] == "会保存吗？"
        assert chat["messages"][1]["content"][0]["text"] == "持久化回答"
        assert chat["messages"][1]["model"]["provider"] == "Fake"


def test_chat_history_is_isolated_between_subjects_and_can_be_cleared(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        math_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        english_id = client.post("/api/subjects", json={"name": "英语"}).json()["id"]
        model_id = create_model(client)
        send_message(client, math_id, "数学问题", model_id)
        send_message(client, english_id, "英语问题", model_id)
        wait_for(lambda: all(
            client.get(f"/api/subjects/{subject_id}/chat").json()["messages"][-1]["status"] == "complete"
            for subject_id in (math_id, english_id)
        ))

        math_chat = client.get(f"/api/subjects/{math_id}/chat").json()
        english_chat = client.get(f"/api/subjects/{english_id}/chat").json()
        assert math_chat["messages"][0]["content"][0]["text"] == "数学问题"
        assert english_chat["messages"][0]["content"][0]["text"] == "英语问题"
        assert client.delete(f"/api/subjects/{math_id}/chat").status_code == 204
        assert client.get(f"/api/subjects/{math_id}/chat").json()["messages"] == []


def test_stop_generation_api_marks_message_stopped(tmp_path):
    fake = WaitingFakeModelClient()
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
        model_id = create_model(client, provider="Slow", model="slow-1")
        sent = send_message(client, subject_id, "长问题", model_id)
        assert sent.status_code == 202
        wait_for(lambda: client.get(f"/api/subjects/{subject_id}/chat").json()["messages"][-1]["status"] == "generating")

        stopped = client.post(f"/api/subjects/{subject_id}/chat/stop")
        assert stopped.status_code == 202
        wait_for(lambda: client.get(f"/api/subjects/{subject_id}/chat").json()["messages"][-1]["status"] == "stopped")
        assert fake.cancelled is True


def test_index_page_is_served(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "AI 学习工具" in response.text
