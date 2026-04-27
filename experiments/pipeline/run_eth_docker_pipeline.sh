#!/usr/bin/env bash
# Unified Eth-Docker pipeline entry.
# Modes:
#   auto                -> collect missing BASE/LINK/NETEM in order, then postprocess
#   netem_pipeline      -> collect missing NETEM only, then postprocess
#   resume_mid          -> collect LINK then NETEM (mid), no postprocess by default
#   wait_resume_post    -> wait resume/link/netem collectors, then postprocess
#   wait_collect_post   -> wait monolithic/split collectors, then postprocess
#   restart_sim_resume  -> stop/start simulation, then run resume_mid
#
# Common env knobs:
#   MODE=auto|...
#   NETEM_N_RUNS=20
#   NETEM_INTERVAL=30
#   ATTACK_TIER=mid
#   GRAPH_PARALLEL_RUNS=4
#   AGGREGATE_STRICT=1
#   CONTINUE_AFTER_AGGREGATE_FAIL=0
#   RUN_POSTPROCESS=1
#   COLLECT_LOG=<path>
#   ED_SIM_ROOT=<sim dir>  (for restart_sim_resume)
#   PRUNE_DOCKER=0|1

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1

PY="${ROOT}/.venv/bin/python"
MODE="${MODE:-auto}"
N_RUNS="${NETEM_N_RUNS:-20}"
INTERVAL="${NETEM_INTERVAL:-30}"
ATTACK_TIER="${ATTACK_TIER:-mid}"
PARALLEL_RUNS="${GRAPH_PARALLEL_RUNS:-4}"

complete_count() {
  local exp_id="$1"
  local attack_label="$2"
  local tier="$3"
  ROOT="$ROOT" EXP_ID="$exp_id" N_RUNS="$N_RUNS" ATTACK_LABEL="$attack_label" ATTACK_TIER="$tier" "${PY}" - <<'PY'
import json, os
root = os.environ["ROOT"]
exp = os.environ["EXP_ID"]
n = int(os.environ["N_RUNS"])
label = os.environ["ATTACK_LABEL"]
tier = os.environ["ATTACK_TIER"]
base = os.path.join(root, "results", "raw", "eth_docker", exp)
ok = 0
for i in range(n):
    p = os.path.join(base, f"run-{i:03d}", "run_manifest.json")
    if not os.path.isfile(p):
        continue
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
    except (json.JSONDecodeError, OSError):
        continue
    prev = m.get("attack_label", "")
    ap = m.get("attack_params") or {}
    if isinstance(ap, str):
        try:
            ap = json.loads(ap)
        except json.JSONDecodeError:
            ap = {}
    strength = ap.get("strength")
    if label == "none":
        if prev in ("none", "", None):
            ok += 1
    elif prev == label and strength in (tier, None, ""):
        ok += 1
print(ok)
PY
}

collect_if_needed() {
  local exp_id="$1"
  local attack_label="$2"
  local script_path="$3"
  local extra_args="${4:-}"
  local have
  have="$(complete_count "$exp_id" "$attack_label" "$ATTACK_TIER")"
  echo "[pipeline] $(date -Is) ${exp_id} complete=${have}/${N_RUNS}"
  if [[ "$have" -ge "$N_RUNS" ]]; then
    echo "[pipeline] $(date -Is) skip ${exp_id} collector"
    return
  fi
  echo "[pipeline] $(date -Is) collect ${exp_id} via ${script_path}"
  # shellcheck disable=SC2086
  "${PY}" "${script_path}" --n-runs "${N_RUNS}" --interval "${INTERVAL}" --attack-tier "${ATTACK_TIER}" ${extra_args}
}

run_postprocess() {
  echo "[pipeline] $(date -Is) compute_eth_docker_metrics_fast.py"
  "${PY}" experiments/compute_eth_docker_metrics_fast.py --input-root results/raw/eth_docker --n-runs "${N_RUNS}"

  echo "[pipeline] $(date -Is) aggregate_eth_docker_collected_stats.py"
  set +e
  if [[ "${AGGREGATE_STRICT:-1}" == "1" ]]; then
    "${PY}" experiments/aggregate_eth_docker_collected_stats.py --raw-root results/raw/eth_docker --n-runs "${N_RUNS}" --strict-n-runs
  else
    "${PY}" experiments/aggregate_eth_docker_collected_stats.py --raw-root results/raw/eth_docker --n-runs "${N_RUNS}"
  fi
  local agg_ec=$?
  set -e
  if [[ "$agg_ec" -ne 0 ]]; then
    echo "[pipeline] $(date -Is) aggregate exit=${agg_ec}"
    if [[ "${CONTINUE_AFTER_AGGREGATE_FAIL:-0}" != "1" ]]; then
      exit "$agg_ec"
    fi
  fi

  echo "[pipeline] $(date -Is) run_eth_docker_experiments.py"
  "${PY}" experiments/run_eth_docker_experiments.py --raw-root results/raw/eth_docker --n-runs "${N_RUNS}" --parallel-runs "${PARALLEL_RUNS}"
  echo "[pipeline] $(date -Is) postprocess done"
}

