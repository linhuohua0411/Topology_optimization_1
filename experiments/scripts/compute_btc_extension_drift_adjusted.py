#!/usr/bin/env python3
"""
Compute BTC extension drift-adjusted deltas:
    delta_attack_net = delta_attack - delta_base

Inputs:
  results/statistics/BTC/BTC-MAIN-*/stats_summary.csv

Output:
  results/statistics/BTC/BTC-extension-drift-adjusted-summary.csv
"""

from __future__ import annotations

import csv
import os
from typing import Dict


ROOT = "/home/ly/project/Topology_optimization_1"
STAT_ROOT = os.path.join(ROOT, "results", "statistics", "BTC")

BASE_EXP = "BTC-MAIN-BASE"
ATTACK_EXPS = [
    "BTC-MAIN-ECLIPSE-low",
    "BTC-MAIN-ECLIPSE-mid",
    "BTC-MAIN-ECLIPSE-high",
    "BTC-MAIN-PARTITION-low",
    "BTC-MAIN-PARTITION-mid",
    "BTC-MAIN-PARTITION-high",
    "BTC-MAIN-NETEM-low",
    "BTC-MAIN-NETEM-mid",
    "BTC-MAIN-NETEM-high",
]

METRICS = [
    "reachable_ratio.paired_delta_runs",
    "peer_count_btc_avg.paired_delta_runs",
    "block_height_spread.paired_delta_runs",
    "topology_edges_directed.paired_delta_runs",
    "fork_events_total_seen.paired_delta_runs",
]


def read_means(exp_id: str) -> Dict[str, float]:
    path = os.path.join(STAT_ROOT, exp_id, "stats_summary.csv")
    out: Dict[str, float] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("stat_key", "")
            if key in METRICS:
                try:
                    out[key] = float(row.get("mean", "nan"))
                except Exception:
                    pass
    return out


def main() -> None:
    base_means = read_means(BASE_EXP)
    out_path = os.path.join(STAT_ROOT, "BTC-extension-drift-adjusted-summary.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "experiment_id",
            "stat_key",
            "delta_attack_mean",
            "delta_base_mean",
            "delta_attack_net_mean",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for exp in ATTACK_EXPS:
            attack_means = read_means(exp)
            for metric in METRICS:
                a = attack_means.get(metric, float("nan"))
                b = base_means.get(metric, float("nan"))
                writer.writerow(
                    {
                        "experiment_id": exp,
                        "stat_key": metric,
                        "delta_attack_mean": a,
                        "delta_base_mean": b,
                        "delta_attack_net_mean": a - b,
                    }
                )
    print(f"[ok] wrote {out_path}")


if __name__ == "__main__":
    main()
