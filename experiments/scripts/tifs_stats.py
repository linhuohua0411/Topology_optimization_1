#!/usr/bin/env python3
"""Shared statistics helpers for ETH/BTC experiment scripts."""

from __future__ import annotations

import csv
import math
import statistics
from typing import Any

from scipy import stats


def mean_std_ci95_t(values: list[float]) -> tuple[float, float, float, float]:
    n = len(values)
    if n == 0:
        return math.nan, math.nan, math.nan, math.nan
    mean = float(statistics.mean(values))
    std = float(statistics.stdev(values)) if n >= 2 else 0.0
    if n < 2:
        return mean, std, mean, mean
    try:
        low, high = stats.t.interval(0.95, n - 1, loc=mean, scale=stats.sem(values))
        return mean, std, float(low), float(high)
    except Exception:
        half = 1.96 * (std / math.sqrt(n))
        return mean, std, mean - half, mean + half


def holm_bonferroni(pvals: list[float | None]) -> list[float | None]:
    valid = [(i, p) for i, p in enumerate(pvals) if p is not None and math.isfinite(float(p))]
    out: list[float | None] = [None] * len(pvals)
    if not valid:
        return out
    valid.sort(key=lambda x: float(x[1]))
    m = len(valid)
    running = 0.0
    for rank, (idx, p) in enumerate(valid):
        adj = (m - rank) * float(p)
        running = max(running, adj)
        out[idx] = min(1.0, running)
    return out


def test_one_sample_deltas_with_normality_gate(deltas: list[float]) -> tuple[float | None, str, float | None, str]:
    n = len(deltas)
    if n < 2:
        return None, "insufficient_n", None, ""
    std = float(statistics.stdev(deltas))
    if std == 0.0:
        return None, "constant_delta", None, ""
    effect = float(statistics.mean(deltas) / std)
    test_name = "one_sample_t"
    p_value: float | None = None
    try:
        if n >= 3:
            _, p_norm = stats.shapiro(deltas)
            if p_norm < 0.05:
                test_name = "wilcoxon"
                _, p_value = stats.wilcoxon(deltas, alternative="two-sided")
            else:
                _, p_value = stats.ttest_1samp(deltas, popmean=0.0)
        else:
            _, p_value = stats.ttest_1samp(deltas, popmean=0.0)
    except Exception:
        p_value = None
        test_name = "descriptive_only"
    return (float(p_value) if p_value is not None else None, test_name, effect, "cohens_dz")


def build_method_comparison_rows(
    experiment_id: str,
    budget_variant: str,
    ours_vals: list[float],
    base_vals_by_method: dict[str, list[float]],
    metric_key: str,
    holm_block: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_ps: list[float | None] = []

    for method, base_vals in base_vals_by_method.items():
        if len(base_vals) != len(ours_vals):
            continue
        deltas = [float(a - b) for a, b in zip(ours_vals, base_vals)]
        mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
        p_raw, test_name, eff, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
        raw_ps.append(p_raw)
        rows.append(
            {
                "comparison_id": f"CMP-{experiment_id}-OUR-{method}",
                "stat_key": f"{metric_key}.paired_delta",
                "budget_variant": budget_variant,
                "experiment_id": experiment_id,
                "test_name": test_name,
                "n": len(deltas),
                "mean": mean,
                "std": std,
                "ci95_low": ci_l,
                "ci95_high": ci_h,
                "p_value": p_raw,
                "p_value_holm": None,
                "effect_size": eff,
                "effect_size_name": eff_name,
            }
        )

    if holm_block and rows:
        holm = holm_bonferroni(raw_ps)
        for r, p_h in zip(rows, holm):
            r["p_value_holm"] = p_h
    return rows


def write_stats_summary_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

