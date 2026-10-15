import httpx
import pytest
from pydantic import BaseModel

from agents.llm import OpenAIStructuredLLMClient
from shared.errors import ConfigurationError


class Result(BaseModel):
    value: str


def test_openai_client_exposes_provider_validation_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(
            400,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            headers={"x-request-id": "req_test"},
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": "model is not available",
                }
            },
        )

    monkeypatch.setattr("agents.llm.httpx.post", fake_post)
    client = OpenAIStructuredLLMClient(api_key="test", model="unavailable-model")

    with pytest.raises(ConfigurationError) as exc_info:
        client.generate_object(
            task="test",
            system="Return data.",
            prompt="Test",
            response_model=Result,
        )

    assert exc_info.value.details == {
        "status_code": 400,
        "request_id": "req_test",
        "provider_error_type": "invalid_request_error",
        "provider_message": "model is not available",
        "provider": "openai",
        "model": "unavailable-model",
        "user_message": (
            "Generation is temporarily unavailable. "
            "Check the OpenAI model and billing configuration."
        ),
    }


def test_openai_client_retries_transient_timeout(monkeypatch) -> None:
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"value":"ok"}'},
        )

    monkeypatch.setattr("agents.llm.httpx.post", fake_post)
    client = OpenAIStructuredLLMClient(
        api_key="test",
        model="test-model",
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    result = client.generate_object(
        task="test",
        system="Return JSON.",
        prompt="Test",
        response_model=Result,
    )

    assert result.value == "ok"
    assert calls == 3


def test_openai_client_does_not_retry_validation_failure(monkeypatch) -> None:
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"wrong":"shape"}'},
        )

    monkeypatch.setattr("agents.llm.httpx.post", fake_post)
    client = OpenAIStructuredLLMClient(
        api_key="test",
        model="test-model",
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    try:
        client.generate_object(
            task="test",
            system="Return JSON.",
            prompt="Test",
            response_model=Result,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected response validation to fail")

    assert calls == 1


def test_openai_client_does_not_retry_exhausted_quota(monkeypatch) -> None:
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"error": {"code": "insufficient_quota", "type": "insufficient_quota"}},
        )

    monkeypatch.setattr("agents.llm.httpx.post", fake_post)
    client = OpenAIStructuredLLMClient(
        api_key="test",
        model="test-model",
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    try:
        client.generate_object(
            task="test",
            system="Return JSON.",
            prompt="Test",
            response_model=Result,
        )
    except ConfigurationError:
        pass
    else:
        raise AssertionError("expected quota error")

    assert calls == 1


def test_openai_client_respects_rate_limit_retry_after(monkeypatch) -> None:
    calls = 0
    delays: list[float] = []

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                headers={"retry-after": "12"},
                json={"error": {"code": "rate_limit_exceeded"}},
            )
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"output_text": '{"value":"ok"}'},
        )

    monkeypatch.setattr("agents.llm.httpx.post", fake_post)
    monkeypatch.setattr("agents.llm.sleep", delays.append)
    client = OpenAIStructuredLLMClient(
        api_key="test",
        model="test-model",
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    result = client.generate_object(
        task="test",
        system="Return JSON.",
        prompt="Test",
        response_model=Result,
    )

    assert result.value == "ok"
    assert calls == 2
    assert delays == [12.0]
