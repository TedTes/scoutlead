from __future__ import annotations

from dataclasses import dataclass
import math

from leads.schemas import AgentFitStatus


MIN_CONTACTED = 30
MIN_POSITIVE = 5
PRIOR_STRENGTH = 10.0
ADJUSTMENT_SCALE = 5.0
ADJUSTMENT_LIMIT = 15.0


@dataclass(frozen=True)
class OutcomeSample:
    signal_tags: tuple[str, ...]
    positive: bool


@dataclass(frozen=True)
class OutcomeWeights:
    n_contacted: int
    n_positive: int
    baseline_rate: float
    weights: dict[str, float]

    @property
    def active(self) -> bool:
        return self.n_contacted >= MIN_CONTACTED and self.n_positive >= MIN_POSITIVE


def compute_outcome_weights(samples: list[OutcomeSample]) -> OutcomeWeights:
    n_contacted = len(samples)
    n_positive = sum(sample.positive for sample in samples)
    baseline = n_positive / n_contacted if n_contacted else 0.0
    if n_contacted < MIN_CONTACTED or n_positive < MIN_POSITIVE or baseline <= 0:
        return OutcomeWeights(n_contacted, n_positive, baseline, {})

    tag_counts: dict[str, list[int]] = {}
    for sample in samples:
        for tag in set(sample.signal_tags):
            counts = tag_counts.setdefault(tag, [0, 0])
            counts[0] += 1
            counts[1] += int(sample.positive)

    weights: dict[str, float] = {}
    for tag, (count, positives) in tag_counts.items():
        smoothed_rate = (positives + baseline * PRIOR_STRENGTH) / (
            count + PRIOR_STRENGTH
        )
        weights[tag] = round(smoothed_rate / baseline, 6)
    return OutcomeWeights(n_contacted, n_positive, baseline, weights)


def outcome_adjustment(
    signal_tags: list[str],
    weights: dict[str, float],
    *,
    scale: float = ADJUSTMENT_SCALE,
) -> float:
    raw = scale * sum(
        math.log(weights[tag])
        for tag in set(signal_tags)
        if tag in weights and weights[tag] > 0
    )
    return round(max(-ADJUSTMENT_LIMIT, min(ADJUSTMENT_LIMIT, raw)), 2)


def adjusted_rank_score(
    *,
    fit_score: float,
    fit_status: AgentFitStatus | str,
    adjustment: float,
) -> float:
    status = AgentFitStatus(fit_status)
    if status == AgentFitStatus.NOT_FIT:
        return float(fit_score)
    return round(max(0.0, min(100.0, fit_score + adjustment)), 2)
