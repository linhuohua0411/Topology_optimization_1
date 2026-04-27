#!/usr/bin/env python3
"""
Fast post-processing for Eth-Docker collected samples (n-runs friendly).

Inputs:
- data/platform_collected/<timestamp>/eth_docker/ED-MAIN-*/run-*/sample_*.json

Outputs (per run):
- metrics_timeseries_fast.csv
- results_rows_fast.json

Output (global):
- field_audit_eth_docker_n_runs_<N>.json

Full ED pipeline (``protocol/04`` §2): collect → **this** → aggregate →
``run_eth_docker_experiments.py`` (mandatory).
"""

import os
import re
import csv
import json
import argparse
from typing import Dict, List, Tuple

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components, shortest_path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

import sys

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments"))
from experiment_protocol import N_RUNS_DEFAULT
from src.models.robustness import compute_R_components


REQUIRED_FIELDS = [
    "timestamp_utc",
    "experiment_id",
    "run_id",
    "phase",
    "attack_label",
    "attack_params",
    "R",
    "lcc_ratio",
    "avg_path_len",
    "peer_count_el",
    "budget_variant",
]


def latest_platform_collected_root() -> str:
    base = os.path.join(ROOT, "data", "platform_collected")
    if not os.path.isdir(base):
        raise FileNotFoundError(f"missing dir: {base}")
    candidates = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    if not candidates:
        raise RuntimeError(f"no timestamp dirs under {base}")
    candidates.sort()
    return os.path.join(base, candidates[-1], "eth_docker")


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sample_files_for_run(run_dir: str) -> List[str]:
    files = [
        os.path.join(run_dir, n)
        for n in os.listdir(run_dir)
        if re.match(r"sample_\d+\.json$", n)
    ]
    files.sort()
    return files


def build_dense_adj_from_sample(sample: dict) -> Tuple[np.ndarray, Dict[int, int], np.ndarray]:
    topo = sample.get("topology", {})
    edges = topo.get("edges", []) or []
    peer_counts = topo.get("peer_counts", {}) or {}

    node_ids = set()
    for e in edges:
        if isinstance(e, list) and len(e) == 2:
            node_ids.add(int(e[0]))
            node_ids.add(int(e[1]))
    for nid in peer_counts.keys():
        try:
            node_ids.add(int(nid))
        except Exception:
            pass

    if not node_ids:
        return np.zeros((0, 0), dtype=np.float64), {}, np.array([], dtype=np.int32)

    ordered = np.array(sorted(node_ids), dtype=np.int32)
    idx = {int(n): i for i, n in enumerate(ordered.tolist())}
    n = len(ordered)

    A = np.zeros((n, n), dtype=np.float64)
    if edges:
        mapped = []
        for e in edges:
            if not (isinstance(e, list) and len(e) == 2):
                continue
            u = idx.get(int(e[0]))
            v = idx.get(int(e[1]))
            if u is None or v is None or u == v:
                continue
            mapped.append((u, v))
        if mapped:
            arr = np.array(mapped, dtype=np.int32)
            A[arr[:, 0], arr[:, 1]] = 1.0
            A[arr[:, 1], arr[:, 0]] = 1.0

    return A, idx, ordered


def fast_graph_metrics(A: np.ndarray) -> Dict[str, float]:
    n = A.shape[0]
    if n == 0:
        return {
            "components": 0,
            "lcc_ratio": 0.0,
            "avg_path_len": 0.0,
        }

    binary = (A > 0).astype(np.float64)
    G = sparse.csr_matrix(binary)
    n_comp, labels = connected_components(G, directed=False)

    counts = np.bincount(labels) if n_comp > 0 else np.array([0])
    lcc_label = int(np.argmax(counts)) if counts.size > 0 else 0
    lcc_idx = np.where(labels == lcc_label)[0]
    lcc_ratio = float(len(lcc_idx) / max(1, n))

    if len(lcc_idx) <= 1:
        avg_path_len = 0.0
    else:
        lcc_graph = G[lcc_idx][:, lcc_idx]
        dist = shortest_path(lcc_graph, directed=False, unweighted=True)
        mask = np.isfinite(dist) & (dist > 0)
        avg_path_len = float(np.mean(dist[mask])) if np.any(mask) else 0.0

    return {
        "components": int(n_comp),
        "lcc_ratio": lcc_ratio,
        "avg_path_len": avg_path_len,
    }


