from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from canonical.semantics import request_semantic_profile, semantic_key
from db.models import NicheModel
from shared.utils import normalize_text


_GENERIC_NICHE_TOKENS = {
    "business",
    "company",
    "contractor",
    "home",
    "independent",
    "local",
    "operator",
    "professional",
    "provider",
    "residential",
    "service",
    "small",
    "team",
}


@dataclass(frozen=True)
class NicheResolution:
    niche_id: str
    slug: str
    label: str
    market_key: str | None
    match_type: str
    score: float


def resolve_niche(
    session: Session,
    *,
    source_inputs: dict[str, Any],
    source_input: str | None,
) -> NicheResolution | None:
    niches = list(
        session.scalars(
            select(NicheModel).where(NicheModel.active.is_(True)).order_by(NicheModel.slug)
        )
    )
    if not niches:
        return None

    profile = request_semantic_profile(
        source_inputs=source_inputs,
        source_input=source_input,
    )
    explicit = _explicit_niche(source_inputs)
    if explicit:
        explicit_key = _slug(explicit)
        for niche in niches:
            if explicit in {niche.id, niche.slug} or explicit_key == niche.slug:
                return _resolution(
                    niche,
                    market_key=profile.market_key,
                    match_type="explicit",
                    score=1.0,
                )
        return None

    request_tokens = _niche_tokens(
        " ".join(
            part
            for part in (
                profile.category_key,
                profile.text,
                normalize_text(source_input),
            )
            if part
        ),
        market_key=profile.market_key,
    )
    if not request_tokens:
        return None

    ranked: list[tuple[float, int, NicheModel]] = []
    for niche in niches:
        niche_tokens = _niche_tokens(
            " ".join(
                part
                for part in (niche.slug, niche.label, niche.category, niche.default_query)
                if part
            ),
            market_key=profile.market_key,
        )
        overlap = request_tokens & niche_tokens
        if not overlap:
            continue
        score = len(overlap) / max(1, len(niche_tokens))
        ranked.append((score, len(overlap), niche))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2].slug), reverse=True)
    best_score, best_overlap, best_niche = ranked[0]
    if len(ranked) > 1:
        next_score, next_overlap, _ = ranked[1]
        if best_score == next_score and best_overlap == next_overlap:
            return None
    return _resolution(
        best_niche,
        market_key=profile.market_key,
        match_type="lexical",
        score=round(best_score, 4),
    )


def source_inputs_from_raw(raw: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    current: dict[str, Any] | None = raw
    while isinstance(current, dict):
        source_inputs = current.get("source_input")
        if isinstance(source_inputs, dict):
            query = normalize_text(
                str(
                    current.get("discovery_query")
                    or source_inputs.get("query")
                    or source_inputs.get("compiled_query")
                    or ""
                )
            )
            return source_inputs, query or None
        if isinstance(current.get("source_request_intent"), dict):
            query = normalize_text(
                str(
                    current.get("discovery_query")
                    or current.get("query")
                    or current.get("search_query")
                    or ""
                )
            )
            return current, query or None
        nested = current.get("raw")
        current = nested if isinstance(nested, dict) else None
    return {}, None


def _resolution(
    niche: NicheModel,
    *,
    market_key: str | None,
    match_type: str,
    score: float,
) -> NicheResolution:
    return NicheResolution(
        niche_id=niche.id,
        slug=niche.slug,
        label=niche.label,
        market_key=market_key,
        match_type=match_type,
        score=score,
    )


def _explicit_niche(source_inputs: dict[str, Any]) -> str | None:
    for key in ("niche_id", "niche_slug", "seed_niche", "niche"):
        value = source_inputs.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_text(value)
    intent = source_inputs.get("source_request_intent")
    if isinstance(intent, dict):
        for key in ("niche_id", "niche_slug", "seed_niche"):
            value = intent.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
    return None


def _niche_tokens(value: str, *, market_key: str | None) -> set[str]:
    tokens = {_stem(token) for token in re.findall(r"[a-z0-9]+", value.lower())}
    generic_tokens = {_stem(token) for token in _GENERIC_NICHE_TOKENS}
    market_tokens = {
        _stem(token) for token in re.findall(r"[a-z0-9]+", (market_key or "").lower())
    }
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in generic_tokens and token not in market_tokens
    }


def _stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        token = f"{token[:-3]}y"
    elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        token = token[:-1]
    if token.endswith("ing") and len(token) > 5:
        stem = token[:-3]
        return stem[:-1] if len(stem) > 3 and stem[-1:] == stem[-2:-1] else stem
    if token.endswith("er") and len(token) > 4:
        return token[:-2]
    return token


def _slug(value: str) -> str:
    return (semantic_key(value) or "").replace(" ", "_")
