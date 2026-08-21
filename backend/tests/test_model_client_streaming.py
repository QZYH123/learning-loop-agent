import json

import httpx
import pytest

from backend.app.model_client import ModelApiClient, ModelClientError
from backend.tests.test_model_client import SEARCH_TOOL, _profile, run


def _sse(*items) -> bytes:
    parts = []
    for item in items:
        if item == "[DONE]":
            parts.append("data: [DONE]\n\n")
        elif isinstance(item, tuple):
            event, data = item
            parts.append(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n")
        else:
            parts.append(f"data: {json.dumps(item, ensure_ascii=False)}\n\n")
    return "".join(parts).encode("utf-8")


def _ndjson(*items) -> bytes:
    return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items).encode("utf-8")


def _stream_client(handler):
    return ModelApiClient(transport=httpx.MockTransport(handler))


def test_chat_completions_stream_text():
    captured = {}
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=_sse(
                {"choices": [{"delta": {"content": "你"}}]},
                {"choices": [{"delta": {"content": "好"}}]},
                "[DONE]",
            ),
        )

    result = run(_stream_client(handler).chat(_profile("openai-chat-completions"), [{"role": "user", "content": "hi"}], on_delta=deltas.append))
    assert captured["body"]["stream"] is True
    assert deltas == ["你", "好"]
    assert result["text"] == "你好"
    assert result["tool_calls"] == []


def test_chat_completions_stream_text_and_tool_calls():
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_sse(
                {"choices": [{"delta": {"content": "先"}}]},
                {"choices": [{"delta": {"content": "查"}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "search_sources", "arguments": ""}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"query\":\"TCP\"}"}}]}}]},
                "[DONE]",
            ),
        )

    result = run(_stream_client(handler).chat(_profile("openai-chat-completions"), [{"role": "user", "content": "查"}], tools=[SEARCH_TOOL], on_delta=deltas.append))
    assert deltas == ["先", "查"]
    assert result["text"] == "先查"
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]


def test_chat_completions_stream_interrupt_is_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("cut")

    with pytest.raises(ModelClientError) as exc:
        run(_stream_client(handler).chat(_profile("openai-chat-completions"), [{"role": "user", "content": "hi"}], on_delta=lambda _: None))
    assert exc.value.code == "MODEL_CONNECTION_FAILED"


def test_responses_stream_text():
    captured = {}
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=_sse(
                ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "你"}),
                ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "好"}),
            ),
        )

    result = run(_stream_client(handler).chat(_profile("openai-responses"), [{"role": "user", "content": "hi"}], on_delta=deltas.append))
    assert captured["body"]["stream"] is True
    assert deltas == ["你", "好"]
    assert result["text"] == "你好"


def test_responses_stream_text_and_function_call():
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_sse(
                ("response.output_text.delta", {"type": "response.output_text.delta", "delta": "先"}),
                (
                    "response.output_item.added",
                    {
                        "type": "response.output_item.added",
                        "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "search_sources", "arguments": ""},
                    },
                ),
                (
                    "response.function_call_arguments.delta",
                    {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": "{\"query\":\"TCP\"}"},
                ),
            ),
        )

    result = run(_stream_client(handler).chat(_profile("openai-responses"), [{"role": "user", "content": "查"}], tools=[SEARCH_TOOL], on_delta=deltas.append))
    assert deltas == ["先"]
    assert result["text"] == "先"
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]


def test_responses_stream_invalid_json_is_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"event: response.output_text.delta\ndata: {not-json}\n\n")

    with pytest.raises(ModelClientError) as exc:
        run(_stream_client(handler).chat(_profile("openai-responses"), [{"role": "user", "content": "hi"}], on_delta=lambda _: None))
    assert exc.value.code == "MODEL_INVALID_RESPONSE"


def test_ollama_stream_text():
    captured = {}
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"role": "assistant", "content": "你"}},
                {"message": {"role": "assistant", "content": "好"}, "done": True},
            ),
        )

    result = run(_stream_client(handler).chat(_profile("ollama", base_url="http://localhost:11434"), [{"role": "user", "content": "hi"}], on_delta=deltas.append))
    assert captured["body"]["stream"] is True
    assert deltas == ["你", "好"]
    assert result["text"] == "你好"


def test_ollama_stream_text_and_tool_calls():
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"content": "先"}},
                {"message": {"content": "查"}},
                {"message": {"content": "", "tool_calls": [{"id": "call_1", "function": {"name": "search_sources", "arguments": {"query": "TCP"}}}]}},
                {"done": True},
            ),
        )

    result = run(
        _stream_client(handler).chat(
            _profile("ollama", base_url="http://localhost:11434"),
            [{"role": "user", "content": "查"}],
            tools=[SEARCH_TOOL],
            on_delta=deltas.append,
        )
    )
    assert deltas == ["先", "查"]
    assert result["text"] == "先查"
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]


def test_ollama_stream_interrupt_is_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("cut")

    with pytest.raises(ModelClientError) as exc:
        run(
            _stream_client(handler).chat(
                _profile("ollama", base_url="http://localhost:11434"),
                [{"role": "user", "content": "hi"}],
                on_delta=lambda _: None,
            )
        )
    assert exc.value.code == "MODEL_CONNECTION_FAILED"


def test_stream_tools_4xx_retries_without_tools():
    calls = []
    deltas = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(400, json={"error": {"message": "tools not supported"}})
        return httpx.Response(
            200,
            content=_sse({"choices": [{"delta": {"content": "普通回答"}}]}, "[DONE]"),
        )

    result = run(
        _stream_client(handler).chat(
            _profile("openai-chat-completions"),
            [{"role": "user", "content": "hi"}],
            tools=[SEARCH_TOOL],
            on_delta=deltas.append,
        )
    )
    assert len(calls) == 2
    assert calls[0]["stream"] is True and "tools" in calls[0]
    assert calls[1]["stream"] is True and "tools" not in calls[1]
    assert deltas == ["普通回答"]
    assert result["text"] == "普通回答"
    assert result["tools_unsupported"] is True
