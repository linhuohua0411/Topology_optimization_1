#!/usr/bin/env python3
"""Self-contained ED collector to generate run-*/sample_*.json assets."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import random
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

ROOT = "/home/ly/project/Topology_optimization_1"
RAW_ROOT = os.path.join(ROOT, "results", "raw", "ETH")

LINK_TIER_PROFILE = {
    "low": {"down_count": 1, "duration_seconds": 45},
    "mid": {"down_count": 1, "duration_seconds": 90},
    "high": {"down_count": 2, "duration_seconds": 120},
}

WAN_TIER_PROFILE = {
    "low": {"bandwidth_mbit": 50, "delay_ms": 80, "jitter_ms": 10, "loss_pct": 0.5, "duration_seconds": 45},
    "mid": {"bandwidth_mbit": 20, "delay_ms": 150, "jitter_ms": 20, "loss_pct": 2.0, "duration_seconds": 90},
    "high": {"bandwidth_mbit": 8, "delay_ms": 250, "jitter_ms": 35, "loss_pct": 5.0, "duration_seconds": 120},
}


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def run_cmd(command: list[str], timeout_sec: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )


def discover_containers() -> dict[int, dict[str, str]]:
    out = run_cmd(["docker", "ps", "--format", "{{.Names}}"], timeout_sec=20).stdout
    containers: dict[int, dict[str, str]] = {}
    for name in out.strip().split("\n"):
        m = re.match(r"as\d+h-Ethereum-POS-(\d+)-([\d.]+)", name.strip())
        if not m:
            continue
        nid = int(m.group(1))
        containers[nid] = {"name": name.strip(), "ip": m.group(2)}
    return containers


def get_peers(container_name: str) -> list[dict[str, Any]]:
    try:
        out = run_cmd(
            [
                "docker",
                "exec",
                container_name,
                "curl",
                "-sf",
                "-m",
                "8",
                "-X",
                "POST",
                "http://localhost:8545",
                "-H",
                "Content-Type: application/json",
                "-d",
                '{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}',
            ],
            timeout_sec=12,
        ).stdout
        data = json.loads(out)
        return data.get("result", []) or []
    except Exception:
        return []


def collect_topology_snapshot() -> tuple[list[list[int]], dict[str, int], int]:
    containers = discover_containers()
    ip_to_nid = {info["ip"]: nid for nid, info in containers.items()}
    all_edges: set[tuple[int, int]] = set()
    peer_counts: dict[str, int] = {}
    failed = 0

    for nid in sorted(containers.keys()):
        peers = get_peers(containers[nid]["name"])
        if peers is None:
            peers = []
            failed += 1
        peer_counts[str(nid)] = len(peers)
        for p in peers:
            remote = (p.get("network", {}) or {}).get("remoteAddress", "")
            peer_ip = remote.rsplit(":", 1)[0] if ":" in remote else remote
            if peer_ip in ip_to_nid:
                m = min(nid, ip_to_nid[peer_ip])
                n = max(nid, ip_to_nid[peer_ip])
                if m != n:
                    all_edges.add((m, n))

    return [[int(u), int(v)] for (u, v) in sorted(all_edges)], peer_counts, failed


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout_sec: int = 10) -> tuple[bool, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            if isinstance(parsed, dict):
                return True, parsed
            return True, {"data": parsed}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return False, {"ok": False, "error": str(exc), "url": url}


def _trigger_real_attack(
    attack_label: str,
    attack_tier: str,
    control_api_base: str,
    run_id: str,
    attack_duration_sec: int,
) -> dict[str, Any]:
    base = control_api_base.rstrip("/")
    if attack_label == "none":
        return {"ok": True, "attack_label": "none", "triggered": False}

    if attack_label == "link_down":
        tier_profile = LINK_TIER_PROFILE.get(attack_tier, LINK_TIER_PROFILE["mid"])
        duration_seconds = int(attack_duration_sec) if int(attack_duration_sec) > 0 else int(
            tier_profile["duration_seconds"]
        )
        down_count = int(tier_profile["down_count"])
        ok, nodes_payload = _http_json(f"{base}/api/v1/chaos/nodes")
        if not ok:
            return {
                "ok": False,
                "attack_label": attack_label,
                "error": "list_nodes_failed",
                "request_context": nodes_payload,
            }
        nodes = nodes_payload.get("nodes", [])
        candidates = [n for n in nodes if n.get("status") == "up" and n.get("container_name")]
        if len(candidates) < down_count:
            return {"ok": False, "attack_label": attack_label, "error": "no_up_nodes_available"}
        random.shuffle(candidates)
        selected = candidates[:down_count]
        requests = []
        responses = []
        all_ok = True
        for chosen in selected:
            req = {
                "container_name": chosen["container_name"],
                "duration_seconds": duration_seconds,
            }
            ok2, down_payload = _http_json(f"{base}/api/v1/chaos/nodes/down", payload=req)
            req_ok = bool(ok2 and down_payload.get("ok", True))
            all_ok = all_ok and req_ok
            requests.append(req)
            responses.append(down_payload)
        return {
            "ok": all_ok,
            "attack_label": attack_label,
            "attack_tier": attack_tier,
            "profile": {"down_count": down_count, "duration_seconds": duration_seconds},
            "requests": requests,
            "responses": responses,
            "run_id": run_id,
        }

    if attack_label == "tc_netem":
        tier_profile = WAN_TIER_PROFILE.get(attack_tier, WAN_TIER_PROFILE["mid"]).copy()
        if int(attack_duration_sec) > 0:
            tier_profile["duration_seconds"] = int(attack_duration_sec)
        ok, targets_payload = _http_json(f"{base}/api/v1/wan/targets")
        if not ok:
            return {
                "ok": False,
                "attack_label": attack_label,
                "error": "list_wan_targets_failed",
                "request_context": targets_payload,
            }
        targets = targets_payload.get("targets", [])
        candidates = [
            t for t in targets if t.get("container_name") and t.get("interface") and not t.get("active", False)
        ]
        if not candidates:
            return {"ok": False, "attack_label": attack_label, "error": "no_wan_targets_available"}
        chosen = candidates[random.randrange(len(candidates))]
        req = {
            "container_name": chosen["container_name"],
            "interface": chosen["interface"],
            **tier_profile,
        }
        ok2, apply_payload = _http_json(f"{base}/api/v1/wan/apply", payload=req)
        return {
            "ok": bool(ok2 and apply_payload.get("ok", True)),
            "attack_label": attack_label,
            "attack_tier": attack_tier,
            "profile": tier_profile,
            "request": req,
            "response": apply_payload,
            "run_id": run_id,
        }

    return {"ok": False, "attack_label": attack_label, "error": f"unsupported_attack_label:{attack_label}"}


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_collection(
    scenarios: list[tuple[str, str]],
    collector_name: str,
    summary_filename: str,
    argv: list[str] | None = None,
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--phase-wait-sec", type=int, default=2)
    parser.add_argument("--skip-existing-run", action="store_true")
    parser.add_argument(
        "--experiments",
        type=str,
        default="all",
        help="Comma-separated scenario ids or 'all'",
    )
    parser.add_argument("--attack-tier", choices=("low", "mid", "high"), default="mid")
    parser.add_argument(
        "--control-api-base",
        type=str,
        default="http://127.0.0.1:8890",
        help="Control API base for real attack injection",
    )
    parser.add_argument(
        "--attack-duration-sec",
        type=int,
        default=150,
        help="Real attack duration in seconds (node down / wan apply)",
    )
    parser.add_argument(
        "--attack-settle-sec",
        type=int,
        default=10,
        help="Wait time after attack trigger before sampling attack phases",
    )
    args = parser.parse_args(argv)

    tier_fraction_map = {"low": 0.33, "mid": 0.66, "high": 1.0}
    selected = None
    if args.experiments.strip().lower() != "all":
        selected = {x.strip() for x in args.experiments.split(",") if x.strip()}

    phases = ["pre_attack", "attack_ramp", "under_attack", "recovery", "post_recovery"]
    summary: dict[str, Any] = {
        "collector": collector_name,
        "collected_at_utc": now_utc(),
        "runs": args.runs,
        "attack_tier": args.attack_tier,
        "experiments": {},
    }

    for exp_id, attack_label in scenarios:
        if selected and exp_id not in selected:
            continue
        exp_tier = args.attack_tier
        for tier_name in ("low", "mid", "high"):
            if exp_id.endswith(f"-{tier_name}"):
                exp_tier = tier_name
                break
        exp_dir = os.path.join(RAW_ROOT, exp_id)
        os.makedirs(exp_dir, exist_ok=True)
        summary["experiments"][exp_id] = []

        for run_idx in range(args.runs):
            run_id = f"run-{run_idx:03d}"
            run_dir = os.path.join(exp_dir, run_id)
            os.makedirs(run_dir, exist_ok=True)

            if args.skip_existing_run and os.path.exists(os.path.join(run_dir, "run_manifest.json")):
                print(f"[{exp_id}] {run_id} skipped (existing run_manifest.json)", flush=True)
                continue

            base_edges, peer_counts, failed_nodes = collect_topology_snapshot()
            n_nodes = len(peer_counts)
            attack_fraction = 0.0 if attack_label == "none" else tier_fraction_map[exp_tier]
            run_samples: list[dict[str, Any]] = []
            attack_exec_info: dict[str, Any] = {"ok": True, "attack_label": attack_label, "triggered": False}
            attack_triggered = False

            for sample_idx, phase in enumerate(phases):
                if attack_label != "none" and phase == "attack_ramp" and not attack_triggered:
                    attack_exec_info = _trigger_real_attack(
                        attack_label=attack_label,
                        attack_tier=exp_tier,
                        control_api_base=args.control_api_base,
                        run_id=run_id,
                        attack_duration_sec=int(args.attack_duration_sec),
                    )
                    attack_triggered = True
                    if not attack_exec_info.get("ok", False):
                        print(
                            f"[{exp_id}] {run_id} failed: real attack trigger failed: {attack_exec_info}",
                            flush=True,
                        )
                        break
                    time.sleep(max(0, int(args.attack_settle_sec)))

                # Collect live topology each phase so real attack effects are visible in samples.
                phase_edges, phase_peer_counts, phase_failed_nodes = collect_topology_snapshot()
                n_nodes = len(phase_peer_counts)
                sample = {
                    "platform": "eth_docker",
                    "experiment_id": exp_id,
                    "run_id": run_id,
                    "sample_index": sample_idx,
                    "phase": phase,
                    "timestamp_utc": now_utc(),
                    "attack_label": attack_label,
                    "attack_params": {
                        "mode": "execution_api",
                        "fraction": attack_fraction,
                        "attack_tier": exp_tier if attack_label != "none" else "none",
                        "control_api_base": args.control_api_base,
                        "attack_duration_sec": int(args.attack_duration_sec),
                        "tier_profile": attack_exec_info.get("profile"),
                    },
                    "budget_variant": "raw",
                    "protocol_variant": "unified_full_protocol",
                    "layer": "execution",
                    "topology": {
                        "edges": phase_edges,
                        "peer_counts": phase_peer_counts,
                        "n_nodes": n_nodes,
                        "n_edges": len(phase_edges),
                        "failed_nodes_count": int(phase_failed_nodes),
                    },
                }
                save_json(os.path.join(run_dir, f"sample_{sample_idx:04d}.json"), sample)
                run_samples.append(sample)
                time.sleep(max(0, int(args.phase_wait_sec)))

            if attack_label != "none" and attack_triggered and not attack_exec_info.get("ok", False):
                continue

            run_manifest = {
                "platform": "eth_docker",
                "experiment_id": exp_id,
                "run_id": run_id,
                "collector": collector_name,
                "attack_label": attack_label,
                "attack_tier": exp_tier if attack_label != "none" else "none",
                "phases": phases,
                "phase_wait_sec": int(args.phase_wait_sec),
                "attack_execution": attack_exec_info,
                "collected_at_utc": now_utc(),
                "n_nodes": n_nodes,
                "n_samples": len(run_samples),
            }
            save_json(os.path.join(run_dir, "run_manifest.json"), run_manifest)
            summary["experiments"][exp_id].append(run_manifest)
            print(f"[{exp_id}] {run_id} done, n_nodes={n_nodes}, edges={len(base_edges)}", flush=True)

        save_json(
            os.path.join(exp_dir, "collection_manifest.json"),
            {
                "platform": "eth_docker",
                "experiment_id": exp_id,
                "collector": collector_name,
                "attack_tier": exp_tier,
                "n_runs": args.runs,
                "collected_at_utc": now_utc(),
            },
        )

    save_json(os.path.join(RAW_ROOT, summary_filename), summary)
    print(f"[done] wrote {os.path.join(RAW_ROOT, summary_filename)}", flush=True)

