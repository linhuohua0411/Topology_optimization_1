#!/usr/bin/env python3
"""
在真实以太坊100节点私有链拓扑上运行完整实验。
"""

import sys
import os
import json
import time
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.robustness import (
    compute_R, compute_R_components, _laplacian_second_eigenvalue
)
from models.global_optimizer import (
    run_optimization, get_edge_changes, DEFAULT_PARAMS, mle_estimate_params
)
from models.baselines import (
    resinet_optimize, fpsblo_optimize, static_optimize,
    attack_simulation_optimize
)

rcParams['font.family'] = 'DejaVu Sans'
rcParams['figure.dpi'] = 150
rcParams['savefig.dpi'] = 300
rcParams['savefig.bbox'] = 'tight'

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')
FIGURES_DIR = os.path.join(os.path.dirname(__file__), 'figures')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'metrics')
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

WEIGHTS = (0.3, 0.4, 0.3)
N_REPEATS = 5


def load_real_topology():
    """加载真实以太坊私有链拓扑（优先 JSON 快照，回退 NPZ）。"""
    snapshot_files = sorted([
        f for f in os.listdir(DATA_DIR)
        if f.startswith('snapshot_') and f.endswith('.json')
    ])
    if snapshot_files:
        matrices = []
        for sf in snapshot_files:
            with open(os.path.join(DATA_DIR, sf), 'r', encoding='utf-8') as f:
                snap = json.load(f)
            n = int(snap['n_nodes'])
            A = np.zeros((n, n), dtype=np.float64)
            for edge in snap['edges']:
                i, j = int(edge[0]), int(edge[1])
                if 0 <= i < n and 0 <= j < n:
                    A[i, j] = 1.0
                    A[j, i] = 1.0
            matrices.append(A)
        node_ids = np.arange(matrices[0].shape[0])
        print(f"Loaded {len(matrices)} snapshots from JSON, {matrices[0].shape[0]} nodes")
        return matrices, node_ids, 'json_snapshots'

    npz_path = os.path.join(DATA_DIR, 'adjacency_matrices.npz')
    data = np.load(npz_path, allow_pickle=True)
    matrices = data['matrices']
    node_ids = data['node_ids']
    print(f"Loaded {len(matrices)} snapshots from NPZ, {matrices[0].shape[0]} nodes")
    return matrices, node_ids, 'npz'


def compute_graph_stats(A):
    """计算图统计量。"""
    G = nx.from_numpy_array((A > 0).astype(int))
    degrees = np.sum(A > 0, axis=1)
    stats = {
        'n_nodes': A.shape[0],
        'n_edges': int(np.sum(A > 0) / 2),
        'mean_degree': float(np.mean(degrees)),
        'std_degree': float(np.std(degrees)),
        'max_degree': int(np.max(degrees)),
        'min_degree': int(np.min(degrees)),
        'clustering_coeff': float(nx.average_clustering(G)),
        'lambda2': float(_laplacian_second_eigenvalue(A)),
        'is_connected': nx.is_connected(G),
        'global_efficiency': float(nx.global_efficiency(G)),
    }
    if nx.is_connected(G):
        stats['avg_path_length'] = float(nx.average_shortest_path_length(G))
        stats['avg_path_length_lcc'] = stats['avg_path_length']
        stats['diameter'] = nx.diameter(G)
        stats['n_components'] = 1
        stats['lcc_ratio'] = 1.0
    else:
        lcc = max(nx.connected_components(G), key=len)
        G_lcc = G.subgraph(lcc).copy()
        stats['avg_path_length'] = float('inf')
        stats['avg_path_length_lcc'] = float(nx.average_shortest_path_length(G_lcc))
        stats['diameter'] = nx.diameter(G_lcc)
        stats['lcc_ratio'] = len(lcc) / A.shape[0]
        stats['n_components'] = nx.number_connected_components(G)
    comps = compute_R_components(A, WEIGHTS)
    stats.update(comps)
    return stats


