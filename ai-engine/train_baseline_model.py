from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev


FEATURES = [
    "request_count",
    "failed_login_count",
    "unique_endpoint_count",
    "time_window_request_rate",
    "service_hop_count",
    "blocked_request_count",
    "risk_score",
]


def train(input_path: Path) -> dict:
    groups: dict[str, list[dict[str, float]]] = defaultdict(list)
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            groups[row["label"]].append({feature: float(row[feature]) for feature in FEATURES})
    if not groups:
        raise ValueError("Training dataset is empty.")

    centroids = {
        label: {feature: round(mean(item[feature] for item in rows), 3) for feature in FEATURES}
        for label, rows in groups.items()
    }
    spreads = {
        label: {feature: round(pstdev([item[feature] for item in rows]) or 1.0, 3) for feature in FEATURES}
        for label, rows in groups.items()
    }
    return {
        "modelType": "centroid-baseline",
        "description": "Dependency-free baseline artifact for Pantheon AI/anomaly experiments.",
        "features": FEATURES,
        "labels": sorted(groups),
        "classCentroids": centroids,
        "classStdDev": spreads,
        "anomalyPolicy": {
            "distanceThreshold": 2.75,
            "highRiskScore": 75,
            "highHopCount": 4,
            "highRequestRate": 120,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a lightweight Pantheon baseline model artifact.")
    parser.add_argument("--input", type=Path, default=Path("synthetic_training_logs.csv"))
    parser.add_argument("--output", type=Path, default=Path("model_artifact.json"))
    args = parser.parse_args()

    artifact = train(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Wrote baseline model artifact to {args.output}")


if __name__ == "__main__":
    main()
