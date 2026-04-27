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

