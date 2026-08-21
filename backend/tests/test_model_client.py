import asyncio
import json

import httpx
import pytest

from backend.app.model_client import ModelApiClient, ModelClientError, ObservedModelClient
from backend.tests.conftest import ImmediateFakeModelClient


def run(coro):
    return asyncio.run(coro)


def test_client_posts_chat_completions_and_parses_text():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/v1/chat/completions"
        body = request.read().decode()
        assert '"stream":false' in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "你好！"}}]})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        {
            "provider": "Fake",
            "api_format": "openai-chat-completions",
            "model": "fake-1",
            "base_url": "http://localhost/v1",
            "api_key": "sk-test",
        },
        [{"role": "user", "content": "你好"}],
    ))
    assert result["text"] == "你好！"
    assert calls[0].headers["Authorization"] == "Bearer sk-test"


def test_client_posts_responses_and_ignores_reasoning_output():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        body = request.read().decode()
        assert '"instructions":"只回答问题"' in body
        assert '"input":[{"role":"user","content":"你好"}' in body
        assert '"type":"input_image"' in body
        assert '"type":"input_file"' in body
        assert '"store":false' in body
        return httpx.Response(200, json={
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "你好！"}],
                },
            ],
        })

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        {
            "provider": "OpenAI",
            "api_format": "openai-responses",
            "model": "gpt-test",
            "base_url": "http://localhost/v1",
            "api_key": "sk-test",
        },
        [
            {"role": "system", "content": "只回答问题"},
            {"role": "user", "content": "你好"},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}},
                {"type": "file", "file": {"filename": "notes.pdf", "file_data": "data:application/pdf;base64,cGRm"}},
            ]},
        ],
    ))

    assert result["text"] == "你好！"


def test_client_reads_responses_output_text_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": [], "output_text": "ok"})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        {
            "provider": "OpenAI",
            "api_format": "openai-responses",
            "model": "gpt-test",
            "base_url": "http://localhost/v1",
            "api_key": "sk-test",
        },
        [{"role": "user", "content": "hi"}],
    ))
    assert result["text"] == "ok"


def test_client_posts_ollama_chat_with_base64_images():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = request.read().decode()
        assert '"images":["aW1hZ2U="]' in body
        assert '"stream":false' in body
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "看到了"}})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        {
            "provider": "Local",
            "api_format": "ollama",
            "model": "vision-test",
            "base_url": "http://localhost:11434",
            "api_key": "",
        },
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": "这是什么？"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}},
            ],
        }],
    ))

    assert result["text"] == "看到了"


def test_client_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.validate({"provider": "Fake", "model": "fake", "base_url": "http://x/v1", "api_key": ""}))
    assert exc.value.code == "MODEL_HTTP_ERROR"
    assert exc.value.status == 401
    assert "API Key" in str(exc.value)
    assert "bad key" not in str(exc.value)


def test_client_raises_when_response_has_no_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.chat({"provider": "Fake", "model": "fake", "base_url": "http://x/v1", "api_key": ""}, [{"role": "user", "content": "x"}]))
    assert exc.value.code == "MODEL_INVALID_RESPONSE"


SEARCH_TOOL = {
    "name": "search_sources",
    "description": "检索资料",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

TOOL_MESSAGES = [
    {"role": "user", "content": "查资料"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}],
    },
    {"role": "tool", "tool_call_id": "call_1", "name": "search_sources", "content": "{\"hits\":1}"},
]


def _profile(api_format, **extra):
    return {
        "provider": extra.get("provider", "Fake"),
        "api_format": api_format,
        "model": extra.get("model", "fake-1"),
        "base_url": extra.get("base_url", "http://localhost/v1"),
        "api_key": extra.get("api_key", "sk-test"),
    }


def test_chat_completions_maps_tools_and_normalizes_tool_calls():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search_sources", "arguments": "{\"query\":\"TCP\"}"},
                    }],
                },
            }],
        })

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "查资料"}], tools=[SEARCH_TOOL]))

    assert captured["body"]["tools"] == [{
        "type": "function",
        "function": {
            "name": "search_sources",
            "description": "检索资料",
            "parameters": SEARCH_TOOL["parameters"],
        },
    }]
    assert result["text"] == ""
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]
    assert "tools_unsupported" not in result


def test_responses_maps_tools_and_normalizes_function_calls():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "output": [{
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "search_sources",
                "arguments": "{\"query\":\"TCP\"}",
            }],
        })

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(_profile("openai-responses"), [{"role": "user", "content": "查资料"}], tools=[SEARCH_TOOL]))

    assert captured["body"]["tools"] == [{
        "type": "function",
        "name": "search_sources",
        "description": "检索资料",
        "parameters": SEARCH_TOOL["parameters"],
    }]
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]


