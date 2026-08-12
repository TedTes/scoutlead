from __future__ import annotations

from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel

from shared.logger import get_logger

TModel = TypeVar("TModel", bound=BaseModel)

logger = get_logger(__name__)


class LLMClient(Protocol):
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
        fallback: TModel,
    ) -> TModel:
        raise NotImplementedError


class HeuristicLLMClient:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
        fallback: TModel,
    ) -> TModel:
        return fallback


class RemoteJsonLLMClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 20.0,
        fallback_on_error: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback_on_error = fallback_on_error

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[TModel],
        context: dict[str, Any] | None = None,
        fallback: TModel,
    ) -> TModel:
        try:
            headers = {"content-type": "application/json"}
            if self.api_key:
                headers["authorization"] = f"Bearer {self.api_key}"
            response = httpx.post(
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
            )
            response.raise_for_status()
            payload = response.json()
            output = payload.get("output", payload) if isinstance(payload, dict) else payload
            return response_model.model_validate(output)
        except Exception as exc:
            logger.warning("remote_llm_failed task=%s error=%s", task, exc)
            if self.fallback_on_error:
                return fallback
            raise