def attack_graph(A, attack_type='random', fraction=0.1, seed=42):
    """攻击图。"""
    rng = np.random.RandomState(seed)
    n = A.shape[0]
    n_remove = max(1, int(n * fraction))
    G = nx.from_numpy_array((A > 0).astype(int))

    if attack_type == 'random':
        nodes_to_remove = rng.choice(n, size=n_remove, replace=False).tolist()
    elif attack_type == 'targeted':
        degrees = np.sum(A > 0, axis=1)
        nodes_to_remove = np.argsort(-degrees)[:n_remove].tolist()
    else:
        raise ValueError(f"Unknown attack type: {attack_type}")

    G.remove_nodes_from(nodes_to_remove)
    remaining = len(G)

    if remaining == 0:
        return {
            'lcc_ratio': 0.0,
            'lcc_size': 0,
            'avg_path_length': float('inf'),
            'n_components': 0,
            'global_efficiency': 0.0,
        }

    components = list(nx.connected_components(G))
    lcc_size = max(len(c) for c in components)
    lcc_ratio = lcc_size / n
    lcc_graph = G.subgraph(max(components, key=len)).copy()
    avg_path = float(nx.average_shortest_path_length(lcc_graph)) if len(lcc_graph) > 1 else 0.0

    return {
        'lcc_ratio': lcc_ratio,
        'lcc_size': lcc_size,
        'avg_path_length': avg_path,
        'n_components': len(components),
        'global_efficiency': float(nx.global_efficiency(G)),
    }


