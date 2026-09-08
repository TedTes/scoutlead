from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from canonical.semantics import business_semantic_profile
from db.models import BusinessModel, SourceObservationModel
from shared.utils import normalize_text, utcnow


@dataclass(frozen=True)
class BusinessEmbeddingCandidate:
    business: BusinessModel
    semantic_text: str


@dataclass(frozen=True)
class EmbeddingBackfillSummary:
    scanned: int
    eligible: int
    embedded: int
    skipped: int
    failed_batches: int
    dry_run: bool


class OpenAIEmbeddingBatchClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.timeout_seconds = timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        normalized = [normalize_text(text) for text in texts]
        if not normalized:
            return []
        payload: dict[str, Any] = {
            "model": self.model,
            "input": normalized,
        }
        if self.dimension and self.model.startswith("text-embedding-3"):
            payload["dimensions"] = self.dimension
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
        vectors: list[list[float] | None] = [None] * len(normalized)
        for item in data:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or index < 0 or index >= len(vectors):
                continue
            if isinstance(embedding, list):
                vectors[index] = [float(value) for value in embedding]
        return vectors


class BusinessEmbeddingBackfillService:
    def __init__(
        self,
        session: Session,
        *,
        embedding_client: OpenAIEmbeddingBatchClient,
    ) -> None:
        self.session = session
        self.embedding_client = embedding_client

    def backfill(
        self,
        *,
        limit: int | None = None,
        batch_size: int = 100,
        force: bool = False,
        dry_run: bool = False,
    ) -> EmbeddingBackfillSummary:
        candidates = self._candidates(limit=limit, force=force)
        if dry_run:
            return EmbeddingBackfillSummary(
                scanned=len(candidates),
                eligible=len(candidates),
                embedded=0,
                skipped=0,
                failed_batches=0,
                dry_run=True,
            )

        embedded = 0
        skipped = 0
        failed_batches = 0
        now = utcnow()
        for batch in _chunks(candidates, max(1, batch_size)):
            texts = [candidate.semantic_text for candidate in batch]
            try:
                vectors = self.embedding_client.embed_texts(texts)
            except httpx.HTTPError:
                failed_batches += 1
                skipped += len(batch)
                continue

            for candidate, vector in zip(batch, vectors, strict=False):
                if not vector:
                    skipped += 1
                    continue
                candidate.business.semantic_text = candidate.semantic_text
                candidate.business.embedding = vector
                candidate.business.embedding_model = self.embedding_client.model
                candidate.business.embedding_updated_at = now
                embedded += 1
            self.session.commit()

        return EmbeddingBackfillSummary(
            scanned=len(candidates),
            eligible=len(candidates),
            embedded=embedded,
            skipped=skipped,
            failed_batches=failed_batches,
            dry_run=False,
        )

    def _candidates(self, *, limit: int | None, force: bool) -> list[BusinessEmbeddingCandidate]:
        statement = select(BusinessModel).order_by(BusinessModel.last_seen_at.desc())
        if not force:
            statement = statement.where(
                or_(
                    BusinessModel.embedding.is_(None),
                    BusinessModel.embedding_model != self.embedding_client.model,
                    BusinessModel.embedding_model.is_(None),
                )
            )
        if limit is not None:
            statement = statement.limit(limit)

        candidates: list[BusinessEmbeddingCandidate] = []
        for business in self.session.scalars(statement):
            semantic_text = normalize_text(business.semantic_text)
            if not semantic_text:
                semantic_text = self._semantic_text_for_business(business)
            if not semantic_text:
                continue
            candidates.append(BusinessEmbeddingCandidate(business=business, semantic_text=semantic_text))
        return candidates

    def _semantic_text_for_business(self, business: BusinessModel) -> str:
        observation = self.session.scalar(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business.id)
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(1)
        )
        raw = observation.raw_payload if observation is not None else {}
        source = observation.source if observation is not None else "canonical_cache"
        profile = business_semantic_profile(
            company_name=business.display_name,
            website_url=business.website_url,
            geography=business.geography,
            description=business.semantic_text,
            source=source,
            raw=raw,
        )
        return profile.text


def _chunks(items: list[BusinessEmbeddingCandidate], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
