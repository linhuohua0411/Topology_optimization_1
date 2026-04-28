#!/usr/bin/env python3
"""
Run BTC-Docker graph optimizer vs baselines on collected samples.

Input:
  results/raw/BTC/BTC-MAIN-*/run-*/sample_*.json

Output (per experiment):
  results/raw/BTC/<experiment_id>/results_rows_graph_optimizer.json
  results/statistics/BTC/<experiment_id>/stats_summary_graph_optimizer.csv
  results/statistics/BTC/<experiment_id>/stats_summary_graph_optimizer.json
  results/statistics/BTC/<experiment_id>/run_manifest_graph_optimizer.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
from datetime import datetime, timezone
from typing import Any

import networkx as nx
import numpy as np

from scipy import stats

ROOT = "/home/ly/project/Topology_optimization_1"
RAW_ROOT = os.path.join(ROOT, "results", "raw", "BTC")
STAT_ROOT = os.path.join(ROOT, "results", "statistics", "BTC")
SRC_ROOT = os.path.join(ROOT, "src")

import sys

sys.path.insert(0, SRC_ROOT)
from models.baselines import attack_simulation_optimize, fpsblo_optimize, resinet_optimize, static_optimize
from models.global_optimizer import DEFAULT_PARAMS, get_edge_changes, run_optimization
from models.robustness import compute_R_components


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

METHODS = ["M-OUR", "M-RESI", "M-STAT", "M-ASIM", "M-FPS"]
METRICS = ["R", "lcc_ratio", "avg_path_len"]
WEIGHTS = (0.3, 0.4, 0.3)
FAIR_EDGE_BUDGET_FLOOR = 10
RAW_BASELINE_TIME_BUDGET_CAP_S = 8.0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_sample_paths(run_dir: str) -> list[str]:
    names = [n for n in os.listdir(run_dir) if re.match(r"sample_\d+\.json$", n)]
    names.sort()
    return [os.path.join(run_dir, n) for n in names]


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_sample_by_phase(run_dir: str, phase: str) -> tuple[dict[str, Any] | None, str | None]:
    paths = list_sample_paths(run_dir)
    for p in paths:
        s = load_json(p)
        if s.get("phase") == phase:
            return s, p
    if paths:
        return load_json(paths[0]), paths[0]
    return None, None


def _norm_node_id(endpoint: str) -> str:
    return endpoint.split(":", 1)[0]


def build_dense_adj_from_btc_sample(sample: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    topo = sample.get("topology", {}) or {}
    left_nodes = sorted(_norm_node_id(k) for k in topo.keys())
    right_nodes = sorted(
        {
            _norm_node_id(str(peer))
            for info in topo.values()
            for peer in (info.get("peers", []) or [])
        }
    )
    # BTC monitor peers are usually in a different IP namespace from monitored node keys.
    # Build a bipartite observation graph: monitored node <-> observed peer endpoint.
    node_ids = [f"node:{x}" for x in left_nodes] + [f"peer:{x}" for x in right_nodes]
    if not node_ids:
        return np.zeros((0, 0), dtype=np.float64), []
    idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    A = np.zeros((n, n), dtype=np.float64)

    for src_key, info in topo.items():
        src = f"node:{_norm_node_id(src_key)}"
        i = idx.get(src)
        if i is None:
            continue
        peers = info.get("peers", []) or []
        for peer in peers:
            dst = f"peer:{_norm_node_id(str(peer))}"
            j = idx.get(dst)
            if j is None or i == j:
                continue
            A[i, j] = 1.0
            A[j, i] = 1.0
    return A, node_ids


def compute_graph_stats(A: np.ndarray) -> dict[str, float]:
    n = int(A.shape[0])
    if n == 0:
        return {"lcc_ratio": 0.0, "avg_path_len": 0.0, "components": 0.0}
    G = nx.from_numpy_array((A > 0.0).astype(np.int8))
    comps = list(nx.connected_components(G))
    if not comps:
        return {"lcc_ratio": 0.0, "avg_path_len": 0.0, "components": 0.0}
    lcc_nodes = max(comps, key=len)
    lcc_ratio = len(lcc_nodes) / n
    if len(lcc_nodes) <= 1:
        apl = 0.0
    else:
        H = G.subgraph(lcc_nodes).copy()
        apl = float(nx.average_shortest_path_length(H))
    return {"lcc_ratio": float(lcc_ratio), "avg_path_len": apl, "components": float(len(comps))}


def last_hist_time_s(history: list[dict[str, Any]]) -> float:
    if not history:
        return 0.0
    t = history[-1].get("time")
    try:
        return float(t)
    except Exception:
        return 0.0


def choose_kmax(A0: np.ndarray) -> int:
    if A0.size == 0:
        return 10
    deg = np.sum(A0 > 0, axis=1)
    max_deg = int(np.max(deg)) if len(deg) else 10
    return max(10, int(round(0.8 * max_deg)))


def run_ours(A0: np.ndarray, seed: int, gradient_mode: str) -> tuple[np.ndarray, dict[str, float], list[dict[str, Any]], int]:
    params = DEFAULT_PARAMS.copy()
    params.update(
        {
            "seed": int(seed),
            "max_steps": 25,
            "min_steps": 5,
            "gradient_mode": gradient_mode,
            "gradient_sample_ratio": 0.02,
            "time_limit": 6.0,
            "k_max": choose_kmax(A0),
            "w1": float(WEIGHTS[0]),
            "w2": float(WEIGHTS[1]),
            "w3": float(WEIGHTS[2]),
        }
    )
    A_star, hist = run_optimization(A0, params, verbose=False)
    comps = compute_R_components(A_star, WEIGHTS)
    chg = get_edge_changes(A0, A_star)
    n_changes = len(chg["edges_to_add"]) + len(chg["edges_to_remove"]) + len(chg["edges_to_modify"])
    return A_star, comps, hist, n_changes


def run_baseline(
    method: str,
    A0: np.ndarray,
    seed: int,
    time_budget: float | None,
    edge_budget: int | None,
) -> tuple[np.ndarray, dict[str, float], list[dict[str, Any]], int]:
    kwargs: dict[str, Any] = {
        "seed": int(seed),
        "weights": WEIGHTS,
        "allow_disconnected_intermediate": True,
        "disconnect_penalty": 0.3,
    }
    if time_budget is not None:
        kwargs["time_limit"] = float(time_budget)
    if edge_budget is not None:
        kwargs["edge_change_budget"] = int(edge_budget)

    if method == "M-RESI":
        A_m, hist = resinet_optimize(A0, max_rewires=120, **kwargs)
    elif method == "M-STAT":
        A_m, hist = static_optimize(A0, max_iters=120, **kwargs)
    elif method == "M-ASIM":
        A_m, hist = attack_simulation_optimize(A0, n_attacks=8, max_rewires=80, **kwargs)
    elif method == "M-FPS":
        A_m, hist = fpsblo_optimize(A0, n_landmarks=8, max_iters=120, **kwargs)
    else:
        raise ValueError(method)

    comps = compute_R_components(A_m, WEIGHTS)
    chg = get_edge_changes(A0, A_m)
    n_changes = len(chg["edges_to_add"]) + len(chg["edges_to_remove"]) + len(chg["edges_to_modify"])
    return A_m, comps, hist, n_changes


def mean_std_ci95(values: list[float]) -> tuple[float, float, float, float]:
    n = len(values)
    mean = float(statistics.mean(values))
    std = float(statistics.stdev(values)) if n >= 2 else 0.0
    if n < 2:
        return mean, std, mean, mean
    try:
        low, high = stats.t.interval(0.95, n - 1, loc=mean, scale=stats.sem(values))
        return mean, std, float(low), float(high)
    except Exception:
        half = 1.96 * (std / math.sqrt(n))
        return mean, std, mean - half, mean + half


def holm_bonferroni(pvals: list[float | None]) -> list[float | None]:
    valid = [(i, p) for i, p in enumerate(pvals) if p is not None and math.isfinite(float(p))]
    out: list[float | None] = [None] * len(pvals)
    if not valid:
        return out
    valid.sort(key=lambda x: float(x[1]))
    m = len(valid)
    running = 0.0
    for rank, (idx, p) in enumerate(valid):
        adj = (m - rank) * float(p)
        running = max(running, adj)
        out[idx] = min(1.0, running)
    return out


def one_sample_test(deltas: list[float]) -> tuple[float | None, str, float | None, str]:
    n = len(deltas)
    if n < 2:
        return None, "insufficient_n", None, ""
    std = float(statistics.stdev(deltas))
    if std == 0.0:
        return None, "constant_delta", None, ""
    effect = float(statistics.mean(deltas) / std)
    test_name = "one_sample_t"
    p_value: float | None = None
    try:
        if n >= 3:
            _, p_norm = stats.shapiro(deltas)
            if p_norm < 0.05:
                test_name = "wilcoxon"
                _, p_value = stats.wilcoxon(deltas, alternative="two-sided")
            else:
                _, p_value = stats.ttest_1samp(deltas, popmean=0.0)
        else:
            _, p_value = stats.ttest_1samp(deltas, popmean=0.0)
    except Exception:
        p_value = None
        test_name = "descriptive_only"
    return (float(p_value) if p_value is not None else None, test_name, effect, "cohens_dz")


def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def aggregate_stats(exp_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for budget_variant in ("fair", "raw"):
        for metric in METRICS:
            ours = [r[metric] for r in rows if r["budget_variant"] == budget_variant and r["method_id"] == "M-OUR"]
            for base in ("M-RESI", "M-STAT", "M-ASIM", "M-FPS"):
                base_vals = [r[metric] for r in rows if r["budget_variant"] == budget_variant and r["method_id"] == base]
                if not ours or len(ours) != len(base_vals):
                    continue
                deltas = [float(a - b) for a, b in zip(ours, base_vals)]
                mean, std, ci_l, ci_h = mean_std_ci95(deltas)
                p, test_name, eff, eff_name = one_sample_test(deltas)
                out.append(
                    {
                        "comparison_id": f"CMP-{exp_id}-OUR-{base}",
                        "stat_key": f"{metric}.paired_delta",
                        "budget_variant": budget_variant,
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
            # Holm correction within one (experiment, budget, metric)
            idxs = [i for i, r in enumerate(out) if r["budget_variant"] == budget_variant and r["stat_key"] == f"{metric}.paired_delta"]
            pvals = [out[i]["p_value"] for i in idxs]
            holm = holm_bonferroni(pvals)
            for i, p_h in zip(idxs, holm):
                out[i]["p_value_holm"] = p_h
    return out


def run_experiment(exp_id: str, n_runs: int, seed_base: int, gradient_mode: str) -> None:
    exp_dir = os.path.join(RAW_ROOT, exp_id)
    if not os.path.isdir(exp_dir):
        print(f"[skip] {exp_id}: missing {exp_dir}")
        return

    sample_phase = "pre_attack" if exp_id == "BTC-MAIN-BASE" else "under_attack"
    rows: list[dict[str, Any]] = []
    run_manifest: list[dict[str, Any]] = []
    for run_idx in range(1, n_runs + 1):
        run_id = f"run-{run_idx:03d}"
        run_dir = os.path.join(exp_dir, run_id)
        if not os.path.isdir(run_dir):
            print(f"[skip] {exp_id}/{run_id}: run dir missing")
            continue
        sample, sample_path = pick_sample_by_phase(run_dir, sample_phase)
        if sample is None:
            print(f"[skip] {exp_id}/{run_id}: sample missing")
            continue
        A0, node_ids = build_dense_adj_from_btc_sample(sample)
        if A0.shape[0] < 2:
            print(f"[skip] {exp_id}/{run_id}: graph too small")
            continue

        seed = seed_base + run_idx
        A_ours, comps_ours, hist_ours, ours_changes = run_ours(A0, seed, gradient_mode=gradient_mode)
        ours_time = max(1.0, last_hist_time_s(hist_ours))
        fair_edge_budget = max(FAIR_EDGE_BUDGET_FLOOR, int(ours_changes))

        for budget_variant in ("raw", "fair"):
            for method in METHODS:
                if method == "M-OUR":
                    A_m, comps_m, hist_m, n_chg = A_ours, comps_ours, hist_ours, ours_changes
                else:
                    if budget_variant == "fair":
                        A_m, comps_m, hist_m, n_chg = run_baseline(
                            method, A0, seed, time_budget=ours_time, edge_budget=fair_edge_budget
                        )
                    else:
                        A_m, comps_m, hist_m, n_chg = run_baseline(
                            method, A0, seed, time_budget=RAW_BASELINE_TIME_BUDGET_CAP_S, edge_budget=None
                        )
                gm = compute_graph_stats(A_m)
                rows.append(
                    {
                        "timestamp_utc": now_utc(),
                        "platform": "BTC-Docker",
                        "experiment_id": exp_id,
                        "run_id": run_id,
                        "phase": sample_phase,
                        "attack_label": sample.get("attack_label", "none"),
                        "attack_params": {"attack_intensity": sample.get("attack_intensity", "0")},
                        "protocol_variant": "unified_full_protocol",
                        "budget_variant": budget_variant,
                        "method_id": method,
                        "R": float(comps_m["R"]),
                        "Rs": float(comps_m["R_s"]),
                        "Rc": float(comps_m["R_c"]),
                        "Rr": float(comps_m["R_r"]),
                        "lcc_ratio": float(gm["lcc_ratio"]),
                        "avg_path_len": float(gm["avg_path_len"]),
                        "components": int(gm["components"]),
                        "peer_count_btc_avg": float(np.mean(np.sum((A_m > 0).astype(np.float64), axis=1))),
                        "budget_cost": int(n_chg),
                        "time_to_converge": last_hist_time_s(hist_m),
                        "random_seed": int(seed),
                        "graph_initial_path": sample_path,
                    }
                )
        run_manifest.append(
            {
                "run_id": run_id,
                "seed": seed,
                "n_nodes": int(A0.shape[0]),
                "node_ids": node_ids,
                "gradient_mode": gradient_mode,
                "input_sample_phase": sample_phase,
                "ours_time_budget_s": ours_time,
                "fair_edge_budget": fair_edge_budget,
                "graph_initial_path": sample_path,
            }
        )
        print(f"[ok] {exp_id}/{run_id}: n_nodes={A0.shape[0]} ours_changes={ours_changes}")

    os.makedirs(exp_dir, exist_ok=True)
    with open(os.path.join(exp_dir, "results_rows_graph_optimizer.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    stat_dir = os.path.join(STAT_ROOT, exp_id)
    os.makedirs(stat_dir, exist_ok=True)
    stats_rows = aggregate_stats(exp_id, rows)
    with open(os.path.join(stat_dir, "stats_summary_graph_optimizer.json"), "w", encoding="utf-8") as f:
        json.dump(stats_rows, f, ensure_ascii=False, indent=2)
    write_csv(stats_rows, os.path.join(stat_dir, "stats_summary_graph_optimizer.csv"))
    with open(os.path.join(stat_dir, "run_manifest_graph_optimizer.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": now_utc(),
                "platform": "BTC-Docker",
                "experiment_id": exp_id,
                "n_runs_requested": n_runs,
                "n_runs_completed": len(run_manifest),
                "gradient_mode": gradient_mode,
                "weights": list(WEIGHTS),
                "statistics_artifacts": [
                    "stats_summary_graph_optimizer.csv",
                    "stats_summary_graph_optimizer.json",
                ],
                "runs": run_manifest,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[done] {exp_id}: rows={len(rows)} stats={len(stats_rows)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-runs", type=int, default=10)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--gradient-mode", choices=("R_s_only", "R_s_R_r", "full"), default="full")
    parser.add_argument("--experiments", type=str, default="all", help="Comma-separated ids or 'all'")
    args = parser.parse_args()

    exps = EXPERIMENTS
    if args.experiments.strip().lower() != "all":
        selected = {x.strip() for x in args.experiments.split(",") if x.strip()}
        exps = [e for e in EXPERIMENTS if e in selected]
    for exp_id in exps:
        run_experiment(exp_id, n_runs=args.n_runs, seed_base=args.seed_base, gradient_mode=args.gradient_mode)
    print("All BTC graph-optimizer experiments done.")


if __name__ == "__main__":
    main()

