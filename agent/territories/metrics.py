from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    LeadOutcomeModel,
    NicheModel,
    TerritoryModel,
)
from outcomes.schemas import LeadOutcome
from leads.schemas import WorkspaceLeadCounts
from territories.repository import TerritoryRepository


class TerritoryWeekMetrics(BaseModel):
    week_start: date
    delivered: int
    shortlisted: int
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


class AudiencePerformanceRead(BaseModel):
    audience_id: str
    product_id: str
    label: str
    niche_label: str | None = None
    place_label: str
    radius_km: int
    state: str
    lead_count: int
    shortlisted_count: int
    contacted_count: int
    shortlist_rate: float
    contact_rate: float
    latest_run_at: datetime | None = None


class WorkspaceOverviewRead(BaseModel):
    counts: WorkspaceLeadCounts
    audiences: list[AudiencePerformanceRead]


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

    def audience_performance(self, *, product_id: str | None = None) -> list[AudiencePerformanceRead]:
        filters = [
            TerritoryModel.workspace_id == self.workspace_id,
            TerritoryModel.status != "archived",
        ]
        if product_id:
            filters.append(TerritoryModel.product_id == product_id)
        audience_rows = list(
            self.session.execute(
                select(TerritoryModel, NicheModel.label)
                .join(NicheModel, NicheModel.id == TerritoryModel.niche_id)
                .where(*filters)
                .order_by(TerritoryModel.created_at.desc())
            )
        )
        audiences = [row[0] for row in audience_rows]
        niche_labels = {row[0].id: row[1] for row in audience_rows}
        if not audiences:
            return []
        audience_ids = [audience.id for audience in audiences]
        runs = list(
            self.session.scalars(
                select(AudienceRunModel)
                .where(
                    AudienceRunModel.workspace_id == self.workspace_id,
                    AudienceRunModel.audience_id.in_(audience_ids),
                )
                .order_by(
                    AudienceRunModel.audience_id,
                    AudienceRunModel.created_at.desc(),
                )
            )
        )
        latest_runs: dict[str, AudienceRunModel] = {}
        for run in runs:
            latest_runs.setdefault(run.audience_id, run)
        run_ids = [run.id for run in runs]
        results = (
            list(
                self.session.scalars(
                    select(AudienceResultModel).where(
                        AudienceResultModel.run_id.in_(run_ids)
                    )
                )
            )
            if run_ids
            else []
        )
        by_run: dict[str, list[AudienceResultModel]] = defaultdict(list)
        for result in results:
            by_run[result.run_id].append(result)
        latest_result_runs: dict[str, AudienceRunModel] = {}
        for run in runs:
            if run.id in by_run:
                latest_result_runs.setdefault(run.audience_id, run)
        rows: list[AudiencePerformanceRead] = []
        for audience in audiences:
            run = latest_runs.get(audience.id)
            result_run = latest_result_runs.get(audience.id)
            batch = by_run.get(result_run.id, []) if result_run else []
            lead_count = len(batch)
            shortlisted_count = sum(result.shortlisted_at is not None for result in batch)
            contacted_count = sum(result.contacted_at is not None for result in batch)
            rows.append(
                AudiencePerformanceRead(
                    audience_id=audience.id,
                    product_id=audience.product_id,
                    label=audience.label,
                    niche_label=niche_labels.get(audience.id),
                    place_label=audience.place_label or audience.city,
                    radius_km=audience.radius_km,
                    state=run.state if run else "setup",
                    lead_count=lead_count,
                    shortlisted_count=shortlisted_count,
                    contacted_count=contacted_count,
                    shortlist_rate=_rate(shortlisted_count, lead_count),
                    contact_rate=_rate(contacted_count, lead_count),
                    latest_run_at=(run.completed_at or run.created_at) if run else None,
                )
            )
        return rows


def _metrics_row(
    *,
    week_start: datetime,
    results: list[AudienceResultModel],
    events: dict[str, set[LeadOutcome]],
) -> TerritoryWeekMetrics:
    delivered = len(results)
    shortlisted = sum(result.shortlisted_at is not None for result in results)
    event_sets = [
        events.get(result.outreach_lead_id, set())
        if result.outreach_lead_id
        else set()
        for result in results
    ]
    contacted = sum(
        result.contacted_at is not None or LeadOutcome.CONTACTED in values
        for result, values in zip(results, event_sets, strict=True)
    )
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
        shortlisted=shortlisted,
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
