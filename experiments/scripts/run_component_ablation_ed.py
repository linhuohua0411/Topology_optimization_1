#!/usr/bin/env python3
"""
ED component ablation on graph optimizer (M-OUR only).

Variants:
- full
- wo_evolution
- wo_self_organization
- wo_Rc
- wo_Rr

Outputs:
- results/ablation_snapshots/component_ablation_ed_base/results_rows_component_ablation.json
- results/ablation_snapshots/component_ablation_ed_base/stats_summary_component_ablation.csv
- results/ablation_snapshots/component_ablation_ed_base/stats_summary_component_ablation.json
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np

from tifs_stats import (
    STATS_SUMMARY_FIELDNAMES,
    mean_std_ci95_t,
    test_one_sample_deltas_with_normality_gate,
    write_stats_summary_csv,
)

from run_eth_docker_experiments import (
    WEIGHTS,
    build_dense_adj_from_sample,
    list_sample_json_paths,
    pick_collected_sample,
    compute_graph_stats,
)

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from models.global_optimizer import DEFAULT_PARAMS, run_optimization
from models.robustness import compute_R_components


def bh_fdr(p_values: List[float | None]) -> List[float | None]:
    valid = [(i, p) for i, p in enumerate(p_values) if p is not None and p == p]
    out = [None] * len(p_values)
    if not valid:
        return out
    valid_sorted = sorted(valid, key=lambda x: x[1])
    m = len(valid_sorted)
    adj = [0.0] * m
    for k, (_, p) in enumerate(valid_sorted, start=1):
        adj[k - 1] = p * m / k
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    for (orig_i, _), q in zip(valid_sorted, adj):
        out[orig_i] = min(1.0, q)
    return out


def variant_params(name: str, seed: int) -> Dict:
    p = DEFAULT_PARAMS.copy()
    p.update(
        {
            "seed": int(seed),
            "max_steps": 60,
            "min_steps": 12,
            "gradient_mode": "full",
            "gradient_sample_ratio": 0.05,
        }
    )
    if name == "full":
        return p
    if name == "wo_evolution":
        p.update({"alpha": 0.0, "beta": 0.0, "sigma": 0.0})
        return p
    if name == "wo_self_organization":
        p.update({"alpha_L": 0.0, "alpha_G": 0.0})
        return p
    if name == "wo_Rc":
        p.update({"w1": 0.5, "w2": 0.0, "w3": 0.5})
        return p
    if name == "wo_Rr":
        p.update({"w1": 0.4285714286, "w2": 0.5714285714, "w3": 0.0})
        return p
    raise ValueError(name)


def run_once(A0: np.ndarray, variant: str, seed: int) -> Dict:
    params = variant_params(variant, seed)
    A_star, hist = run_optimization(A0, params=params, verbose=False)
    weights = (params["w1"], params["w2"], params["w3"])
    comps = compute_R_components(A_star, weights)
    g = compute_graph_stats(A_star, WEIGHTS)
    return {
        "variant": variant,
        "seed": int(seed),
        "R": float(comps["R"]),
        "R_s": float(comps["R_s"]),
        "R_c": float(comps["R_c"]),
        "R_r": float(comps["R_r"]),
        "lcc_ratio": float(g["lcc_ratio"]),
        "avg_path_len": float(g["avg_path_length"]),
        "n_components": int(g["n_components"]),
        "steps": int(len(hist) - 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", default="ED-MAIN-BASE")
    parser.add_argument("--raw-root", default="results/raw/eth_docker")
    parser.add_argument("--n-runs", type=int, default=20)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--sample-pick", choices=("first_pre_attack", "first_sample"), default="first_pre_attack")
    parser.add_argument(
        "--out-dir",
        default="results/ablation_snapshots/component_ablation_ed_base",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    variants = ["full", "wo_evolution", "wo_self_organization", "wo_Rc", "wo_Rr"]
    results_rows: List[Dict] = []
    by_run: Dict[str, Dict[str, Dict]] = {}

    for run_idx in range(args.n_runs):
        run_id = f"run-{run_idx:03d}"
        seed = args.seed_base + run_idx
        run_dir = os.path.join(args.raw_root, args.experiment_id, run_id)
        sample_paths = list_sample_json_paths(run_dir)
        sample, sample_path = pick_collected_sample(sample_paths, args.sample_pick)
        if sample is None:
            continue
        A0, _, _ = build_dense_adj_from_sample(sample)
        by_run[run_id] = {}
        for v in variants:
            r = run_once(A0, v, seed)
            r.update(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "platform": "eth_docker",
                    "experiment_id": args.experiment_id,
                    "run_id": run_id,
                    "protocol_variant": "ablation_components",
                    "budget_variant": "fair",
                    "comparison_id": "CMP-ABL-COMP",
                    "graph_initial_path": sample_path,
                }
            )
            by_run[run_id][v] = r
            results_rows.append(r)
        print(f"[ok] {run_id}")

    stats_rows: List[Dict] = []
    metrics = ["R", "lcc_ratio", "avg_path_len"]
    variants_abl = [v for v in variants if v != "full"]
    for metric in metrics:
        pvals: List[float | None] = []
        tmp_rows: List[Dict] = []
        for v in variants_abl:
            deltas = []
            for run_id, row_map in by_run.items():
                if "full" in row_map and v in row_map:
                    deltas.append(row_map["full"][metric] - row_map[v][metric])
            if len(deltas) < 2:
                continue
            mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
            p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
            pvals.append(p_raw)
            tmp_rows.append(
                {
                    "comparison_id": f"CMP-ABL-COMP-{args.experiment_id}-FULL-vs-{v}",
                    "stat_key": f"{metric}.paired_delta_full_minus_variant",
                    "budget_variant": "fair",
                    "experiment_id": args.experiment_id,
                    "test_name": test_name,
                    "n": len(deltas),
                    "mean": mean,
                    "std": std,
                    "ci95_low": ci_l,
                    "ci95_high": ci_h,
                    "p_value": p_raw,
                    "p_value_holm": None,  # reused as FDR(BH) adjusted p for ablation family
                    "effect_size": eff,
                    "effect_size_name": eff_name,
                }
            )
        qvals = bh_fdr(pvals)
        for r, q in zip(tmp_rows, qvals):
            r["p_value_holm"] = q
            stats_rows.append(r)

    rows_path = os.path.join(out_dir, "results_rows_component_ablation.json")
    with open(rows_path, "w", encoding="utf-8") as f:
        json.dump(results_rows, f, indent=2, ensure_ascii=False)

    csv_path = os.path.join(out_dir, "stats_summary_component_ablation.csv")
    write_stats_summary_csv(stats_rows, csv_path)
    json_path = os.path.join(out_dir, "stats_summary_component_ablation.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": stats_rows,
                "fieldnames": STATS_SUMMARY_FIELDNAMES,
                "note": "ablation family uses FDR(BH) adjusted p in p_value_holm field",
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Saved: {rows_path}")
    print(f"Saved: {csv_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()

