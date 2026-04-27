#!/usr/bin/env bash
# Compatibility wrapper. Unified entry:
#   experiments/pipeline/run_eth_docker_pipeline.sh MODE=netem_pipeline
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MODE=netem_pipeline bash experiments/pipeline/run_eth_docker_pipeline.sh
