#!/usr/bin/env bash
# Compatibility wrapper. Unified entry:
#   experiments/pipeline/run_eth_docker_pipeline.sh MODE=wait_resume_post
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
MODE=wait_resume_post bash experiments/pipeline/run_eth_docker_pipeline.sh
