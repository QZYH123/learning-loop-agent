import asyncio

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.store import WorkspaceService, WorkspaceStore


class ImmediateFakeModelClient:
    def __init__(self, answer="这是通用知识模式下的回答。"):
        self.answer = answer
        self.chat_calls = []
        self.validate_calls = []

    async def validate(self, profile):
        self.validate_calls.append(profile)
        return {"text": "ok", "provider": profile["provider"], "model": profile["model"]}

    async def chat(self, profile, messages):
        self.chat_calls.append({"profile": profile, "messages": messages})
        return {"text": self.answer, "provider": profile["provider"], "model": profile["model"]}


class WaitingFakeModelClient:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def validate(self, profile):
        return {"text": "ok", "provider": profile["provider"], "model": profile["model"]}

    async def chat(self, profile, messages):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {"text": "完成", "provider": profile["provider"], "model": profile["model"]}


def make_client(tmp_path, model_client=None):
    app = create_app(data_dir=tmp_path / "data", model_client=model_client or ImmediateFakeModelClient())
    return TestClient(app), app


def wait_for(predicate, timeout=3.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")