def main():
    print("="*70)
    print("TIFS Real Ethereum Private Chain Experiments")
    print("="*70)

    matrices, node_ids, source_type = load_real_topology()
    A0 = matrices[0]
    n = A0.shape[0]

    results = {}
    results['data_source'] = {
        'type': source_type,
        'path': DATA_DIR,
        'n_snapshots': len(matrices),
        'n_nodes': int(n),
    }

    # === 1. Baseline topology analysis ===
    print("\n" + "="*60)
    print("1. Baseline Topology Analysis")
    print("="*60)
    stats0 = compute_graph_stats(A0)
    print(f"  Nodes: {stats0['n_nodes']}, Edges: {stats0['n_edges']}")
    print(f"  Mean degree: {stats0['mean_degree']:.1f} ± {stats0['std_degree']:.1f}")
    print(f"  Clustering: {stats0['clustering_coeff']:.4f}")
    print(f"  Avg path length: {stats0['avg_path_length']:.4f}")
    print(f"  λ₂: {stats0['lambda2']:.4f}")
    print(f"  R={stats0['R']:.6f} (R_s={stats0['R_s']:.4f}, R_c={stats0['R_c']:.4f}, R_r={stats0['R_r']:.4f})")
    results['baseline'] = stats0

    # === 2. MLE Parameter Estimation ===
    print("\n" + "="*60)
    print("2. MLE Parameter Estimation")
    print("="*60)
    estimated, loss = mle_estimate_params(matrices, dt_obs=60.0, n_restarts=5, max_iter=100, seed=42)
    print(f"  MLE Loss: {loss:.4f}")
    print(f"  Estimated params: {estimated}")
    results['mle'] = {'params': estimated, 'loss': loss}

    # === 3. Optimization ===
    print("\n" + "="*60)
    print("3. Topology Optimization on Real Ethereum Topology")
    print("="*60)
    params = DEFAULT_PARAMS.copy()
    params['max_steps'] = 150
    params['min_steps'] = 30
    params['gradient_sample_ratio'] = 0.10
    params['k_max'] = int(stats0['max_degree'])

    A_star, history = run_optimization(A0, params, verbose=True)
    stats_star = compute_graph_stats(A_star)
    changes = get_edge_changes(A0, A_star)

    r_improvement = (stats_star['R'] - stats0['R']) / max(stats0['R'], 1e-6) * 100
    print(f"\n  R: {stats0['R']:.4f} -> {stats_star['R']:.4f} ({r_improvement:+.2f}%)")
    print(f"  Path: {stats0['avg_path_length']:.2f} -> {stats_star['avg_path_length']:.2f}")
    print(f"  Clustering: {stats0['clustering_coeff']:.4f} -> {stats_star['clustering_coeff']:.4f}")
    print(f"  Edges add/remove/modify: {len(changes['edges_to_add'])}/{len(changes['edges_to_remove'])}/{len(changes['edges_to_modify'])}")

    results['optimization'] = {
        'before': stats0,
        'after': stats_star,
        'R_improvement_pct': r_improvement,
        'changes': {
            'add': len(changes['edges_to_add']),
            'remove': len(changes['edges_to_remove']),
            'modify': len(changes['edges_to_modify']),
        },
        'steps': len(history) - 1,
        'time_s': history[-1]['time'],
    }
    results['optimization_history'] = history

    # === 4. Attack Scenarios ===
    print("\n" + "="*60)
    print("4. Attack Scenarios on Real Topology")
    print("="*60)

    results['attack_pre_state'] = {
        'baseline': {
            'is_connected': bool(stats0['is_connected']),
            'lcc_ratio': float(stats0.get('lcc_ratio', 1.0)),
            'n_components': int(stats0.get('n_components', 1)),
            'global_efficiency': float(stats0.get('global_efficiency', 0.0)),
        },
        'optimized': {
            'is_connected': bool(stats_star['is_connected']),
            'lcc_ratio': float(stats_star.get('lcc_ratio', 1.0)),
            'n_components': int(stats_star.get('n_components', 1)),
            'global_efficiency': float(stats_star.get('global_efficiency', 0.0)),
        },
    }

    attack_configs = [
        ('random', 0.05), ('random', 0.10), ('random', 0.15),
        ('targeted', 0.03), ('targeted', 0.05), ('targeted', 0.10),
    ]

    attack_results = []
    for attack_type, fraction in attack_configs:
        base_scores = [attack_graph(A0, attack_type, fraction, seed=s) for s in range(N_REPEATS)]
        opt_scores = [attack_graph(A_star, attack_type, fraction, seed=s) for s in range(N_REPEATS)]

        r = {
            'attack_type': attack_type,
            'fraction': fraction,
            'baseline_lcc_mean': float(np.mean([s['lcc_ratio'] for s in base_scores])),
            'baseline_lcc_std': float(np.std([s['lcc_ratio'] for s in base_scores])),
            'optimized_lcc_mean': float(np.mean([s['lcc_ratio'] for s in opt_scores])),
            'optimized_lcc_std': float(np.std([s['lcc_ratio'] for s in opt_scores])),
            'baseline_path_mean': float(np.mean([s['avg_path_length'] for s in base_scores])),
            'optimized_path_mean': float(np.mean([s['avg_path_length'] for s in opt_scores])),
            'baseline_components_mean': float(np.mean([s['n_components'] for s in base_scores])),
            'optimized_components_mean': float(np.mean([s['n_components'] for s in opt_scores])),
            'baseline_lcc_size_mean': float(np.mean([s['lcc_size'] for s in base_scores])),
            'optimized_lcc_size_mean': float(np.mean([s['lcc_size'] for s in opt_scores])),
            'baseline_efficiency_mean': float(np.mean([s['global_efficiency'] for s in base_scores])),
            'optimized_efficiency_mean': float(np.mean([s['global_efficiency'] for s in opt_scores])),
        }
        attack_results.append(r)
        lcc_change = (r['optimized_lcc_mean'] - r['baseline_lcc_mean']) / max(r['baseline_lcc_mean'], 1e-6) * 100
        print(f"  {attack_type} {fraction*100:.0f}%: LCC {r['baseline_lcc_mean']:.4f}->{r['optimized_lcc_mean']:.4f} ({lcc_change:+.1f}%), "
              f"Path {r['baseline_path_mean']:.2f}->{r['optimized_path_mean']:.2f}")

    results['attack'] = attack_results

    # === 5. Comparison with Baselines ===
    print("\n" + "="*60)
    print("5. Comparison with Baselines (Real Topology)")
    print("="*60)

    R0 = stats0['R']
    comparison = {}

    comparison['Ours'] = {
        'R_final': stats_star['R'],
        'R_improvement_pct': r_improvement,
        'time_s': history[-1]['time'],
        'R_s': stats_star['R_s'], 'R_c': stats_star['R_c'], 'R_r': stats_star['R_r'],
    }
    print(f"  Ours: R={stats_star['R']:.4f} ({r_improvement:+.2f}%), time={history[-1]['time']:.1f}s")

    for method_name, method_func, method_kwargs in [
        ('ResiNet', resinet_optimize, {'max_rewires': 300}),
        ('FPSblo-EP', fpsblo_optimize, {'n_landmarks': 15, 'max_iters': 80}),
        ('Static', static_optimize, {'max_iters': 300}),
        ('AttackSim', attack_simulation_optimize, {'n_attacks': 30, 'max_rewires': 100}),
    ]:
        t0 = time.time()
        A_m, hist_m = method_func(A0, seed=42, weights=WEIGHTS, **method_kwargs)
        t_m = time.time() - t0
        comps_m = compute_R_components(A_m, WEIGHTS)
        imp = (comps_m['R'] - R0) / max(R0, 1e-6) * 100
        comparison[method_name] = {
            'R_final': comps_m['R'], 'R_improvement_pct': imp, 'time_s': t_m,
            'R_s': comps_m['R_s'], 'R_c': comps_m['R_c'], 'R_r': comps_m['R_r'],
        }
        print(f"  {method_name}: R={comps_m['R']:.4f} ({imp:+.2f}%), time={t_m:.1f}s")

    results['comparison'] = comparison

    # === 6. Parameter Stability ===
    print("\n" + "="*60)
    print("6. Parameter Stability (5 runs)")
    print("="*60)
    stability_results = []
    for ri in range(N_REPEATS):
        p = params.copy()
        p['seed'] = 42 + ri
        p['max_steps'] = 80
        A_s, h = run_optimization(A0, p, verbose=False)
        cs = compute_R_components(A_s, WEIGHTS)
        imp = (cs['R'] - R0) / max(R0, 1e-6) * 100
        stability_results.append({
            'run': ri, 'R_improvement_pct': imp, 'R_final': cs['R'],
            'time_s': h[-1]['time'], 'steps': len(h) - 1
        })
        print(f"  Run {ri}: R improvement = {imp:.2f}%, time = {h[-1]['time']:.1f}s")

    imp_mean = np.mean([r['R_improvement_pct'] for r in stability_results])
    imp_std = np.std([r['R_improvement_pct'] for r in stability_results])
    print(f"  Summary: {imp_mean:.2f}% ± {imp_std:.2f}%")
    results['stability'] = stability_results

    # === Generate Figures ===
    print("\n" + "="*60)
    print("Generating Figures for Real Ethereum Data")
    print("="*60)

    # Fig: Robustness evolution
    fig, ax = plt.subplots(figsize=(8, 5))
    steps = [h['step'] for h in history]
    ax.plot(steps, [h['R'] for h in history], 'k-', lw=2, label='R (total)')
    ax.plot(steps, [h['R_s'] for h in history], 'b--', lw=1.5, label='$R_s$')
    ax.plot(steps, [h['R_c'] for h in history], 'r-.', lw=1.5, label='$R_c$')
    ax.plot(steps, [h['R_r'] for h in history], 'g:', lw=1.5, label='$R_r$')
    ax.set_xlabel('Optimization Step')
    ax.set_ylabel('Robustness Score')
    ax.set_title('Robustness Evolution (Real Ethereum 106-node Topology)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_eth_real_evolution.png'))
    plt.close()
    print("  Saved: fig_eth_real_evolution.png")

    # Fig: Degree distribution
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    deg0 = np.sum(A0 > 0, axis=1).astype(int)
    deg_star = np.sum(A_star > 0, axis=1).astype(int)
    max_d = max(deg0.max(), deg_star.max()) + 1
    bins = np.arange(0, max_d + 1) - 0.5
    ax1.hist(deg0, bins=bins, alpha=0.7, color='steelblue', edgecolor='black')
    ax1.set_xlabel('Degree'); ax1.set_ylabel('Count')
    ax1.set_title('Before Optimization (Real ETH)')
    ax1.grid(True, alpha=0.3)
    ax2.hist(deg_star, bins=bins, alpha=0.7, color='coral', edgecolor='black')
    ax2.set_xlabel('Degree'); ax2.set_ylabel('Count')
    ax2.set_title('After Optimization (Real ETH)')
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_eth_real_degree.png'))
    plt.close()
    print("  Saved: fig_eth_real_degree.png")

    # Fig: Attack comparison
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    for ax, atype, title in [(ax1, 'random', 'Random Attack'), (ax2, 'targeted', 'Targeted Attack')]:
        subset = [r for r in attack_results if r['attack_type'] == atype]
        fracs = [r['fraction'] * 100 for r in subset]
        base_lcc = [r['baseline_lcc_mean'] for r in subset]
        opt_lcc = [r['optimized_lcc_mean'] for r in subset]
        x = np.arange(len(fracs))
        w = 0.35
        ax.bar(x - w/2, base_lcc, w, label='Baseline', color='steelblue', capsize=3)
        ax.bar(x + w/2, opt_lcc, w, label='Optimized', color='coral', capsize=3)
        ax.set_xlabel('Removal Fraction (%)')
        ax.set_ylabel('LCC Ratio')
        ax.set_title(f'{title} (Real ETH)')
        ax.set_xticks(x)
        ax.set_xticklabels([f'{f:.0f}%' for f in fracs])
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_eth_real_attack.png'))
    plt.close()
    print("  Saved: fig_eth_real_attack.png")

    # Fig: Comparison bar
    methods = list(comparison.keys())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    colors = ['coral', 'steelblue', 'mediumpurple', 'forestgreen', 'goldenrod']
    x = np.arange(len(methods))
    ax1.bar(x, [comparison[m]['R_final'] for m in methods], color=colors[:len(methods)], edgecolor='black')
    ax1.set_ylabel('Final Robustness R')
    ax1.set_title('Robustness (Real ETH)')
    ax1.set_xticks(x)
    ax1.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
    ax1.grid(True, alpha=0.3, axis='y')
    ax2.bar(x, [comparison[m]['R_improvement_pct'] for m in methods], color=colors[:len(methods)], edgecolor='black')
    ax2.set_ylabel('Improvement (%)')
    ax2.set_title('Improvement (Real ETH)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_eth_real_comparison.png'))
    plt.close()
    print("  Saved: fig_eth_real_comparison.png")

    # Save results
    def make_serializable(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, dict): return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)): return [make_serializable(v) for v in obj]
        return obj

    with open(os.path.join(RESULTS_DIR, 'eth_real_results.json'), 'w') as f:
        json.dump(make_serializable(results), f, indent=2, ensure_ascii=False)
    out_json = os.path.join(RESULTS_DIR, 'eth_real_results.json')
    print(f"\n  Results saved to: {out_json}")
    print(f"  Result file exists: {os.path.exists(out_json)}")

    # Print summary
    print("\n" + "="*70)
    print("SUMMARY: Real Ethereum Private Chain Results")
    print("="*70)
    print(f"\nBaseline: {stats0['n_nodes']} nodes, {stats0['n_edges']} edges, "
          f"R={stats0['R']:.4f}, path={stats0['avg_path_length']:.2f}")
    print(f"Optimized: R={stats_star['R']:.4f} ({r_improvement:+.2f}%), "
          f"path={stats_star['avg_path_length']:.2f}")
    print(f"\nComparison:")
    for m, r in comparison.items():
        print(f"  {m:<15} R={r['R_final']:.4f} ({r['R_improvement_pct']:+.2f}%) "
              f"R_c={r['R_c']:.4f} time={r['time_s']:.1f}s")
    print(f"\nStability: {imp_mean:.2f}% ± {imp_std:.2f}%")


if __name__ == '__main__':
    main()
