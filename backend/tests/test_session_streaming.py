import asyncio

from backend.tests.conftest import ImmediateFakeModelClient, make_client, wait_for


def _assistant_text(session):
    last = session["messages"][-1]
    blocks = last.get("content") or []
    return "".join(block.get("text") or "" for block in blocks if isinstance(block, dict)), last


def _subject_and_model(client):
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
    model_id = client.post(
        "/api/models",
        json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
    ).json()["id"]
    client.put("/api/models/current", json={"model_id": model_id})
    return subject_id, model_id


class HalfStreamFake:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.chat_calls = []
        self.validate_calls = []

    async def validate(self, profile):
        self.validate_calls.append(profile)
        return {"text": "ok", "provider": profile["provider"], "model": profile["model"], "tool_calls": []}

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.chat_calls.append({"profile": profile, "messages": messages, "max_tokens": max_tokens, "tools": tools})
        if on_delta:
            on_delta("已生成")
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            raise
        if on_delta:
            on_delta("完毕")
        return {"text": "已生成完毕", "provider": profile["provider"], "model": profile["model"], "tool_calls": []}


def test_session_message_persists_increasing_stream_prefixes(tmp_path):
    fake = ImmediateFakeModelClient(script=[{"deltas": ["你", "好", "啊"], "delta_sleep": 0.35}])
    client, _ = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        sent = client.post(
            f"/api/sessions/{session['id']}/messages",
            json={"content": "问好", "model_id": model_id, "grounding_mode": "general-knowledge"},
        )
        assert sent.status_code == 202
        prefixes = []

        def progressed():
            current = client.get(f"/api/sessions/{session['id']}").json()
            text, last = _assistant_text(current)
            if last["status"] == "generating" and text and (not prefixes or text != prefixes[-1]):
                prefixes.append(text)
            return last["status"] == "complete"

        wait_for(progressed, timeout=5)
        final, last = _assistant_text(client.get(f"/api/sessions/{session['id']}").json())
        assert last["status"] == "complete"
        assert final == "你好啊"
        assert prefixes
        assert any(prefixes[index] and prefixes[index] in prefixes[index + 1] and prefixes[index] != prefixes[index + 1] for index in range(len(prefixes) - 1))
        assert prefixes[0]


def test_stop_keeps_streamed_prefix_and_retry_works(tmp_path):
    fake = HalfStreamFake()
    client, app = make_client(tmp_path, model_client=fake)
    with client:
        subject_id, model_id = _subject_and_model(client)
        session = client.post(f"/api/subjects/{subject_id}/sessions", json={}).json()
        sent = client.post(
            f"/api/sessions/{session['id']}/messages",
            json={"content": "停一下", "model_id": model_id, "grounding_mode": "general-knowledge"},
        ).json()
        wait_for(fake.started.is_set)
        wait_for(lambda: "已生成" in _assistant_text(client.get(f"/api/sessions/{session['id']}").json())[0])
        client.post(f"/api/operations/{sent['operation']['id']}/cancel")
        wait_for(lambda: client.get(f"/api/operations/{sent['operation']['id']}").json()["status"] == "canceled")
        stopped = client.get(f"/api/sessions/{session['id']}").json()
        text, last = _assistant_text(stopped)
        assert last["status"] == "stopped"
        assert "已生成" in text

        app.state.learning_service.model_client = ImmediateFakeModelClient(answer="重试成功")
        retried = client.post(f"/api/sessions/{session['id']}/messages/{last['id']}/retry", json={"model_id": model_id}).json()
        wait_for(lambda: client.get(f"/api/operations/{retried['operation']['id']}").json()["status"] == "succeeded")
        restored = client.get(f"/api/sessions/{session['id']}").json()
        text, last = _assistant_text(restored)
        assert last["status"] == "complete"
        assert text == "重试成功"
