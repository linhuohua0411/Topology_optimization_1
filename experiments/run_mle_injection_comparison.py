#!/usr/bin/env python3
"""
MLE 注入 vs 非注入对比实验（合成 BA 100 节点）。

目标：
1) 先在时序快照上估计 MLE 参数；
2) 在相同初始拓扑与相同随机种子下，比较：
   - non_injected: 使用默认优化参数
   - injected: 在默认参数基础上注入 MLE 的 6 个动力学参数
3) 输出到 experiments/metrics/mle_injection_comparison.json
"""

import os
import sys
import json
import time
import argparse
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from data.io_utils import generate_topology, generate_temporal_topology
from models.robustness import compute_R_components
from models.global_optimizer import DEFAULT_PARAMS, run_optimization, mle_estimate_params


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "metrics")
os.makedirs(RESULTS_DIR, exist_ok=True)


def _set_full_gradient(params):
    params["gradient_mode"] = "full"
    params["gradient_sample_ratio"] = 0.05
    return params


def _run_once(A0, params):
    t0 = time.time()
    A_star, history = run_optimization(A0, params=params, verbose=False)
    elapsed = time.time() - t0

    w = (params["w1"], params["w2"], params["w3"])
    before = compute_R_components(A0, w)
    after = compute_R_components(A_star, w)
    imp = (after["R"] - before["R"]) / max(before["R"], 1e-12) * 100.0
    return {
        "R_before": before["R"],
        "R_after": after["R"],
        "R_improvement_pct": imp,
        "R_s_after": after["R_s"],
        "R_c_after": after["R_c"],
        "R_r_after": after["R_r"],
        "convergence_steps": len(history) - 1,
        "time_s": elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-repeats", type=int, default=3, help="paired repeats")
    parser.add_argument("--seed-base", type=int, default=42, help="base random seed")
    parser.add_argument("--n-snapshots", type=int, default=30, help="temporal snapshots for MLE")
    parser.add_argument("--change-rate", type=float, default=0.05, help="temporal change rate")
    args = parser.parse_args()

    A0 = generate_topology(100, model="ba", m=3, seed=42)
    snapshots = generate_temporal_topology(
        A0, n_snapshots=args.n_snapshots, change_rate=args.change_rate, seed=42
    )
    mle_params, mle_loss = mle_estimate_params(
        snapshots, dt_obs=1.0, n_restarts=5, max_iter=100, seed=42
    )

    base_params = DEFAULT_PARAMS.copy()
    base_params["max_steps"] = 150
    base_params["min_steps"] = 30
    _set_full_gradient(base_params)

    injected_template = base_params.copy()
    injected_template.update(mle_params)

    paired_runs = []
    for i in range(args.n_repeats):
        seed = args.seed_base + i

        p_non = base_params.copy()
        p_non["seed"] = seed
        r_non = _run_once(A0, p_non)

        p_inj = injected_template.copy()
        p_inj["seed"] = seed
        r_inj = _run_once(A0, p_inj)

        paired_runs.append(
            {
                "run": i,
                "seed": seed,
                "non_injected": r_non,
                "injected": r_inj,
                "delta_improvement_pct_injected_minus_non": (
                    r_inj["R_improvement_pct"] - r_non["R_improvement_pct"]
                ),
            }
        )

    non_imps = np.array([r["non_injected"]["R_improvement_pct"] for r in paired_runs], dtype=float)
    inj_imps = np.array([r["injected"]["R_improvement_pct"] for r in paired_runs], dtype=float)
    deltas = inj_imps - non_imps

    result = {
        "experiment": "mle_injection_vs_non_injection",
        "settings": {
            "n_repeats": args.n_repeats,
            "seed_base": args.seed_base,
            "optimization": {
                "max_steps": base_params["max_steps"],
                "min_steps": base_params["min_steps"],
                "gradient_mode": base_params["gradient_mode"],
                "gradient_sample_ratio": base_params["gradient_sample_ratio"],
            },
            "mle_temporal": {
                "n_snapshots": args.n_snapshots,
                "change_rate": args.change_rate,
                "dt_obs": 1.0,
                "n_restarts": 5,
                "max_iter": 100,
            },
        },
        "mle_estimation": {
            "estimated_params": mle_params,
            "mle_loss": mle_loss,
        },
        "paired_runs": paired_runs,
        "summary": {
            "non_injected_improvement_mean_pct": float(non_imps.mean()),
            "non_injected_improvement_std_pct": float(non_imps.std()),
            "injected_improvement_mean_pct": float(inj_imps.mean()),
            "injected_improvement_std_pct": float(inj_imps.std()),
            "delta_mean_pct": float(deltas.mean()),
            "delta_std_pct": float(deltas.std()),
        },
    }

    out_path = os.path.join(RESULTS_DIR, "mle_injection_comparison.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()

