#!/usr/bin/env python3
"""
Collect BTC-MAIN raw runs with phased sampling.

Experiments:
  - BTC-MAIN-BASE
  - BTC-MAIN-ECLIPSE-mid
  - BTC-MAIN-PARTITION-mid
  - BTC-MAIN-NETEM-mid

Each experiment collects N runs with 5 phases:
  pre_attack -> attack_ramp -> under_attack -> recovery -> post_recovery
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any


REPO_ROOT = "/home/ly/project/Topology_optimization_1"
RAW_ROOT = os.path.join(REPO_ROOT, "results", "raw", "BTC")
MONITOR_CONTAINER = "btcvirtnet-12as108n-btc_monitor-1"
BTC_CLI = "bitcoin-cli -datadir=/data/bitcoin -rpcuser=btcrpc -rpcpassword=btcrpc_s3cure"

PARTITION_TARGETS = [
    f"btcvirtnet-12as108n-hnode_{asn}_host{host}-1"
    for asn in range(175, 179)
    for host in range(9)
]

NETEM_TARGETS = [
    f"btcvirtnet-12as108n-hnode_{asn}_host{host}-1"
    for asn in range(179, 183)
    for host in (0, 1, 2)
]

ECLIPSE_TARGETS = [
    f"btcvirtnet-12as108n-hnode_182_host{host}-1"
    for host in range(9)
]


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def run_cmd(
    command: list[str],
    check: bool = True,
    timeout_sec: int = 25,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )


def fetch_monitor_json(path: str) -> Any:
    # Host cannot directly access :8890 in this environment.
    code = (
        "import urllib.request;"
        f"u='http://127.0.0.1:8890{path}';"
        "print(urllib.request.urlopen(u,timeout=20).read().decode())"
    )
    out = run_cmd(["docker", "exec", MONITOR_CONTAINER, "python3", "-c", code]).stdout.strip()
    return json.loads(out)


def set_network_active(containers: list[str], active: bool) -> None:
    value = "true" if active else "false"
    for c in containers:
        run_cmd(
            ["docker", "exec", c, "sh", "-lc", f"{BTC_CLI} setnetworkactive {value}"],
            check=False,
            timeout_sec=12,
        )


def apply_netem(containers: list[str], delay_ms: int, loss_pct: float) -> None:
    for c in containers:
        run_cmd(
            [
                "docker",
                "exec",
                c,
                "sh",
                "-lc",
                f"tc qdisc replace dev eth0 root netem delay {delay_ms}ms loss {loss_pct}%",
            ],
            check=False,
            timeout_sec=12,
        )


def clear_netem(containers: list[str]) -> None:
    for c in containers:
        run_cmd(
            ["docker", "exec", c, "sh", "-lc", "tc qdisc del dev eth0 root"],
            check=False,
            timeout_sec=12,
        )


@dataclass
class ExperimentSpec:
    experiment_id: str
    attack_label: str
    attack_intensity: str
    budget_variant: str = "fair"


EXPERIMENTS = [
    ExperimentSpec("BTC-MAIN-BASE", "none", "0"),
    ExperimentSpec("BTC-MAIN-ECLIPSE-low", "eclipse", "low"),
    ExperimentSpec("BTC-MAIN-ECLIPSE-mid", "eclipse", "mid"),
    ExperimentSpec("BTC-MAIN-ECLIPSE-high", "eclipse", "high"),
    ExperimentSpec("BTC-MAIN-PARTITION-low", "partition", "low"),
    ExperimentSpec("BTC-MAIN-PARTITION-mid", "partition", "mid"),
    ExperimentSpec("BTC-MAIN-PARTITION-high", "partition", "high"),
    ExperimentSpec("BTC-MAIN-NETEM-low", "tc_netem_delay_loss", "low"),
    ExperimentSpec("BTC-MAIN-NETEM-mid", "tc_netem_delay_loss", "mid"),
    ExperimentSpec("BTC-MAIN-NETEM-high", "tc_netem_delay_loss", "high"),
]

TARGET_FRACTION = {
    "low": 0.33,
    "mid": 0.66,
    "high": 1.0,
    "0": 0.0,
}

NETEM_PARAMS = {
    "low": {"delay_ms": 40, "loss_pct": 1.0},
    "mid": {"delay_ms": 80, "loss_pct": 2.0},
    "high": {"delay_ms": 120, "loss_pct": 5.0},
}


def targets_by_intensity(targets: list[str], intensity: str) -> list[str]:
    frac = TARGET_FRACTION.get(intensity, 1.0)
    if frac <= 0.0:
        return []
    k = max(1, int(round(len(targets) * frac)))
    return targets[:k]


def collect_sample(spec: ExperimentSpec, run_id: str, phase: str, idx: int) -> dict[str, Any]:
    nodes = fetch_monitor_json("/api/v1/nodes")
    topology = fetch_monitor_json("/api/v1/topology")
    reachability = fetch_monitor_json("/api/v1/reachability")
    forks = fetch_monitor_json("/api/v1/forks?limit=200")

    heights = [int(v.get("height", 0) or 0) for v in nodes.values()]
    conns = [int(v.get("connections", 0) or 0) for v in nodes.values()]
    total_nodes = len(reachability)
    reachable_nodes = sum(1 for v in reachability.values() if v.get("reachable"))
    peer_edges_directed = sum(len(v.get("peers", [])) for v in topology.values())
    reachable_ratio = (reachable_nodes / total_nodes) if total_nodes else 0.0

    return {
        "platform": "BTC-Docker",
        "experiment_id": spec.experiment_id,
        "run_id": run_id,
        "sample_index": idx,
        "phase": phase,
        "timestamp_utc": now_utc(),
        "attack_label": spec.attack_label,
        "attack_intensity": spec.attack_intensity,
        "budget_variant": spec.budget_variant,
        "protocol_variant": "unified_full_protocol",
        "derived_metrics": {
            "node_count_total": total_nodes,
            "node_count_reachable": reachable_nodes,
            "reachable_ratio": reachable_ratio,
            "peer_count_btc_avg": (sum(conns) / len(conns)) if conns else 0.0,
            "block_height_min": min(heights) if heights else 0,
            "block_height_max": max(heights) if heights else 0,
            "block_height_spread": (max(heights) - min(heights)) if heights else 0,
            "topology_edges_directed": peer_edges_directed,
            "fork_events_total_seen": len(forks),
        },
        "nodes": nodes,
        "topology": topology,
        "reachability": reachability,
        "fork_events": forks,
    }


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_experiment(spec: ExperimentSpec, n_runs: int, phase_wait_sec: int, skip_existing_run: bool) -> None:
    out_dir = os.path.join(RAW_ROOT, spec.experiment_id)
    os.makedirs(out_dir, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []

    collection_manifest = {
        "platform": "BTC-Docker",
        "experiment_id": spec.experiment_id,
        "attack_label": spec.attack_label,
        "attack_intensity": spec.attack_intensity,
        "budget_variant": spec.budget_variant,
        "n_runs": n_runs,
        "collected_at_utc": now_utc(),
        "runs": [],
    }

    for i in range(1, n_runs + 1):
        run_id = f"run-{i:03d}"
        run_dir = os.path.join(out_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)
        if skip_existing_run and os.path.exists(os.path.join(run_dir, "run_manifest.json")):
            print(f"[{spec.experiment_id}] {run_id} skipped (existing run_manifest.json)", flush=True)
            continue

        network_rows: list[dict[str, Any]] = []
        phase_samples: list[dict[str, Any]] = []
        partition_targets = targets_by_intensity(PARTITION_TARGETS, spec.attack_intensity)
        eclipse_targets = targets_by_intensity(ECLIPSE_TARGETS, spec.attack_intensity)
        netem_targets = targets_by_intensity(NETEM_TARGETS, spec.attack_intensity)
        netem_params = NETEM_PARAMS.get(spec.attack_intensity, NETEM_PARAMS["mid"])

        # Always restore attack state before each run.
        set_network_active(ECLIPSE_TARGETS, True)
        set_network_active(PARTITION_TARGETS, True)
        clear_netem(NETEM_TARGETS)

        phases = ["pre_attack", "attack_ramp", "under_attack", "recovery", "post_recovery"]
        try:
            for idx, phase in enumerate(phases):
                if spec.attack_label == "partition":
                    if phase == "attack_ramp":
                        set_network_active(partition_targets, False)
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "setnetworkactive_false",
                                "target_count": len(partition_targets),
                            }
                        )
                    elif phase == "recovery":
                        set_network_active(partition_targets, True)
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "setnetworkactive_true",
                                "target_count": len(partition_targets),
                            }
                        )

                if spec.attack_label == "eclipse":
                    if phase == "attack_ramp":
                        set_network_active(eclipse_targets, False)
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "setnetworkactive_false",
                                "target_count": len(eclipse_targets),
                            }
                        )
                    elif phase == "recovery":
                        set_network_active(eclipse_targets, True)
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "setnetworkactive_true",
                                "target_count": len(eclipse_targets),
                            }
                        )

                if spec.attack_label == "tc_netem_delay_loss":
                    if phase == "attack_ramp":
                        apply_netem(
                            netem_targets,
                            delay_ms=netem_params["delay_ms"],
                            loss_pct=netem_params["loss_pct"],
                        )
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "netem_apply",
                                "params": {
                                    "delay_ms": netem_params["delay_ms"],
                                    "loss_pct": netem_params["loss_pct"],
                                },
                                "target_count": len(netem_targets),
                            }
                        )
                    elif phase == "recovery":
                        clear_netem(netem_targets)
                        network_rows.append(
                            {
                                "timestamp_utc": now_utc(),
                                "phase": phase,
                                "attack_label": spec.attack_label,
                                "action": "netem_clear",
                                "target_count": len(netem_targets),
                            }
                        )

                sample = collect_sample(spec, run_id, phase, idx)
                phase_samples.append(sample)
                save_json(os.path.join(run_dir, f"sample_{idx:04d}.json"), sample)
                time.sleep(phase_wait_sec)

        finally:
            # Ensure cleanup even if one run fails.
            set_network_active(ECLIPSE_TARGETS, True)
            set_network_active(PARTITION_TARGETS, True)
            clear_netem(NETEM_TARGETS)

        if phase_samples:
            last = phase_samples[-1]["derived_metrics"]
            summary_rows.append(
                {
                    "run_id": run_id,
                    "reachable_ratio": last["reachable_ratio"],
                    "block_height_spread": last["block_height_spread"],
                    "fork_events_total_seen": last["fork_events_total_seen"],
                }
            )

        with open(os.path.join(run_dir, "network_condition.csv"), "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["timestamp_utc", "phase", "attack_label", "action", "target_count", "params"],
            )
            writer.writeheader()
            for row in network_rows:
                row = dict(row)
                if "params" in row:
                    row["params"] = json.dumps(row["params"], ensure_ascii=False)
                writer.writerow(row)

        timeseries = {
            "experiment_id": spec.experiment_id,
            "run_id": run_id,
            "phases": [s["phase"] for s in phase_samples],
            "samples": [
                {
                    "sample_index": s["sample_index"],
                    "timestamp_utc": s["timestamp_utc"],
                    **s["derived_metrics"],
                }
                for s in phase_samples
            ],
        }
        save_json(os.path.join(run_dir, "timeseries.json"), timeseries)

        run_manifest = {
            "platform": "BTC-Docker",
            "experiment_id": spec.experiment_id,
            "run_id": run_id,
            "attack_label": spec.attack_label,
            "attack_intensity": spec.attack_intensity,
            "budget_variant": spec.budget_variant,
            "protocol_variant": "unified_full_protocol",
            "phases": phases,
            "phase_wait_sec": phase_wait_sec,
            "collected_at_utc": now_utc(),
            "source": "btc_monitor_api + docker_exec_attack_controls",
            "summary_last_sample": phase_samples[-1]["derived_metrics"] if phase_samples else {},
        }
        save_json(os.path.join(run_dir, "run_manifest.json"), run_manifest)

        collection_manifest["runs"].append(
            {
                "run_id": run_id,
                "run_path": run_dir,
                "samples": len(phase_samples),
                "summary_last_sample": run_manifest["summary_last_sample"],
            }
        )
        print(
            f"[{spec.experiment_id}] {run_id} done, "
            f"reachable_ratio={run_manifest['summary_last_sample'].get('reachable_ratio', 'NA')}, "
            f"height_spread={run_manifest['summary_last_sample'].get('block_height_spread', 'NA')}"
            ,
            flush=True,
        )

    save_json(os.path.join(out_dir, "collection_manifest.json"), collection_manifest)
    with open(os.path.join(out_dir, "run_summary.csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["run_id", "reachable_ratio", "block_height_spread", "fork_events_total_seen"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)


def ensure_monitor_ready() -> None:
    health = fetch_monitor_json("/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"btc_monitor health check failed: {health}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10, help="Runs per experiment")
    parser.add_argument("--phase-wait-sec", type=int, default=3, help="Sleep between phase samples")
    parser.add_argument(
        "--experiments",
        type=str,
        default="all",
        help="Comma-separated experiment ids to run, or 'all'",
    )
    parser.add_argument(
        "--skip-existing-run",
        action="store_true",
        help="Skip run-NNN when run_manifest.json already exists",
    )
    args = parser.parse_args()

    ensure_monitor_ready()
    selected = set()
    if args.experiments.strip().lower() != "all":
        selected = {x.strip() for x in args.experiments.split(",") if x.strip()}
    for spec in EXPERIMENTS:
        if selected and spec.experiment_id not in selected:
            continue
        run_experiment(
            spec,
            n_runs=args.runs,
            phase_wait_sec=args.phase_wait_sec,
            skip_existing_run=args.skip_existing_run,
        )
    print("All BTC experiments collected successfully.")


if __name__ == "__main__":
    main()
