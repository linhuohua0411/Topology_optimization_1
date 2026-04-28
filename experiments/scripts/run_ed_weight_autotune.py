#!/usr/bin/env python3
"""
ED-MAIN-BASE exploratory auto-tuning for robustness weights:
R = w1*R_s + w2*R_c + w3*R_r, with w constrained by softmax.

Protocol:
- Reuse frozen fair-budget baseline rows (same run_id pairing).
- Search weight candidates (fixed + random softmax trials).
- Optimize objective on R paired delta (ours - average of 4 baselines).
- Export candidate-level comparisons and full stats rows.
"""

from __future__ import annotations

import argparse
import json
import math
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


def softmax3(u: Tuple[float, float, float]) -> Tuple[float, float, float]:
    arr = np.asarray(u, dtype=float)
    arr = arr - np.max(arr)
    e = np.exp(arr)
    p = e / np.sum(e)
    return float(p[0]), float(p[1]), float(p[2])


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


def run_ours_once(
    A0: np.ndarray,
    seed: int,
    weights: Tuple[float, float, float],
    max_steps: int,
    min_steps: int,
    sigma: float,
    beta: float,
) -> Dict[str, float]:
    params = DEFAULT_PARAMS.copy()
    params.update(
        {
            "seed": int(seed),
            "max_steps": int(max_steps),
            "min_steps": int(min_steps),
            "gradient_mode": "full",
            "gradient_sample_ratio": 0.05,
            "k_max": choose_adaptive_kmax(compute_graph_stats(A0, WEIGHTS)),
            "w1": float(weights[0]),
            "w2": float(weights[1]),
            "w3": float(weights[2]),
            "sigma": float(sigma),
            "beta": float(beta),
        }
    )
    A_star, hist = run_optimization(A0, params=params, verbose=False)
    comps = compute_R_components(A_star, (params["w1"], params["w2"], params["w3"]))
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
    }


