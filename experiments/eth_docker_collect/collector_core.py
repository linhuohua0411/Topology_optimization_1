#!/usr/bin/env python3
"""
Shared implementation for Eth-Docker scenario collectors.

Entry points (split runs, smaller disk bursts per campaign):
``ed_main_base/collect.py``, ``ed_main_link/collect.py``, ``ed_main_netem/collect.py``.
Legacy all-in-one: ``experiments/collect_eth_docker_scenarios.py``.
"""

import os
import sys
import json
import time
import csv
import argparse
import subprocess
from datetime import datetime, timezone

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXPERIMENTS_DIR = os.path.dirname(_THIS_DIR)
ROOT = os.path.dirname(_EXPERIMENTS_DIR)
sys.path.insert(0, _EXPERIMENTS_DIR)
from eth_topology_collector import discover_containers, collect_topology_snapshot
from experiment_protocol import N_RUNS_DEFAULT, PROTOCOL_VERSION


RAW_BASE = os.path.join(ROOT, "results", "raw", "eth_docker")
SIM_CONTAINER = "eth_simulation"
PHASES = [
    ("pre_attack", 3),
    ("attack_ramp", 5),
    ("under_attack", 3),
    ("recovery", 5),
    ("post_recovery", 3),
]


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def sh_json(cmd, subprocess_timeout_s: float | None = None):
    """Run docker/curl shell pipeline; always bound wall time (curl -m is not enough if docker hangs)."""
    to = 120.0 if subprocess_timeout_s is None else float(subprocess_timeout_s)
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=max(5.0, to),
        )
    except subprocess.TimeoutExpired:
        return False, {"ok": False, "error": "subprocess_timeout"}
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        return False, {"ok": False, "error": (p.stderr or out or "command_failed").strip()}
    if not out:
        return True, {}
    try:
        return True, json.loads(out)
    except json.JSONDecodeError:
        return True, {"raw": out}


def sim_api_get(path):
    cmd = (
        f"docker exec {SIM_CONTAINER} curl -s -m 8 "
        f"http://127.0.0.1:8890{path}"
    )
    return sh_json(cmd, subprocess_timeout_s=25)


def sim_api_post(path, payload, timeout_s: int = 60):
    payload_str = json.dumps(payload, ensure_ascii=False)
    timeout_s = max(1, int(timeout_s))
    cmd = (
        f"docker exec {SIM_CONTAINER} curl -s -m {timeout_s} -X POST "
        f"http://127.0.0.1:8890{path} "
        f"-H \"Content-Type: application/json\" "
        f"-d '{payload_str}'"
    )
    return sh_json(cmd, subprocess_timeout_s=max(45, int(timeout_s) + 45))


def wait_sim_health(max_attempts: int = 8, sleep_s: float = 2.0):
    """Wait for eth_simulation control API to become healthy."""
    last = {}
    for _ in range(max_attempts):
        ok, health = sim_api_get("/healthz")
        last = health
        if ok and health.get("status") == "ok":
            return True, health
        time.sleep(sleep_s)
    return False, last


def restart_sim_container_and_wait():
    """Clear WAN chaos slot leaks (sim may leave entries on failed tc restore)."""
    print(f"[preflight] docker restart {SIM_CONTAINER}", flush=True)
    subprocess.run(["docker", "restart", SIM_CONTAINER], check=False)
    time.sleep(25)
    ok, health = wait_sim_health(max_attempts=45, sleep_s=4.0)
    if not ok:
        raise RuntimeError(f"eth_simulation unhealthy after restart: {health}")


