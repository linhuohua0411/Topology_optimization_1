# Eth-Docker Pipeline Scripts

This directory contains all shell entry scripts for Eth-Docker collection/postprocess.

## Recommended single entry

- `run_eth_docker_pipeline.sh`

Examples:

- Auto collect missing BASE/LINK/NETEM, then postprocess:
  - `MODE=auto bash experiments/pipeline/run_eth_docker_pipeline.sh`
- NETEM-only recollect + postprocess:
  - `MODE=netem_pipeline bash experiments/pipeline/run_eth_docker_pipeline.sh`
- Resume LINK->NETEM only (no postprocess):
  - `MODE=resume_mid RUN_POSTPROCESS=0 bash experiments/pipeline/run_eth_docker_pipeline.sh`

## Compatibility wrappers

These wrappers keep familiar names but route to the unified entry:

- `resume_ed_docker_collection_mid.sh`
- `run_netem_recollect_then_postprocess.sh`
- `wait_resume_then_postprocess.sh`
- `wait_ed_collect_then_postprocess.sh`
- `stop_sim_restart_and_resume_ed_collect.sh`

## Common env knobs

- `NETEM_N_RUNS` (default `20`)
- `NETEM_INTERVAL` (default `30`)
- `ATTACK_TIER` (default `mid`)
- `GRAPH_PARALLEL_RUNS` (default `4`)
- `AGGREGATE_STRICT` (default `1`)
- `CONTINUE_AFTER_AGGREGATE_FAIL` (default `0`)
- `PRUNE_DOCKER` (default `0`)
- `ED_SIM_ROOT` (for restart mode)
