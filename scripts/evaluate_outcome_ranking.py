#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from db.models import LeadModel, LeadOutcomeModel  # noqa: E402
from evaluation.outcome_learning import (  # noqa: E402
    OutcomeSample,
    adjusted_rank_score,
    compute_outcome_weights,
    outcome_adjustment,
)
from outcomes.policy import POSITIVE_OUTCOMES  # noqa: E402
from outcomes.schemas import LeadOutcome  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate learned lead ranking on a time holdout.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--niche", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--holdout",
        help="ISO timestamp separating training from test outcomes; defaults to the 70th percentile.",
    )
    args = parser.parse_args()

    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        outcomes = list(
            session.scalars(
                select(LeadOutcomeModel)
                .where(
                    LeadOutcomeModel.workspace_id == args.workspace,
                    LeadOutcomeModel.product_id == args.product,
                    LeadOutcomeModel.niche_id == args.niche,
                )
                .order_by(LeadOutcomeModel.occurred_at)
            )
        )
        if not outcomes:
            raise SystemExit("No outcomes found for that workspace, offer, and niche.")
        holdout = _holdout_time(outcomes, args.holdout)
        train = [event for event in outcomes if _aware(event.occurred_at) < holdout]
        training_samples = _samples(session, train)
        model = compute_outcome_weights(training_samples)
        test_rows = _evaluation_rows(session, outcomes, model.weights, holdout=holdout)
        if not test_rows:
            raise SystemExit("No contacted leads exist in the holdout period.")
        top_k = max(1, min(args.top_k, len(test_rows)))
        baseline = sorted(test_rows, key=lambda row: row[1], reverse=True)[:top_k]
        adjusted = sorted(test_rows, key=lambda row: row[2], reverse=True)[:top_k]
        print(f"holdout={holdout.isoformat()}")
        print(f"training_contacted={model.n_contacted} training_positive={model.n_positive}")
        print(f"test_contacted={len(test_rows)} top_k={top_k}")
        print(f"baseline_top_k_positive_rate={_positive_rate(baseline):.3f}")
        print(f"adjusted_top_k_positive_rate={_positive_rate(adjusted):.3f}")
    finally:
        session_generator.close()


def _samples(session, events: list[LeadOutcomeModel]) -> list[OutcomeSample]:
    by_lead = _events_by_lead(events)
    samples: list[OutcomeSample] = []
    for lead_id, lead_events in by_lead.items():
        event_types = {LeadOutcome(event.outcome) for event in lead_events}
        if LeadOutcome.CONTACTED not in event_types:
            continue
        lead = session.get(LeadModel, lead_id)
        qualification = lead.qualification if lead and isinstance(lead.qualification, dict) else {}
        samples.append(
            OutcomeSample(
                tuple(qualification.get("signal_tags") or []),
                bool(event_types & POSITIVE_OUTCOMES),
            )
        )
    return samples


def _evaluation_rows(
    session,
    events: list[LeadOutcomeModel],
    weights: dict[str, float],
    *,
    holdout: datetime,
):
    rows = []
    for lead_id, lead_events in _events_by_lead(events).items():
        event_types = {LeadOutcome(event.outcome) for event in lead_events}
        if LeadOutcome.CONTACTED not in event_types:
            continue
        contacted_at = min(
            _aware(event.occurred_at)
            for event in lead_events
            if event.outcome == LeadOutcome.CONTACTED.value
        )
        if contacted_at < holdout:
            continue
        lead = session.get(LeadModel, lead_id)
        qualification = lead.qualification if lead and isinstance(lead.qualification, dict) else {}
        breakdown = qualification.get("score_breakdown") or {}
        fit_score = float(breakdown.get("fit_score", qualification.get("score", 0)))
        adjustment = outcome_adjustment(qualification.get("signal_tags") or [], weights)
        fit_status = qualification.get("fit_status") or "not_fit"
        rows.append(
            (
                lead_id,
                fit_score,
                adjusted_rank_score(
                    fit_score=fit_score,
                    fit_status=fit_status,
                    adjustment=adjustment,
                ),
                bool(event_types & POSITIVE_OUTCOMES),
            )
        )
    return rows


def _events_by_lead(events: list[LeadOutcomeModel]):
    grouped: dict[str, list[LeadOutcomeModel]] = defaultdict(list)
    for event in events:
        grouped[event.lead_id].append(event)
    return grouped


def _holdout_time(events: list[LeadOutcomeModel], raw: str | None) -> datetime:
    if raw:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    index = min(len(events) - 1, max(1, math.floor(len(events) * 0.7)))
    return _aware(events[index].occurred_at)


def _positive_rate(rows) -> float:
    return sum(row[3] for row in rows) / len(rows) if rows else 0.0


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    main()