def peer_count_el_from_sample(sample: dict, A: np.ndarray) -> float:
    topo = sample.get("topology", {})
    peer_counts = topo.get("peer_counts", {}) or {}
    if peer_counts:
        vals = []
        for v in peer_counts.values():
            try:
                vals.append(float(v))
            except Exception:
                pass
        if vals:
            return float(np.mean(vals))
    if A.size == 0:
        return 0.0
    deg = np.sum((A > 0).astype(np.float64), axis=1)
    return float(np.mean(deg))


def compute_row(sample: dict, budget_variant: str) -> dict:
    A, _, _ = build_dense_adj_from_sample(sample)
    gm = fast_graph_metrics(A)

    if A.shape[0] > 1:
        rc = compute_R_components(A)
        r = float(rc.get("R", 0.0))
        rs = float(rc.get("R_s", 0.0))
        rconn = float(rc.get("R_c", 0.0))
        rr = float(rc.get("R_r", 0.0))
    else:
        r, rs, rconn, rr = 0.0, 0.0, 0.0, 0.0

    ap = sample.get("attack_params", {})
    row = {
        "timestamp_utc": sample.get("timestamp_utc"),
        "platform": sample.get("platform", "eth_docker"),
        "experiment_id": sample.get("experiment_id"),
        "run_id": sample.get("run_id"),
        "phase": sample.get("phase"),
        "attack_label": sample.get("attack_label"),
        "attack_params": ap,
        "budget_variant": budget_variant,
        "R": r,
        "Rs": rs,
        "Rc": rconn,
        "Rr": rr,
        "lcc_ratio": gm["lcc_ratio"],
        "avg_path_len": gm["avg_path_len"],
        "components": gm["components"],
        "peer_count_el": peer_count_el_from_sample(sample, A),
    }
    return row


def write_csv(rows: List[dict], path: str) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def field_audit(rows: List[dict]) -> Dict[str, str]:
    if not rows:
        return {k: "missing" for k in REQUIRED_FIELDS}
    status = {}
    for k in REQUIRED_FIELDS:
        ok = all((k in r and r.get(k) is not None) for r in rows)
        status[k] = "present" if ok else "missing_or_null"
    return status


TOPOLOGY_METRICS_COLUMNS = [
    "timestamp_utc",
    "platform",
    "experiment_id",
    "run_id",
    "phase",
    "attack_label",
    "attack_params",
    "protocol_variant",
    "budget_variant",
    "layer",
    "R",
    "Rs",
    "Rc",
    "Rr",
    "lcc_ratio",
    "avg_path_len",
    "components",
    "peer_count_el",
]


def _rows_for_topology_metrics_csv(rows: List[dict]) -> List[dict]:
    out = []
    for r in rows:
        ap = r.get("attack_params")
        if isinstance(ap, dict):
            ap_str = json.dumps(ap, ensure_ascii=False)
        else:
            ap_str = ap if ap is not None else ""
        out.append(
            {
                "timestamp_utc": r.get("timestamp_utc"),
                "platform": r.get("platform", "eth_docker"),
                "experiment_id": r.get("experiment_id"),
                "run_id": r.get("run_id"),
                "phase": r.get("phase"),
                "attack_label": r.get("attack_label"),
                "attack_params": ap_str,
                "protocol_variant": r.get("protocol_variant", "unified_full_protocol"),
                "budget_variant": r.get("budget_variant", "raw"),
                "layer": r.get("layer", "execution"),
                "R": r.get("R"),
                "Rs": r.get("Rs"),
                "Rc": r.get("Rc"),
                "Rr": r.get("Rr"),
                "lcc_ratio": r.get("lcc_ratio"),
                "avg_path_len": r.get("avg_path_len"),
                "components": r.get("components"),
                "peer_count_el": r.get("peer_count_el"),
            }
        )
    return out


