#!/usr/bin/env python3
"""
Eth-Docker graph optimizer vs baselines (M-OUR vs M-RESI/M-STAT/M-ASIM/M-FPS).

**Protocol**：与观测链并列的 **必做** 步骤（见 ``protocol/04`` §二、``protocol/03`` §0.1/§6.4、``claim_traceability.md`` C007）。

**Default**: reads `collect_eth_docker_scenarios.py` outputs —
`results/raw/eth_docker/<experiment_id>/run-*/sample_*.json` (topology under `topology`).

**Legacy**: `--from-snapshots` + `--snapshot-dir` uses flat `snapshot_*.json` with top-level `edges`
(one A0 for all runs; backward compatible).

Outputs use *_graph_optimizer* filenames so they do not overwrite observation `results_rows.json`.

Parallelism: use ``--parallel-runs N`` (ProcessPoolExecutor) to run independent ``run_idx`` jobs
on up to N processes; each job still runs M-OUR then baselines in sequence for fair budget.

M-OUR gradient: ``--gradient-mode`` (``full`` default, ``R_s_only``, ``R_s_R_r``) is written to
``results_rows_graph_optimizer.json`` and run manifests for TIFS traceability.
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np

_EXP = os.path.dirname(__file__)
EXP_DIR = os.path.abspath(os.path.join(_EXP, ".."))
ROOT = os.path.abspath(os.path.join(_EXP, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, EXP_DIR)
sys.path.insert(0, _EXP)

from compute_eth_docker_metrics_fast import build_dense_adj_from_sample
from experiment_protocol import (
    PROTOCOL_VERSION,
    WEIGHTS,
    USE_SCENARIO_WEIGHTS,
    SCENARIO_WEIGHTS,
    ATTACK_TIERS,
    DEFAULT_ATTACK_TIER,
    N_RUNS_DEFAULT,
    KMAX_FLOOR,
    KMAX_RATIO,
    KMAX_BUSINESS_CAP,
    BASELINE_ALLOW_DISCONNECTED_INTERMEDIATE,
    BASELINE_DISCONNECT_PENALTY,
    FAIR_EDGE_BUDGET_FLOOR,
    OURS_TIME_BUDGET_CAP_S,
    RAW_BASELINE_TIME_BUDGET_CAP_S,
    CONNECTIVITY_REPAIR_WEIGHT,
    CONNECTIVITY_REPAIR_BUDGET_RATIO,
    CONNECTIVITY_REPAIR_BUDGET_MIN,
    CONNECTIVITY_REPAIR_PENALTY_LAMBDA,
)
from graph_metrics import attack_graph, compute_graph_stats
from models.baselines import (
    attack_simulation_optimize,
    fpsblo_optimize,
    resinet_optimize,
    static_optimize,
)
from models.global_optimizer import DEFAULT_PARAMS, get_edge_changes, run_optimization
from models.robustness import compute_R_components
from tifs_stats import build_method_comparison_rows, write_stats_summary_csv

DEFAULT_RAW_ROOT = os.path.join(ROOT, "results", "raw", "eth_docker")
DEFAULT_SNAPSHOT_DIR = os.path.join(ROOT, "results", "derived", "eth_snapshots")
RESULTS_BASE = os.path.join(ROOT, "results")


def choose_adaptive_kmax(stats):
    ratio_target = int(round(KMAX_RATIO * stats["max_degree"]))
    return int(min(KMAX_BUSINESS_CAP, max(KMAX_FLOOR, ratio_target)))


def get_experiment_weights(exp_id):
    base_id = exp_id
    for suffix in ("-low", "-mid", "-high"):
        if exp_id.endswith(suffix):
            base_id = exp_id[: -len(suffix)]
            break
    if USE_SCENARIO_WEIGHTS and base_id in SCENARIO_WEIGHTS:
        return tuple(float(x) for x in SCENARIO_WEIGHTS[base_id])
    return tuple(float(x) for x in WEIGHTS)


def _last_hist_time_s(history) -> float:
    """Wall-clock seconds at last optimizer step (0.0 if missing)."""
    if not history:
        return 0.0
    last = history[-1]
    if isinstance(last, dict) and "time" in last:
        try:
            return float(last["time"])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def load_eth_snapshots(snapshot_dir: str):
    if not os.path.isdir(snapshot_dir):
        raise RuntimeError(f"snapshot directory missing: {snapshot_dir}")
    files = sorted(
        f for f in os.listdir(snapshot_dir) if f.startswith("snapshot_") and f.endswith(".json")
    )
    if not files:
        raise RuntimeError(f"no snapshot_*.json in {snapshot_dir}")

    snapshots = []
    node_id_set = set()
    for sf in files:
        with open(os.path.join(snapshot_dir, sf), "r", encoding="utf-8") as f:
            snap = json.load(f)
        snapshots.append(snap)
        for e in snap.get("edges", []):
            if len(e) >= 2:
                node_id_set.add(int(e[0]))
                node_id_set.add(int(e[1]))
        for nid in snap.get("peer_counts", {}).keys():
            node_id_set.add(int(nid))

    node_ids = sorted(node_id_set) if node_id_set else list(range(int(snapshots[0]["n_nodes"])))
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    matrices = []
    for snap in snapshots:
        A = np.zeros((n, n), dtype=np.float64)
        for e in snap.get("edges", []):
            if len(e) < 2:
                continue
            src, dst = int(e[0]), int(e[1])
            if src in id_to_idx and dst in id_to_idx:
                i, j = id_to_idx[src], id_to_idx[dst]
                A[i, j] = 1.0
                A[j, i] = 1.0
        matrices.append(A)
    return matrices, np.array(node_ids, dtype=np.int64)


def list_sample_json_paths(run_dir: str):
    if not os.path.isdir(run_dir):
        return []
    names = [n for n in os.listdir(run_dir) if re.match(r"sample_\d+\.json$", n)]
    return [os.path.join(run_dir, n) for n in sorted(names)]


def pick_collected_sample(paths, pick: str):
    """Return (sample_dict, path) for graph construction."""
    if not paths:
        return None, None
    if pick == "first_sample":
        p = paths[0]
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f), p
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            s = json.load(f)
        if s.get("phase") == "pre_attack":
            return s, p
    with open(paths[0], "r", encoding="utf-8") as f:
        return json.load(f), paths[0]


def run_ours(A0, seed, weights, time_budget=None, gradient_mode="full"):
    stats0 = compute_graph_stats(A0, weights)
    params = DEFAULT_PARAMS.copy()
    params.update(
        {
            "seed": int(seed),
            "max_steps": 120,
            "min_steps": 25,
            "gradient_mode": gradient_mode,
            "gradient_sample_ratio": 0.05,
            "k_max": choose_adaptive_kmax(stats0),
            "w1": float(weights[0]),
            "w2": float(weights[1]),
            "w3": float(weights[2]),
            "connectivity_repair_weight": float(CONNECTIVITY_REPAIR_WEIGHT),
            "connectivity_repair_budget_ratio": float(CONNECTIVITY_REPAIR_BUDGET_RATIO),
            "connectivity_repair_budget_min": int(CONNECTIVITY_REPAIR_BUDGET_MIN),
            "connectivity_repair_penalty_lambda": float(CONNECTIVITY_REPAIR_PENALTY_LAMBDA),
        }
    )
    if time_budget is not None:
        params["time_limit"] = float(time_budget)
    else:
        # Cap OURS runtime to avoid exploding fair-time budgets.
        params["time_limit"] = float(OURS_TIME_BUDGET_CAP_S)
    A_star, hist = run_optimization(A0, params, verbose=False)
    comps = compute_R_components(A_star, weights)
    chg = get_edge_changes(A0, A_star)
    n_changes = len(chg["edges_to_add"]) + len(chg["edges_to_remove"]) + len(chg["edges_to_modify"])
    return A_star, comps, hist, n_changes


def run_baseline(method_name, A0, seed, weights, time_budget=None, edge_budget=None):
    kwargs = {
        "seed": int(seed),
        "weights": weights,
        "allow_disconnected_intermediate": BASELINE_ALLOW_DISCONNECTED_INTERMEDIATE,
        "disconnect_penalty": BASELINE_DISCONNECT_PENALTY,
    }
    if time_budget is not None:
        kwargs["time_limit"] = float(time_budget)
    if edge_budget is not None:
        kwargs["edge_change_budget"] = int(edge_budget)

    if method_name == "M-RESI":
        A_m, hist = resinet_optimize(A0, max_rewires=3000, **kwargs)
    elif method_name == "M-STAT":
        A_m, hist = static_optimize(A0, max_iters=3000, **kwargs)
    elif method_name == "M-ASIM":
        A_m, hist = attack_simulation_optimize(A0, n_attacks=40, max_rewires=1200, **kwargs)
    elif method_name == "M-FPS":
        A_m, hist = fpsblo_optimize(A0, n_landmarks=15, max_iters=1500, **kwargs)
    else:
        raise ValueError(method_name)

    comps = compute_R_components(A_m, weights)
    chg = get_edge_changes(A0, A_m)
    n_changes = len(chg["edges_to_add"]) + len(chg["edges_to_remove"]) + len(chg["edges_to_modify"])
    return A_m, comps, hist, n_changes


def phase_attack_eval(A_before, A_after, attack_type, frac, n_repeats, run_seed):
    base_scores = [attack_graph(A_before, attack_type, frac, seed=run_seed * 100 + i) for i in range(n_repeats)]
    opt_scores = [attack_graph(A_after, attack_type, frac, seed=run_seed * 100 + i) for i in range(n_repeats)]
    return {
        "baseline_lcc": float(np.mean([s["lcc_ratio"] for s in base_scores])),
        "optimized_lcc": float(np.mean([s["lcc_ratio"] for s in opt_scores])),
        "baseline_path": float(np.mean([s["avg_path_length"] for s in base_scores])),
        "optimized_path": float(np.mean([s["avg_path_length"] for s in opt_scores])),
        "baseline_components": float(np.mean([s["n_components"] for s in base_scores])),
        "optimized_components": float(np.mean([s["n_components"] for s in opt_scores])),
    }


def run_graph_optimizer_single_job(job):
    """
    One (experiment, run_idx) graph-optimizer job for ProcessPoolExecutor.
    ``job`` is a plain dict (picklable). Each run still: run_ours -> baselines (raw/fair).
    """
    exp_id = job["exp_id"]
    attack_label = job["attack_label"]
    attack_cfg = job["attack_cfg"]
    run_idx = int(job["run_idx"])
    seed = int(job["seed"])
    raw_root = job["raw_root"]
    sample_pick = job["sample_pick"]
    from_snapshots = bool(job["from_snapshots"])
    attack_repeats = int(job["attack_repeats"])
    gradient_mode = job.get("gradient_mode") or "full"
    weights = tuple(float(x) for x in job["weights"])
    attack_tier = job.get("attack_tier")
    methods = ["M-OUR", "M-RESI", "M-STAT", "M-ASIM", "M-FPS"]

    run_id = f"run-{run_idx:03d}"
    sample_path = None

    if from_snapshots:
        A0 = np.asarray(job["legacy_A0"], dtype=np.float64).copy()
    else:
        run_dir = os.path.join(raw_root, exp_id, run_id)
        paths = list_sample_json_paths(run_dir)
        sample, sample_path = pick_collected_sample(paths, sample_pick)
        if sample is None:
            return {
                "run_idx": run_idx,
                "skipped": True,
                "skip_reason": f"no sample_*.json in {run_dir}",
                "rows": [],
                "manifest": None,
            }
        A0, _, _ordered = build_dense_adj_from_sample(sample)
        if A0.shape[0] < 2:
            return {
                "run_idx": run_idx,
                "skipped": True,
                "skip_reason": f"graph too small n={A0.shape[0]} from {sample_path}",
                "rows": [],
                "manifest": None,
            }

    n_nodes = int(A0.shape[0])

    A_ours, comps_ours, hist_ours, ours_changes = run_ours(
        A0, seed, weights=weights, gradient_mode=gradient_mode
    )
    ours_time = _last_hist_time_s(hist_ours)
    fair_edge_budget = max(FAIR_EDGE_BUDGET_FLOOR, int(ours_changes))

    exp_rows = []
    for budget_variant in ("raw", "fair"):
        for method in methods:
            if method == "M-OUR":
                A_m, comps_m, hist_m, n_chg = A_ours, comps_ours, hist_ours, ours_changes
            else:
                if budget_variant == "fair":
                    A_m, comps_m, hist_m, n_chg = run_baseline(
                        method, A0, seed, weights=weights, time_budget=ours_time, edge_budget=fair_edge_budget
                    )
                else:
                    A_m, comps_m, hist_m, n_chg = run_baseline(
                        method,
                        A0,
                        seed,
                        weights=weights,
                        time_budget=RAW_BASELINE_TIME_BUDGET_CAP_S,
                    )

            stats_m = compute_graph_stats(A_m, weights)
            row = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "platform": "eth_docker",
                "experiment_id": exp_id,
                "run_id": run_id,
                "phase": "post_recovery" if attack_label != "none" else "pre_attack",
                "attack_label": attack_label,
                "attack_params": (
                    {
                        "mode": attack_cfg[0],
                        "fraction": attack_cfg[1],
                        "attack_tier": attack_tier,
                    }
                    if attack_cfg
                    else {"attack_tier": "none"}
                ),
                "protocol_variant": "unified_full_protocol",
                "protocol_version": PROTOCOL_VERSION,
                "gradient_mode": gradient_mode,
                "weights": [float(weights[0]), float(weights[1]), float(weights[2])],
                "budget_variant": budget_variant,
                "method_id": method,
                "R": float(comps_m["R"]),
                "Rs": float(comps_m["R_s"]),
                "Rc": float(comps_m["R_c"]),
                "Rr": float(comps_m["R_r"]),
                "lcc_ratio": float(stats_m["lcc_ratio"]),
                "avg_path_len": float(stats_m["avg_path_length"]),
                "components": int(stats_m["n_components"]),
                "peer_count_el": float(np.mean(np.sum(A_m > 0, axis=1))),
                "budget_cost": int(n_chg),
                "time_to_converge": _last_hist_time_s(hist_m),
                "random_seed": int(seed),
                "graph_initial_source": "legacy_snapshot" if from_snapshots else "collected_sample_json",
                "graph_initial_path": sample_path,
            }
            if attack_cfg is not None:
                atk = phase_attack_eval(A0, A_m, attack_cfg[0], attack_cfg[1], attack_repeats, seed)
                row.update(
                    {
                        "under_attack_baseline_lcc": atk["baseline_lcc"],
                        "under_attack_method_lcc": atk["optimized_lcc"],
                        "under_attack_baseline_path": atk["baseline_path"],
                        "under_attack_method_path": atk["optimized_path"],
                    }
                )
            exp_rows.append(row)

    manifest = {
        "run_id": run_id,
        "seed": int(seed),
        "attack_tier": attack_tier or "none",
        "gradient_mode": gradient_mode,
        "protocol_version": PROTOCOL_VERSION,
        "weights": [float(weights[0]), float(weights[1]), float(weights[2])],
        "ours_time_budget_s": ours_time,
        "fair_edge_budget": int(fair_edge_budget),
        "n_nodes": n_nodes,
        "graph_initial_path": sample_path,
    }
    return {"run_idx": run_idx, "skipped": False, "skip_reason": None, "rows": exp_rows, "manifest": manifest}


def _build_graph_optimizer_job(
    exp_id,
    attack_label,
    attack_cfg,
    run_idx,
    seed,
    raw_root_abs,
    sample_pick,
    from_snapshots,
    snapshot_dir_abs,
    attack_repeats,
    legacy_A0,
    gradient_mode,
    weights,
    attack_tier,
):
    j = {
        "exp_id": exp_id,
        "attack_label": attack_label,
        "attack_cfg": attack_cfg,
        "run_idx": run_idx,
        "seed": seed,
        "raw_root": raw_root_abs,
        "sample_pick": sample_pick,
        "from_snapshots": from_snapshots,
        "snapshot_dir": snapshot_dir_abs or "",
        "attack_repeats": attack_repeats,
        "gradient_mode": gradient_mode,
        "weights": [float(weights[0]), float(weights[1]), float(weights[2])],
        "attack_tier": attack_tier,
    }
    if from_snapshots and legacy_A0 is not None:
        j["legacy_A0"] = np.asarray(legacy_A0, dtype=np.float64).copy()
    return j


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-runs", type=int, default=N_RUNS_DEFAULT)
    parser.add_argument("--attack-repeats", type=int, default=5)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument(
        "--raw-root",
        default=DEFAULT_RAW_ROOT,
        help="Eth-Docker collection root (default: results/raw/eth_docker)",
    )
    parser.add_argument(
        "--sample-pick",
        choices=("first_pre_attack", "first_sample"),
        default="first_pre_attack",
        help="Which sample_*.json to build A0 from",
    )
    parser.add_argument(
        "--from-snapshots",
        action="store_true",
        help="Legacy: use snapshot_*.json under --snapshot-dir as one A0 for all runs",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=DEFAULT_SNAPSHOT_DIR,
        help="Used only with --from-snapshots",
    )
    parser.add_argument(
        "--parallel-runs",
        type=int,
        default=1,
        metavar="N",
        help="Run up to N run_idx jobs in parallel via ProcessPoolExecutor (default 1 = sequential).",
    )
    parser.add_argument(
        "--gradient-mode",
        choices=("R_s_only", "R_s_R_r", "full"),
        default="full",
        help="M-OUR gradient ablation (default full: strongest objective alignment; use R_s_only/R_s_R_r for ablation).",
    )
    parser.add_argument(
        "--attack-tier",
        choices=("low", "mid", "high", "all"),
        default=DEFAULT_ATTACK_TIER,
        help="Attack tier for LINK/NETEM. Use 'all' to run low/mid/high in one pass.",
    )
    args = parser.parse_args()

    parallel_runs = max(1, int(args.parallel_runs))
    parallel_runs = min(parallel_runs, max(1, int(args.n_runs)))

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = os.path.join(RESULTS_BASE, "raw", "eth_docker")
    proc_dir = os.path.join(RESULTS_BASE, "processed", "eth_docker")
    stat_dir = os.path.join(RESULTS_BASE, "statistics")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(proc_dir, exist_ok=True)
    os.makedirs(stat_dir, exist_ok=True)

    if args.attack_tier == "all":
        tier_items = [("low", ATTACK_TIERS["low"]), ("mid", ATTACK_TIERS["mid"]), ("high", ATTACK_TIERS["high"])]
    else:
        tier_items = [(args.attack_tier, ATTACK_TIERS[args.attack_tier])]

    experiments = [("ED-MAIN-BASE", "none", None, "none")]
    for tier_name, tier_frac in tier_items:
        experiments.append((f"ED-MAIN-LINK-{tier_name}", "link_down", ("targeted", tier_frac), tier_name))
        experiments.append((f"ED-MAIN-NETEM-{tier_name}", "tc_netem", ("random", tier_frac), tier_name))

    legacy_A0 = None
    if args.from_snapshots:
        os.makedirs(args.snapshot_dir, exist_ok=True)
        matrices, _legacy_node_ids = load_eth_snapshots(args.snapshot_dir)
        legacy_A0 = matrices[0]

    raw_root_abs = os.path.abspath(args.raw_root)
    snapshot_dir_abs = os.path.abspath(args.snapshot_dir) if args.from_snapshots else ""

    global_rows = []
    for exp_id, attack_label, attack_cfg, attack_tier in experiments:
        print(f"\n=== {exp_id} ({attack_label}) ===")
        if parallel_runs > 1:
            print(f"  parallel-runs={parallel_runs} (process pool)")
        exp_rows = []
        exp_run_manifest = []

        jobs = [
            _build_graph_optimizer_job(
                exp_id,
                attack_label,
                attack_cfg,
                run_idx,
                args.seed_base + run_idx,
                raw_root_abs,
                args.sample_pick,
                args.from_snapshots,
                snapshot_dir_abs,
                args.attack_repeats,
                legacy_A0,
                args.gradient_mode,
                get_experiment_weights(exp_id),
                attack_tier,
            )
            for run_idx in range(args.n_runs)
        ]

        if parallel_runs <= 1:
            run_results = [run_graph_optimizer_single_job(j) for j in jobs]
        else:
            with ProcessPoolExecutor(max_workers=parallel_runs) as pool:
                run_results = list(pool.map(run_graph_optimizer_single_job, jobs))

        run_results.sort(key=lambda r: r["run_idx"])
        for r in run_results:
            if r["skipped"]:
                print(f"    [skip] run {r['run_idx']:03d}: {r['skip_reason']}")
                continue
            print(f"  run {r['run_idx']+1}/{args.n_runs} seed={r['manifest']['seed']} ok")
            exp_rows.extend(r["rows"])
            global_rows.extend(r["rows"])
            exp_run_manifest.append(r["manifest"])

        exp_raw_dir = os.path.join(raw_dir, exp_id)
        exp_proc_dir = os.path.join(proc_dir, exp_id)
        exp_stat_dir = os.path.join(stat_dir, exp_id)
        os.makedirs(exp_raw_dir, exist_ok=True)
        os.makedirs(exp_proc_dir, exist_ok=True)
        os.makedirs(exp_stat_dir, exist_ok=True)

        raw_path = os.path.join(exp_raw_dir, "results_rows_graph_optimizer.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(exp_rows, f, ensure_ascii=False, indent=2)

        stats_rows = []
        for budget_variant in ("fair", "raw"):
            for metric_key in ("R", "lcc_ratio", "avg_path_len"):
                ours_vals = [
                    r[metric_key]
                    for r in exp_rows
                    if r["budget_variant"] == budget_variant and r["method_id"] == "M-OUR"
                ]
                base_vals_by_method = {}
                for method in ("M-RESI", "M-STAT", "M-ASIM", "M-FPS"):
                    base_vals_by_method[method] = [
                        r[metric_key]
                        for r in exp_rows
                        if r["budget_variant"] == budget_variant and r["method_id"] == method
                    ]
                lens = [len(ours_vals)] + [len(base_vals_by_method[m]) for m in base_vals_by_method]
                if not ours_vals or any(L != len(ours_vals) for L in lens):
                    continue
                stats_rows.extend(
                    build_method_comparison_rows(
                        experiment_id=exp_id,
                        budget_variant=budget_variant,
                        ours_vals=ours_vals,
                        base_vals_by_method=base_vals_by_method,
                        metric_key=metric_key,
                        holm_block=True,
                    )
                )

        stats_json_path = os.path.join(exp_stat_dir, "stats_summary_graph_optimizer.json")
        stats_csv_path = os.path.join(exp_stat_dir, "stats_summary_graph_optimizer.csv")
        with open(stats_json_path, "w", encoding="utf-8") as f:
            json.dump(stats_rows, f, ensure_ascii=False, indent=2)
        write_stats_summary_csv(stats_rows, stats_csv_path)
        print(f"  wrote {stats_csv_path}")
        with open(os.path.join(exp_stat_dir, "run_manifest_graph_optimizer.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at_utc": now,
                    "experiment_id": exp_id,
                    "protocol_version": PROTOCOL_VERSION,
                    "input_mode": "legacy_snapshots" if args.from_snapshots else "collected_samples",
                    "raw_root": os.path.abspath(args.raw_root),
                    "sample_pick": args.sample_pick,
                    "snapshot_dir": os.path.abspath(args.snapshot_dir) if args.from_snapshots else None,
                    "n_runs_requested": args.n_runs,
                    "parallel_runs": parallel_runs,
                    "gradient_mode": args.gradient_mode,
                    "attack_tier": attack_tier,
                    "weights": [float(x) for x in get_experiment_weights(exp_id)],
                    "statistics_artifacts": [
                        "stats_summary_graph_optimizer.csv",
                        "stats_summary_graph_optimizer.json",
                    ],
                    "results_rows_artifact": "results_rows_graph_optimizer.json",
                    "runs": exp_run_manifest,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    data_source_note = (
        os.path.abspath(args.snapshot_dir)
        if args.from_snapshots
        else f"collected_samples:{os.path.abspath(args.raw_root)}"
    )
    summary_path = os.path.join(RESULTS_BASE, "statistics", "eth_docker_graph_optimizer_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": now,
                "platform": "eth_docker",
                "protocol_version": PROTOCOL_VERSION,
                "experiments": [e[0] for e in experiments],
                "n_rows": len(global_rows),
                "n_runs": args.n_runs,
                "gradient_mode": args.gradient_mode,
                "attack_tier": args.attack_tier,
                "data_source": data_source_note,
                "input_mode": "legacy_snapshots" if args.from_snapshots else "collected_samples",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nDone. Summary: {summary_path}")


if __name__ == "__main__":
    main()
