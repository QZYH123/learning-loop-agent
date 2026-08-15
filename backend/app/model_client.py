"""OpenAI-compatible /chat/completions model client."""
from __future__ import annotations

import httpx


class ModelClientError(Exception):
    def __init__(self, message: str, code: str = "MODEL_REQUEST_FAILED", status: int | None = None):
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
