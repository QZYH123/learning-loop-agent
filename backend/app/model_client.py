"""HTTP adapters for the model API formats supported by the app."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from urllib.parse import urlparse

import httpx

from .operations import CURRENT_OPERATION_ID


class ModelClientError(Exception):
    def __init__(self, message: str, code: str = "MODEL_INVALID_RESPONSE", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class ModelApiClient:
    def __init__(self, timeout: float = 120.0, transport=None):
        self.timeout = timeout
        self.transport = transport

    async def validate(self, profile: dict) -> dict:
        return await self._chat(profile, [{"role": "user", "content": "请只回复 ok"}])

    async def chat(self, profile: dict, messages: list[dict], max_tokens: int | None = None) -> dict:
        return await self._chat(profile, messages, max_tokens=max_tokens)

    async def _chat(self, profile: dict, messages: list[dict], max_tokens: int | None = None) -> dict:
        api_format = profile.get("api_format", "openai-chat-completions")
        if api_format == "openai-chat-completions":
            url = self._endpoint(profile["base_url"], "/chat/completions")
            payload = {"model": profile["model"], "messages": messages, "stream": False}
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
        elif api_format == "openai-responses":
            url = self._endpoint(profile["base_url"], "/responses")
            instructions, inputs = self._responses_input(messages)
            payload = {"model": profile["model"], "input": inputs, "store": False}
            if instructions:
                payload["instructions"] = instructions
            if max_tokens is not None:
                payload["max_output_tokens"] = max_tokens
        elif api_format == "ollama":
            url = self._ollama_chat_endpoint(profile["base_url"])
            payload = {"model": profile["model"], "messages": self._ollama_messages(messages), "stream": False}
            if max_tokens is not None:
                payload["options"] = {"num_predict": max_tokens}
        else:
            raise ModelClientError("不支持的模型 API 格式", code="MODEL_API_FORMAT_UNSUPPORTED")

        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:4173",
            "X-Title": "Learning Loop",
        }
        if profile.get("api_key"):
            headers["Authorization"] = f"Bearer {profile['api_key']}"
            headers["X-Api-Key"] = profile["api_key"]

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                raise ModelClientError("无法连接模型服务，请检查 Base URL 和网络设置", code="MODEL_CONNECTION_FAILED") from exc

        if response.status_code >= 400:
            raise ModelClientError(
                self._public_http_error(response.status_code),
                code="MODEL_HTTP_ERROR",
                status=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelClientError("模型服务返回了无法解析的响应", code="MODEL_INVALID_RESPONSE", status=response.status_code) from exc
        if not isinstance(payload, dict):
            raise ModelClientError("模型服务返回了无效响应", code="MODEL_INVALID_RESPONSE", status=response.status_code)

        if api_format == "openai-chat-completions":
            content = self._chat_completions_text(payload)
        elif api_format == "openai-responses":
            content = self._responses_text(payload)
        else:
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content:
            raise ModelClientError("模型服务响应中缺少文本内容", code="MODEL_INVALID_RESPONSE", status=response.status_code)
        return {
            "text": content,
            "provider": profile["provider"],
            "api_format": api_format,
            "model": profile["model"],
        }

    @staticmethod
    def _chat_completions_text(payload: dict) -> str | None:
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else None

    @staticmethod
    def _responses_text(payload: dict) -> str | None:
        chunks: list[str] = []
        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("text"), str) and item.get("type") in {None, "output_text", "text", "message"}:
                    if item.get("type") in {"output_text", "text"}:
                        chunks.append(item["text"])
                for part in item.get("content") or []:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
        joined = "".join(chunks)
        if joined:
            return joined
        output_text = payload.get("output_text")
        return output_text if isinstance(output_text, str) and output_text else None

    @staticmethod
    def _public_http_error(status: int) -> str:
        if status == 401:
            return "模型服务拒绝了请求，请检查 API Key"
        if status == 403:
            return "模型服务暂时不可用"
        if status == 429:
            return "模型服务请求过于频繁，请稍后再试"
        return f"模型服务返回错误（HTTP {status}）"

    @staticmethod
    def _endpoint(base_url: str, suffix: str) -> str:
        base = base_url.rstrip("/")
        return base if base.endswith(suffix) else f"{base}{suffix}"

    @staticmethod
    def _ollama_chat_endpoint(base_url: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/api/chat"):
            return base
        if base.endswith("/api"):
            return f"{base}/chat"
        return f"{base}/api/chat"

    def _responses_input(self, messages: list[dict]) -> tuple[str, list[dict]]:
        instructions = []
        inputs = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in {"system", "developer"}:
                instructions.append(self._instruction_text(content))
                continue
            inputs.append({"role": role, "content": self._responses_content(content)})
        instruction_text = "\n\n".join(item for item in instructions if item)
        return instruction_text or "请遵循输入中的指令并回答用户。", inputs

    def _instruction_text(self, content) -> str:
        if isinstance(content, str):
            return content
        text = []
        for part in content or []:
            if part.get("type") != "text":
                raise ModelClientError("系统指令只支持文本内容", code="MODEL_INPUT_UNSUPPORTED")
            text.append(part.get("text", ""))
        return "\n".join(text)

    def _responses_content(self, content):
        if isinstance(content, str):
            return content
        result = []
        for part in content or []:
            kind = part.get("type")
            if kind == "text":
                result.append({"type": "input_text", "text": part.get("text", "")})
            elif kind == "image_url":
                image = part.get("image_url") or {}
                url = image.get("url") if isinstance(image, dict) else image
                mapped = {"type": "input_image", "image_url": url}
                if isinstance(image, dict) and image.get("detail"):
                    mapped["detail"] = image["detail"]
                result.append(mapped)
            elif kind == "file":
                file = part.get("file") or {}
                mapped = {"type": "input_file"}
                for source, target in (("file_data", "file_data"), ("filename", "filename"), ("file_id", "file_id")):
                    if file.get(source):
                        mapped[target] = file[source]
                result.append(mapped)
            else:
                raise ModelClientError("当前 Responses 输入类型不受支持", code="MODEL_INPUT_UNSUPPORTED")
        return result

    def _ollama_messages(self, messages: list[dict]) -> list[dict]:
        result = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                result.append({"role": message.get("role"), "content": content})
                continue
            text = []
            images = []
            for part in content or []:
                kind = part.get("type")
                if kind == "text":
                    text.append(part.get("text", ""))
                elif kind == "image_url":
                    image = part.get("image_url") or {}
                    url = image.get("url") if isinstance(image, dict) else image
                    images.append(self._data_url_payload(url))
                else:
                    raise ModelClientError("Ollama 原生格式不支持文件输入", code="MODEL_INPUT_UNSUPPORTED")
            mapped = {"role": message.get("role"), "content": "\n".join(text)}
            if images:
                mapped["images"] = images
            result.append(mapped)
        return result

    @staticmethod
    def _data_url_payload(value) -> str:
        if not isinstance(value, str):
            raise ModelClientError("图片输入缺少有效地址", code="MODEL_INPUT_UNSUPPORTED")
        parsed = urlparse(value)
        if parsed.scheme != "data" or ";base64," not in value:
            raise ModelClientError("Ollama 原生格式只支持 base64 图片输入", code="MODEL_INPUT_UNSUPPORTED")
        return value.split(";base64,", 1)[1]


class ObservedModelClient:
    """Measures model waits without exposing prompts, source text, or credentials."""

    def __init__(self, client, observer, now=None):
        self.client = client
        self.observer = observer
        self._now = now or (lambda: int(time.time() * 1000))

    async def validate(self, profile: dict) -> dict:
        return await self._call("validate", profile)

    async def chat(self, profile: dict, messages: list[dict], max_tokens: int | None = None) -> dict:
        if max_tokens is None:
            return await self._call("chat", profile, messages)
        return await self._call("chat", profile, messages, max_tokens)

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
                    {
                        "method": method,
                        "provider": profile.get("provider"),
                        "api_format": profile.get("api_format", "openai-chat-completions"),
                        "model": profile.get("model"),
                        "input": args,
                    },
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
                            "api_format": profile.get("api_format", "openai-chat-completions"),
                            "model": profile.get("model"),
                            "request_fingerprint": fingerprint,
                        },
                    )
                except Exception:
                    pass
