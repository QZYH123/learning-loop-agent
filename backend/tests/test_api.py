import time

from backend.tests.conftest import ImmediateFakeModelClient, WaitingFakeModelClient, make_client, wait_for


def workspace(client):
    return client.get("/api/workspace").json()["workspace"]


def test_subject_lifecycle_api(tmp_path):
    client, _ = make_client(tmp_path)

    created = client.post("/api/subjects", json={"name": "数学"}).json()
    assert created["ok"] is True
    math_id = created["workspace"]["active_subject_id"]

    english = client.post("/api/subjects", json={"name": "英语"}).json()["workspace"]
    english_id = next(s["id"] for s in english["subjects"] if s["name"] == "英语")

    renamed = client.patch(f"/api/subjects/{english_id}", json={"name": "大学英语"}).json()
    assert renamed["ok"] is True
    assert client.post(f"/api/subjects/{math_id}/activate").json()["workspace"]["active_subject_id"] == math_id

    deleted = client.delete(f"/api/subjects/{math_id}").json()
    assert deleted["workspace"]["active_subject_id"] == english_id
    assert len(deleted["workspace"]["subjects"]) == 1

    duplicate = client.post("/api/subjects", json={"name": " 大学英语 "})
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "SUBJECT_NAME_DUPLICATE"


def test_workspace_persists_between_app_restarts(tmp_path):
    client, _ = make_client(tmp_path)
    created = client.post("/api/subjects", json={"name": "数学"}).json()["workspace"]
    subject_id = created["active_subject_id"]

    client2, _ = make_client(tmp_path)
    reopened = workspace(client2)
    assert reopened["active_subject_id"] == subject_id
    assert [s["name"] for s in reopened["subjects"]] == ["数学"]


def test_model_verify_and_chat_message_metadata_api(tmp_path):
    fake = ImmediateFakeModelClient()
    client, _ = make_client(tmp_path, model_client=fake)

    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["workspace"]["active_subject_id"]
    model_id = client.post("/api/models", json={
        "provider": "FakeAI",
        "model": "fake-1",
        "base_url": "http://localhost/v1",
        "api_key": "secret",
    }).json()["workspace"]["models"][0]["id"]

    verified = client.post(f"/api/models/{model_id}/verify").json()
    assert verified["workspace"]["models"][0]["last_validation"]["status"] == "ok"

    sent = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
        "content": "你好",
        "model_id": model_id,
    })
    assert sent.status_code == 202
    assert sent.json()["workspace"]["subjects"][0]["data"]["chat"]["messages"][1]["status"] == "generating"

    def completed():
        chat = workspace(client)["subjects"][0]["data"]["chat"]
        return chat["messages"][1]["status"] == "complete"

    wait_for(completed)
    chat = workspace(client)["subjects"][0]["data"]["chat"]
    assert chat["messages"][0]["content"] == "你好"
    assert chat["messages"][1]["content"] == "这是通用知识模式下的回答。"
    assert chat["messages"][1]["mode"] == "general-knowledge"
    assert chat["messages"][1]["model"]["provider"] == "FakeAI"
    assert chat["messages"][1]["model"]["model"] == "fake-1"
    assert len(fake.chat_calls) == 1
    assert fake.chat_calls[0]["messages"] == [{"role": "user", "content": "你好"}]


def test_chat_history_and_model_config_restore_after_restart(tmp_path):
    fake = ImmediateFakeModelClient(answer="持久化回答")
    client, _ = make_client(tmp_path, model_client=fake)
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["workspace"]["active_subject_id"]
    model_id = client.post("/api/models", json={
        "provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1"
    }).json()["workspace"]["models"][0]["id"]
    client.post(f"/api/subjects/{subject_id}/chat/messages", json={"content": "会保存吗？", "model_id": model_id})

    def completed():
        chat = workspace(client)["subjects"][0]["data"]["chat"]
        return chat["messages"][1]["status"] == "complete"

    wait_for(completed)

    client2, _ = make_client(tmp_path)
    restored = workspace(client2)
    assert restored["models"][0]["model"] == "fake-1"
    chat = restored["subjects"][0]["data"]["chat"]
    assert chat["messages"][0]["content"] == "会保存吗？"
    assert chat["messages"][1]["content"] == "持久化回答"
    assert chat["messages"][1]["model"]["provider"] == "Fake"


def test_chat_history_is_isolated_between_subjects_and_can_be_cleared(tmp_path):
    client, _ = make_client(tmp_path)
    math_id = client.post("/api/subjects", json={"name": "数学"}).json()["workspace"]["active_subject_id"]
    english_id = client.post("/api/subjects", json={"name": "英语"}).json()["workspace"]["active_subject_id"]
    model_id = client.post("/api/models", json={
        "provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1"
    }).json()["workspace"]["models"][0]["id"]

    client.post(f"/api/subjects/{math_id}/chat/messages", json={"content": "数学问题", "model_id": model_id})
    client.post(f"/api/subjects/{english_id}/chat/messages", json={"content": "英语问题", "model_id": model_id})

    wait_for(lambda: all(
        m["status"] == "complete"
        for s in workspace(client)["subjects"]
        for m in s["data"]["chat"]["messages"]
        if m["role"] == "assistant"
    ))

    state = workspace(client)
    math_chat = next(s for s in state["subjects"] if s["id"] == math_id)["data"]["chat"]
    english_chat = next(s for s in state["subjects"] if s["id"] == english_id)["data"]["chat"]
    assert math_chat["messages"][0]["content"] == "数学问题"
    assert english_chat["messages"][0]["content"] == "英语问题"

    cleared = client.delete(f"/api/subjects/{math_id}/chat").json()
    assert cleared["ok"] is True
    assert workspace(client)["subjects"][0]["data"]["chat"]["messages"] == []


def test_stop_generation_api_marks_message_stopped(tmp_path):
    fake = WaitingFakeModelClient()
    client, _ = make_client(tmp_path, model_client=fake)
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["workspace"]["active_subject_id"]
    model_id = client.post("/api/models", json={
        "provider": "Slow", "model": "slow-1", "base_url": "http://localhost/v1"
    }).json()["workspace"]["models"][0]["id"]

    sent = client.post(f"/api/subjects/{subject_id}/chat/messages", json={
        "content": "长问题", "model_id": model_id
    })
    assert sent.status_code == 202

    stopped = client.post(f"/api/subjects/{subject_id}/chat/stop").json()
    assert stopped["ok"] is True

    def message_stopped():
        chat = workspace(client)["subjects"][0]["data"]["chat"]
        return chat["messages"][1]["status"] == "stopped"

    wait_for(message_stopped)
    chat = workspace(client)["subjects"][0]["data"]["chat"]
    assert chat["messages"][1]["status"] == "stopped"
    assert fake.cancelled is True


def test_index_page_is_served(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "AI 学习工具" in response.text
