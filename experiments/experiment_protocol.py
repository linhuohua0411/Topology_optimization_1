#!/usr/bin/env python3
"""
Frozen experiment protocol for TIFS submission.

This file centralizes critical experiment settings so ETH/dual scripts
share exactly the same evaluation protocol.
"""

# Update only when intentionally changing paper protocol.
PROTOCOL_VERSION = "tifs-freeze-v1"

# Robustness composition
WEIGHTS = (0.3, 0.4, 0.3)

# Repeat count for attack/stability
N_REPEATS = 5
N_RUNS_DEFAULT = 10

# Adaptive k_max policy
KMAX_FLOOR = 50
KMAX_RATIO = 0.8
KMAX_BUSINESS_CAP = 150

# Baseline search policy
BASELINE_ALLOW_DISCONNECTED_INTERMEDIATE = True
BASELINE_DISCONNECT_PENALTY = 0.3

# Scenario-level weight policy for ED mainline.
USE_SCENARIO_WEIGHTS = False
SCENARIO_WEIGHTS = {}

# Attack tiers (fraction of affected nodes/links).
ATTACK_TIERS = {
    "low": 0.33,
    "mid": 0.66,
    "high": 1.00,
}
DEFAULT_ATTACK_TIER = "mid"

# Fairness budgets
# 1) fair-time: use Ours wall-clock time as budget
# 2) fair-edge: use max(FLOOR, Ours edge changes) as budget
FAIR_EDGE_BUDGET_FLOOR = 10

# Runtime budgets.
OURS_TIME_BUDGET_CAP_S = 8.0
RAW_BASELINE_TIME_BUDGET_CAP_S = 8.0

# Connectivity repair controls used by graph optimizer.
CONNECTIVITY_REPAIR_WEIGHT = 1.0
CONNECTIVITY_REPAIR_BUDGET_RATIO = 0.15
CONNECTIVITY_REPAIR_BUDGET_MIN = 5
CONNECTIVITY_REPAIR_PENALTY_LAMBDA = 0.3

