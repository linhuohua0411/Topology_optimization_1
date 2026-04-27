#!/usr/bin/env python3
"""
TIFS-oriented statistics helpers: paired tests, effect sizes, Holm correction, CSV export.

Used by optimization pipelines (e.g. run_eth_docker_experiments) and collected-data aggregators.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from scipy import stats as scipy_stats
except ImportError:  # pragma: no cover
    scipy_stats = None


STATS_SUMMARY_FIELDNAMES = [
    "comparison_id",
    "stat_key",
    "budget_variant",
    "experiment_id",
    "test_name",
    "n",
    "mean",
    "std",
    "ci95_low",
    "ci95_high",
    "p_value",
    "p_value_holm",
    "effect_size",
    "effect_size_name",
]


def mean_std_ci95_t(values: Sequence[float], alpha: float = 0.05) -> Tuple[float, float, float, float]:
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    mean = float(np.mean(arr)) if n else 0.0
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    if n <= 1:
        return mean, std, mean, mean
    se = std / np.sqrt(n)
    tcrit = scipy_stats.t.ppf(1 - alpha / 2, df=n - 1) if scipy_stats is not None else 1.96
    half = float(tcrit * se)
    return mean, std, mean - half, mean + half


def cohens_dz_one_sample(d: Sequence[float]) -> float:
    """Cohen's d_z for paired differences vs 0: mean(d) / sd(d)."""
    arr = np.asarray(d, dtype=float)
    if len(arr) < 2:
        return 0.0
    sd = float(np.std(arr, ddof=1))
    if sd == 0.0:
        return 0.0
    return float(np.mean(arr) / sd)


def paired_ttest_pvalue(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Two-sided paired t-test p-value; None if scipy missing or invalid."""
    if scipy_stats is None:
        return None
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if len(x) != len(y) or len(x) < 2:
        return None
    try:
        _, p = scipy_stats.ttest_rel(x, y)
        return float(p) if p == p else None  # NaN guard
    except Exception:
        return None


def one_sample_ttest_pvalue(d: Sequence[float], mu0: float = 0.0) -> Optional[float]:
    """Two-sided one-sample t-test on d vs mu0 (e.g. paired deltas vs 0)."""
    if scipy_stats is None:
        return None
    arr = np.asarray(d, dtype=float)
    if len(arr) < 2:
        return None
    try:
        _, p = scipy_stats.ttest_1samp(arr, mu0)
        return float(p) if p == p else None
    except Exception:
        return None


def wilcoxon_signed_rank_vs_zero_pvalue(d: Sequence[float]) -> Optional[float]:
    """Two-sided Wilcoxon signed-rank on d vs 0 (paired under−pre deltas)."""
    if scipy_stats is None:
        return None
    arr = np.asarray(d, dtype=float)
    if len(arr) < 2:
        return None
    if np.allclose(arr, 0.0):
        return None
    try:
        _, p = scipy_stats.wilcoxon(arr, zero_method="wilcox", alternative="two-sided")
        return float(p) if p == p else None
    except Exception:
        return None


def test_one_sample_deltas_with_normality_gate(
    d: Sequence[float],
    shapiro_alpha: float = 0.05,
) -> Tuple[Optional[float], str, float, str]:
    """
    Align with protocol matrix §6: Shapiro-Wilk(alpha) on deltas;
    if not reject normality -> one-sample t vs 0; else Wilcoxon signed-rank vs 0.
    Returns (p_value, test_name, effect_size, effect_size_name).
    """
    arr = np.asarray(d, dtype=float)
    dz = cohens_dz_one_sample(arr)
    if len(arr) < 2:
        return None, "insufficient_n", dz, ""
    use_t = True
    if scipy_stats is not None and len(arr) >= 3:
        try:
            _, p_shapiro = scipy_stats.shapiro(arr)
            if p_shapiro < shapiro_alpha:
                use_t = False
        except Exception:
            use_t = True
    if use_t:
        p = one_sample_ttest_pvalue(arr, 0.0)
        return p, "one_sample_t_delta_vs_0", dz, "cohens_dz_paired"
    p = wilcoxon_signed_rank_vs_zero_pvalue(arr)
    return p, "wilcoxon_signed_rank_delta_vs_0", dz, "cohens_dz_descriptive_under_non_normal"


def holm_bonferroni(p_values: Sequence[Optional[float]]) -> List[Optional[float]]:
    """
    Holm step-down adjusted p-values (same order as input).
    None / NaN entries are passed through as None.
    """
    n = len(p_values)
    indexed = [(i, p) for i, p in enumerate(p_values) if p is not None and p == p]
    if not indexed:
        return [None] * n
    sorted_pairs = sorted(indexed, key=lambda t: t[1])
    m = len(sorted_pairs)
    q_prev = 0.0
    adjusted_by_index: Dict[int, float] = {}
    for rank, (orig_i, p) in enumerate(sorted_pairs, start=1):
        q_i = max(q_prev, (m - rank + 1) * p)
        q_prev = q_i
        adjusted_by_index[orig_i] = min(1.0, q_i)
    out: List[Optional[float]] = []
    for i, p in enumerate(p_values):
        if p is None or p != p:
            out.append(None)
        else:
            out.append(adjusted_by_index.get(i))
    return out


def build_method_comparison_rows(
    *,
    experiment_id: str,
    budget_variant: str,
    ours_vals: Sequence[float],
    base_vals_by_method: Dict[str, Sequence[float]],
    metric_key: str,
    holm_block: bool = True,
) -> List[Dict[str, Any]]:
    """
    Rows: OUR vs each baseline, paired on run index; deltas = ours - baseline.
    """
    ours = np.asarray(ours_vals, dtype=float)
    rows: List[Dict[str, Any]] = []
    raw_ps: List[Optional[float]] = []

    for method, base in base_vals_by_method.items():
        b = np.asarray(base, dtype=float)
        if len(ours) != len(b) or len(ours) < 2:
            continue
        deltas = (ours - b).tolist()
        mean, std, ci_l, ci_h = mean_std_ci95_t(deltas)
        p_raw, test_name, dz, eff_name = test_one_sample_deltas_with_normality_gate(deltas)
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
                "effect_size": dz,
                "effect_size_name": eff_name,
            }
        )

    if holm_block and rows:
        holm = holm_bonferroni(raw_ps)
        for r, ph in zip(rows, holm):
            r["p_value_holm"] = ph

    return rows


def write_stats_summary_csv(rows: List[Dict[str, Any]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=STATS_SUMMARY_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in STATS_SUMMARY_FIELDNAMES})
