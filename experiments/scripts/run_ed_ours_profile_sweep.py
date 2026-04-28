#!/usr/bin/env python3
"""
ED-MAIN-BASE exploratory profile sweep (M-OUR only, paired against frozen baselines).

Purpose:
- Re-run M-OUR under multiple parameter profiles on the same per-run A0.
- Reuse existing baseline rows from results/raw/ETH/ED-MAIN-BASE/results_rows_graph_optimizer.json
  for paired deltas on identical run_id (budget_variant=fair).
- Write outputs to ablation_snapshots to avoid polluting main-text statistics.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from run_component_ablation_ed import bh_fdr
from run_eth_docker_experiments import (
    WEIGHTS,
    build_dense_adj_from_sample,
    choose_adaptive_kmax,
    compute_graph_stats,
    list_sample_json_paths,
    pick_collected_sample,
)
from tifs_stats import (
    STATS_SUMMARY_FIELDNAMES,
    mean_std_ci95_t,
    test_one_sample_deltas_with_normality_gate,
    write_stats_summary_csv,
)

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from models.global_optimizer import DEFAULT_PARAMS, run_optimization
from models.robustness import compute_R_components


PROFILE_CONFIGS = {
    "full_default": {},
    "stability_first": {"sigma": 0.03, "beta": 0.08, "alpha_G": 0.32, "alpha_L": 0.18},
    "connectivity_bias": {"w1": 0.25, "w2": 0.55, "w3": 0.20, "sigma": 0.03},
}

BASELINES = ("M-RESI", "M-STAT", "M-ASIM", "M-FPS")
METRICS = ("R", "lcc_ratio", "avg_path_len")


def load_frozen_baselines(path: str, experiment_id: str) -> Dict[str, Dict[str, Dict[str, float]]]:
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for r in rows:
        if (
            r.get("experiment_id") != experiment_id
            or r.get("budget_variant") != "fair"
            or r.get("method_id") not in BASELINES
        ):
            continue
        rid = str(r["run_id"])
        out.setdefault(rid, {})[str(r["method_id"])] = {m: float(r[m]) for m in METRICS}
    return out


def run_profile_once(A0: np.ndarray, seed: int, profile_name: str) -> Dict[str, float]:
    params = DEFAULT_PARAMS.copy()
    params.update(
        {
            "seed": int(seed),
            "max_steps": 120,
            "min_steps": 25,
            "gradient_mode": "full",
            "gradient_sample_ratio": 0.05,
            "k_max": choose_adaptive_kmax(compute_graph_stats(A0, WEIGHTS)),
        }
    )
    params.update(PROFILE_CONFIGS[profile_name])
    A_star, hist = run_optimization(A0, params=params, verbose=False)
    weights = (params["w1"], params["w2"], params["w3"])
    comps = compute_R_components(A_star, weights)
    g = compute_graph_stats(A_star, WEIGHTS)
    return {
        "R": float(comps["R"]),
        "Rs": float(comps["R_s"]),
        "Rc": float(comps["R_c"]),
        "Rr": float(comps["R_r"]),
        "lcc_ratio": float(g["lcc_ratio"]),
        "avg_path_len": float(g["avg_path_length"]),
        "components": int(g["n_components"]),
        "steps": int(max(0, len(hist) - 1)),
        "time_to_converge": float(hist[-1]["time"]) if hist else 0.0,
        "k_max": int(params["k_max"]),
    }


def build_stats_rows(rows: List[Dict], experiment_id: str) -> List[Dict]:
    by_key: Dict[tuple, List[float]] = {}
    for r in rows:
        key = (r["profile_id"], r["method_id"], r["stat_key"])
        by_key.setdefault(key, []).append(float(r["delta"]))

    stats_rows: List[Dict] = []
    for profile_id in PROFILE_CONFIGS.keys():
        for metric in METRICS:
            pvals: List[Optional[float]] = []
            temp: List[Dict] = []
            for method in BASELINES:
                deltas = by_key.get((profile_id, method, f"{metric}.paired_delta"), [])
                if len(deltas) < 2:
                    continue
                mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
                p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
                pvals.append(p_raw)
                temp.append(
                    {
                        "comparison_id": f"CMP-ABL-PROFILE-{experiment_id}-{profile_id}-OUR-{method}",
                        "stat_key": f"{metric}.paired_delta",
                        "budget_variant": "fair",
                        "experiment_id": experiment_id,
                        "test_name": test_name,
                        "n": len(deltas),
                        "mean": mean,
                        "std": std,
                        "ci95_low": ci_l,
                        "ci95_high": ci_h,
                        "p_value": p_raw,
                        "p_value_holm": None,
                        "effect_size": eff,
                        "effect_size_name": eff_name,
                    }
                )
            qvals = bh_fdr(pvals)
            for row, q in zip(temp, qvals):
                row["p_value_holm"] = q
                stats_rows.append(row)
    return stats_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", default="ED-MAIN-BASE")
    parser.add_argument("--raw-root", default="results/raw/ETH")
    parser.add_argument("--n-runs", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--sample-pick", choices=("first_pre_attack", "first_sample"), default="first_pre_attack")
    parser.add_argument(
        "--frozen-baseline-rows",
        default="results/raw/ETH/ED-MAIN-BASE/results_rows_graph_optimizer.json",
    )
    parser.add_argument(
        "--out-dir",
        default="results/ablation_snapshots/ours_profile_sweep_ed_base",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    frozen = load_frozen_baselines(args.frozen_baseline_rows, args.experiment_id)
    result_rows: List[Dict] = []
    delta_rows: List[Dict] = []

    for run_idx in range(args.n_runs):
        run_id = f"run-{run_idx:03d}"
        seed = args.seed_base + run_idx
        run_dir = os.path.join(args.raw_root, args.experiment_id, run_id)
        sample_paths = list_sample_json_paths(run_dir)
        sample, sample_path = pick_collected_sample(sample_paths, args.sample_pick)
        if sample is None or run_id not in frozen:
            continue
        A0, _, _ = build_dense_adj_from_sample(sample)
        for profile_id in PROFILE_CONFIGS.keys():
            r = run_profile_once(A0, seed, profile_id)
            payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "platform": "eth_docker",
                "experiment_id": args.experiment_id,
                "run_id": run_id,
                "protocol_variant": "exploratory_profile_sweep",
                "budget_variant": "fair",
                "method_id": "M-OUR",
                "profile_id": profile_id,
                "graph_initial_path": sample_path,
                **r,
            }
            result_rows.append(payload)
            for method in BASELINES:
                b = frozen[run_id].get(method)
                if not b:
                    continue
                for metric in METRICS:
                    delta_rows.append(
                        {
                            "profile_id": profile_id,
                            "run_id": run_id,
                            "method_id": method,
                            "stat_key": f"{metric}.paired_delta",
                            "delta": float(r[metric] - b[metric]),
                        }
                    )
        print(f"[ok] {run_id}")

    stats_rows = build_stats_rows(delta_rows, args.experiment_id)

    with open(os.path.join(out_dir, "results_rows_ours_profile_sweep.json"), "w", encoding="utf-8") as f:
        json.dump(result_rows, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "paired_deltas_ours_profile_sweep.json"), "w", encoding="utf-8") as f:
        json.dump(delta_rows, f, indent=2, ensure_ascii=False)
    write_stats_summary_csv(stats_rows, os.path.join(out_dir, "stats_summary_ours_profile_sweep.csv"))
    with open(os.path.join(out_dir, "stats_summary_ours_profile_sweep.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": stats_rows,
                "fieldnames": STATS_SUMMARY_FIELDNAMES,
                "note": "Exploratory profile sweep; p_value_holm stores FDR(BH) within profile+metric baseline family.",
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    with open(os.path.join(out_dir, "run_manifest_ours_profile_sweep.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "experiment_id": args.experiment_id,
                "protocol_variant": "exploratory_profile_sweep",
                "n_runs_requested": args.n_runs,
                "profiles": PROFILE_CONFIGS,
                "frozen_baseline_rows": os.path.abspath(args.frozen_baseline_rows),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved: {out_dir}")


if __name__ == "__main__":
    main()
