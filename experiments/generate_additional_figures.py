#!/usr/bin/env python3
"""生成额外的论文图表：拓扑可视化、鲁棒性子项分解、收敛曲线详图。"""

import sys
import os
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data.io_utils import generate_topology
from models.robustness import compute_R_components
from models.global_optimizer import run_optimization, DEFAULT_PARAMS, get_edge_changes

rcParams['font.family'] = 'DejaVu Sans'
rcParams['figure.dpi'] = 150
rcParams['savefig.dpi'] = 300
rcParams['savefig.bbox'] = 'tight'

FIGURES_DIR = os.path.join(os.path.dirname(__file__), 'figures')
WEIGHTS = (0.3, 0.4, 0.3)
os.makedirs(FIGURES_DIR, exist_ok=True)


def plot_topology_comparison(A0, A_star, save_path):
    """绘制优化前后拓扑结构可视化对比。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    G0 = nx.from_numpy_array((A0 > 0).astype(int))
    G_star = nx.from_numpy_array((A_star > 0).astype(int))

    pos = nx.spring_layout(G0, seed=42, k=1.5/np.sqrt(100))

    degrees_0 = dict(G0.degree())
    node_sizes_0 = [20 + degrees_0[n] * 15 for n in G0.nodes()]
    node_colors_0 = [degrees_0[n] for n in G0.nodes()]

    nx.draw_networkx(G0, pos, ax=ax1, with_labels=False,
                     node_size=node_sizes_0, node_color=node_colors_0,
                     cmap=plt.cm.YlOrRd, edge_color='gray', alpha=0.7,
                     width=0.5, vmin=0, vmax=max(node_colors_0))
    ax1.set_title('Before Optimization (Baseline)', fontsize=13)

    degrees_star = dict(G_star.degree())
    node_sizes_star = [20 + degrees_star[n] * 15 for n in G_star.nodes()]
    node_colors_star = [degrees_star[n] for n in G_star.nodes()]

    nx.draw_networkx(G_star, pos, ax=ax2, with_labels=False,
                     node_size=node_sizes_star, node_color=node_colors_star,
                     cmap=plt.cm.YlOrRd, edge_color='gray', alpha=0.7,
                     width=0.5, vmin=0, vmax=max(max(node_colors_0), max(node_colors_star)))
    ax2.set_title('After Optimization', fontsize=13)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_convergence_detail(history, save_path):
    """绘制详细收敛曲线（含各子项和时间）。"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))

    steps = [h['step'] for h in history]
    Rs = [h['R'] for h in history]
    R_s = [h['R_s'] for h in history]
    R_c = [h['R_c'] for h in history]
    R_r = [h['R_r'] for h in history]
    times = [h['time'] for h in history]

    ax = axes[0, 0]
    ax.plot(steps, Rs, 'k-', linewidth=2)
    ax.fill_between(steps, [r * 0.98 for r in Rs], [r * 1.02 for r in Rs], alpha=0.1, color='blue')
    ax.set_xlabel('Optimization Step')
    ax.set_ylabel('Total Robustness $R$')
    ax.set_title('(a) Total Robustness Evolution')
    ax.grid(True, alpha=0.3)

    ax = axes[0, 1]
    ax.plot(steps, R_s, 'b-', linewidth=1.5, label='$R_s$ (Structural)')
    ax.plot(steps, R_c, 'r-', linewidth=1.5, label='$R_c$ (Connectivity)')
    ax.plot(steps, R_r, 'g-', linewidth=1.5, label='$R_r$ (Recovery)')
    ax.set_xlabel('Optimization Step')
    ax.set_ylabel('Sub-component Score')
    ax.set_title('(b) Robustness Components')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    delta_R = [0] + [Rs[i] - Rs[i-1] for i in range(1, len(Rs))]
    ax.bar(steps, delta_R, color='steelblue', alpha=0.7)
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.set_xlabel('Optimization Step')
    ax.set_ylabel('$\\Delta R$ per Step')
    ax.set_title('(c) Per-step Robustness Change')
    ax.grid(True, alpha=0.3)

    ax = axes[1, 1]
    ax.plot(times, Rs, 'ko-', markersize=3, linewidth=1.5)
    ax.set_xlabel('Wall-clock Time (seconds)')
    ax.set_ylabel('Total Robustness $R$')
    ax.set_title('(d) Robustness vs. Computation Time')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_robustness_breakdown(results_dict, save_path):
    """绘制优化前后 R 子项分解对比图。"""
    topologies = list(results_dict.keys())
    n_topo = len(topologies)

    fig, axes = plt.subplots(1, n_topo, figsize=(5 * n_topo, 5))
    if n_topo == 1:
        axes = [axes]

    for idx, topo in enumerate(topologies):
        ax = axes[idx]
        before = results_dict[topo]['before']
        after = results_dict[topo]['after']

        labels = ['$R_s$', '$R_c$', '$R_r$', '$R$ (total)']
        before_vals = [before['R_s'], before['R_c'], before['R_r'], before['R']]
        after_vals = [after['R_s'], after['R_c'], after['R_r'], after['R']]

        x = np.arange(len(labels))
        width = 0.35
        ax.bar(x - width/2, before_vals, width, label='Before', color='steelblue', alpha=0.8)
        ax.bar(x + width/2, after_vals, width, label='After', color='coral', alpha=0.8)

        for i, (bv, av) in enumerate(zip(before_vals, after_vals)):
            pct = (av - bv) / max(bv, 1e-6) * 100
            ax.annotate(f'{pct:+.1f}%', xy=(i + width/2, av), fontsize=8,
                       ha='center', va='bottom', color='darkred')

        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel('Score')
        ax.set_title(topo)
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_ylim(0, max(max(before_vals), max(after_vals)) * 1.15)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def main():
    print("Generating additional figures...")

    A0 = generate_topology(100, model='ba', m=3, seed=42)
    params = DEFAULT_PARAMS.copy()
    params['max_steps'] = 150
    params['min_steps'] = 30
    params['gradient_sample_ratio'] = 0.10

    A_star, history = run_optimization(A0, params, verbose=True)

    plot_topology_comparison(A0, A_star,
                             os.path.join(FIGURES_DIR, 'fig_topology_comparison.png'))

    plot_convergence_detail(history,
                            os.path.join(FIGURES_DIR, 'fig_convergence_detail.png'))

    topologies = {
        'BA(m=3)': generate_topology(100, model='ba', m=3, seed=42),
        'WS(k=6,p=0.3)': generate_topology(100, model='ws', k=6, p=0.3, seed=42),
        'ER(p=0.06)': generate_topology(100, model='er', p=0.06, seed=42),
    }

    results_dict = {}
    for topo_name, A0_t in topologies.items():
        comps_before = compute_R_components(A0_t, WEIGHTS)
        A_star_t, _ = run_optimization(A0_t, params, verbose=False)
        comps_after = compute_R_components(A_star_t, WEIGHTS)
        results_dict[topo_name] = {
            'before': comps_before,
            'after': comps_after,
        }

    plot_robustness_breakdown(results_dict,
                               os.path.join(FIGURES_DIR, 'fig_robustness_breakdown.png'))

    changes = get_edge_changes(A0, A_star)
    print(f"\nEdge changes summary:")
    print(f"  Added: {len(changes['edges_to_add'])}")
    print(f"  Removed: {len(changes['edges_to_remove'])}")
    print(f"  Modified: {len(changes['edges_to_modify'])}")

    print("\nAll additional figures generated!")


if __name__ == '__main__':
    main()
