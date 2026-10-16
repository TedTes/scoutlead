from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib.resources import files
import json
from typing import Any

from pydantic import BaseModel, Field

from outreach_packages.schemas import CallBranch, OutreachEvidence, OutreachStrategy


class BranchDefinition(BaseModel):
    key: str
    label: str
    acknowledgement: str
    question: str | None = None
    value_hypothesis: str | None = None
    next_step: str | None = None
    terminal: bool = False


class SignalDefinition(BaseModel):
    signal_key: str
    match_values: list[bool | int | float | str | None] | None = None
    evidence_statement: str
    observation: str
    discovery_question: str
    permitted_claims: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)


class ServicePlaybook(BaseModel):
    service_key: str
    version: int
    goal: str
    seller_positioning: str
    value_hypothesis: str
    next_step: str
    branch_set: str
    signals: list[SignalDefinition]


class PlaybookCatalog(BaseModel):
    catalog_version: int
    permission_variants: list[str]
    branch_sets: dict[str, list[BranchDefinition]]
    services: list[ServicePlaybook]


class PlaybookMatch(BaseModel):
    playbook: ServicePlaybook
    signal: SignalDefinition
    evidence: OutreachEvidence


class PlaybookRepository:
    def __init__(self, catalog: PlaybookCatalog | None = None) -> None:
        self.catalog = catalog or load_playbook_catalog()

    def resolve(
        self,
        *,
        service_keys: list[str],
        matched_services: list[dict[str, Any]],
        evidence: list[OutreachEvidence],
    ) -> PlaybookMatch | None:
        evidence_by_key: dict[str, list[OutreachEvidence]] = {}
        for item in evidence:
            evidence_by_key.setdefault(item.signal_key, []).append(item)

        matched_pairs = _matched_service_pairs(matched_services)
        ordered_services = list(dict.fromkeys([
            *(service for service, _ in matched_pairs),
            *service_keys,
        ]))
        playbooks = {item.service_key: item for item in self.catalog.services}
        if not ordered_services:
            for item in evidence:
                for playbook in self.catalog.services:
                    for signal in playbook.signals:
                        if signal.signal_key != item.signal_key:
                            continue
                        if _matches_value(signal.match_values, item.value):
                            return PlaybookMatch(
                                playbook=playbook,
                                signal=signal,
                                evidence=item,
                            )
            return None

        for service_key in ordered_services:
            playbook = playbooks.get(service_key)
            if playbook is None:
                continue
            preferred_signals = [
                signal for service, signal in matched_pairs if service == service_key
            ]
            signal_order = list(dict.fromkeys([
                *preferred_signals,
                *(item.signal_key for item in evidence),
            ]))
            for signal_key in signal_order:
                for signal in playbook.signals:
                    if signal.signal_key != signal_key:
                        continue
                    for item in evidence_by_key.get(signal_key, []):
                        if _matches_value(signal.match_values, item.value):
                            return PlaybookMatch(
                                playbook=playbook,
                                signal=signal,
                                evidence=item,
                            )
        return None

    def strategy_for(
        self,
        match: PlaybookMatch,
        *,
        stable_key: str,
    ) -> OutreachStrategy:
        playbook = match.playbook
        signal = match.signal
        variant_index = _stable_index(stable_key, len(self.catalog.permission_variants))
        permission = self.catalog.permission_variants[variant_index]
        branches = [
            CallBranch.model_validate(item.model_dump())
            for item in self.catalog.branch_sets.get(playbook.branch_set, [])
        ]
        evidence_statement = _with_value(signal.evidence_statement, match.evidence.value)
        observation = _with_value(signal.observation, match.evidence.value)
        permitted_claims = signal.permitted_claims or [evidence_statement]
        return OutreachStrategy(
            strategy_id=f"{playbook.service_key}:{signal.signal_key}",
            strategy_version=self.catalog.catalog_version,
            playbook_id=f"{playbook.service_key}:{signal.signal_key}",
            playbook_version=playbook.version,
            service_key=playbook.service_key,
            primary_signal_key=match.evidence.signal_key,
            primary_signal_value=match.evidence.value,
            goal=playbook.goal,
            evidence_statement=evidence_statement,
            observation=observation,
            permission=permission,
            discovery_question=signal.discovery_question,
            seller_positioning=playbook.seller_positioning,
            value_hypothesis=playbook.value_hypothesis,
            next_step=playbook.next_step,
            permitted_claims=permitted_claims,
            prohibited_claims=signal.prohibited_claims,
            selected_variant=f"permission:{variant_index + 1}",
            renderer_version=1,
            phrasing_provider="deterministic",
            call_branches=branches,
        )


@lru_cache(maxsize=1)
def load_playbook_catalog() -> PlaybookCatalog:
    path = files("outreach_packages").joinpath("playbooks.json")
    return PlaybookCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _matched_service_pairs(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in rows:
        service_key = str(row.get("service_key") or "")
        if not service_key:
            continue
        for item in row.get("supporting_evidence") or []:
            if not isinstance(item, dict):
                continue
            signal_key = str(item.get("signal_key") or "")
            if signal_key:
                pairs.append((service_key, signal_key))
    return pairs


def _matches_value(
    expected: list[bool | int | float | str | None] | None,
    actual: bool | int | float | str | None,
) -> bool:
    if expected is None:
        return True
    return actual in expected


def _stable_index(value: str, count: int) -> int:
    if count <= 1:
        return 0
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count


def _with_value(template: str, value: object) -> str:
    return template.replace("{value}", _display_value(value))


def _display_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value if value is not None else "unknown")
