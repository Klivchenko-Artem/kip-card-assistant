import json

import httpx
import pytest

from app.config import Settings
from app.llm import GroqClient, LlmBadOutput, LlmConfigError, LlmUnavailable
from tests.helpers import make_draft

SETTINGS = Settings(api_key="test", model="m", timeout=1, max_rewrites=2)
MESSAGES = [{"role": "user", "content": "x"}]


def ok_response():
    content = make_draft().model_dump_json()
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def client_with(*replies):
    queue = list(replies)
    waits = []

    def handler(request):
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    client = GroqClient(SETTINGS, transport=httpx.MockTransport(handler), sleep=waits.append)
    return client, waits, queue


def test_no_key():
    with pytest.raises(LlmConfigError, match="GROQ_API_KEY"):
        GroqClient(Settings(api_key="", model="m", timeout=1, max_rewrites=0))


def test_success():
    client, _, _ = client_with(ok_response())
    draft, raw = client.complete(MESSAGES)
    assert draft.seo_title
    assert json.loads(raw)["seo_title"] == draft.seo_title


def test_bad_key_is_not_retried():
    client, _, queue = client_with(httpx.Response(401), ok_response())
    with pytest.raises(LlmConfigError, match="ключ"):
        client.complete(MESSAGES)
    assert len(queue) == 1


def test_rate_limit_waits_as_told():
    client, waits, _ = client_with(httpx.Response(429, headers={"retry-after": "7"}), ok_response())
    client.complete(MESSAGES)
    assert waits == [7.0]


def test_server_errors_then_give_up():
    client, waits, _ = client_with(*[httpx.Response(code) for code in (500, 502, 503, 500)])
    with pytest.raises(LlmUnavailable, match="временно"):
        client.complete(MESSAGES)
    assert len(waits) == 3


def test_timeout():
    error = httpx.ReadTimeout("slow")
    client, _, _ = client_with(error, error, error, error)
    with pytest.raises(LlmUnavailable, match="вовремя"):
        client.complete(MESSAGES)


def test_connection_error_then_success():
    client, _, _ = client_with(httpx.ConnectError("no"), ok_response())
    assert client.complete(MESSAGES)[0].seo_title


def test_bad_model_output_is_retried():
    broken = httpx.Response(200, json={"choices": [{"message": {"content": "не json"}}]})
    client, _, _ = client_with(broken, ok_response())
    assert client.complete(MESSAGES)[0].seo_title


def test_bad_model_output_gives_up():
    def broken():
        return httpx.Response(200, json={"choices": []})

    client, _, _ = client_with(broken(), broken(), broken(), broken())
    with pytest.raises(LlmBadOutput):
        client.complete(MESSAGES)


def test_schema_failure_from_api_is_retried():
    failed = httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
    client, _, _ = client_with(failed, ok_response())
    assert client.complete(MESSAGES)[0].seo_title


def test_other_client_error_is_not_retried():
    client, _, queue = client_with(httpx.Response(404), ok_response())
    with pytest.raises(LlmUnavailable, match="404"):
        client.complete(MESSAGES)
    assert len(queue) == 1


def test_too_large_request_is_not_retried():
    client, _, queue = client_with(httpx.Response(413), ok_response())
    with pytest.raises(LlmUnavailable, match="слишком большие"):
        client.complete(MESSAGES)
    assert len(queue) == 1


def test_long_retry_after_is_not_waited():
    client, waits, queue = client_with(httpx.Response(429, headers={"retry-after": "3600"}), ok_response())
    with pytest.raises(LlmUnavailable, match="лимит"):
        client.complete(MESSAGES)
    assert waits == [] and len(queue) == 1


def test_time_is_shared_between_calls():
    client, _, queue = client_with(ok_response())
    client.deadline = 0
    with pytest.raises(LlmUnavailable, match="время"):
        client.complete(MESSAGES)
    assert len(queue) == 1
