from __future__ import annotations

from typing import Any, Protocol

import httpx

from shared.logger import get_logger
from shared.utils import normalize_text


logger = get_logger(__name__)


class EmbeddingClient(Protocol):
    model: str | None
    dimension: int

    def embed_text(self, text: str) -> list[float] | None:
        raise NotImplementedError


class MissingEmbeddingClient:
    def __init__(self, *, model: str | None = None, dimension: int = 1536) -> None:
        self.model = model
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float] | None:
        del text
        return None


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds

    def embed_text(self, text: str) -> list[float] | None:
        normalized = normalize_text(text)
        if not normalized:
            return None

        payload: dict[str, Any] = {
            "model": self.model,
            "input": normalized,
        }
        if self.dimension and self.model.startswith("text-embedding-3"):
            payload["dimensions"] = self.dimension

        try:
            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
                timeout=self.timeout_seconds,
                json=payload,
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            if not data or not isinstance(data[0], dict):
                raise ValueError("OpenAI embedding response did not contain data")
            embedding = data[0].get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("OpenAI embedding response did not contain a vector")
            return [float(value) for value in embedding]
        except Exception as exc:
            logger.warning("openai_embedding_failed model=%s error=%s", self.model, exc)
            return None