def write_topology_metrics_timeseries_csv(rows: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mrows = _rows_for_topology_metrics_csv(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TOPOLOGY_METRICS_COLUMNS)
        w.writeheader()
        for r in mrows:
            w.writerow(r)


def process_run(
    run_dir: str,
    budget_variant: str,
    processed_run_dir: str | None = None,
) -> Tuple[List[dict], Dict[str, str]]:
    rows = []
    for path in sample_files_for_run(run_dir):
        sample = load_json(path)
        row = compute_row(sample, budget_variant=budget_variant)
        # align with TIFS raw field names when samples carry protocol fields
        row.setdefault("protocol_variant", sample.get("protocol_variant", "unified_full_protocol"))
        row.setdefault("layer", sample.get("layer", "execution"))
        rows.append(row)

    out_json = os.path.join(run_dir, "results_rows_fast.json")
    out_csv = os.path.join(run_dir, "metrics_timeseries_fast.csv")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    write_csv(rows, out_csv)
    topo_csv_run = os.path.join(run_dir, "topology_metrics_timeseries.csv")
    write_topology_metrics_timeseries_csv(rows, topo_csv_run)
    if processed_run_dir:
        os.makedirs(processed_run_dir, exist_ok=True)
        write_topology_metrics_timeseries_csv(
            rows, os.path.join(processed_run_dir, "topology_metrics_timeseries.csv")
        )
    return rows, field_audit(rows)


def discover_ed_experiment_dirs(input_root: str) -> List[str]:
    if not os.path.isdir(input_root):
        return []
    out = []
    for name in sorted(os.listdir(input_root)):
        if not name.startswith("ED-MAIN-"):
            continue
        p = os.path.join(input_root, name)
        if os.path.isdir(p):
            out.append(name)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", default=None, help="eth_docker root (raw or platform_collected)")
    parser.add_argument(
        "--processed-root",
        default=None,
        help="default: <repo>/results/processed/eth_docker (mirrors matrix paths)",
    )
    parser.add_argument("--no-mirror-processed", action="store_true")
    parser.add_argument("--n-runs", type=int, default=N_RUNS_DEFAULT)
    parser.add_argument("--budget-variant", default="raw", choices=["raw", "fair"])
    args = parser.parse_args()

    if args.input_root:
        input_root = args.input_root
    else:
        raw_guess = os.path.join(ROOT, "results", "raw", "eth_docker")
        if os.path.isdir(raw_guess):
            input_root = raw_guess
        else:
            input_root = latest_platform_collected_root()

    processed_root = args.processed_root
    if processed_root is None:
        processed_root = os.path.join(ROOT, "results", "processed", "eth_docker")
    mirror_proc = not args.no_mirror_processed

    scenarios = discover_ed_experiment_dirs(input_root)
    if not scenarios:
        scenarios = ["ED-MAIN-BASE", "ED-MAIN-LINK", "ED-MAIN-NETEM"]

    audit = {
        "input_root": input_root,
        "processed_root": processed_root if mirror_proc else None,
        "n_runs": args.n_runs,
        "budget_variant": args.budget_variant,
        "scenarios": {},
    }

    for exp_id in scenarios:
        exp_dir = os.path.join(input_root, exp_id)
        exp_audit = {}
        for run_idx in range(args.n_runs):
            run_id = f"run-{run_idx:03d}"
            run_dir = os.path.join(exp_dir, run_id)
            if not os.path.isdir(run_dir):
                exp_audit[run_id] = {"status": "missing_run_dir"}
                continue
            proc_run = os.path.join(processed_root, exp_id, run_id) if mirror_proc else None
            rows, fa = process_run(
                run_dir,
                budget_variant=args.budget_variant,
                processed_run_dir=proc_run,
            )
            exp_audit[run_id] = {
                "status": "ok",
                "n_rows": len(rows),
                "field_status": fa,
                "outputs": [
                    os.path.join(run_dir, "results_rows_fast.json"),
                    os.path.join(run_dir, "metrics_timeseries_fast.csv"),
                    os.path.join(run_dir, "topology_metrics_timeseries.csv"),
                ],
            }
            if mirror_proc and proc_run:
                exp_audit[run_id]["outputs"].append(
                    os.path.join(proc_run, "topology_metrics_timeseries.csv")
                )
        audit["scenarios"][exp_id] = exp_audit

    audit_path = os.path.join(
        input_root, f"field_audit_eth_docker_n_runs_{args.n_runs}.json"
    )
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"[done] audit: {audit_path}")


if __name__ == "__main__":
    main()
