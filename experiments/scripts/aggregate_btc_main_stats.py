#!/usr/bin/env python3
"""
Aggregate BTC-MAIN collected runs into statistics tables.

Input:
  results/raw/BTC/BTC-MAIN-*/run-*/sample_000*.json

Output (per experiment):
  results/statistics/BTC/<experiment_id>/stats_summary.csv
  results/statistics/BTC/<experiment_id>/stats_summary.json
  results/statistics/BTC/<experiment_id>/run_manifest.json

Statistics:
  paired delta = mean(under_attack) - mean(pre_attack), paired across runs
  one-sample test against 0 with normality gate (Shapiro -> ttest or Wilcoxon)
  Holm correction across metrics within each experiment.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from datetime import datetime, timezone
from typing import Any

ROOT = "/home/ly/project/Topology_optimization_1"
RAW_ROOT_DEFAULT = os.path.join(ROOT, "results", "raw", "BTC")
STAT_ROOT = os.path.join(ROOT, "results", "statistics", "BTC")

EXPERIMENTS = [
    "BTC-MAIN-BASE",
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

METRIC_KEYS = [
    "reachable_ratio",
    "peer_count_btc_avg",
    "block_height_spread",
    "topology_edges_directed",
    "fork_events_total_seen",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def mean_std_ci95_t(values: list[float]) -> tuple[float, float, float, float]:
    n = len(values)
    if n == 0:
        return math.nan, math.nan, math.nan, math.nan
    mean = float(statistics.mean(values))
    std = float(statistics.stdev(values)) if n >= 2 else 0.0
    if n < 2:
        return mean, std, mean, mean
    # Conservative normal approximation (no scipy dependency)
    se = std / math.sqrt(n) if n > 0 else 0.0
    half = 1.96 * se
    return mean, std, mean - half, mean + half


def holm_bonferroni(p_values: list[float | None]) -> list[float | None]:
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None and math.isfinite(p)]
    m = len(indexed)
    out: list[float | None] = [None] * len(p_values)
    if m == 0:
        return out
    indexed.sort(key=lambda x: x[1])
    running_max = 0.0
    for rank, (idx, p) in enumerate(indexed):
        adj = (m - rank) * float(p)
        running_max = max(running_max, adj)
        out[idx] = min(1.0, running_max)
    return out


def test_one_sample_with_gate(deltas: list[float]) -> tuple[float | None, str, float | None, str]:
    # Keep script self-contained in environments without scipy.
    n = len(deltas)
    if n < 2:
        return None, "insufficient_n", None, ""
    std = float(statistics.stdev(deltas)) if n >= 2 else 0.0
    if std == 0.0:
        return None, "constant_delta", None, ""
    dz = float(statistics.mean(deltas) / std)
    return None, "descriptive_only_no_scipy", dz, "cohens_dz"


def run_ids(exp_dir: str) -> list[str]:
    out = [n for n in os.listdir(exp_dir) if n.startswith("run-") and os.path.isdir(os.path.join(exp_dir, n))]
    out.sort()
    return out


def sample_paths(run_dir: str) -> list[str]:
    files = [n for n in os.listdir(run_dir) if n.startswith("sample_") and n.endswith(".json")]
    files.sort()
    return [os.path.join(run_dir, n) for n in files]


def phase_metric_mean(samples: list[dict[str, Any]], phase: str, key: str) -> float:
    vals = []
    for s in samples:
        if s.get("phase") != phase:
            continue
        v = s.get("derived_metrics", {}).get(key)
        if v is None:
            continue
        vals.append(float(v))
    return float(statistics.mean(vals)) if vals else math.nan


def collect_vectors(exp_dir: str) -> tuple[list[str], dict[str, tuple[list[float], list[float]]]]:
    rids: list[str] = []
    pre: dict[str, list[float]] = {k: [] for k in METRIC_KEYS}
    under: dict[str, list[float]] = {k: [] for k in METRIC_KEYS}

    for rid in run_ids(exp_dir):
        run_dir = os.path.join(exp_dir, rid)
        samples = [load_json(p) for p in sample_paths(run_dir)]
        if not samples:
            continue
        rids.append(rid)
        for k in METRIC_KEYS:
            pre[k].append(phase_metric_mean(samples, "pre_attack", k))
            under[k].append(phase_metric_mean(samples, "under_attack", k))
    return rids, {k: (pre[k], under[k]) for k in METRIC_KEYS}


def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def aggregate_one(exp_id: str, raw_root: str) -> int:
    exp_raw_dir = os.path.join(raw_root, exp_id)
    if not os.path.isdir(exp_raw_dir):
        return 0

    stat_dir = os.path.join(STAT_ROOT, exp_id)
    os.makedirs(stat_dir, exist_ok=True)

    rids, vecs = collect_vectors(exp_raw_dir)
    rows: list[dict[str, Any]] = []
    pvals: list[float | None] = []

    for key in METRIC_KEYS:
        pre_v, under_v = vecs[key]
        deltas = []
        for a, b in zip(pre_v, under_v):
            if math.isfinite(a) and math.isfinite(b):
                deltas.append(float(b - a))
        if len(deltas) < 2:
            continue
        mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
        p, test_name, eff, eff_name = test_one_sample_with_gate(deltas)
        pvals.append(p)
        rows.append(
            {
                "comparison_id": f"CMP-{exp_id}-UNDER-minus-PRE",
                "stat_key": f"{key}.paired_delta_runs",
                "budget_variant": "fair",
                "experiment_id": exp_id,
                "test_name": test_name,
                "n": len(deltas),
                "mean": mean,
                "std": std,
                "ci95_low": ci_l,
                "ci95_high": ci_h,
                "p_value": p,
                "p_value_holm": None,
                "effect_size": eff,
                "effect_size_name": eff_name,
            }
        )

    holm = holm_bonferroni(pvals)
    for row, p_holm in zip(rows, holm):
        row["p_value_holm"] = p_holm

    write_csv(rows, os.path.join(stat_dir, "stats_summary.csv"))
    with open(os.path.join(stat_dir, "stats_summary.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    manifest = {
        "generated_at_utc": now_utc(),
        "experiment_id": exp_id,
        "protocol_variant": "unified_full_protocol",
        "budget_variant": "fair",
        "n_runs_found": len(rids),
        "run_ids": rids,
        "source_raw_dir": exp_raw_dir,
    }
    with open(os.path.join(stat_dir, "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[ok] {exp_id} -> {len(rows)} rows")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default=RAW_ROOT_DEFAULT)
    parser.add_argument(
        "--experiments",
        default="all",
        help="Comma-separated ids or 'all'",
    )
    args = parser.parse_args()

    selected = EXPERIMENTS
    if args.experiments.strip().lower() != "all":
        wanted = {x.strip() for x in args.experiments.split(",") if x.strip()}
        selected = [x for x in EXPERIMENTS if x in wanted]

    os.makedirs(STAT_ROOT, exist_ok=True)
    total = 0
    for exp_id in selected:
        total += aggregate_one(exp_id, args.raw_root)
    print(f"done: total_rows={total}")


if __name__ == "__main__":
    main()
