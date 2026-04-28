#!/usr/bin/env python3
"""
Aggregate Eth-Docker *collected* runs (results/raw/ETH) into TIFS-style statistics.

- Phase contrast (attack scenarios): mean metric in under_attack minus pre_attack, paired across runs.
- One-sample test on deltas vs 0: Shapiro-Wilk (n≥3) → t or Wilcoxon (`tifs_stats.test_one_sample_deltas_with_normality_gate`), §6.1 aligned.
- Holm correction across metrics in the same experiment block.
- Writes results/statistics/ETH/<experiment_id>/stats_summary.csv + run_manifest.json

Run after: collect_eth_docker_scenarios.py && compute_eth_docker_metrics_fast.py

Then run **``run_eth_docker_experiments.py``** (mandatory graph-optimizer / method
comparison for ED; ``protocol/04`` §2).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from experiment_protocol import PROTOCOL_VERSION, N_RUNS_DEFAULT
from compute_eth_docker_metrics_fast import (
    compute_row,
    discover_ed_experiment_dirs,
    load_json,
    sample_files_for_run,
)
from tifs_stats import (
    mean_std_ci95_t,
    holm_bonferroni,
    test_one_sample_deltas_with_normality_gate,
    write_stats_summary_csv,
)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_ETH_DOCKER = os.path.join(ROOT, "results", "raw", "ETH")
STAT_ROOT = os.path.join(ROOT, "results", "statistics", "ETH")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def rows_for_run(run_dir: str, budget_variant: str = "raw") -> List[dict]:
    rows = []
    for path in sample_files_for_run(run_dir):
        sample = load_json(path)
        row = compute_row(sample, budget_variant=budget_variant)
        row.setdefault("protocol_variant", sample.get("protocol_variant", "unified_full_protocol"))
        row.setdefault("layer", sample.get("layer", "execution"))
        rows.append(row)
    return rows


def phase_mean(rows: List[dict], phase: str, key: str) -> float:
    vals = [r[key] for r in rows if r.get("phase") == phase and r.get(key) is not None]
    if not vals:
        return float("nan")
    return float(np.mean(vals))


def collect_run_vectors(
    exp_dir: str, n_runs: int, budget_variant: str
) -> Tuple[List[str], Dict[str, List[float]], Dict[str, List[float]]]:
    """Returns (run_ids, pre_means_by_metric, under_means_by_metric)."""
    pre_R, under_R = [], []
    pre_lcc, under_lcc = [], []
    pre_path, under_path = [], []
    run_ids: List[str] = []

    for run_idx in range(n_runs):
        run_id = f"run-{run_idx:03d}"
        run_dir = os.path.join(exp_dir, run_id)
        if not os.path.isdir(run_dir):
            continue
        rows = rows_for_run(run_dir, budget_variant=budget_variant)
        if not rows:
            continue
        run_ids.append(run_id)
        pre_R.append(phase_mean(rows, "pre_attack", "R"))
        under_R.append(phase_mean(rows, "under_attack", "R"))
        pre_lcc.append(phase_mean(rows, "pre_attack", "lcc_ratio"))
        under_lcc.append(phase_mean(rows, "under_attack", "lcc_ratio"))
        pre_path.append(phase_mean(rows, "pre_attack", "avg_path_len"))
        under_path.append(phase_mean(rows, "under_attack", "avg_path_len"))

    vecs = {
        "R": (pre_R, under_R),
        "lcc_ratio": (pre_lcc, under_lcc),
        "avg_path_len": (pre_path, under_path),
    }
    return run_ids, vecs


def paired_delta(pre: List[float], post: List[float]) -> List[float]:
    out: List[float] = []
    for x, y in zip(pre, post):
        if np.isfinite(x) and np.isfinite(y):
            out.append(float(y - x))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default=RAW_ETH_DOCKER)
    parser.add_argument("--n-runs", type=int, default=N_RUNS_DEFAULT)
    parser.add_argument("--budget-variant", default="raw", choices=["raw", "fair"])
    parser.add_argument(
        "--strict-n-runs",
        action="store_true",
        help="Exit with code 2 if any experiment has fewer runs on disk than --n-runs.",
    )
    args = parser.parse_args()

    raw_root = args.raw_root
    os.makedirs(STAT_ROOT, exist_ok=True)
    experiments = discover_ed_experiment_dirs(raw_root)
    if not experiments:
        print(f"[warn] no ED-MAIN-* under {raw_root}")
        return

    exit_code = 0
    for exp_id in experiments:
        exp_dir = os.path.join(raw_root, exp_id)
        run_ids, vecs = collect_run_vectors(exp_dir, args.n_runs, args.budget_variant)
        stat_dir = os.path.join(STAT_ROOT, exp_id)
        os.makedirs(stat_dir, exist_ok=True)

        manifest = {
            "generated_at_utc": now_utc(),
            "protocol_version": PROTOCOL_VERSION,
            "experiment_id": exp_id,
            "source_raw_root": os.path.abspath(raw_root),
            "n_runs_requested": args.n_runs,
            "n_runs_found": len(run_ids),
            "run_ids": run_ids,
            "budget_variant": args.budget_variant,
        }
        with open(os.path.join(stat_dir, "run_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        if len(run_ids) < args.n_runs:
            msg = f"[warn] {exp_id}: found {len(run_ids)} runs, requested {args.n_runs}"
            print(msg, file=sys.stderr)
            if args.strict_n_runs:
                exit_code = 2

        stats_rows = []
        if exp_id == "ED-MAIN-BASE":
            # Descriptive: between-run variability of run-mean R (no attack contrast).
            run_mean_r = []
            for rid in run_ids:
                rows = rows_for_run(os.path.join(exp_dir, rid), budget_variant=args.budget_variant)
                vals = [r["R"] for r in rows if r.get("R") is not None]
                if vals:
                    run_mean_r.append(float(np.mean(vals)))
            if len(run_mean_r) >= 2:
                mean, std, ci_l, ci_h = mean_std_ci95_t(run_mean_r)
                stats_rows.append(
                    {
                        "comparison_id": f"CMP-{exp_id}-RUN-MEAN-R-DESCRIPTIVE",
                        "stat_key": "R.run_mean_across_samples",
                        "budget_variant": args.budget_variant,
                        "experiment_id": exp_id,
                        "test_name": "descriptive_ci_across_runs",
                        "n": len(run_mean_r),
                        "mean": mean,
                        "std": std,
                        "ci95_low": ci_l,
                        "ci95_high": ci_h,
                        "p_value": None,
                        "p_value_holm": None,
                        "effect_size": None,
                        "effect_size_name": "",
                    }
                )
        else:
            raw_ps = []
            block_rows = []
            for metric_key, (pre_v, under_v) in vecs.items():
                d = paired_delta(pre_v, under_v)
                if len(d) < 2:
                    continue
                mean, std, ci_l, ci_h = mean_std_ci95_t(d)
                p_raw, test_name, dz, eff_name = test_one_sample_deltas_with_normality_gate(d)
                raw_ps.append(p_raw)
                block_rows.append(
                    {
                        "comparison_id": f"CMP-{exp_id}-UNDER-minus-PRE",
                        "stat_key": f"{metric_key}.paired_delta_runs",
                        "budget_variant": args.budget_variant,
                        "experiment_id": exp_id,
                        "test_name": test_name,
                        "n": len(d),
                        "mean": mean,
                        "std": std,
                        "ci95_low": ci_l,
                        "ci95_high": ci_h,
                        "p_value": p_raw,
                        "p_value_holm": None,
                        "effect_size": dz,
                        "effect_size_name": eff_name,
                    }
                )
            holm = holm_bonferroni(raw_ps)
            for r, ph in zip(block_rows, holm):
                r["p_value_holm"] = ph
            stats_rows.extend(block_rows)

        out_csv = os.path.join(stat_dir, "stats_summary.csv")
        write_stats_summary_csv(stats_rows, out_csv)
        with open(os.path.join(stat_dir, "stats_summary.json"), "w", encoding="utf-8") as f:
            json.dump(stats_rows, f, ensure_ascii=False, indent=2)
        print(f"[ok] {exp_id} -> {out_csv} ({len(stats_rows)} rows)")

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
