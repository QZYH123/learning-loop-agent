import asyncio

import httpx
import pytest

from backend.app.model_client import ModelApiClient, ModelClientError


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


def test_client_raises_when_response_has_no_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = ModelApiClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.chat({"provider": "Fake", "model": "fake", "base_url": "http://x/v1", "api_key": ""}, [{"role": "user", "content": "x"}]))
    assert exc.value.code == "MODEL_INVALID_RESPONSE"
