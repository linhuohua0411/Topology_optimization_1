#!/usr/bin/env bash
# Compatibility wrapper. Unified entry:
#   experiments/pipeline/run_eth_docker_pipeline.sh MODE=restart_sim_resume
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MODE=restart_sim_resume RUN_POSTPROCESS="${RUN_POSTPROCESS:-0}" bash experiments/pipeline/run_eth_docker_pipeline.sh
