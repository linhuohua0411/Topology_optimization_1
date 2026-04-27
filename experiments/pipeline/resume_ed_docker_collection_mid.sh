#!/usr/bin/env bash
# Compatibility wrapper. Unified entry:
#   experiments/pipeline/run_eth_docker_pipeline.sh MODE=resume_mid
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MODE=resume_mid RUN_POSTPROCESS="${RUN_POSTPROCESS:-0}" bash experiments/pipeline/run_eth_docker_pipeline.sh
