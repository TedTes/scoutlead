from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.schemas import CampaignRead
from db.models import BusinessIndexSegmentModel, QueueJobModel
from job_queue.schemas import JobType
from leads.schemas import LeadRead
from run_diagnostics.repository import RunPipelineEventRepository
from run_diagnostics.schemas import (
    RunDiagnostics,
    RunJobDiagnostic,
    RunPipelineEventRead,
    RunSourceDiagnostic,
)


def build_run_diagnostics(
    session: Session,
    *,
    run: CampaignRead,
    final_results: list[LeadRead],
) -> RunDiagnostics:
    source_inputs = run.source_inputs or {}
    segment_id = _text(source_inputs.get("business_index_segment_id")) or None
    segment = session.get(BusinessIndexSegmentModel, segment_id) if segment_id else None
    event_models = RunPipelineEventRepository(session).list_by_campaign(run.id)
    events = [RunPipelineEventRead.model_validate(event) for event in event_models]
    instrumented = any(event.event_type == "request_created" for event in events)
    final_by_source = Counter(result.source for result in final_results)

    plan = list(segment.source_plan or []) if segment is not None else []
    state = dict(segment.source_state or {}) if segment is not None else {}
    sources = _source_diagnostics(
        plan=plan,
        state=state,
        events=events,
        final_by_source=final_by_source,
        exact_history=instrumented,
    )
    jobs = _jobs_for_run(session, run_id=run.id, segment_id=segment_id)
    fetched_count = sum(source.fetched_count for source in sources)
    accepted_values = [source.accepted_count for source in sources]
    rejected_values = [source.rejected_count for source in sources]
    index_event = next(
        (event for event in reversed(events) if event.event_type == "index_query"),
        None,
    )
    existing_match_count = _int_value(
        (index_event.response_payload or {}).get("match_count") if index_event else None
    )
    request_payload = {
        "prompt": source_inputs.get("source_request_prompt") or run.source_input,
        "source": source_inputs.get("source_request_source"),
        "intent": source_inputs.get("source_request_intent"),
        "contract": source_inputs.get("business_index_contract"),
        "requested_result_count": source_inputs.get("requested_result_count") or run.max_leads,
    }
    caveats: list[str] = []
    retention = "exact" if instrumented else "aggregate_only"
    if not instrumented:
        caveats.append(
            "This run predates row-level pipeline retention. Provider totals are the latest segment snapshot; individual rejected rows are unavailable."
        )
    if segment is None:
        caveats.append("This run is not linked to a business-index segment.")
    if any(source.rejected_count is None for source in sources):
        caveats.append(
            "A written-count difference is not labeled as rejection because older data can also include deduplication."
        )

    return RunDiagnostics(
        run_id=run.id,
        run_name=run.name,
        run_status=run.status.value,
        run_stage=run.stage.value,
        created_at=run.created_at,
        updated_at=run.updated_at,
        retention=retention,
        request=_redact(request_payload),
        segment=(
            {
                "id": segment.id,
                "niche_id": segment.niche_id,
                "market_key": segment.market_key,
                "market_label": segment.market_label,
                "status": segment.status,
                "target_business_count": segment.target_business_count,
                "last_refresh_at": segment.last_refresh_at,
                "last_success_at": segment.last_success_at,
            }
            if segment is not None
            else None
        ),
        summary={
            "requested": int(source_inputs.get("requested_result_count") or run.max_leads),
            "existing_matches": existing_match_count,
            "fetched": fetched_count,
            "accepted": sum(value for value in accepted_values if value is not None)
            if instrumented
            else None,
            "rejected": sum(value for value in rejected_values if value is not None)
            if instrumented
            else None,
            "failed_sources": sum(1 for source in sources if source.failure),
            "final": len(final_results),
        },
        sources=sources,
        jobs=jobs,
        events=events,
        final_results=final_results,
        caveats=caveats,
    )


def _source_diagnostics(
    *,
    plan: list[dict[str, Any]],
    state: dict[str, Any],
    events: list[RunPipelineEventRead],
    final_by_source: Counter[str],
    exact_history: bool,
) -> list[RunSourceDiagnostic]:
    rows: list[RunSourceDiagnostic] = []
    state_items = list(state.items())
    for index, task in enumerate(plan):
        provider_id = _text(task.get("provider_id")) or "unknown"
        query = _text(task.get("query"))
        matching_state = _state_for_task(state_items, provider_id, query, index)
        fetch_event = next(
            (
                event
                for event in reversed(events)
                if event.event_type == "provider_fetch"
                and event.provider_id == provider_id
                and _text((event.request_payload or {}).get("query")) == query
            ),
            None,
        )
        decisions = [
            event
            for event in events
            if event.event_type == "candidate_decision"
            and event.provider_id == provider_id
            and _text((event.request_payload or {}).get("query")) == query
        ]
        fetched = (
            _int_value((fetch_event.response_payload or {}).get("fetched_count"))
            if fetch_event
            else (0 if exact_history else _int_value(matching_state.get("fetched_count")))
        )
        accepted = sum(1 for event in decisions if event.status == "accepted") if exact_history else None
        rejected = sum(1 for event in decisions if event.status == "rejected") if exact_history else None
        failure = (
            fetch_event.reason
            if fetch_event and fetch_event.status == "failed"
            else _text(matching_state.get("failure")) or None
        )
        rows.append(
            RunSourceDiagnostic(
                key=f"{provider_id}:{index}",
                provider_id=provider_id,
                query=query,
                quota=_int_value(task.get("max_results")),
                status=(
                    "failed"
                    if failure
                    else (fetch_event.status if fetch_event else ("not_run" if exact_history else "snapshot"))
                ),
                fetched_count=fetched,
                accepted_count=accepted,
                rejected_count=rejected,
                written_count=(
                    accepted or 0
                    if exact_history
                    else _int_value(matching_state.get("written_count"))
                ),
                final_count=final_by_source.get(provider_id, 0),
                failure=failure,
                request=_redact(
                    {
                        "query": query,
                        "input": task.get("input") or {},
                        "config": task.get("config") or {},
                        "reason": task.get("reason"),
                    }
                ),
                state=_redact(matching_state),
                exact_decisions=exact_history,
            )
        )
    return rows


def _state_for_task(
    items: list[tuple[str, Any]],
    provider_id: str,
    query: str,
    index: int,
) -> dict[str, Any]:
    exact_key = f"{provider_id}:{index}"
    for key, value in items:
        if key == exact_key and isinstance(value, dict):
            return value
    for _, value in items:
        if not isinstance(value, dict):
            continue
        if value.get("provider_id") == provider_id and _text(value.get("query")) == query:
            return value
    return {}


def _jobs_for_run(session: Session, *, run_id: str, segment_id: str | None) -> list[RunJobDiagnostic]:
    candidates = list(
        session.scalars(
            select(QueueJobModel)
            .where(QueueJobModel.type == JobType.BUSINESS_INDEX_REFRESH.value)
            .order_by(QueueJobModel.created_at.desc())
        )
    )
    exact = [job for job in candidates if job.payload.get("campaign_id") == run_id]
    selected = exact or [
        job for job in candidates if segment_id and job.payload.get("segment_id") == segment_id
    ][:5]
    return [
        RunJobDiagnostic(
            id=job.id,
            type=job.type,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            payload=_redact(job.payload),
            last_error=job.last_error,
            run_after=job.run_after,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        for job in selected
    ]


def _int_value(value: Any, *, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _redact(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        str(key): "[redacted]" if _secret_key(str(key)) else _redact(item)
        for key, item in value.items()
    }


def _secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in ("api_key", "token", "secret", "password", "authorization"))
