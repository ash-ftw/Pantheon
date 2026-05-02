from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


ATTACK_PROFILES = {
    "Normal Traffic": {
        "request_count": (8, 30),
        "failed_login_count": (0, 2),
        "unique_endpoint_count": (4, 10),
        "time_window_request_rate": (5, 35),
        "service_hop_count": (1, 2),
        "blocked_request_count": (0, 1),
        "risk_score": (5, 22),
    },
    "Brute Force": {
        "request_count": (35, 90),
        "failed_login_count": (25, 80),
        "unique_endpoint_count": (1, 3),
        "time_window_request_rate": (60, 180),
        "service_hop_count": (1, 2),
        "blocked_request_count": (0, 20),
        "risk_score": (55, 82),
    },
    "SQL Injection": {
        "request_count": (12, 45),
        "failed_login_count": (0, 4),
        "unique_endpoint_count": (2, 6),
        "time_window_request_rate": (20, 80),
        "service_hop_count": (1, 3),
        "blocked_request_count": (0, 12),
        "risk_score": (62, 88),
    },
    "Lateral Movement": {
        "request_count": (24, 70),
        "failed_login_count": (2, 12),
        "unique_endpoint_count": (5, 12),
        "time_window_request_rate": (35, 95),
        "service_hop_count": (3, 6),
        "blocked_request_count": (0, 14),
        "risk_score": (70, 96),
    },
    "DDoS-Style Traffic": {
        "request_count": (80, 180),
        "failed_login_count": (0, 8),
        "unique_endpoint_count": (1, 4),
        "time_window_request_rate": (140, 420),
        "service_hop_count": (1, 2),
        "blocked_request_count": (0, 45),
        "risk_score": (68, 94),
    },
    "Multi-Stage Attack": {
        "request_count": (45, 120),
        "failed_login_count": (4, 20),
        "unique_endpoint_count": (5, 14),
        "time_window_request_rate": (55, 160),
        "service_hop_count": (4, 7),
        "blocked_request_count": (0, 20),
        "risk_score": (82, 100),
    },
}


def generate_dataset(rows: int, seed: int) -> list[dict[str, int | str]]:
    random.seed(seed)
    labels = list(ATTACK_PROFILES)
    dataset = []
    for index in range(rows):
        label = labels[index % len(labels)]
        profile = ATTACK_PROFILES[label]
        record: dict[str, int | str] = {"label": label}
        for feature, bounds in profile.items():
            low, high = bounds
            record[feature] = random.randint(low, high)
        dataset.append(record)
    random.shuffle(dataset)
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Pantheon synthetic AI training data.")
    parser.add_argument("--rows", type=int, default=420)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("synthetic_training_logs.csv"))
    args = parser.parse_args()

    dataset = generate_dataset(max(args.rows, len(ATTACK_PROFILES)), args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["label", *next(iter(ATTACK_PROFILES.values())).keys()])
        writer.writeheader()
        writer.writerows(dataset)
    print(f"Wrote {len(dataset)} rows to {args.output}")


if __name__ == "__main__":
    main()
