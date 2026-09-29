from evaluation.outcome_learning import (
    ADJUSTMENT_LIMIT,
    OutcomeSample,
    adjusted_rank_score,
    compute_outcome_weights,
    outcome_adjustment,
)
from leads.schemas import AgentFitStatus


def test_learning_stays_inactive_below_evidence_thresholds() -> None:
    samples = [OutcomeSample(("fleet",), index < 4) for index in range(29)]
    result = compute_outcome_weights(samples)
    assert result.weights == {}
    assert result.active is False


def test_learning_uses_smoothed_lift_after_activation() -> None:
    samples = [
        OutcomeSample(("fleet",), index < 8)
        for index in range(20)
    ] + [
        OutcomeSample(("owner_operated",), index < 2)
        for index in range(20)
    ]
    result = compute_outcome_weights(samples)

    assert result.active is True
    assert result.n_contacted == 40
    assert result.n_positive == 10
    assert result.weights["fleet"] > 1
    assert result.weights["owner_operated"] < 1


def test_adjustment_is_clamped_and_never_promotes_not_fit() -> None:
    adjustment = outcome_adjustment([f"tag-{index}" for index in range(20)], {
        f"tag-{index}": 10.0 for index in range(20)
    })
    assert adjustment == ADJUSTMENT_LIMIT
    assert adjusted_rank_score(
        fit_score=40,
        fit_status=AgentFitStatus.NOT_FIT,
        adjustment=15,
    ) == 40
    assert adjusted_rank_score(
        fit_score=80,
        fit_status=AgentFitStatus.GOOD_FIT,
        adjustment=8,
    ) == 88