def make_candidates(n_random: int, seed: int) -> List[Dict]:
    rng = np.random.RandomState(seed)
    cands = [
        {"candidate_id": "fixed_default", "w1": 0.3, "w2": 0.4, "w3": 0.3, "source": "fixed"},
        {"candidate_id": "connectivity_bias", "w1": 0.25, "w2": 0.55, "w3": 0.20, "source": "seeded"},
    ]
    for i in range(n_random):
        u = (
            float(rng.uniform(-1.0, 1.0)),
            float(rng.uniform(-1.0, 1.0)),
            float(rng.uniform(-1.0, 1.0)),
        )
        w1, w2, w3 = softmax3(u)
        cands.append(
            {
                "candidate_id": f"auto_{i:02d}",
                "w1": w1,
                "w2": w2,
                "w3": w3,
                "source": "softmax_random",
                "u": u,
            }
        )
    return cands


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", default="ED-MAIN-BASE")
    parser.add_argument("--raw-root", default="results/raw/ETH")
    parser.add_argument("--n-runs", type=int, default=6)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--sample-pick", choices=("first_pre_attack", "first_sample"), default="first_pre_attack")
    parser.add_argument(
        "--frozen-baseline-rows",
        default="results/raw/ETH/ED-MAIN-BASE/results_rows_graph_optimizer.json",
    )
    parser.add_argument("--n-random", type=int, default=6)
    parser.add_argument("--search-seed", type=int, default=20260421)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--min-steps", type=int, default=12)
    parser.add_argument("--sigma", type=float, default=0.03)
    parser.add_argument("--beta", type=float, default=0.08)
    parser.add_argument(
        "--out-dir",
        default="results/ablation_snapshots/weight_autotune_ed_base",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    frozen = load_frozen_baselines(args.frozen_baseline_rows, args.experiment_id)
    candidates = make_candidates(args.n_random, args.search_seed)

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
        for c in candidates:
            weights = (float(c["w1"]), float(c["w2"]), float(c["w3"]))
            ours = run_ours_once(
                A0,
                seed=seed,
                weights=weights,
                max_steps=args.max_steps,
                min_steps=args.min_steps,
                sigma=args.sigma,
                beta=args.beta,
            )
            result_rows.append(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "platform": "eth_docker",
                    "experiment_id": args.experiment_id,
                    "run_id": run_id,
                    "protocol_variant": "exploratory_weight_autotune",
                    "budget_variant": "fair",
                    "method_id": "M-OUR",
                    "candidate_id": c["candidate_id"],
                    "w1": c["w1"],
                    "w2": c["w2"],
                    "w3": c["w3"],
                    "graph_initial_path": sample_path,
                    **ours,
                }
            )
            for m in BASELINES:
                b = frozen[run_id].get(m)
                if not b:
                    continue
                for metric in METRICS:
                    delta_rows.append(
                        {
                            "candidate_id": c["candidate_id"],
                            "run_id": run_id,
                            "method_id": m,
                            "stat_key": f"{metric}.paired_delta",
                            "delta": float(ours[metric] - b[metric]),
                        }
                    )
        print(f"[ok] {run_id}")

    # objective: mean R delta against average baseline per run
    by_candidate_run: Dict[Tuple[str, str], List[float]] = {}
    for d in delta_rows:
        if d["stat_key"] != "R.paired_delta":
            continue
        by_candidate_run.setdefault((d["candidate_id"], d["run_id"]), []).append(float(d["delta"]))

    objective_by_candidate: Dict[str, List[float]] = {}
    for (cid, run_id), vals in by_candidate_run.items():
        if vals:
            objective_by_candidate.setdefault(cid, []).append(float(np.mean(vals)))

    candidate_summary = []
    for c in candidates:
        cid = c["candidate_id"]
        vals = objective_by_candidate.get(cid, [])
        mean, std, ci_l, ci_h = mean_std_ci95_t(vals) if vals else (0.0, 0.0, 0.0, 0.0)
        candidate_summary.append(
            {
                "candidate_id": cid,
                "w1": c["w1"],
                "w2": c["w2"],
                "w3": c["w3"],
                "n_runs_used": len(vals),
                "objective_name": "R_delta_vs_mean_baselines",
                "objective_mean": mean,
                "objective_std": std,
                "objective_ci95_low": ci_l,
                "objective_ci95_high": ci_h,
            }
        )
    candidate_summary.sort(key=lambda x: x["objective_mean"], reverse=True)
    best = candidate_summary[0] if candidate_summary else None
    fixed = next((x for x in candidate_summary if x["candidate_id"] == "fixed_default"), None)

    # build tifs-style stats rows for all candidates
    stats_rows: List[Dict] = []
    for c in candidates:
        cid = c["candidate_id"]
        for metric in METRICS:
            pvals: List[Optional[float]] = []
            temp: List[Dict] = []
            for m in BASELINES:
                deltas = [
                    float(d["delta"])
                    for d in delta_rows
                    if d["candidate_id"] == cid and d["method_id"] == m and d["stat_key"] == f"{metric}.paired_delta"
                ]
                if len(deltas) < 2:
                    continue
                mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
                p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
                pvals.append(p_raw)
                temp.append(
                    {
                        "comparison_id": f"CMP-ABL-WAUTO-{args.experiment_id}-{cid}-OUR-{m}",
                        "stat_key": f"{metric}.paired_delta",
                        "budget_variant": "fair",
                        "experiment_id": args.experiment_id,
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

    with open(os.path.join(out_dir, "results_rows_weight_autotune.json"), "w", encoding="utf-8") as f:
        json.dump(result_rows, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "paired_deltas_weight_autotune.json"), "w", encoding="utf-8") as f:
        json.dump(delta_rows, f, ensure_ascii=False, indent=2)
    write_stats_summary_csv(stats_rows, os.path.join(out_dir, "stats_summary_weight_autotune.csv"))
    with open(os.path.join(out_dir, "stats_summary_weight_autotune.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "rows": stats_rows,
                "fieldnames": STATS_SUMMARY_FIELDNAMES,
                "note": "Exploratory weight autotune; p_value_holm stores FDR(BH) within candidate+metric family.",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(os.path.join(out_dir, "candidate_objective_summary.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "protocol_variant": "exploratory_weight_autotune",
                "experiment_id": args.experiment_id,
                "objective_name": "R_delta_vs_mean_baselines",
                "candidate_summary": candidate_summary,
                "best_candidate": best,
                "fixed_candidate": fixed,
                "better_than_fixed": bool(best and fixed and best["objective_mean"] > fixed["objective_mean"]),
                "objective_gain_vs_fixed": (
                    float(best["objective_mean"] - fixed["objective_mean"])
                    if best is not None and fixed is not None
                    else None
                ),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(os.path.join(out_dir, "run_manifest_weight_autotune.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "protocol_variant": "exploratory_weight_autotune",
                "experiment_id": args.experiment_id,
                "n_runs_requested": args.n_runs,
                "n_random": args.n_random,
                "search_seed": args.search_seed,
                "max_steps": args.max_steps,
                "min_steps": args.min_steps,
                "sigma": args.sigma,
                "beta": args.beta,
                "frozen_baseline_rows": os.path.abspath(args.frozen_baseline_rows),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Saved: {out_dir}")


if __name__ == "__main__":
    main()
