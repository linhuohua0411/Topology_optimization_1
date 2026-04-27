#!/usr/bin/env python3
"""
Frozen experiment protocol for TIFS submission.

This file centralizes critical experiment settings so ETH/dual scripts
share exactly the same evaluation protocol.
"""

# Update only when intentionally changing paper protocol.
PROTOCOL_VERSION = "tifs-freeze-v3"

# Robustness composition (fixed mainline setting).
# Selection principle:
# 1) external public metrics (lcc_ratio / avg_path_len) are primary;
# 2) choose cross-scenario stable setting under ED-MAIN-BASE/LINK/NETEM;
# 3) keep reproducible fixed weights for unified_full_protocol.
# Final adopted fixed weights: connectivity_bias = (0.25, 0.55, 0.20).
WEIGHTS = (0.25, 0.55, 0.20)

# Optional scenario-gated fixed weights (offline selected, reproducible).
# If disabled, all scenarios use WEIGHTS.
# Tiered IDs (e.g., ED-MAIN-LINK-low) are normalized by prefix in runner.
USE_SCENARIO_WEIGHTS = True
SCENARIO_WEIGHTS = {
    "ED-MAIN-BASE": (0.25, 0.55, 0.20),
    "ED-MAIN-LINK": (0.22, 0.60, 0.18),
    "ED-MAIN-NETEM": (0.24, 0.58, 0.18),
}

# Tiered attack design (1 + 2x3):
# - BASE: one condition (no attack)
# - LINK / NETEM: low/mid/high degradation tiers
ATTACK_TIERS = {
    "low": 0.05,
    "mid": 0.10,
    "high": 0.20,
}
DEFAULT_ATTACK_TIER = "mid"

# Repeat count for attack/stability
N_REPEATS = 5
N_RUNS_DEFAULT = 20

# Adaptive k_max policy
KMAX_FLOOR = 50
KMAX_RATIO = 0.8
KMAX_BUSINESS_CAP = 150

# Baseline search policy
BASELINE_ALLOW_DISCONNECTED_INTERMEDIATE = True
BASELINE_DISCONNECT_PENALTY = 0.3

# Fairness budgets
# 1) fair-time: use Ours wall-clock time as budget
# 2) fair-edge: use max(FLOOR, Ours edge changes) as budget
FAIR_EDGE_BUDGET_FLOOR = 10
OURS_TIME_BUDGET_CAP_S = 45.0
RAW_BASELINE_TIME_BUDGET_CAP_S = 45.0

# Connectivity repair control in optimizer.
# Repair edges are no longer "free": we cap repair operations and add a
# cumulative repair penalty in optimization score selection.
CONNECTIVITY_REPAIR_WEIGHT = 0.10
CONNECTIVITY_REPAIR_BUDGET_RATIO = 0.08
CONNECTIVITY_REPAIR_BUDGET_MIN = 2
CONNECTIVITY_REPAIR_PENALTY_LAMBDA = 0.002

