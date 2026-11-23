"""Train the dependency-free local website-upgrade baseline from exported labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from website_assessments.contracts import WebsiteAssessmentFeatures  # noqa: E402
from website_assessments.training import TrainingExample, train_logistic_baseline  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train a local website assessment model.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="trained-1")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    examples: list[TrainingExample] = []
    for row in payload.get("examples", []):
        label_payload = row.get("label")
        label = label_payload.get("label") if isinstance(label_payload, dict) else None
        features = row.get("features")
        if not label or not isinstance(features, dict):
            continue
        examples.append(
            TrainingExample(
                features=WebsiteAssessmentFeatures(
                    business_id=str(features["business_id"]),
                    website_url=features.get("website_url"),
                    values=dict(features.get("values") or {}),
                    evidence=dict(features.get("evidence") or {}),
                ),
                label=str(label),
            )
        )
    intercept, coefficients = train_logistic_baseline(examples)
    model = {
        "model_key": "linear_website_baseline",
        "model_version": args.version,
        "training_example_count": len(examples),
        "intercept": intercept,
        "coefficients": coefficients,
    }
    args.output.write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "training_example_count": len(examples)}))


if __name__ == "__main__":
    main()
