"""OpenAI-compatible /chat/completions model client."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

import httpx

from .operations import CURRENT_OPERATION_ID


class ModelClientError(Exception):
    def __init__(self, message: str, code: str = "MODEL_INVALID_RESPONSE", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class OpenAiCompatibleModelClient:
    def __init__(self, timeout: float = 120.0, transport=None):
        self.timeout = timeout
        self.transport = transport

    async def validate(self, profile: dict) -> dict:
        return await self._chat(profile, [{"role": "user", "content": "请只回复 ok"}], max_tokens=4)

    async def chat(self, profile: dict, messages: list[dict]) -> dict:
        return await self._chat(profile, messages)

    async def _chat(self, profile: dict, messages: list[dict], max_tokens: int | None = None) -> dict:
        url = f"{profile['base_url']}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if profile.get("api_key"):
            headers["Authorization"] = f"Bearer {profile['api_key']}"
        payload = {"model": profile["model"], "messages": messages, "stream": False}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise ModelClientError("无法连接模型服务，请检查 Base URL 和网络设置", code="MODEL_CONNECTION_FAILED") from exc

        if response.status_code >= 400:
            detail = (response.text or "").strip().replace("\n", " ")
            if len(detail) > 300:
                detail = detail[:300] + "…"
            raise ModelClientError(
                f"模型服务返回错误（HTTP {response.status_code}）：{detail or '未提供错误详情'}",
                code="MODEL_HTTP_ERROR",
                status=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelClientError("模型服务返回了无法解析的响应", code="MODEL_INVALID_RESPONSE", status=response.status_code) from exc

        content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        if not isinstance(content, str):
            raise ModelClientError("模型服务响应中缺少文本内容", code="MODEL_INVALID_RESPONSE", status=response.status_code)
        return {"text": content, "provider": profile["provider"], "model": profile["model"]}


class ObservedModelClient:
    """Measures model waits without exposing prompts, source text, or credentials."""

    def __init__(self, client, observer, now=None):
        self.client = client
        self.observer = observer
        self._now = now or (lambda: int(time.time() * 1000))

    async def validate(self, profile: dict) -> dict:
        return await self._call("validate", profile)

    async def chat(self, profile: dict, messages: list[dict]) -> dict:
        return await self._call("chat", profile, messages)

    async def _call(self, method: str, profile: dict, *args) -> dict:
        operation_id = CURRENT_OPERATION_ID.get()
        started_at = self._now()
        started = time.perf_counter()
        status = "succeeded"
        try:
            return await getattr(self.client, method)(profile, *args)
        except BaseException as exc:
            status = "canceled" if isinstance(exc, asyncio.CancelledError) else "failed"
            raise
        finally:
            if operation_id:
                completed_at = self._now()
                elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
                fingerprint = hashlib.sha256(json.dumps(
                    {"method": method, "provider": profile.get("provider"), "model": profile.get("model"), "input": args},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")).hexdigest()
                try:
                    self.observer.stage_recorded(
                        operation_id,
                        name="model-call",
                        status=status,
                        started_at=started_at,
                        completed_at=completed_at,
                        outer_elapsed_ms=elapsed_ms,
                        model_wait_ms=elapsed_ms,
                        counters={"model_calls": 1},
                        attributes={
                            "provider": profile.get("provider"),
                            "model": profile.get("model"),
                            "request_fingerprint": fingerprint,
                        },
                    )
                except Exception:
                    pass
