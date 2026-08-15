import asyncio

import httpx
import pytest

from backend.app.model_client import ModelClientError, OpenAiCompatibleModelClient


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

    client = OpenAiCompatibleModelClient(transport=httpx.MockTransport(handler))
    result = run(client.chat(
        {"provider": "Fake", "model": "fake-1", "base_url": "http://localhost/v1", "api_key": "sk-test"},
        [{"role": "user", "content": "你好"}],
    ))
    assert result["text"] == "你好！"
    assert calls[0].headers["Authorization"] == "Bearer sk-test"


def test_client_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = OpenAiCompatibleModelClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.validate({"provider": "Fake", "model": "fake", "base_url": "http://x/v1", "api_key": ""}))
    assert exc.value.code == "MODEL_HTTP_ERROR"
    assert exc.value.status == 401


def test_client_raises_when_response_has_no_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = OpenAiCompatibleModelClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelClientError) as exc:
        run(client.chat({"provider": "Fake", "model": "fake", "base_url": "http://x/v1", "api_key": ""}, [{"role": "user", "content": "x"}]))
    assert exc.value.code == "MODEL_INVALID_RESPONSE"
