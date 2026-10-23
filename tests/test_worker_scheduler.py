from types import SimpleNamespace

import job_queue.worker as worker


def _services(*, territory_scheduler_enabled: bool):
    return SimpleNamespace(
        settings=SimpleNamespace(
            business_index_scheduler_enabled=False,
            territory_scheduler_enabled=territory_scheduler_enabled,
            no_response_days=14,
        )
    )


def _reset_scheduler_state(monkeypatch) -> None:
    monkeypatch.setattr(worker, "_last_audience_run_scheduler_tick", 0.0)
    monkeypatch.setattr(worker, "_last_business_index_scheduler_tick", 0.0)
    monkeypatch.setattr(worker, "_last_evidence_expiry_tick", 0.0)
    monkeypatch.setattr(worker, "_last_territory_scheduler_tick", 0.0)
    monkeypatch.setattr(worker, "_last_outcome_maintenance_date", None)
    monkeypatch.setattr(worker, "monotonic", lambda: 100.0)
    monkeypatch.setattr(worker, "enqueue_waiting_audience_runs", lambda session: 0)
    monkeypatch.setattr(worker, "enqueue_due_business_index_refreshes", lambda session: 0)


def test_outcome_maintenance_runs_when_territory_scheduler_is_disabled(
    monkeypatch,
) -> None:
    _reset_scheduler_state(monkeypatch)
    maintenance_calls = []
    territory_calls = []
    monkeypatch.setattr(
        worker,
        "run_outcome_maintenance",
        lambda session, *, no_response_days: maintenance_calls.append(
            (session, no_response_days)
        ),
    )
    monkeypatch.setattr(
        worker,
        "enqueue_due_territories",
        lambda session: territory_calls.append(session),
    )
    session = object()

    worker._scheduler_tick(
        session,
        _services(territory_scheduler_enabled=False),
    )
    worker._scheduler_tick(
        session,
        _services(territory_scheduler_enabled=False),
    )

    assert maintenance_calls == [(session, 14)]
    assert territory_calls == []


def test_territory_scheduler_still_runs_when_enabled(monkeypatch) -> None:
    _reset_scheduler_state(monkeypatch)
    territory_calls = []
    monkeypatch.setattr(worker, "run_outcome_maintenance", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "enqueue_due_territories",
        lambda session: territory_calls.append(session),
    )
    session = object()

    worker._scheduler_tick(
        session,
        _services(territory_scheduler_enabled=True),
    )

    assert territory_calls == [session]