wait_collectors_resume() {
  while pgrep -f 'resume_ed_docker_collection_mid.sh' >/dev/null 2>&1 \
     || pgrep -f 'run_netem_recollect_then_postprocess.sh' >/dev/null 2>&1 \
     || pgrep -f 'eth_docker_collect/ed_main_link/collect.py' >/dev/null 2>&1 \
     || pgrep -f 'eth_docker_collect/ed_main_netem/collect.py' >/dev/null 2>&1; do
    sleep 45
  done
}

wait_collectors_any() {
  while pgrep -f "${ROOT}/.venv/bin/python experiments/collect_eth_docker_scenarios.py" >/dev/null 2>&1 \
     || pgrep -f '\.venv/bin/python experiments/collect_eth_docker_scenarios.py' >/dev/null 2>&1 \
     || pgrep -f "${ROOT}/.venv/bin/python experiments/eth_docker_collect/ed_main_base/collect.py" >/dev/null 2>&1 \
     || pgrep -f "${ROOT}/.venv/bin/python experiments/eth_docker_collect/ed_main_link/collect.py" >/dev/null 2>&1 \
     || pgrep -f "${ROOT}/.venv/bin/python experiments/eth_docker_collect/ed_main_netem/collect.py" >/dev/null 2>&1 \
     || pgrep -f '\.venv/bin/python experiments/eth_docker_collect/ed_main_' >/dev/null 2>&1; do
    sleep 45
  done
}

mode_resume_mid() {
  echo "[pipeline] $(date -Is) resume_mid: LINK -> NETEM"
  collect_if_needed "ED-MAIN-LINK" "link_down" "experiments/eth_docker_collect/ed_main_link/collect.py"
  collect_if_needed "ED-MAIN-NETEM" "tc_netem" "experiments/eth_docker_collect/ed_main_netem/collect.py" "--restart-sim-before-netem"
  if [[ "${RUN_POSTPROCESS:-0}" == "1" ]]; then
    run_postprocess
  fi
}

mode_netem_pipeline() {
  echo "[pipeline] $(date -Is) netem_pipeline"
  if [[ "${NETEM_RESET:-0}" == "1" ]]; then
    rm -rf "${ROOT}/results/raw/eth_docker/ED-MAIN-NETEM" "${ROOT}/results/processed/eth_docker/ED-MAIN-NETEM"
  fi
  collect_if_needed "ED-MAIN-NETEM" "tc_netem" "experiments/eth_docker_collect/ed_main_netem/collect.py" "--restart-sim-before-netem"
  run_postprocess
}

mode_auto() {
  echo "[pipeline] $(date -Is) auto collect missing BASE -> LINK -> NETEM"
  collect_if_needed "ED-MAIN-BASE" "none" "experiments/eth_docker_collect/ed_main_base/collect.py"
  collect_if_needed "ED-MAIN-LINK" "link_down" "experiments/eth_docker_collect/ed_main_link/collect.py"
  collect_if_needed "ED-MAIN-NETEM" "tc_netem" "experiments/eth_docker_collect/ed_main_netem/collect.py" "--restart-sim-before-netem"
  run_postprocess
}

mode_restart_sim_resume() {
  local default_sim="${ROOT}/data/repos/eth-docker/ethereum_Virtual_Network-main/12as_100nodes"
  local sim_dir="${ED_SIM_ROOT:-$default_sim}"
  if [[ ! -f "${sim_dir}/start.sh" ]]; then
    echo "[pipeline] ERROR: start.sh not found under ${sim_dir}"
    exit 1
  fi
  echo "[pipeline] $(date -Is) restart sim under ${sim_dir}"
  (cd "${sim_dir}" && ./start.sh stop)
  if [[ "${PRUNE_DOCKER:-0}" == "1" ]]; then
    docker system prune -f || true
  fi
  (cd "${sim_dir}" && ./start.sh)
  sleep 30
  RUN_POSTPROCESS="${RUN_POSTPROCESS:-0}" mode_resume_mid
}

case "$MODE" in
  auto) mode_auto ;;
  netem_pipeline) mode_netem_pipeline ;;
  resume_mid) mode_resume_mid ;;
  wait_resume_post) wait_collectors_resume; run_postprocess ;;
  wait_collect_post) wait_collectors_any; run_postprocess ;;
  restart_sim_resume) mode_restart_sim_resume ;;
  *)
    echo "Unknown MODE=${MODE}"
    exit 2
    ;;
esac
