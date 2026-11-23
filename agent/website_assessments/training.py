from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Iterable

from website_assessments.contracts import WebsiteAssessmentFeatures, WebsiteAssessmentLabel
from website_assessments.models import DEFAULT_COEFFICIENTS


POSITIVE_LABELS = {
    WebsiteAssessmentLabel.UPGRADE_CANDIDATE.value,
    WebsiteAssessmentLabel.BROKEN.value,
}


@dataclass(frozen=True)
class TrainingExample:
    features: WebsiteAssessmentFeatures
    label: str


def train_logistic_baseline(
    examples: Iterable[TrainingExample],
    *,
    epochs: int = 800,
    learning_rate: float = 0.08,
    l2: float = 0.01,
) -> tuple[float, dict[str, float]]:
    rows = list(examples)
    if not rows:
        raise ValueError("at least one labeled example is required")
    keys = tuple(DEFAULT_COEFFICIENTS)
    weights = {key: 0.0 for key in keys}
    intercept = 0.0
    for _ in range(epochs):
        intercept_gradient = 0.0
        gradients = {key: 0.0 for key in keys}
        for row in rows:
            values = {key: float(row.features.values.get(key) or 0.0) for key in keys}
            target = 1.0 if row.label in POSITIVE_LABELS else 0.0
            logit = intercept + sum(weights[key] * values[key] for key in keys)
            prediction = 1.0 / (1.0 + exp(-max(-30.0, min(30.0, logit))))
            error = prediction - target
            intercept_gradient += error
            for key in keys:
                gradients[key] += error * values[key]
        scale = 1.0 / len(rows)
        intercept -= learning_rate * intercept_gradient * scale
        for key in keys:
            weights[key] -= learning_rate * (
                gradients[key] * scale + l2 * weights[key]
            )
    return intercept, weights
