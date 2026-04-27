#!/usr/bin/env python3
"""
Compare fixed weights vs online adaptive weights for M-OUR,
using identical run_id pairing and frozen baseline rows.

Outputs go to results/ablation_snapshots/adaptive_vs_fixed_ed/
to avoid polluting main statistics directories.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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


BASELINES = ("M-RESI", "M-STAT", "M-ASIM", "M-FPS")
METRICS = ("R", "lcc_ratio", "avg_path_len")
SCENARIOS = ("ED-MAIN-BASE", "ED-MAIN-LINK", "ED-MAIN-NETEM")


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


def run_ours_variant(A0: np.ndarray, seed: int, mode: str, max_steps: int, min_steps: int) -> Dict:
    params = DEFAULT_PARAMS.copy()
    params.update(
        {
            "seed": int(seed),
            "max_steps": int(max_steps),
            "min_steps": int(min_steps),
            "gradient_mode": "full",
            "gradient_sample_ratio": 0.05,
            "k_max": choose_adaptive_kmax(compute_graph_stats(A0, WEIGHTS)),
        }
    )
    if mode == "adaptive":
        params.update(
            {
                "adaptive_weights_enabled": True,
                "adaptive_update_every": 5,
                "adaptive_warmup_steps": 10,
                "adaptive_eta": 0.12,
                "adaptive_min_weight": 0.10,
                "adaptive_max_weight": 0.70,
            }
        )
    A_star, hist = run_optimization(A0, params=params, verbose=False)
    # final runtime weights used for component decomposition
    w_final = (
        float(hist[-1].get("w1", params["w1"])),
        float(hist[-1].get("w2", params["w2"])),
        float(hist[-1].get("w3", params["w3"])),
    )
    comps = compute_R_components(A_star, w_final)
    g = compute_graph_stats(A_star, WEIGHTS)
    return {
        "R": float(comps["R"]),
        "Rs": float(comps["R_s"]),
        "Rc": float(comps["R_c"]),
        "Rr": float(comps["R_r"]),
        "lcc_ratio": float(g["lcc_ratio"]),
        "avg_path_len": float(g["avg_path_length"]),
        "steps": int(max(0, len(hist) - 1)),
        "w1_final": w_final[0],
        "w2_final": w_final[1],
        "w3_final": w_final[2],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default="results/raw/eth_docker")
    parser.add_argument("--n-runs", type=int, default=6)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--min-steps", type=int, default=12)
    parser.add_argument("--sample-pick", choices=("first_pre_attack", "first_sample"), default="first_pre_attack")
    parser.add_argument(
        "--out-dir",
        default="results/ablation_snapshots/adaptive_vs_fixed_ed",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    rows: List[Dict] = []
    method_vs_base_deltas: List[Dict] = []
    adaptive_minus_fixed: List[Dict] = []

    for exp_id in SCENARIOS:
        frozen_path = os.path.join(args.raw_root, exp_id, "results_rows_graph_optimizer.json")
        frozen = load_frozen_baselines(frozen_path, exp_id)
        for run_idx in range(args.n_runs):
            run_id = f"run-{run_idx:03d}"
            seed = args.seed_base + run_idx
            run_dir = os.path.join(args.raw_root, exp_id, run_id)
            sample_paths = list_sample_json_paths(run_dir)
            sample, sample_path = pick_collected_sample(sample_paths, args.sample_pick)
            if sample is None or run_id not in frozen:
                continue
            A0, _, _ = build_dense_adj_from_sample(sample)
            fixed = run_ours_variant(A0, seed, "fixed", args.max_steps, args.min_steps)
            adapt = run_ours_variant(A0, seed, "adaptive", args.max_steps, args.min_steps)

            for mode, r in (("fixed", fixed), ("adaptive", adapt)):
                rows.append(
                    {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "platform": "eth_docker",
                        "experiment_id": exp_id,
                        "run_id": run_id,
                        "protocol_variant": "exploratory_adaptive_vs_fixed",
                        "budget_variant": "fair",
                        "method_id": "M-OUR",
                        "weight_mode": mode,
                        "graph_initial_path": sample_path,
                        **r,
                    }
                )
                for m in BASELINES:
                    b = frozen[run_id].get(m)
                    if not b:
                        continue
                    for metric in METRICS:
                        method_vs_base_deltas.append(
                            {
                                "experiment_id": exp_id,
                                "run_id": run_id,
                                "weight_mode": mode,
                                "baseline": m,
                                "stat_key": f"{metric}.paired_delta",
                                "delta": float(r[metric] - b[metric]),
                            }
                        )
            for metric in METRICS:
                adaptive_minus_fixed.append(
                    {
                        "experiment_id": exp_id,
                        "run_id": run_id,
                        "stat_key": f"{metric}.adaptive_minus_fixed",
                        "delta": float(adapt[metric] - fixed[metric]),
                    }
                )
            print(f"[ok] {exp_id} {run_id}")

    stats_rows: List[Dict] = []
    # 1) OUR-vs-baselines deltas under each mode
    for exp_id in SCENARIOS:
        for mode in ("fixed", "adaptive"):
            for metric in METRICS:
                pvals: List[Optional[float]] = []
                temp: List[Dict] = []
                for m in BASELINES:
                    deltas = [
                        float(d["delta"])
                        for d in method_vs_base_deltas
                        if d["experiment_id"] == exp_id
                        and d["weight_mode"] == mode
                        and d["baseline"] == m
                        and d["stat_key"] == f"{metric}.paired_delta"
                    ]
                    if len(deltas) < 2:
                        continue
                    mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
                    p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
                    pvals.append(p_raw)
                    temp.append(
                        {
                            "comparison_id": f"CMP-ABL-ADP-{exp_id}-{mode}-OUR-{m}",
                            "stat_key": f"{metric}.paired_delta",
                            "budget_variant": "fair",
                            "experiment_id": exp_id,
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
                for r, q in zip(temp, qvals):
                    r["p_value_holm"] = q
                    stats_rows.append(r)

    # 2) adaptive - fixed (same OUR, paired on run_id)
    for exp_id in SCENARIOS:
        pvals: List[Optional[float]] = []
        temp: List[Dict] = []
        for metric in METRICS:
            deltas = [
                float(d["delta"])
                for d in adaptive_minus_fixed
                if d["experiment_id"] == exp_id and d["stat_key"] == f"{metric}.adaptive_minus_fixed"
            ]
            if len(deltas) < 2:
                continue
            mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
            p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
            pvals.append(p_raw)
            temp.append(
                {
                    "comparison_id": f"CMP-ABL-ADP-{exp_id}-ADAPTIVE-minus-FIXED",
                    "stat_key": f"{metric}.adaptive_minus_fixed",
                    "budget_variant": "fair",
                    "experiment_id": exp_id,
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
        for r, q in zip(temp, qvals):
            r["p_value_holm"] = q
            stats_rows.append(r)

    with open(os.path.join(out_dir, "results_rows_adaptive_vs_fixed.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "deltas_our_vs_baselines.json"), "w", encoding="utf-8") as f:
        json.dump(method_vs_base_deltas, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "deltas_adaptive_minus_fixed.json"), "w", encoding="utf-8") as f:
        json.dump(adaptive_minus_fixed, f, ensure_ascii=False, indent=2)
    write_stats_summary_csv(stats_rows, os.path.join(out_dir, "stats_summary_adaptive_vs_fixed.csv"))
    with open(os.path.join(out_dir, "stats_summary_adaptive_vs_fixed.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": stats_rows,
                "fieldnames": STATS_SUMMARY_FIELDNAMES,
                "note": "Exploratory adaptive-vs-fixed comparison; p_value_holm stores FDR(BH) within each family.",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(os.path.join(out_dir, "run_manifest_adaptive_vs_fixed.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "protocol_variant": "exploratory_adaptive_vs_fixed",
                "scenarios": list(SCENARIOS),
                "n_runs_requested": args.n_runs,
                "max_steps": args.max_steps,
                "min_steps": args.min_steps,
                "adaptive_settings": {
                    "adaptive_update_every": 5,
                    "adaptive_warmup_steps": 10,
                    "adaptive_eta": 0.12,
                    "adaptive_min_weight": 0.10,
                    "adaptive_max_weight": 0.70,
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Saved: {out_dir}")


if __name__ == "__main__":
    main()
