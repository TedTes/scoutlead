from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import LeadModel, LeadOutcomeModel, TerritoryDeliveryModel
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
        deliveries = list(
            self.session.scalars(
                select(TerritoryDeliveryModel).where(
                    TerritoryDeliveryModel.workspace_id == self.workspace_id,
                    TerritoryDeliveryModel.territory_id == territory_id,
                    TerritoryDeliveryModel.delivered_at >= start,
                )
            )
        )
        campaign_week = {
            delivery.campaign_id: _week_start(_aware(delivery.delivered_at or delivery.created_at))
            for delivery in deliveries
        }
        leads = list(
            self.session.scalars(
                select(LeadModel).where(LeadModel.campaign_id.in_(campaign_week))
            )
        ) if campaign_week else []
        events = list(
            self.session.scalars(
                select(LeadOutcomeModel).where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.lead_id.in_([lead.id for lead in leads]),
                )
            )
        ) if leads else []
        events_by_lead: dict[str, set[LeadOutcome]] = defaultdict(set)
        for event in events:
            events_by_lead[event.lead_id].add(LeadOutcome(event.outcome))
        leads_by_week: dict[datetime, list[LeadModel]] = defaultdict(list)
        for lead in leads:
            leads_by_week[campaign_week[lead.campaign_id]].append(lead)
        rows = [
            _metrics_row(week_start=week, leads=leads_by_week.get(week, []), events=events_by_lead)
            for week in (start + timedelta(weeks=index) for index in range(weeks))
        ]
        return TerritoryMetricsRead(
            territory_id=territory_id,
            weeks=weeks,
            totals=_metrics_row(week_start=start, leads=leads, events=events_by_lead),
            by_week=rows,
        )


def _metrics_row(
    *,
    week_start: datetime,
    leads: list[LeadModel],
    events: dict[str, set[LeadOutcome]],
) -> TerritoryWeekMetrics:
    delivered = len(leads)
    event_sets = [events.get(lead.id, set()) for lead in leads]
    contacted = sum(LeadOutcome.CONTACTED in values for values in event_sets)
    replied = sum(
        bool(values & {LeadOutcome.REPLIED_POSITIVE, LeadOutcome.REPLIED_NEGATIVE})
        for values in event_sets
    )
    positive = sum(LeadOutcome.REPLIED_POSITIVE in values for values in event_sets)
    meetings = sum(LeadOutcome.MEETING_BOOKED in values for values in event_sets)
    won = sum(LeadOutcome.WON in values for values in event_sets)
    not_fit = sum(LeadOutcome.NOT_A_FIT in values for values in event_sets)
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