def test_ollama_maps_tools_and_normalizes_object_arguments():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "function": {"name": "search_sources", "arguments": {"query": "TCP"}},
                }],
            },
        })

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        _profile("ollama", provider="Local", model="vision-test", base_url="http://localhost:11434", api_key=""),
        [{"role": "user", "content": "查资料"}],
        tools=[SEARCH_TOOL],
    ))

    assert captured["body"]["tools"] == [{
        "type": "function",
        "function": {
            "name": "search_sources",
            "description": "检索资料",
            "parameters": SEARCH_TOOL["parameters"],
        },
    }]
    assert result["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]


def test_chat_completions_sends_assistant_tool_calls_and_tool_results():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "依据资料"}}]})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(_profile("openai-chat-completions"), TOOL_MESSAGES))

    assert captured["body"]["messages"][1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "search_sources", "arguments": "{\"query\": \"TCP\"}"},
        }],
    }
    assert captured["body"]["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "search_sources",
        "content": "{\"hits\":1}",
    }
    assert result["tool_calls"] == []
    assert result["text"] == "依据资料"


def test_responses_sends_function_call_and_output_items():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output_text": "依据资料"})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    run(client.chat(_profile("openai-responses"), TOOL_MESSAGES))

    assert {"type": "function_call", "call_id": "call_1", "name": "search_sources", "arguments": "{\"query\": \"TCP\"}"} in captured["body"]["input"]
    assert {"type": "function_call_output", "call_id": "call_1", "output": "{\"hits\":1}"} in captured["body"]["input"]


def test_ollama_sends_tool_role_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "依据资料"}})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    run(client.chat(
        _profile("ollama", provider="Local", base_url="http://localhost:11434", api_key=""),
        TOOL_MESSAGES,
    ))

    assert captured["body"]["messages"][1]["tool_calls"] == [{
        "id": "call_1",
        "function": {"name": "search_sources", "arguments": {"query": "TCP"}},
    }]
    assert captured["body"]["messages"][2] == {
        "role": "tool",
        "content": "{\"hits\":1}",
        "tool_name": "search_sources",
    }


def test_tools_rejected_with_4xx_retries_without_tools_and_marks_unsupported():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(400, json={"error": {"message": "tools not supported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "普通回答"}}]})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "你好"}], tools=[SEARCH_TOOL]))

    assert len(calls) == 2
    assert "tools" in calls[0]
    assert "tools" not in calls[1]
    assert result["text"] == "普通回答"
    assert result["tool_calls"] == []
    assert result["tools_unsupported"] is True


def test_tools_5xx_does_not_retry_without_tools():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(503, json={"error": {"message": "busy"}})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "你好"}], tools=[SEARCH_TOOL]))
    assert exc.value.code == "MODEL_HTTP_ERROR"
    assert exc.value.status == 503
    assert len(calls) == 1
    assert "tools" in calls[0]


def test_invalid_tool_arguments_json_raises_without_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {"name": "search_sources", "arguments": "{not-json"},
                    }],
                },
            }],
        })

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "x"}], tools=[SEARCH_TOOL]))
    assert exc.value.code == "MODEL_INVALID_RESPONSE"
    assert "工具参数" in str(exc.value)


def test_fake_model_script_returns_tool_calls_and_accepts_tool_results():
    fake = ImmediateFakeModelClient(script=[
        {"text": "", "tool_calls": [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]},
        {"text": "依据资料"},
    ])
    first = run(fake.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "查资料"}], tools=[SEARCH_TOOL]))
    second = run(fake.chat(_profile("openai-chat-completions"), TOOL_MESSAGES, tools=[SEARCH_TOOL]))

    assert first["tool_calls"] == [{"id": "call_1", "name": "search_sources", "arguments": {"query": "TCP"}}]
    assert first["text"] == ""
    assert second["text"] == "依据资料"
    assert second["tool_calls"] == []
    assert fake.chat_calls[1]["messages"][2]["role"] == "tool"


def test_fake_model_rejects_tools_and_marks_unsupported():
    fake = ImmediateFakeModelClient(answer="普通回答", reject_tools=True)
    result = run(fake.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "你好"}], tools=[SEARCH_TOOL]))
    assert result["text"] == "普通回答"
    assert result["tool_calls"] == []
    assert result["tools_unsupported"] is True


def test_observed_client_forwards_tools_without_changing_plain_calls():
    inner = ImmediateFakeModelClient(answer="ok")
    observed = ObservedModelClient(inner, observer=type("Obs", (), {"stage_recorded": staticmethod(lambda *a, **k: None)})())
    run(observed.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "hi"}]))
    run(observed.chat(_profile("openai-chat-completions"), [{"role": "user", "content": "hi"}], tools=[SEARCH_TOOL]))
    assert inner.chat_calls[0]["tools"] is None
    assert inner.chat_calls[1]["tools"] == [SEARCH_TOOL]
