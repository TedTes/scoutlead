from __future__ import annotations

from time import sleep
from typing import Any, Callable, Protocol, TypeVar

import httpx
from pydantic import BaseModel
from shared.utils import safe_json_loads

from shared.errors import ConfigurationError
from shared.logger import get_logger

TModel = TypeVar("TModel", bound=BaseModel)

logger = get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5


class LLMClient(Protocol):
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
    ) -> TModel:
        raise NotImplementedError


class MissingLLMClient:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
    ) -> TModel:
        raise ConfigurationError(
            "real LLM provider is required for this environment",
            {"task": task},
        )


class RemoteJsonLLMClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 20.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = max(0, retry_backoff_seconds)

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
    ) -> TModel:
        try:
            headers = {"content-type": "application/json"}
            if self.api_key:
                headers["authorization"] = f"Bearer {self.api_key}"
            response = _post_with_retry(
                provider="remote",
                task=task,
                max_attempts=self.max_attempts,
                backoff_seconds=self.retry_backoff_seconds,
                request=lambda: httpx.post(
                    self.endpoint,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    json={
                        "task": task,
                        "system": system,
                        "prompt": prompt,
                        "context": context or {},
                        "schema": response_model.model_json_schema(),
                        "model": self.model,
                    },
                ),
            )
            payload = response.json()
            output = payload.get("output", payload) if isinstance(payload, dict) else payload
            return response_model.model_validate(output)
        except Exception as exc:
            logger.warning("remote_llm_failed task=%s error=%s", task, exc)
            raise


class OpenAIStructuredLLMClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.retry_backoff_seconds = max(0, retry_backoff_seconds)

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
    ) -> TModel:
        try:
            schema = response_model.model_json_schema()
            response = _post_with_retry(
                provider="openai",
                task=task,
                max_attempts=self.max_attempts,
                backoff_seconds=self.retry_backoff_seconds,
                request=lambda: httpx.post(
                    "https://api.openai.com/v1/responses",
                    headers={
                        "authorization": f"Bearer {self.api_key}",
                        "content-type": "application/json",
                    },
                    timeout=self.timeout_seconds,
                    json={
                        "model": self.model,
                        "input": [
                            {"role": "system", "content": system},
                            {
                                "role": "user",
                                "content": "\n\n".join(
                                    [
                                        prompt,
                                        f"Task: {task}",
                                        f"Context JSON: {context or {}}",
                                    ]
                                ),
                            },
                        ],
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": response_model.__name__,
                                "schema": schema,
                                "strict": False,
                            }
                        },
                    },
                ),
            )
            payload = response.json()
            output_text = self._extract_output_text(payload)
            parsed = safe_json_loads(output_text)
            if parsed is None:
                raise ValueError("OpenAI response did not contain parseable JSON output")
            return response_model.model_validate(parsed)
        except Exception as exc:
            logger.warning("openai_structured_llm_failed task=%s error=%s", task, exc)
            raise

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]
        for item in payload.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str):
                    return text
        raise ValueError("missing output text")


def _post_with_retry(
    *,
    provider: str,
    task: str,
    max_attempts: int,
    backoff_seconds: float,
    request: Callable[[], httpx.Response],
) -> httpx.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            response = request()
            response.raise_for_status()
            return response
        except Exception as exc:
            if attempt >= max_attempts or not _retryable_request_error(exc):
                raise
            delay = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "%s_llm_retry task=%s attempt=%s max_attempts=%s delay_seconds=%s error=%s",
                provider,
                task,
                attempt,
                max_attempts,
                delay,
                exc,
            )
            if delay:
                sleep(delay)
    raise RuntimeError("LLM retry loop exited unexpectedly")


def _retryable_request_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False
