from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


CandidateState = Literal["eligible", "disqualified", "pending", "not_matched", "not_scoped"]


@dataclass(frozen=True)
class CandidateComponent:
    """One visible input to the audience-candidate score.

    ``match_value`` is the business value for the current audience, from 0 to 1.
    It is intentionally separate from evidence confidence and freshness.
    """

    key: str
    label: str
    group: str
    weight: float
    match_value: float | None
    confidence: float | None
    freshness: float = 1.0
    hard_gate: bool = False
    status: str = "observed"
    reason: str = ""


def candidate_score(
    components: list[CandidateComponent],
    *,
    opportunity_scoped: bool,
    opportunity_matched: bool | None,
) -> dict:
    """Calculate the one candidate score shared by matching and admin.

    Formula per attribute: weight * match value * evidence confidence * freshness.
    Hard-gate failures disqualify regardless of the numeric score. Missing hard-gate
    evidence remains pending rather than being treated as a zero-quality business.
    """

    rows: list[dict] = []
    disqualifiers: list[str] = []
    pending: list[str] = []
    contribution = 0.0
    for component in components:
        match_value = _unit(component.match_value)
        confidence = _percent_unit(component.confidence)
        freshness = _unit(component.freshness) or 0.0
        value = (
            component.weight * match_value * confidence * freshness
            if match_value is not None and confidence is not None
            else None
        )
        row = asdict(component)
        row["match_value"] = (
            round(match_value * 100.0, 1) if match_value is not None else None
        )
        row["confidence"] = (
            round(confidence * 100.0, 1) if confidence is not None else None
        )
        row["freshness"] = round(freshness * 100.0, 1)
        row["contribution"] = round(value, 2) if value is not None else None
        rows.append(row)
        if value is not None:
            contribution += value
        if component.hard_gate:
            if component.status == "failed" or match_value == 0.0:
                disqualifiers.append(component.reason or f"{component.label} failed")
            elif match_value is None or confidence is None or component.status == "missing":
                pending.append(component.reason or f"{component.label} is unverified")

    if disqualifiers:
        state: CandidateState = "disqualified"
    elif pending:
        state = "pending"
    elif not opportunity_scoped:
        state = "not_scoped"
    elif not opportunity_matched:
        state = "not_matched"
    else:
        state = "eligible"

    return {
        "score": round(contribution, 1) if opportunity_scoped else None,
        "state": state,
        "total_weight": round(sum(row.weight for row in components), 1),
        "components": rows,
        "disqualifiers": disqualifiers,
        "pending_reasons": pending,
        "formula": "weight × attribute match × evidence confidence × freshness",
    }


def _unit(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def _percent_unit(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    return _unit(numeric / 100.0 if numeric > 1.0 else numeric)
