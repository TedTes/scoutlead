from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AudienceResultModel, AudienceRunModel, LeadOutcomeModel
from outcomes.schemas import LeadOutcome
from territories.repository import TerritoryRepository


class TerritoryWeekMetrics(BaseModel):
    week_start: date
    delivered: int
    contacted: int
    replied: int
    positive_reply_rate: float
    meetings: int
    won: int
    not_a_fit_rate: float
    data_quality_issue_rate: float
    outcome_coverage: float


class TerritoryMetricsRead(BaseModel):
    territory_id: str
    weeks: int
    totals: TerritoryWeekMetrics
    by_week: list[TerritoryWeekMetrics]


class TerritoryMetricsService:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.territories = TerritoryRepository(session, workspace_id=workspace_id)

    def calculate(self, territory_id: str, *, weeks: int) -> TerritoryMetricsRead:
        self.territories.get(territory_id)
        now = datetime.now(timezone.utc)
        start = _week_start(now) - timedelta(weeks=weeks - 1)
        runs = list(
            self.session.scalars(
                select(AudienceRunModel).where(
                    AudienceRunModel.workspace_id == self.workspace_id,
                    AudienceRunModel.audience_id == territory_id,
                    AudienceRunModel.state.in_(("ready", "partial")),
                    AudienceRunModel.completed_at >= start,
                )
            )
        )
        run_week = {
            run.id: _week_start(_aware(run.completed_at or run.created_at))
            for run in runs
        }
        results = list(
            self.session.scalars(
                select(AudienceResultModel).where(AudienceResultModel.run_id.in_(run_week))
            )
        ) if run_week else []
        outreach_lead_ids = [
            result.outreach_lead_id for result in results if result.outreach_lead_id
        ]
        events = list(
            self.session.scalars(
                select(LeadOutcomeModel).where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.lead_id.in_(outreach_lead_ids),
                )
            )
        ) if outreach_lead_ids else []
        events_by_lead: dict[str, set[LeadOutcome]] = defaultdict(set)
        for event in events:
            events_by_lead[event.lead_id].add(LeadOutcome(event.outcome))
        results_by_week: dict[datetime, list[AudienceResultModel]] = defaultdict(list)
        for result in results:
            results_by_week[run_week[result.run_id]].append(result)
        rows = [
            _metrics_row(
                week_start=week,
                results=results_by_week.get(week, []),
                events=events_by_lead,
            )
            for week in (start + timedelta(weeks=index) for index in range(weeks))
        ]
        return TerritoryMetricsRead(
            territory_id=territory_id,
            weeks=weeks,
            totals=_metrics_row(week_start=start, results=results, events=events_by_lead),
            by_week=rows,
        )


def _metrics_row(
    *,
    week_start: datetime,
    results: list[AudienceResultModel],
    events: dict[str, set[LeadOutcome]],
) -> TerritoryWeekMetrics:
    delivered = len(results)
    event_sets = [
        events.get(result.outreach_lead_id, set())
        if result.outreach_lead_id
        else set()
        for result in results
    ]
    contacted = sum(LeadOutcome.CONTACTED in values for values in event_sets)
    replied = sum(
        bool(values & {LeadOutcome.REPLIED_POSITIVE, LeadOutcome.REPLIED_NEGATIVE})
        for values in event_sets
    )
    positive = sum(LeadOutcome.REPLIED_POSITIVE in values for values in event_sets)
    meetings = sum(LeadOutcome.MEETING_BOOKED in values for values in event_sets)
    won = sum(LeadOutcome.WON in values for values in event_sets)
    not_fit = sum(
        result.review_status == "not_fit" or LeadOutcome.NOT_A_FIT in values
        for result, values in zip(results, event_sets, strict=True)
    )
    quality = sum(
        bool(values & {LeadOutcome.WRONG_CONTACT, LeadOutcome.BOUNCED})
        for values in event_sets
    )
    covered = sum(bool(values) for values in event_sets)
    return TerritoryWeekMetrics(
        week_start=week_start.date(),
        delivered=delivered,
        contacted=contacted,
        replied=replied,
        positive_reply_rate=_rate(positive, contacted),
        meetings=meetings,
        won=won,
        not_a_fit_rate=_rate(not_fit, delivered),
        data_quality_issue_rate=_rate(quality, delivered),
        outcome_coverage=_rate(covered, delivered),
    )


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _week_start(value: datetime) -> datetime:
    aware = _aware(value)
    return (aware - timedelta(days=aware.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def territory_metrics_csv(metrics: TerritoryMetricsRead) -> str:
    output = StringIO()
    fieldnames = list(TerritoryWeekMetrics.model_fields)
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in metrics.by_week:
        writer.writerow(row.model_dump(mode="json"))
    return output.getvalue()
