from __future__ import annotations

from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel
from shared.utils import safe_json_loads

from shared.errors import ConfigurationError
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
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

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
            raise


class OpenAIStructuredLLMClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

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
            response = httpx.post(
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
            )
            response.raise_for_status()
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