def ensure_dirs(exp_id, run_id):
    run_dir = os.path.join(RAW_BASE, exp_id, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def write_edges_csv(samples, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp_utc", "phase", "sample_idx", "src", "dst"],
        )
        writer.writeheader()
        for s in samples:
            ts = s["timestamp_utc"]
            phase = s["phase"]
            idx = s["sample_idx"]
            for src, dst in s["topology"]["edges"]:
                writer.writerow(
                    {
                        "timestamp_utc": ts,
                        "phase": phase,
                        "sample_idx": idx,
                        "src": src,
                        "dst": dst,
                    }
                )


def _attack_injection_active(attack_label: str, phase: str) -> bool:
    if attack_label == "none":
        return False
    return phase in ("attack_ramp", "under_attack")


def _wan_active_entries(wan_active: dict) -> list:
    """Normalize sim /wan/active payload (schema varies: active_links vs active_profiles)."""
    if not isinstance(wan_active, dict):
        return []
    for key in ("active_links", "links", "active_profiles"):
        v = wan_active.get(key)
        if isinstance(v, list):
            return v
    return []


def _wan_active_count(wan_active: dict) -> int:
    return len(_wan_active_entries(wan_active))


def write_network_condition_csv(samples, csv_path):
    """Per-sample network / injection state aligned with phase (TIFS matrix: network_condition)."""
    fieldnames = [
        "timestamp_utc",
        "experiment_id",
        "run_id",
        "phase",
        "sample_idx",
        "attack_label",
        "attack_strength",
        "injection_active",
        "delay_ms",
        "loss_pct",
        "jitter_ms",
        "bandwidth_mbit",
        "nodes_down_registered",
        "wan_netem_links_active",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in samples:
            ap = s.get("attack_params") or {}
            if isinstance(ap, str):
                try:
                    ap = json.loads(ap)
                except json.JSONDecodeError:
                    ap = {}
            strength = ap.get("strength", "none")
            label = s.get("attack_label", "")
            phase = s.get("phase", "")
            inj = _attack_injection_active(label, phase)
            w.writerow(
                {
                    "timestamp_utc": s.get("timestamp_utc"),
                    "experiment_id": s.get("experiment_id"),
                    "run_id": s.get("run_id"),
                    "phase": phase,
                    "sample_idx": s.get("sample_idx"),
                    "attack_label": label,
                    "attack_strength": strength,
                    "injection_active": int(bool(inj)),
                    "delay_ms": ap.get("delay_ms", ""),
                    "loss_pct": ap.get("loss_pct", ""),
                    "jitter_ms": ap.get("jitter_ms", ""),
                    "bandwidth_mbit": ap.get("bandwidth_mbit", ""),
                    "nodes_down_registered": json.dumps(ap.get("container_names", []), ensure_ascii=False)
                    if ap.get("container_names")
                    else (ap.get("container_name") or ""),
                    "wan_netem_links_active": _wan_active_count(s.get("wan_active") or {}),
                }
            )


def append_budget_log(
    exp_id: str, run_id: str, attack_label: str, attack_tier: str, collector_name: str
):
    """Observation-only runs: budget_cost=0, traceable for fair/raw matrix fields."""
    exp_raw = os.path.join(RAW_BASE, exp_id)
    os.makedirs(exp_raw, exist_ok=True)
    path = os.path.join(exp_raw, "budget_log.jsonl")
    line = {
        "timestamp_utc": now_utc(),
        "platform": "eth_docker",
        "experiment_id": exp_id,
        "run_id": run_id,
        "protocol_variant": "unified_full_protocol",
        "protocol_version": PROTOCOL_VERSION,
        "budget_variant": "raw",
        "budget_cost": 0,
        "attack_label": attack_label,
        "attack_strength": attack_tier,
        "collector": collector_name,
        "notes": "topology_observation_only_no_optimizer_edge_budget",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _up_node_names_from_sim():
    ok, data = sim_api_get("/api/v1/chaos/nodes")
    if ok:
        nodes = data.get("nodes", [])
        up_nodes = [n for n in nodes if n.get("status") == "up"]
        up_nodes.sort(key=lambda x: x.get("container_name", ""))
        return [n.get("container_name") for n in up_nodes if n.get("container_name")]
    local = discover_containers()
    if isinstance(local, dict) and local:
        return sorted(v.get("name", "") for v in local.values() if v.get("name"))
    return []


def pick_link_targets(k: int):
    """Deterministic first-k up nodes (protocol 2.3: low/mid/high ~ 5/10/20% of up nodes)."""
    names = _up_node_names_from_sim()
    if not names:
        return []
    k = max(1, min(len(names), int(k)))
    return names[:k]


def link_down_count_for_tier(tier: str, n_up: int) -> int:
    frac = {"low": 0.05, "mid": 0.10, "high": 0.20}.get(tier, 0.10)
    if n_up <= 0:
        return 1
    k = int(round(frac * n_up))
    k = max(1, min(n_up, k))
    # nodes/down may block ~duration per target; default cap keeps wall time sane for smoke.
    # Set ED_LINK_DOWN_MAX_NODES to a large integer (e.g. 999) to match full matrix fraction.
    raw = os.getenv("ED_LINK_DOWN_MAX_NODES")
    if raw is None or str(raw).strip() == "":
        return min(k, 5)
    try:
        max_nodes = int(raw)
    except ValueError:
        return min(k, 5)
    if max_nodes <= 0:
        return k
    max_nodes = max(1, max_nodes)
    return min(k, max_nodes)


def netem_params_for_tier(tier: str, base_duration: int):
    """Matrix 2.3 templates: delay/loss (ms, %); jitter/bw registered for traceability."""
    tpl = {
        "low": (50, 1.0, 10, 50),
        "mid": (150, 5.0, 30, 20),
        "high": (300, 10.0, 50, 10),
    }
    delay_ms, loss_pct, jitter_ms, bw = tpl.get(tier, tpl["mid"])
    return {
        "delay_ms": delay_ms,
        "jitter_ms": jitter_ms,
        "loss_pct": loss_pct,
        "bandwidth_mbit": bw,
        "duration_seconds": base_duration,
    }


def pick_wan_target():
    ok, data = sim_api_get("/api/v1/wan/targets")
    if not ok:
        return None, None
    targets = data.get("targets", [])
    if not targets:
        return None, None
    # Prefer inactive links first, then deterministic name ordering.
    targets.sort(
        key=lambda x: (
            1 if x.get("active", False) else 0,
            x.get("container_name", ""),
            x.get("interface", ""),
        )
    )
    t = targets[0]
    return t.get("container_name"), t.get("interface")


def pick_wan_target_rotated(offset: int = 0):
    """Same ordering as pick_wan_target but cycle through candidates when slots stay busy."""
    ok, data = sim_api_get("/api/v1/wan/targets")
    if not ok:
        return None, None
    targets = data.get("targets", [])
    if not targets:
        return None, None
    targets.sort(
        key=lambda x: (
            1 if x.get("active", False) else 0,
            x.get("container_name", ""),
            x.get("interface", ""),
        )
    )
    usable = [t for t in targets if t.get("container_name") and t.get("interface")]
    if not usable:
        return None, None
    t = usable[int(offset) % len(usable)]
    return t.get("container_name"), t.get("interface")


def free_one_wan_slot():
    """Reset one active WAN link; try each active link until a reset succeeds."""
    ok, data = sim_api_get("/api/v1/wan/active")
    if not ok:
        return False
    active_links = _wan_active_entries(data)
    if not active_links:
        return False
    active_links.sort(key=lambda x: (x.get("container_name", ""), x.get("interface", "")))
    for target in active_links:
        c_name = target.get("container_name")
        iface = target.get("interface")
        if not c_name or not iface:
            continue
        ok, resp = sim_api_post(
            "/api/v1/wan/reset",
            {"container_name": c_name, "interface": iface},
            timeout_s=90,
        )
        if ok and resp.get("ok", False):
            return True
    return False


def free_wan_slots_up_to(max_frees: int = 16) -> int:
    """Free successive WAN slots (sim chaos may fill many); returns count of successful resets."""
    n = 0
    for _ in range(max(1, int(max_frees))):
        if not free_one_wan_slot():
            break
        n += 1
        time.sleep(0.35)
    return n


def pick_wan_target_with_recovery(max_attempts: int = 3, wait_s: float = 1.5):
    """Try to obtain one WAN target; if none, free one active slot and retry."""
    for _ in range(max_attempts):
        c_name, iface = pick_wan_target()
        if c_name and iface:
            return c_name, iface
        freed = free_one_wan_slot()
        if not freed:
            time.sleep(wait_s)
            continue
        time.sleep(wait_s)
    return None, None


def inject_link_down_with_retry(
    node: str, duration_seconds: int, timeout_seconds: int, max_retries: int = 2
):
    """Retry transient link_down failures from simulation API."""
    last_resp = None
    for attempt in range(max_retries + 1):
        ok, resp = sim_api_post(
            "/api/v1/chaos/nodes/down",
            {"container_name": node, "duration_seconds": duration_seconds},
            timeout_s=timeout_seconds,
        )
        if ok and resp.get("ok", False):
            return True, resp
        last_resp = resp
        err = str((resp or {}).get("error", ""))
        msg = str((resp or {}).get("message", ""))
        # If node is already down/active under chaos, treat as effectively injected.
        if "already down" in err or "already down" in msg:
            return True, resp
        if attempt < max_retries:
            time.sleep(1.5 + attempt * 1.5)
    return False, last_resp or {}


def collect_one_sample(containers, exp_id, run_id, phase, sample_idx, attack_label, attack_params):
    topo = collect_topology_snapshot(containers)
    _, sim_status = sim_api_get("/api/v1/status")
    _, nodes_status = sim_api_get("/api/v1/chaos/nodes")
    _, wan_active = sim_api_get("/api/v1/wan/active")
    return {
        "timestamp_utc": now_utc(),
        "platform": "eth_docker",
        "experiment_id": exp_id,
        "run_id": run_id,
        "phase": phase,
        "sample_idx": sample_idx,
        "attack_label": attack_label,
        "attack_params": attack_params,
        "protocol_variant": "unified_full_protocol",
        "budget_variant": "raw",
        "layer": "execution",
        "topology": topo,
        "sim_status": sim_status,
        "nodes_status": nodes_status,
        "wan_active": wan_active,
    }


def run_scenario(
    exp_id,
    attack_label,
    run_idx,
    interval,
    containers,
    attack_tier: str,
    collector_name: str,
):
    run_id = f"run-{run_idx:03d}"
    run_dir = ensure_dirs(exp_id, run_id)
    samples = []
    sample_idx = 0

    attack_params: dict = {}
    active_nodes: list = []
    active_wan = (None, None)
    dur_scale = {"low": 0.85, "mid": 1.0, "high": 1.15, "none": 1.0}.get(attack_tier, 1.0)
    attack_duration = int((interval * (5 + 3) + 15) * dur_scale)  # attack_ramp + under_attack
    # Cap per-request wall time: sim WAN apply can stall; full attack_duration-based timeouts
    # make a 32-slot retry loop multi-hour. Subprocess still bounds each curl.
    wan_curl_timeout = min(240, max(90, int(attack_duration) + 45))

    if attack_label == "none":
        attack_params = {
            "strength": "none",
            "injection_semantics": "unified_phase_timeline_no_chaos_injection",
        }
    elif attack_label == "link_down":
        up_names = _up_node_names_from_sim()
        k = link_down_count_for_tier(attack_tier, len(up_names))
        active_nodes = pick_link_targets(k)
        if not active_nodes:
            raise RuntimeError("no available node target for link_down")
        attack_params = {
            "strength": attack_tier,
            "target_selection_rule": "deterministic_first_k_up_nodes_from_sim_ordered",
            "container_names": active_nodes,
            "container_name": active_nodes[0],
            "duration_seconds": attack_duration,
            "n_nodes_down": len(active_nodes),
        }
    elif attack_label == "tc_netem":
        c_name, iface = pick_wan_target_with_recovery(max_attempts=4, wait_s=2.0)
        if not c_name or not iface:
            raise RuntimeError("no available wan target for tc_netem")
        active_wan = (c_name, iface)
        net = netem_params_for_tier(attack_tier, attack_duration)
        attack_params = {
            "strength": attack_tier,
            "target_selection_rule": "first_available_wan_target_sim_api_sorted",
            "container_name": c_name,
            "interface": iface,
            **net,
        }

    for phase, count in PHASES:
        if phase == "attack_ramp":
            if attack_label == "link_down":
                for node in active_nodes:
                    ok, resp = inject_link_down_with_retry(
                        node=node,
                        duration_seconds=attack_duration,
                        timeout_seconds=max(90, int(attack_duration) + 30),
                        max_retries=2,
                    )
                    if not ok:
                        raise RuntimeError(f"inject link_down failed for {node}: {resp}")
            elif attack_label == "tc_netem":
                # WAN chaos in the sim may fill all slots; reset can fail (tc restore). Wait for TTL
                # and retry apply with fresh targets (active_profiles schema in /wan/active).
                free_wan_slots_up_to(24)
                apply_ok = False
                last_resp: dict = {}
                for slot_round in range(32):
                    print(
                        f"[tc_netem] wan/apply attempt {slot_round + 1}/32 "
                        f"target={attack_params.get('container_name')} "
                        f"iface={attack_params.get('interface')} timeout_s={wan_curl_timeout}",
                        flush=True,
                    )
                    ok, resp = sim_api_post(
                        "/api/v1/wan/apply", attack_params, timeout_s=wan_curl_timeout
                    )
                    last_resp = resp if isinstance(resp, dict) else {}
                    if ok and last_resp.get("ok", False):
                        apply_ok = True
                        break
                    err = str(last_resp.get("error", ""))
                    msg = str(last_resp.get("message", ""))
                    if "already active" in err or "already active" in msg:
                        apply_ok = True
                        break
                    if "link_already_active" in err or "link_already_active" in msg:
                        apply_ok = True
                        break
                    if "max_concurrent_links_reached" in err or "max_concurrent_links_reached" in msg:
                        n_freed = free_wan_slots_up_to(48)
                        print(f"[tc_netem] max_concurrent: freed_wan_slots={n_freed}", flush=True)
                        c2, i2 = pick_wan_target_rotated(slot_round)
                        if not c2 or not i2:
                            c2, i2 = pick_wan_target_with_recovery(max_attempts=10, wait_s=2.0)
                        if c2 and i2:
                            attack_params["container_name"] = c2
                            attack_params["interface"] = i2
                            active_wan = (c2, i2)
                        time.sleep(8 if slot_round < 20 else 4)
                        continue
                    raise RuntimeError(f"inject tc_netem failed: {last_resp}")
                if not apply_ok:
                    raise RuntimeError(
                        f"inject tc_netem: wan slots stayed busy after retries: {last_resp}"
                    )

        if phase == "recovery":
            if attack_label == "link_down" and active_nodes:
                up_to = max(45, int(attack_duration) + 20)
                for node in reversed(active_nodes):
                    sim_api_post(
                        "/api/v1/chaos/nodes/up",
                        {"container_name": node},
                        timeout_s=up_to,
                    )
            elif attack_label == "tc_netem" and active_wan[0]:
                sim_api_post(
                    "/api/v1/wan/reset",
                    {"container_name": active_wan[0], "interface": active_wan[1]},
                    timeout_s=wan_curl_timeout,
                )

        for _ in range(count):
            sample = collect_one_sample(
                containers=containers,
                exp_id=exp_id,
                run_id=run_id,
                phase=phase,
                sample_idx=sample_idx,
                attack_label=attack_label,
                attack_params=attack_params,
            )
            samples.append(sample)

            snap_path = os.path.join(run_dir, f"sample_{sample_idx:04d}.json")
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(sample, f, ensure_ascii=False, indent=2)

            sample_idx += 1
            if not (phase == PHASES[-1][0] and sample_idx == sum(p[1] for p in PHASES)):
                time.sleep(interval)

    with open(os.path.join(run_dir, "timeseries.json"), "w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)
    write_edges_csv(samples, os.path.join(run_dir, "topology_edges_timeseries.csv"))
    write_network_condition_csv(samples, os.path.join(run_dir, "network_condition.csv"))

    tier_applied = attack_tier if attack_label != "none" else "none"
    target_rule = {
        "none": "unified_timeline_no_injection",
        "link_down": "deterministic_first_k_up_nodes_from_sim_ordered",
        "tc_netem": "first_available_wan_target_sim_api_sorted",
    }.get(attack_label, "unknown")
    manifest = {
        "generated_at_utc": now_utc(),
        "protocol_version": PROTOCOL_VERSION,
        "experiment_id": exp_id,
        "run_id": run_id,
        "attack_label": attack_label,
        "attack_params": attack_params,
        "attack_tier_applied": tier_applied,
        "target_selection_rule": target_rule,
        "interval_seconds": interval,
        "phase_plan": PHASES,
        "n_samples": len(samples),
    }
    with open(os.path.join(run_dir, "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    append_budget_log(
        exp_id,
        run_id,
        attack_label,
        attack_tier if attack_label != "none" else "none",
        collector_name,
    )


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-runs", type=int, default=N_RUNS_DEFAULT, help="runs per scenario")
    parser.add_argument("--interval", type=int, default=30, help="sampling interval seconds")
    parser.add_argument(
        "--attack-tier",
        choices=("low", "mid", "high"),
        default="mid",
        help="registered attack strength (matrix 2.3); change tier requires re-collect or delete conflicting runs",
    )
    parser.add_argument(
        "--no-continue-on-error",
        action="store_true",
        help="Abort entire collection on first run_scenario failure (default: log error and continue).",
    )
    parser.add_argument(
        "--restart-sim-before-netem",
        action="store_true",
        help="Docker-restart eth_simulation once before ED-MAIN-NETEM (clears WAN slot leaks after failed tc restore).",
    )
    parser.add_argument(
        "--legacy-flat-exp-id",
        action="store_true",
        help=(
            "Use legacy flat experiment_id output (e.g., ED-MAIN-LINK). "
            "Default uses tiered experiment_id for attack scenarios "
            "(e.g., ED-MAIN-LINK-low / ED-MAIN-NETEM-mid)."
        ),
    )
    return parser


def run_collection(
    scenarios: list[tuple[str, str]],
    collector_name: str,
    summary_filename: str,
    argv: list[str] | None = None,
) -> None:
    """Run one or more (experiment_id, attack_label) pairs; write per-campaign summary JSON."""
    parser = build_argparser()
    args = parser.parse_args(argv)
    continue_on_error = not args.no_continue_on_error

    def _effective_exp_id(base_exp_id: str, attack_label: str, tier: str) -> str:
        if args.legacy_flat_exp_id or attack_label == "none":
            return base_exp_id
        return f"{base_exp_id}-{tier}"

    os.makedirs(RAW_BASE, exist_ok=True)
    containers = discover_containers()
    if not containers:
        raise RuntimeError("no ethereum containers discovered")

    ok, health = wait_sim_health(max_attempts=10, sleep_s=2.5)
    if not ok:
        raise RuntimeError(f"eth_simulation control api unavailable: {health}")

    collection_errors: list[dict] = []
    netem_restart_done = False
    for exp_id, attack_label in scenarios:
        if attack_label == "tc_netem" and args.restart_sim_before_netem and not netem_restart_done:
            restart_sim_container_and_wait()
            containers = discover_containers()
            if not containers:
                raise RuntimeError("no ethereum containers discovered after sim restart")
            netem_restart_done = True
        tier = "none" if attack_label == "none" else args.attack_tier
        out_exp_id = _effective_exp_id(exp_id, attack_label, tier)
        for run_idx in range(args.n_runs):
            print(
                f"[collect] {out_exp_id} (base={exp_id}) {attack_label} tier={tier} run={run_idx}"
            )
            run_id = f"run-{run_idx:03d}"
            run_manifest = os.path.join(RAW_BASE, out_exp_id, run_id, "run_manifest.json")
            if os.path.exists(run_manifest):
                try:
                    with open(run_manifest, "r", encoding="utf-8") as rf:
                        prev = json.load(rf)
                    prev_attack = prev.get("attack_label", "")
                    prev_strength = (prev.get("attack_params") or {}).get("strength")
                    if attack_label == "none":
                        if prev_attack in ("none", "", None):
                            print(f"[skip] existing run manifest: {run_manifest}")
                            continue
                    elif prev_attack == attack_label and (
                        prev_strength in (args.attack_tier, None, "")
                    ):
                        print(f"[skip] existing run manifest: {run_manifest}")
                        continue
                except (json.JSONDecodeError, OSError):
                    pass
            try:
                run_scenario(
                    out_exp_id,
                    attack_label,
                    run_idx,
                    args.interval,
                    containers,
                    tier,
                    collector_name,
                )
            except Exception as exc:
                err_rec = {
                    "experiment_id": out_exp_id,
                    "base_experiment_id": exp_id,
                    "attack_label": attack_label,
                    "run_idx": run_idx,
                    "run_id": run_id,
                    "error": repr(exc),
                }
                collection_errors.append(err_rec)
                print(f"[error] {out_exp_id} {run_id}: {exc}")
                if not continue_on_error:
                    raise
                print("[error] continuing (default: continue-on-error)")

    summary = {
        "generated_at_utc": now_utc(),
        "platform": "eth_docker",
        "collector": collector_name,
        "n_runs_per_scenario": args.n_runs,
        "interval_seconds": args.interval,
        "attack_tier": args.attack_tier,
        "scenarios": [s[0] for s in scenarios],
        "effective_scenarios": [
            _effective_exp_id(s[0], s[1], "none" if s[1] == "none" else args.attack_tier)
            for s in scenarios
        ],
        "output_dir": RAW_BASE,
        "continue_on_error": continue_on_error,
        "errors": collection_errors,
        "legacy_flat_exp_id": bool(args.legacy_flat_exp_id),
    }
    summary_path = os.path.join(ROOT, "results", "raw", summary_filename)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("collection done")
    if collection_errors:
        print(f"[warn] {len(collection_errors)} run(s) failed; see summary errors[] and logs above")

