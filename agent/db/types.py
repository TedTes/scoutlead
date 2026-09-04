from __future__ import annotations

import json
from typing import Any, Iterable

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator, UserDefinedType


class PGVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def get_col_spec(self, **kw: Any) -> str:
        del kw
        return f"vector({self.dimension})"


class EmbeddingVector(TypeDecorator):
    """Store vectors as pgvector in Postgres and JSON in local SQLite tests."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimension: int = 1536) -> None:
        super().__init__()
        self.dimension = dimension

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGVector(self.dimension))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        vector = _coerce_vector(value)
        if dialect.name == "postgresql":
            return _vector_literal(vector)
        return vector

    def process_result_value(self, value, dialect):
        del dialect
        if value is None:
            return None
        if isinstance(value, str):
            return _parse_vector_literal(value)
        if isinstance(value, list):
            return _coerce_vector(value)
        return value


def _coerce_vector(value: Iterable[Any]) -> list[float]:
    return [float(item) for item in value]


def _vector_literal(value: Iterable[Any]) -> str:
    return json.dumps(_coerce_vector(value), separators=(",", ":"))


def _parse_vector_literal(value: str) -> list[float]:
    trimmed = value.strip()
    if not trimmed:
        return []
    parsed = json.loads(trimmed)
    if not isinstance(parsed, list):
        return []
    return _coerce_vector(parsed)
