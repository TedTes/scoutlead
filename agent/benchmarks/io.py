from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from benchmarks.schemas import BenchmarkRecord


def read_jsonl(path: Path) -> list[BenchmarkRecord]:
    records: list[BenchmarkRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(BenchmarkRecord.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid benchmark record on line {line_number}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: Iterable[BenchmarkRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")

