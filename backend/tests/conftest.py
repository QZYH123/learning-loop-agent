import asyncio

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.store import WorkspaceService, WorkspaceStore


class ImmediateFakeModelClient:
    def __init__(self, answer="这是通用知识模式下的回答。", *, script=None, reject_tools=False):
        self.answer = answer
        self.chat_calls = []
        self.validate_calls = []
        self.script = list(script or [])
        self.reject_tools = reject_tools
        self._script_index = 0

    async def validate(self, profile):
        self.validate_calls.append(profile)
        return {"text": "ok", "provider": profile["provider"], "model": profile["model"], "tool_calls": []}

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.chat_calls.append({"profile": profile, "messages": messages, "max_tokens": max_tokens, "tools": tools})
        if self.reject_tools and tools:
            if on_delta and self.answer:
                on_delta(self.answer)
            return {
                "text": self.answer,
                "provider": profile["provider"],
                "model": profile["model"],
                "tool_calls": [],
                "tools_unsupported": True,
            }
        if self.script:
            step = self.script[min(self._script_index, len(self.script) - 1)]
            self._script_index += 1
            if callable(step):
                step = step(profile, messages, tools)
            deltas = step.get("deltas") or []
            text = step.get("text", self.answer)
            if deltas:
                if "text" not in step:
                    text = "".join(str(chunk) for chunk in deltas)
                if on_delta:
                    delay = float(step.get("delta_sleep") or 0)
                    for chunk in deltas:
                        on_delta(str(chunk))
                        if delay:
                            await asyncio.sleep(delay)
            elif on_delta and text:
                on_delta(text)
            result = {
                "text": text,
                "provider": profile["provider"],
                "model": profile["model"],
                "tool_calls": list(step.get("tool_calls") or []),
            }
            if step.get("tools_unsupported"):
                result["tools_unsupported"] = True
            return result
        if on_delta and self.answer:
            on_delta(self.answer)
        return {"text": self.answer, "provider": profile["provider"], "model": profile["model"], "tool_calls": []}


class WaitingFakeModelClient:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def validate(self, profile):
        return {"text": "ok", "provider": profile["provider"], "model": profile["model"], "tool_calls": []}

    async def chat(self, profile, messages, max_tokens=None, tools=None, on_delta=None):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return {"text": "完成", "provider": profile["provider"], "model": profile["model"], "tool_calls": []}


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
