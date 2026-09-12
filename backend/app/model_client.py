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

    async def chat(
        self,
        profile: dict,
        messages: list[dict],
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        on_delta=None,
    ) -> dict:
        return await self._chat(profile, messages, max_tokens=max_tokens, tools=tools, on_delta=on_delta)

    async def _chat(
        self,
        profile: dict,
        messages: list[dict],
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        on_delta=None,
    ) -> dict:
        stream = on_delta is not None
        api_format, url, payload = self._request(profile, messages, max_tokens=max_tokens, tools=tools, stream=stream)
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:4173",
            "X-Title": "Stilldesk",
        }
        if profile.get("api_key"):
            headers["Authorization"] = f"Bearer {profile['api_key']}"
            headers["X-Api-Key"] = profile["api_key"]

        tools_unsupported = False
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            if stream:
                status, parsed = await self._post_stream(client, url, headers, payload, api_format, on_delta)
                if tools and 400 <= status < 500:
                    retry_payload = {key: value for key, value in payload.items() if key != "tools"}
                    retry_status, retry_parsed = await self._post_stream(
                        client, url, headers, retry_payload, api_format, on_delta
                    )
                    if retry_status < 400:
                        status, parsed = retry_status, retry_parsed
                        tools_unsupported = True
                    else:
                        status = retry_status
                if status >= 400:
                    raise ModelClientError(self._public_http_error(status), code="MODEL_HTTP_ERROR", status=status)
                text = parsed["text"]
                tool_calls = parsed["tool_calls"]
            else:
                response = await self._post(client, url, headers, payload)
                if tools and 400 <= response.status_code < 500:
                    retry_payload = {key: value for key, value in payload.items() if key != "tools"}
                    retry = await self._post(client, url, headers, retry_payload)
                    if retry.status_code < 400:
                        response = retry
                        tools_unsupported = True
                    else:
                        response = retry
                if response.status_code >= 400:
                    raise ModelClientError(
                        self._public_http_error(response.status_code),
                        code="MODEL_HTTP_ERROR",
                        status=response.status_code,
                    )
                text, tool_calls = self._parse_response_body(api_format, response)

        result = {
            "text": text,
            "provider": profile["provider"],
            "api_format": api_format,
            "model": profile["model"],
            "tool_calls": tool_calls,
        }
        if tools_unsupported:
            result["tools_unsupported"] = True
        return result

    def _request(
        self,
        profile: dict,
        messages: list[dict],
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> tuple[str, str, dict]:
        api_format = profile.get("api_format", "openai-chat-completions")
        if api_format == "openai-chat-completions":
            url = self._endpoint(profile["base_url"], "/chat/completions")
            payload = {"model": profile["model"], "messages": self._chat_completions_messages(messages), "stream": stream}
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
        elif api_format == "openai-responses":
            url = self._endpoint(profile["base_url"], "/responses")
            instructions, inputs = self._responses_input(messages)
            payload = {"model": profile["model"], "input": inputs, "store": False}
            if stream:
                payload["stream"] = True
            if instructions:
                payload["instructions"] = instructions
            if max_tokens is not None:
                payload["max_output_tokens"] = max_tokens
        elif api_format == "ollama":
            url = self._ollama_chat_endpoint(profile["base_url"])
            payload = {"model": profile["model"], "messages": self._ollama_messages(messages), "stream": stream}
            if max_tokens is not None:
                payload["options"] = {"num_predict": max_tokens}
        else:
            raise ModelClientError("不支持的模型 API 格式", code="MODEL_API_FORMAT_UNSUPPORTED")
        if tools:
            payload["tools"] = self._map_tools(api_format, tools)
        return api_format, url, payload

    @staticmethod
    async def _post(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> httpx.Response:
        try:
            return await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ModelClientError("无法连接模型服务，请检查 Base URL 和网络设置", code="MODEL_CONNECTION_FAILED") from exc

    def _parse_response_body(self, api_format: str, response: httpx.Response) -> tuple[str, list[dict]]:
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelClientError("模型服务返回了无法解析的响应", code="MODEL_INVALID_RESPONSE", status=response.status_code) from exc
        if not isinstance(body, dict):
            raise ModelClientError("模型服务返回了无效响应", code="MODEL_INVALID_RESPONSE", status=response.status_code)
        if api_format == "openai-chat-completions":
            content = self._chat_completions_text(body)
            tool_calls = self._normalize_tool_calls(self._chat_completions_tool_calls(body))
        elif api_format == "openai-responses":
            content = self._responses_text(body)
            tool_calls = self._normalize_tool_calls(self._responses_tool_calls(body))
        else:
            message = body.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            tool_calls = self._normalize_tool_calls(message.get("tool_calls") if isinstance(message, dict) else None)
        text = content if isinstance(content, str) else ""
        if not text and not tool_calls:
            raise ModelClientError("模型服务响应中缺少文本内容", code="MODEL_INVALID_RESPONSE", status=response.status_code)
        return text, tool_calls

    async def _post_stream(self, client, url, headers, payload, api_format, on_delta) -> tuple[int, dict | None]:
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    await response.aread()
                    return response.status_code, None
                if api_format == "openai-chat-completions":
                    parsed = await self._parse_chat_completions_stream(response, on_delta)
                elif api_format == "openai-responses":
                    parsed = await self._parse_responses_stream(response, on_delta)
                else:
                    parsed = await self._parse_ollama_stream(response, on_delta)
                return response.status_code, parsed
        except asyncio.CancelledError:
            raise
        except httpx.HTTPError as exc:
            raise ModelClientError("无法连接模型服务，请检查 Base URL 和网络设置", code="MODEL_CONNECTION_FAILED") from exc

    @staticmethod
    async def _iter_sse(response):
        event_name = None
        data_lines = []
        async for line in response.aiter_lines():
            raw = line.rstrip("\r")
            if raw.startswith(":"):
                continue
            if not raw:
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                    event_name = None
                    data_lines = []
                continue
            if raw.startswith("event:"):
                event_name = raw[6:].strip()
            elif raw.startswith("data:"):
                data_lines.append(raw[5:].lstrip())
        if data_lines:
            yield event_name, "\n".join(data_lines)

    @staticmethod
    def _load_stream_json(data: str, status: int | None) -> dict:
        try:
            body = json.loads(data)
        except ValueError as exc:
            raise ModelClientError("模型服务返回了无法解析的响应", code="MODEL_INVALID_RESPONSE", status=status) from exc
        if not isinstance(body, dict):
            raise ModelClientError("模型服务返回了无效响应", code="MODEL_INVALID_RESPONSE", status=status)
        return body

    def _finish_stream_result(self, text: str, tool_calls: list[dict], status: int | None) -> dict:
        if not text and not tool_calls:
            raise ModelClientError("模型服务响应中缺少文本内容", code="MODEL_INVALID_RESPONSE", status=status)
        return {"text": text, "tool_calls": tool_calls}

    async def _parse_chat_completions_stream(self, response, on_delta) -> dict:
        text_parts = []
        buffers: dict[int, dict] = {}
        async for _, data in self._iter_sse(response):
            if data.strip() == "[DONE]":
                break
            body = self._load_stream_json(data, response.status_code)
            choices = body.get("choices")
            first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                text_parts.append(content)
                on_delta(content)
            for fragment in delta.get("tool_calls") or []:
                if not isinstance(fragment, dict):
                    continue
                index = fragment.get("index", 0)
                slot = buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if isinstance(fragment.get("id"), str) and fragment["id"]:
                    slot["id"] = fragment["id"]
                function = fragment.get("function") if isinstance(fragment.get("function"), dict) else {}
                if isinstance(function.get("name"), str) and function["name"]:
                    slot["name"] += function["name"]
                if isinstance(function.get("arguments"), str):
                    slot["arguments"] += function["arguments"]
        raw = [
            {"id": slot["id"], "type": "function", "function": {"name": slot["name"], "arguments": slot["arguments"]}}
            for _, slot in sorted(buffers.items())
        ]
        return self._finish_stream_result("".join(text_parts), self._normalize_tool_calls(raw), response.status_code)

    async def _parse_responses_stream(self, response, on_delta) -> dict:
        text_parts = []
        calls: dict[str, dict] = {}
        order: list[str] = []
        current = None
        async for event_name, data in self._iter_sse(response):
            if not data.strip():
                continue
            body = self._load_stream_json(data, response.status_code)
            event_type = str(body.get("type") or event_name or "")
            if event_type.endswith("output_text.delta"):
                delta = body.get("delta")
                if isinstance(delta, str) and delta:
                    text_parts.append(delta)
                    on_delta(delta)
                continue
            if event_type.endswith("output_item.added"):
                item = body.get("item") if isinstance(body.get("item"), dict) else {}
                if item.get("type") == "function_call":
                    key = item.get("id") or item.get("call_id") or f"call_{len(order) + 1}"
                    calls[key] = {
                        "id": item.get("call_id") or item.get("id") or key,
                        "name": item.get("name") or "",
                        "arguments": item.get("arguments") if isinstance(item.get("arguments"), str) else "",
                    }
                    order.append(key)
                    current = key
                continue
            if event_type.endswith("function_call_arguments.delta"):
                delta = body.get("delta")
                key = body.get("item_id") if body.get("item_id") in calls else current
                if key and isinstance(delta, str):
                    calls[key]["arguments"] += delta
                continue
            if event_type.endswith("output_item.done"):
                item = body.get("item") if isinstance(body.get("item"), dict) else {}
                if item.get("type") != "function_call":
                    continue
                key = item.get("id") or item.get("call_id") or current
                if not key:
                    continue
                slot = calls.setdefault(key, {"id": item.get("call_id") or key, "name": "", "arguments": ""})
                if item.get("name"):
                    slot["name"] = item["name"]
                if isinstance(item.get("arguments"), str) and item["arguments"]:
                    slot["arguments"] = item["arguments"]
                if key not in order:
                    order.append(key)
        raw = [{"call_id": calls[key]["id"], "name": calls[key]["name"], "arguments": calls[key]["arguments"]} for key in order]
        return self._finish_stream_result("".join(text_parts), self._normalize_tool_calls(raw), response.status_code)

    async def _parse_ollama_stream(self, response, on_delta) -> dict:
        text_parts = []
        tool_items = []
        async for line in response.aiter_lines():
            raw = line.strip()
            if not raw:
                continue
            body = self._load_stream_json(raw, response.status_code)
            message = body.get("message") if isinstance(body.get("message"), dict) else {}
            content = message.get("content")
            if isinstance(content, str) and content:
                text_parts.append(content)
                on_delta(content)
            for item in message.get("tool_calls") or []:
                if isinstance(item, dict):
                    tool_items.append(item)
        return self._finish_stream_result("".join(text_parts), self._normalize_tool_calls(tool_items), response.status_code)

    @staticmethod
    def _map_tools(api_format: str, tools: list[dict]) -> list[dict]:
        mapped = []
        for item in tools:
            name = item.get("name") or ""
            description = item.get("description") or ""
            parameters = item.get("parameters") or {"type": "object", "properties": {}}
            if api_format == "openai-responses":
                mapped.append({
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                })
            else:
                mapped.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                })
        return mapped

    @staticmethod
    def _chat_completions_text(payload: dict) -> str | None:
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else None

    @staticmethod
    def _chat_completions_tool_calls(payload: dict):
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = first.get("message")
        return message.get("tool_calls") if isinstance(message, dict) else None

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
    def _responses_tool_calls(payload: dict) -> list[dict]:
        output = payload.get("output")
        if not isinstance(output, list):
            return []
        return [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]

    def _normalize_tool_calls(self, items) -> list[dict]:
        if not isinstance(items, list):
            return []
        result = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            function = item.get("function") if isinstance(item.get("function"), dict) else None
            name = (function or {}).get("name") if function else item.get("name")
            raw_arguments = (function or {}).get("arguments") if function else item.get("arguments")
            if not isinstance(name, str) or not name:
                continue
            call_id = item.get("call_id") or item.get("id")
            if not isinstance(call_id, str) or not call_id:
                call_id = f"call_{index + 1}"
            result.append({
                "id": call_id,
                "name": name,
                "arguments": self._tool_arguments(raw_arguments),
            })
        return result

    @staticmethod
    def _tool_arguments(value) -> dict:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            try:
                parsed = json.loads(stripped)
            except ValueError as exc:
                raise ModelClientError("模型服务返回了无法解析的工具参数", code="MODEL_INVALID_RESPONSE") from exc
            if not isinstance(parsed, dict):
                raise ModelClientError("模型服务返回了无效的工具参数", code="MODEL_INVALID_RESPONSE")
            return parsed
        raise ModelClientError("模型服务返回了无效的工具参数", code="MODEL_INVALID_RESPONSE")

    @staticmethod
    def _encode_tool_arguments(value) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False)

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

    def _chat_completions_messages(self, messages: list[dict]) -> list[dict]:
        result = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                content = message.get("content", "")
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                mapped = {"role": "tool", "tool_call_id": message.get("tool_call_id") or "", "content": content}
                if message.get("name"):
                    mapped["name"] = message["name"]
                result.append(mapped)
                continue
            tool_calls = message.get("tool_calls")
            if role == "assistant" and tool_calls:
                content = message.get("content")
                mapped = {
                    "role": "assistant",
                    "content": content if isinstance(content, str) else None,
                    "tool_calls": [
                        {
                            "id": call.get("id") or call.get("call_id") or "",
                            "type": "function",
                            "function": {
                                "name": call.get("name") or (call.get("function") or {}).get("name") or "",
                                "arguments": self._encode_tool_arguments(
                                    call.get("arguments")
                                    if "arguments" in call or not isinstance(call.get("function"), dict)
                                    else call["function"].get("arguments")
                                ),
                            },
                        }
                        for call in tool_calls
                        if isinstance(call, dict)
                    ],
                }
                result.append(mapped)
                continue
            result.append(message)
        return result

    def _responses_input(self, messages: list[dict]) -> tuple[str, list[dict]]:
        instructions = []
        inputs = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in {"system", "developer"}:
                instructions.append(self._instruction_text(content))
                continue
            if role == "tool":
                output = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                inputs.append({
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id") or "",
                    "output": output,
                })
                continue
            tool_calls = message.get("tool_calls")
            if role == "assistant" and tool_calls:
                if isinstance(content, str):
                    if content:
                        inputs.append({"role": "assistant", "content": self._responses_content(content)})
                elif content:
                    inputs.append({"role": "assistant", "content": self._responses_content(content)})
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") if isinstance(call.get("function"), dict) else None
                    name = call.get("name") or (function or {}).get("name") or ""
                    raw_arguments = call.get("arguments") if "arguments" in call or function is None else function.get("arguments")
                    inputs.append({
                        "type": "function_call",
                        "call_id": call.get("call_id") or call.get("id") or "",
                        "name": name,
                        "arguments": self._encode_tool_arguments(raw_arguments),
                    })
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
            role = message.get("role")
            if role == "tool":
                content = message.get("content", "")
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                mapped = {"role": "tool", "content": content}
                if message.get("name"):
                    mapped["tool_name"] = message["name"]
                result.append(mapped)
                continue
            mapped = self._ollama_content_message(message)
            tool_calls = message.get("tool_calls")
            if role == "assistant" and tool_calls:
                mapped["tool_calls"] = []
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") if isinstance(call.get("function"), dict) else None
                    name = call.get("name") or (function or {}).get("name") or ""
                    raw_arguments = call.get("arguments") if "arguments" in call or function is None else function.get("arguments")
                    if isinstance(raw_arguments, str):
                        try:
                            raw_arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
                        except ValueError:
                            raw_arguments = {}
                    if not isinstance(raw_arguments, dict):
                        raw_arguments = {}
                    item = {"function": {"name": name, "arguments": raw_arguments}}
                    call_id = call.get("id") or call.get("call_id")
                    if call_id:
                        item["id"] = call_id
                    mapped["tool_calls"].append(item)
            result.append(mapped)
        return result

    def _ollama_content_message(self, message: dict) -> dict:
        content = message.get("content", "")
        if isinstance(content, str):
            return {"role": message.get("role"), "content": content}
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
        return mapped

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

    async def chat(
        self,
        profile: dict,
        messages: list[dict],
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        on_delta=None,
    ) -> dict:
        kwargs = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools is not None:
            kwargs["tools"] = tools
        if on_delta is not None:
            kwargs["on_delta"] = on_delta
        if kwargs:
            return await self._call("chat", profile, messages, **kwargs)
        return await self._call("chat", profile, messages)

    async def _call(self, method: str, profile: dict, *args, **kwargs) -> dict:
        operation_id = CURRENT_OPERATION_ID.get()
        started_at = self._now()
        started = time.perf_counter()
        status = "succeeded"
        try:
            return await getattr(self.client, method)(profile, *args, **kwargs)
        except BaseException as exc:
            status = "canceled" if isinstance(exc, asyncio.CancelledError) else "failed"
            raise
        finally:
            if operation_id:
                completed_at = self._now()
                elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
                payload = {
                    "method": method,
                    "provider": profile.get("provider"),
                    "api_format": profile.get("api_format", "openai-chat-completions"),
                    "model": profile.get("model"),
                    "input": args,
                }
                if kwargs:
                    payload["kwargs"] = {
                        key: value
                        for key, value in kwargs.items()
                        if key not in {"messages", "on_delta"}
                    }
                fingerprint = hashlib.sha256(json.dumps(
                    payload,
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
