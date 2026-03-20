#!/usr/bin/env python3
"""
完整实验运行脚本：有效性验证、参数敏感性、对比实验、攻击场景。
生成所有实验结果数据和论文图表。

对应论文第 4 章实验设计。
"""

import sys
import os
import time
import json
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data.io_utils import generate_topology, generate_temporal_topology
from models.robustness import (
    compute_R, compute_R_components, compute_R_s, compute_R_c, compute_R_r,
    _laplacian_second_eigenvalue
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

RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'metrics')
FIGURES_DIR = os.path.join(os.path.dirname(__file__), 'figures')
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)

N_NODES = 100
WEIGHTS = (0.3, 0.4, 0.3)
N_REPEATS = 5
GRADIENT_SAMPLE_RATIO = 0.10


def compute_graph_stats(A):
    """计算图的结构统计量。"""
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
        'avg_path_length': float(nx.average_shortest_path_length(G)) if nx.is_connected(G) else float('inf'),
        'diameter': nx.diameter(G) if nx.is_connected(G) else float('inf'),
        'lambda2': float(_laplacian_second_eigenvalue(A)),
        'is_connected': nx.is_connected(G),
    }
    comps = compute_R_components(A, WEIGHTS)
    stats.update(comps)
    return stats


def attack_graph(A, attack_type='random', fraction=0.1, seed=42):
    """对图执行攻击并返回攻击后的统计量。"""
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
        return {'lcc_ratio': 0.0, 'avg_path_length': float('inf'), 'n_components': 0}

    components = list(nx.connected_components(G))
    lcc_size = max(len(c) for c in components)
    lcc_ratio = lcc_size / n

    lcc_graph = G.subgraph(max(components, key=len)).copy()
    avg_path = float(nx.average_shortest_path_length(lcc_graph)) if len(lcc_graph) > 1 else 0.0

    return {
        'lcc_ratio': lcc_ratio,
        'avg_path_length': avg_path,
        'n_components': len(components),
        'remaining_nodes': remaining,
    }


def experiment_411_mle(results_collector):
    """4.1.1 参数估计有效性实验。"""
    print("\n" + "="*60)
    print("Experiment 4.1.1: MLE Parameter Estimation")
    print("="*60)

    A0 = generate_topology(N_NODES, model='ba', m=3, seed=42)
    snapshots = generate_temporal_topology(A0, n_snapshots=30, change_rate=0.05, seed=42)

    estimated_params, loss = mle_estimate_params(
        snapshots, dt_obs=1.0, n_restarts=5, max_iter=100, seed=42
    )
    print(f"MLE Loss: {loss:.6f}")
    print(f"Estimated params: {estimated_params}")

    A_pred = snapshots[0].copy()
    edge_acc_list = []
    degree_err_list = []
    path_err_list = []
    cluster_err_list = []

    for t in range(1, min(len(snapshots), 11)):
        A_true = snapshots[t]
        binary_pred = (A_pred > 0.5).astype(float)
        binary_true = (A_true > 0.5).astype(float)
        n_total = N_NODES * (N_NODES - 1) // 2
        correct = 0
        for i in range(N_NODES):
            for j in range(i + 1, N_NODES):
                if binary_pred[i, j] == binary_true[i, j]:
                    correct += 1
        edge_acc = correct / n_total
        edge_acc_list.append(edge_acc)

        deg_pred = np.mean(np.sum(A_pred > 0, axis=1))
        deg_true = np.mean(np.sum(A_true > 0, axis=1))
        degree_err_list.append(abs(deg_pred - deg_true) / max(deg_true, 1e-6))

        G_pred = nx.from_numpy_array((A_pred > 0).astype(int))
        G_true = nx.from_numpy_array((A_true > 0).astype(int))
        if nx.is_connected(G_pred) and nx.is_connected(G_true):
            p_pred = nx.average_shortest_path_length(G_pred)
            p_true = nx.average_shortest_path_length(G_true)
            path_err_list.append(abs(p_pred - p_true) / max(p_true, 1e-6))
        else:
            path_err_list.append(0.5)

        c_pred = nx.average_clustering(G_pred)
        c_true = nx.average_clustering(G_true)
        cluster_err_list.append(abs(c_pred - c_true) / max(c_true, 1e-6))

    mle_results = {
        'edge_accuracy_mean': float(np.mean(edge_acc_list)),
        'edge_accuracy_std': float(np.std(edge_acc_list)),
        'degree_rel_error_mean': float(np.mean(degree_err_list)),
        'degree_rel_error_std': float(np.std(degree_err_list)),
        'path_rel_error_mean': float(np.mean(path_err_list)),
        'path_rel_error_std': float(np.std(path_err_list)),
        'cluster_rel_error_mean': float(np.mean(cluster_err_list)),
        'cluster_rel_error_std': float(np.std(cluster_err_list)),
        'estimated_params': estimated_params,
        'mle_loss': loss,
    }
    results_collector['mle'] = mle_results

    print(f"\nMLE Results:")
    print(f"  Edge accuracy: {mle_results['edge_accuracy_mean']:.4f} ± {mle_results['edge_accuracy_std']:.4f}")
    print(f"  Degree rel error: {mle_results['degree_rel_error_mean']:.4f} ± {mle_results['degree_rel_error_std']:.4f}")
    print(f"  Path rel error: {mle_results['path_rel_error_mean']:.4f} ± {mle_results['path_rel_error_std']:.4f}")
    print(f"  Cluster rel error: {mle_results['cluster_rel_error_mean']:.4f} ± {mle_results['cluster_rel_error_std']:.4f}")

    return mle_results


def experiment_412_optimization(results_collector):
    """4.1.2 拓扑结构全局优化有效性实验。"""
    print("\n" + "="*60)
    print("Experiment 4.1.2: Topology Optimization Effectiveness")
    print("="*60)

    topologies = {
        'BA(m=3)': generate_topology(N_NODES, model='ba', m=3, seed=42),
        'WS(k=6,p=0.3)': generate_topology(N_NODES, model='ws', k=6, p=0.3, seed=42),
        'ER(p=0.06)': generate_topology(N_NODES, model='er', p=0.06, seed=42),
    }

    opt_results = {}
    all_histories = {}

    for topo_name, A0 in topologies.items():
        print(f"\n--- Topology: {topo_name} ---")
        stats_before = compute_graph_stats(A0)

        params = DEFAULT_PARAMS.copy()
        params['max_steps'] = 150
        params['min_steps'] = 30
        params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO

        A_star, history = run_optimization(A0, params, verbose=True)
        stats_after = compute_graph_stats(A_star)
        changes = get_edge_changes(A0, A_star)

        r_improvement = (stats_after['R'] - stats_before['R']) / max(stats_before['R'], 1e-6) * 100

        opt_results[topo_name] = {
            'before': stats_before,
            'after': stats_after,
            'R_improvement_pct': r_improvement,
            'edges_added': len(changes['edges_to_add']),
            'edges_removed': len(changes['edges_to_remove']),
            'edges_modified': len(changes['edges_to_modify']),
            'convergence_steps': len(history) - 1,
            'convergence_time_s': history[-1]['time'],
        }
        all_histories[topo_name] = history

        print(f"  R: {stats_before['R']:.4f} -> {stats_after['R']:.4f} ({r_improvement:+.2f}%)")
        print(f"  Path: {stats_before['avg_path_length']:.2f} -> {stats_after['avg_path_length']:.2f}")
        print(f"  Clustering: {stats_before['clustering_coeff']:.4f} -> {stats_after['clustering_coeff']:.4f}")

    results_collector['optimization'] = opt_results
    results_collector['optimization_histories'] = all_histories
    return opt_results, all_histories


def experiment_42_parameter_sensitivity(results_collector):
    """4.2 参数敏感性实验（固定参数 + 随机扰动）。"""
    print("\n" + "="*60)
    print("Experiment 4.2: Parameter Sensitivity")
    print("="*60)

    A0 = generate_topology(N_NODES, model='ba', m=3, seed=42)

    print("\n--- 4.2.1 Fixed parameters, multiple runs ---")
    fixed_results = []
    for run_i in range(N_REPEATS):
        params = DEFAULT_PARAMS.copy()
        params['seed'] = 42 + run_i
        params['max_steps'] = 100
        params['min_steps'] = 30
        params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO

        A_star, history = run_optimization(A0, params, verbose=False)
        comps_star = compute_R_components(A_star, WEIGHTS)
        comps_orig = compute_R_components(A0, WEIGHTS)
        improvement = (comps_star['R'] - comps_orig['R']) / max(comps_orig['R'], 1e-6) * 100

        G_star = nx.from_numpy_array((A_star > 0).astype(int))
        fixed_results.append({
            'run': run_i,
            'R_improvement_pct': improvement,
            'R_final': comps_star['R'],
            'avg_path_length': float(nx.average_shortest_path_length(G_star)) if nx.is_connected(G_star) else float('inf'),
            'clustering': float(nx.average_clustering(G_star)),
            'convergence_time': history[-1]['time'],
            'convergence_steps': len(history) - 1,
        })
        print(f"  Run {run_i}: R improvement = {improvement:.2f}%, time = {history[-1]['time']:.1f}s")

    fixed_df = pd.DataFrame(fixed_results)
    print(f"\n  Summary: R improvement = {fixed_df['R_improvement_pct'].mean():.2f}% ± {fixed_df['R_improvement_pct'].std():.2f}%")
    print(f"  Convergence time = {fixed_df['convergence_time'].mean():.1f}s ± {fixed_df['convergence_time'].std():.1f}s")

    print("\n--- 4.2.2 Random parameter perturbation ---")
    rng = np.random.RandomState(123)
    n_perturb = 20
    perturbed_results = []

    param_names = ['alpha', 'beta', 'sigma', 'alpha_L', 'alpha_G', 'lambda_L', 'lambda_G', 'w1', 'w2', 'w3']
    default_vals = {k: DEFAULT_PARAMS[k] for k in param_names}

    for pi in range(n_perturb):
        params = DEFAULT_PARAMS.copy()
        perturbation = {}
        for pname in param_names:
            factor = 1.0 + rng.uniform(-0.2, 0.2)
            params[pname] = max(0.01, default_vals[pname] * factor)
            perturbation[pname] = factor

        if 'w1' in perturbation:
            total_w = params['w1'] + params['w2'] + params['w3']
            params['w1'] /= total_w
            params['w2'] /= total_w
            params['w3'] /= total_w

        params['max_steps'] = 40
        params['min_steps'] = 8
        params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO
        params['seed'] = 200 + pi

        try:
            A_star, history = run_optimization(A0, params, verbose=False)
            weights_p = (params['w1'], params['w2'], params['w3'])
            comps_star = compute_R_components(A_star, weights_p)
            comps_orig = compute_R_components(A0, weights_p)
            improvement = (comps_star['R'] - comps_orig['R']) / max(comps_orig['R'], 1e-6) * 100

            G_star = nx.from_numpy_array((A_star > 0).astype(int))
            result = {
                'perturb_idx': pi,
                'R_improvement_pct': improvement,
                'R_final': comps_star['R'],
                'convergence_time': history[-1]['time'],
            }
            result.update({f'{k}_factor': v for k, v in perturbation.items()})
            perturbed_results.append(result)
        except Exception as e:
            print(f"  Perturb {pi} failed: {e}")

    perturbed_df = pd.DataFrame(perturbed_results)
    print(f"\n  Perturbed: R improvement = {perturbed_df['R_improvement_pct'].mean():.2f}% ± {perturbed_df['R_improvement_pct'].std():.2f}%")

    results_collector['param_fixed'] = fixed_results
    results_collector['param_perturbed'] = perturbed_results
    return fixed_results, perturbed_results


def experiment_413_attack_scenarios(results_collector):
    """4.1.3 攻击场景下的模型验证。"""
    print("\n" + "="*60)
    print("Experiment 4.1.3: Attack Scenario Validation")
    print("="*60)

    A0 = generate_topology(N_NODES, model='ba', m=3, seed=42)

    params = DEFAULT_PARAMS.copy()
    params['max_steps'] = 80
    params['min_steps'] = 15
    params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO
    A_star, _ = run_optimization(A0, params, verbose=False)

    attack_configs = [
        ('random', 0.05),
        ('random', 0.10),
        ('random', 0.15),
        ('targeted', 0.03),
        ('targeted', 0.05),
        ('targeted', 0.10),
    ]

    attack_results = []
    for attack_type, fraction in attack_configs:
        baseline_scores = []
        optimized_scores = []

        for seed in range(N_REPEATS):
            base_result = attack_graph(A0, attack_type, fraction, seed=seed)
            opt_result = attack_graph(A_star, attack_type, fraction, seed=seed)
            baseline_scores.append(base_result)
            optimized_scores.append(opt_result)

        result = {
            'attack_type': attack_type,
            'fraction': fraction,
            'baseline_lcc_mean': float(np.mean([s['lcc_ratio'] for s in baseline_scores])),
            'baseline_lcc_std': float(np.std([s['lcc_ratio'] for s in baseline_scores])),
            'optimized_lcc_mean': float(np.mean([s['lcc_ratio'] for s in optimized_scores])),
            'optimized_lcc_std': float(np.std([s['lcc_ratio'] for s in optimized_scores])),
            'baseline_path_mean': float(np.mean([s['avg_path_length'] for s in baseline_scores])),
            'optimized_path_mean': float(np.mean([s['avg_path_length'] for s in optimized_scores])),
        }
        attack_results.append(result)

        lcc_improve = (result['optimized_lcc_mean'] - result['baseline_lcc_mean']) / max(result['baseline_lcc_mean'], 1e-6) * 100
        print(f"  {attack_type} {fraction*100:.0f}%: LCC baseline={result['baseline_lcc_mean']:.4f}, "
              f"optimized={result['optimized_lcc_mean']:.4f} ({lcc_improve:+.1f}%)")

    results_collector['attack'] = attack_results
    return attack_results


def experiment_43_comparison(results_collector):
    """4.3 与主流方法的对比实验。"""
    print("\n" + "="*60)
    print("Experiment 4.3: Comparison with Baselines")
    print("="*60)

    A0 = generate_topology(N_NODES, model='ba', m=3, seed=42)
    comps_orig = compute_R_components(A0, WEIGHTS)
    R0 = comps_orig['R']

    comparison_results = {}

    print("\n--- Our method ---")
    params = DEFAULT_PARAMS.copy()
    params['max_steps'] = 200
    params['min_steps'] = 40
    params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO
    t0 = time.time()
    A_ours, history_ours = run_optimization(A0, params, verbose=False)
    t_ours = time.time() - t0
    comps_ours = compute_R_components(A_ours, WEIGHTS)
    comparison_results['Ours'] = {
        'R_final': comps_ours['R'],
        'R_improvement_pct': (comps_ours['R'] - R0) / max(R0, 1e-6) * 100,
        'time_s': t_ours,
        'R_s': comps_ours['R_s'],
        'R_c': comps_ours['R_c'],
        'R_r': comps_ours['R_r'],
    }
    print(f"  R: {R0:.4f} -> {comps_ours['R']:.4f} ({comparison_results['Ours']['R_improvement_pct']:+.2f}%), time={t_ours:.1f}s")

    print("\n--- ResiNet ---")
    t0 = time.time()
    A_resi, history_resi = resinet_optimize(A0, max_rewires=200, seed=42, weights=WEIGHTS)
    t_resi = time.time() - t0
    comps_resi = compute_R_components(A_resi, WEIGHTS)
    comparison_results['ResiNet'] = {
        'R_final': comps_resi['R'],
        'R_improvement_pct': (comps_resi['R'] - R0) / max(R0, 1e-6) * 100,
        'time_s': t_resi,
        'R_s': comps_resi['R_s'],
        'R_c': comps_resi['R_c'],
        'R_r': comps_resi['R_r'],
    }
    print(f"  R: {R0:.4f} -> {comps_resi['R']:.4f} ({comparison_results['ResiNet']['R_improvement_pct']:+.2f}%), time={t_resi:.1f}s")

    print("\n--- FPSblo-EP ---")
    t0 = time.time()
    A_fps, history_fps = fpsblo_optimize(A0, n_landmarks=15, max_iters=50, seed=42, weights=WEIGHTS)
    t_fps = time.time() - t0
    comps_fps = compute_R_components(A_fps, WEIGHTS)
    comparison_results['FPSblo-EP'] = {
        'R_final': comps_fps['R'],
        'R_improvement_pct': (comps_fps['R'] - R0) / max(R0, 1e-6) * 100,
        'time_s': t_fps,
        'R_s': comps_fps['R_s'],
        'R_c': comps_fps['R_c'],
        'R_r': comps_fps['R_r'],
    }
    print(f"  R: {R0:.4f} -> {comps_fps['R']:.4f} ({comparison_results['FPSblo-EP']['R_improvement_pct']:+.2f}%), time={t_fps:.1f}s")

    print("\n--- Static Optimization ---")
    t0 = time.time()
    A_static, history_static = static_optimize(A0, max_iters=200, seed=42, weights=WEIGHTS)
    t_static = time.time() - t0
    comps_static = compute_R_components(A_static, WEIGHTS)
    comparison_results['Static'] = {
        'R_final': comps_static['R'],
        'R_improvement_pct': (comps_static['R'] - R0) / max(R0, 1e-6) * 100,
        'time_s': t_static,
        'R_s': comps_static['R_s'],
        'R_c': comps_static['R_c'],
        'R_r': comps_static['R_r'],
    }
    print(f"  R: {R0:.4f} -> {comps_static['R']:.4f} ({comparison_results['Static']['R_improvement_pct']:+.2f}%), time={t_static:.1f}s")

    print("\n--- Attack Simulation ---")
    t0 = time.time()
    A_atksim, history_atk = attack_simulation_optimize(
        A0, n_attacks=30, attack_fraction=0.1, max_rewires=100, seed=42, weights=WEIGHTS
    )
    t_atk = time.time() - t0
    comps_atk = compute_R_components(A_atksim, WEIGHTS)
    comparison_results['AttackSim'] = {
        'R_final': comps_atk['R'],
        'R_improvement_pct': (comps_atk['R'] - R0) / max(R0, 1e-6) * 100,
        'time_s': t_atk,
        'R_s': comps_atk['R_s'],
        'R_c': comps_atk['R_c'],
        'R_r': comps_atk['R_r'],
    }
    print(f"  R: {R0:.4f} -> {comps_atk['R']:.4f} ({comparison_results['AttackSim']['R_improvement_pct']:+.2f}%), time={t_atk:.1f}s")

    results_collector['comparison'] = comparison_results
    return comparison_results


def experiment_scalability(results_collector):
    """可扩展性实验：不同规模下的运行时间与鲁棒性。"""
    print("\n" + "="*60)
    print("Experiment: Scalability Analysis")
    print("="*60)

    scales = [50, 100, 150]
    scale_results = []

    for n in scales:
        A0 = generate_topology(n, model='ba', m=3, seed=42)
        params = DEFAULT_PARAMS.copy()
        params['max_steps'] = 30
        params['min_steps'] = 8
        params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO

        comps_orig = compute_R_components(A0, WEIGHTS)
        t0 = time.time()
        A_star, history = run_optimization(A0, params, verbose=False)
        t_elapsed = time.time() - t0
        comps_star = compute_R_components(A_star, WEIGHTS)

        improvement = (comps_star['R'] - comps_orig['R']) / max(comps_orig['R'], 1e-6) * 100

        scale_results.append({
            'n_nodes': n,
            'R_before': comps_orig['R'],
            'R_after': comps_star['R'],
            'R_improvement_pct': improvement,
            'time_s': t_elapsed,
            'steps': len(history) - 1,
        })
        print(f"  N={n}: R {comps_orig['R']:.4f} -> {comps_star['R']:.4f} ({improvement:+.2f}%), time={t_elapsed:.1f}s")

    results_collector['scalability'] = scale_results
    return scale_results


# ======================================================================
# Plotting functions
# ======================================================================

def plot_robustness_evolution(histories, save_path):
    """绘制鲁棒性演化曲线 (Figure 5)。"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    for idx, (topo_name, history) in enumerate(histories.items()):
        ax = axes[idx]
        steps = [h['step'] for h in history]
        Rs = [h['R'] for h in history]
        R_s = [h['R_s'] for h in history]
        R_c = [h['R_c'] for h in history]
        R_r = [h['R_r'] for h in history]

        ax.plot(steps, Rs, 'k-', linewidth=2, label='R (total)')
        ax.plot(steps, R_s, 'b--', linewidth=1.5, label='$R_s$')
        ax.plot(steps, R_c, 'r-.', linewidth=1.5, label='$R_c$')
        ax.plot(steps, R_r, 'g:', linewidth=1.5, label='$R_r$')
        ax.set_xlabel('Optimization Step')
        ax.set_ylabel('Robustness Score')
        ax.set_title(f'{topo_name}')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_degree_distribution(A_before, A_after, topo_name, save_path):
    """绘制优化前后的度分布对比 (Figure 6)。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    deg_before = np.sum(A_before > 0, axis=1).astype(int)
    deg_after = np.sum(A_after > 0, axis=1).astype(int)

    max_deg = max(deg_before.max(), deg_after.max()) + 1
    bins = np.arange(0, max_deg + 1) - 0.5

    ax1.hist(deg_before, bins=bins, alpha=0.7, color='steelblue', edgecolor='black')
    ax1.set_xlabel('Degree')
    ax1.set_ylabel('Count')
    ax1.set_title(f'{topo_name} - Before Optimization')
    ax1.grid(True, alpha=0.3)

    ax2.hist(deg_after, bins=bins, alpha=0.7, color='coral', edgecolor='black')
    ax2.set_xlabel('Degree')
    ax2.set_ylabel('Count')
    ax2.set_title(f'{topo_name} - After Optimization')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_attack_results(attack_results, save_path):
    """绘制攻击场景下的 LCC 对比 (Figure 7)。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    random_attacks = [r for r in attack_results if r['attack_type'] == 'random']
    targeted_attacks = [r for r in attack_results if r['attack_type'] == 'targeted']

    fracs_r = [r['fraction'] * 100 for r in random_attacks]
    base_r = [r['baseline_lcc_mean'] for r in random_attacks]
    opt_r = [r['optimized_lcc_mean'] for r in random_attacks]
    base_r_err = [r['baseline_lcc_std'] for r in random_attacks]
    opt_r_err = [r['optimized_lcc_std'] for r in random_attacks]

    x_r = np.arange(len(fracs_r))
    width = 0.35
    ax1.bar(x_r - width/2, base_r, width, yerr=base_r_err, label='Baseline', color='steelblue', capsize=3)
    ax1.bar(x_r + width/2, opt_r, width, yerr=opt_r_err, label='Optimized', color='coral', capsize=3)
    ax1.set_xlabel('Removal Fraction (%)')
    ax1.set_ylabel('LCC Ratio')
    ax1.set_title('Random Attack')
    ax1.set_xticks(x_r)
    ax1.set_xticklabels([f'{f:.0f}%' for f in fracs_r])
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')

    fracs_t = [r['fraction'] * 100 for r in targeted_attacks]
    base_t = [r['baseline_lcc_mean'] for r in targeted_attacks]
    opt_t = [r['optimized_lcc_mean'] for r in targeted_attacks]
    base_t_err = [r['baseline_lcc_std'] for r in targeted_attacks]
    opt_t_err = [r['optimized_lcc_std'] for r in targeted_attacks]

    x_t = np.arange(len(fracs_t))
    ax2.bar(x_t - width/2, base_t, width, yerr=base_t_err, label='Baseline', color='steelblue', capsize=3)
    ax2.bar(x_t + width/2, opt_t, width, yerr=opt_t_err, label='Optimized', color='coral', capsize=3)
    ax2.set_xlabel('Removal Fraction (%)')
    ax2.set_ylabel('LCC Ratio')
    ax2.set_title('Targeted Attack')
    ax2.set_xticks(x_t)
    ax2.set_xticklabels([f'{f:.0f}%' for f in fracs_t])
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_parameter_sensitivity(perturbed_results, save_path):
    """绘制参数敏感性分析 (Figure 8)。"""
    df = pd.DataFrame(perturbed_results)

    param_cols = [c for c in df.columns if c.endswith('_factor')]
    n_params = len(param_cols)
    ncols = 4
    nrows = (n_params + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 3.5 * nrows))
    axes = axes.flatten() if nrows > 1 else (axes if isinstance(axes, np.ndarray) else [axes])

    for idx, pcol in enumerate(param_cols):
        if idx >= len(axes):
            break
        ax = axes[idx]
        pname = pcol.replace('_factor', '')
        ax.scatter(df[pcol], df['R_improvement_pct'], alpha=0.6, s=30, c='steelblue')
        ax.set_xlabel(f'{pname} factor')
        ax.set_ylabel('R improvement (%)')
        ax.set_title(pname)
        ax.axhline(y=df['R_improvement_pct'].mean(), color='r', linestyle='--', alpha=0.5)
        ax.grid(True, alpha=0.3)

    for idx in range(len(param_cols), len(axes)):
        axes[idx].set_visible(False)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_comparison_bar(comparison_results, save_path):
    """绘制方法对比柱状图 (Figure 9)。"""
    methods = list(comparison_results.keys())
    R_vals = [comparison_results[m]['R_final'] for m in methods]
    improvements = [comparison_results[m]['R_improvement_pct'] for m in methods]
    times = [comparison_results[m]['time_s'] for m in methods]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5))

    colors = ['coral', 'steelblue', 'mediumpurple', 'forestgreen', 'goldenrod']
    x = np.arange(len(methods))

    ax1.bar(x, R_vals, color=colors[:len(methods)], edgecolor='black')
    ax1.set_ylabel('Final Robustness R')
    ax1.set_title('Robustness Score')
    ax1.set_xticks(x)
    ax1.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
    ax1.grid(True, alpha=0.3, axis='y')

    ax2.bar(x, improvements, color=colors[:len(methods)], edgecolor='black')
    ax2.set_ylabel('Improvement (%)')
    ax2.set_title('Robustness Improvement')
    ax2.set_xticks(x)
    ax2.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')

    ax3.bar(x, times, color=colors[:len(methods)], edgecolor='black')
    ax3.set_ylabel('Time (seconds)')
    ax3.set_title('Convergence Time')
    ax3.set_xticks(x)
    ax3.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
    ax3.set_yscale('log')
    ax3.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_scalability(scale_results, save_path):
    """绘制可扩展性分析 (Figure 10)。"""
    df = pd.DataFrame(scale_results)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ax1.plot(df['n_nodes'], df['R_improvement_pct'], 'bo-', linewidth=2, markersize=8)
    ax1.set_xlabel('Number of Nodes')
    ax1.set_ylabel('R Improvement (%)')
    ax1.set_title('Robustness Improvement vs. Scale')
    ax1.grid(True, alpha=0.3)

    ax2.plot(df['n_nodes'], df['time_s'], 'rs-', linewidth=2, markersize=8)
    ax2.set_xlabel('Number of Nodes')
    ax2.set_ylabel('Optimization Time (s)')
    ax2.set_title('Computation Time vs. Scale')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def plot_robustness_components_radar(comparison_results, save_path):
    """绘制各方法鲁棒性子项雷达图 (Figure 11)。"""
    methods = list(comparison_results.keys())
    categories = ['$R_s$', '$R_c$', '$R_r$']

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    angles += angles[:1]

    colors = ['coral', 'steelblue', 'mediumpurple', 'forestgreen', 'goldenrod']

    for idx, method in enumerate(methods):
        values = [
            comparison_results[method]['R_s'],
            comparison_results[method]['R_c'],
            comparison_results[method]['R_r'],
        ]
        values += values[:1]
        ax.plot(angles, values, 'o-', linewidth=2, label=method, color=colors[idx % len(colors)])
        ax.fill(angles, values, alpha=0.1, color=colors[idx % len(colors)])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=12)
    ax.set_title('Robustness Components Comparison', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"  Saved: {save_path}")


def main():
    """运行所有实验并生成图表。"""
    print("="*60)
    print("TIFS Paper: Complete Experimental Evaluation")
    print("Blockchain Network Topology Optimization via Evolutionary Dynamics")
    print(f"N_NODES={N_NODES}, N_REPEATS={N_REPEATS}")
    print("="*60)

    results = {}
    total_start = time.time()

    # 4.1.1 MLE
    experiment_411_mle(results)

    # 4.1.2 Optimization effectiveness
    opt_results, opt_histories = experiment_412_optimization(results)

    # 4.1.3 Attack scenarios
    attack_results = experiment_413_attack_scenarios(results)

    # 4.2 Parameter sensitivity
    fixed_results, perturbed_results = experiment_42_parameter_sensitivity(results)

    # 4.3 Comparison with baselines
    comparison_results = experiment_43_comparison(results)

    # Scalability
    scale_results = experiment_scalability(results)

    total_time = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"Total experiment time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"{'='*60}")

    # Generate plots
    print("\n--- Generating Figures ---")

    plot_robustness_evolution(
        opt_histories,
        os.path.join(FIGURES_DIR, 'fig5_robustness_evolution.png')
    )

    A0_ba = generate_topology(N_NODES, model='ba', m=3, seed=42)
    params = DEFAULT_PARAMS.copy()
    params['max_steps'] = 80
    params['min_steps'] = 15
    params['gradient_sample_ratio'] = GRADIENT_SAMPLE_RATIO
    A_star_ba, _ = run_optimization(A0_ba, params, verbose=False)
    plot_degree_distribution(
        A0_ba, A_star_ba, 'BA(m=3)',
        os.path.join(FIGURES_DIR, 'fig6_degree_distribution.png')
    )

    plot_attack_results(
        attack_results,
        os.path.join(FIGURES_DIR, 'fig7_attack_results.png')
    )

    plot_parameter_sensitivity(
        perturbed_results,
        os.path.join(FIGURES_DIR, 'fig8_parameter_sensitivity.png')
    )

    plot_comparison_bar(
        comparison_results,
        os.path.join(FIGURES_DIR, 'fig9_comparison.png')
    )

    plot_scalability(
        scale_results,
        os.path.join(FIGURES_DIR, 'fig10_scalability.png')
    )

    plot_robustness_components_radar(
        comparison_results,
        os.path.join(FIGURES_DIR, 'fig11_radar.png')
    )

    # Save all results to JSON
    results_path = os.path.join(RESULTS_DIR, 'all_results.json')

    def make_serializable(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [make_serializable(v) for v in obj]
        return obj

    with open(results_path, 'w') as f:
        json.dump(make_serializable(results), f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {results_path}")

    # Print summary tables for paper
    print("\n" + "="*60)
    print("SUMMARY TABLES FOR PAPER")
    print("="*60)

    print("\n--- Table 3: Optimization Effectiveness ---")
    print(f"{'Topology':<20} {'R_before':>10} {'R_after':>10} {'Improvement':>12} {'Steps':>8} {'Time(s)':>10}")
    for name, r in opt_results.items():
        print(f"{name:<20} {r['before']['R']:>10.4f} {r['after']['R']:>10.4f} "
              f"{r['R_improvement_pct']:>+11.2f}% {r['convergence_steps']:>8} {r['convergence_time_s']:>10.1f}")

    print("\n--- Table 4: Comparison with Baselines ---")
    print(f"{'Method':<20} {'R_final':>10} {'Improvement':>12} {'R_s':>8} {'R_c':>8} {'R_r':>8} {'Time(s)':>10}")
    for name, r in comparison_results.items():
        print(f"{name:<20} {r['R_final']:>10.4f} {r['R_improvement_pct']:>+11.2f}% "
              f"{r['R_s']:>8.4f} {r['R_c']:>8.4f} {r['R_r']:>8.4f} {r['time_s']:>10.1f}")

    print("\n--- Table 5: Attack Resilience ---")
    print(f"{'Attack':<20} {'Base LCC':>10} {'Opt LCC':>10} {'Base Path':>10} {'Opt Path':>10}")
    for r in attack_results:
        label = f"{r['attack_type']} {r['fraction']*100:.0f}%"
        print(f"{label:<20} {r['baseline_lcc_mean']:>10.4f} {r['optimized_lcc_mean']:>10.4f} "
              f"{r['baseline_path_mean']:>10.2f} {r['optimized_path_mean']:>10.2f}")

    print("\n--- Table 6: Parameter Stability (Fixed) ---")
    fixed_df = pd.DataFrame(fixed_results)
    print(f"  R improvement: {fixed_df['R_improvement_pct'].mean():.2f}% ± {fixed_df['R_improvement_pct'].std():.2f}%")
    print(f"  Convergence time: {fixed_df['convergence_time'].mean():.1f}s ± {fixed_df['convergence_time'].std():.1f}s")
    print(f"  Path length: {fixed_df['avg_path_length'].mean():.2f} ± {fixed_df['avg_path_length'].std():.2f}")

    print("\n--- Table 7: Scalability ---")
    print(f"{'N':>8} {'R_before':>10} {'R_after':>10} {'Improvement':>12} {'Time(s)':>10}")
    for r in scale_results:
        print(f"{r['n_nodes']:>8} {r['R_before']:>10.4f} {r['R_after']:>10.4f} "
              f"{r['R_improvement_pct']:>+11.2f}% {r['time_s']:>10.1f}")

    print("\n--- MLE Parameter Estimation ---")
    mle = results['mle']
    print(f"  Edge accuracy: {mle['edge_accuracy_mean']:.4f} ± {mle['edge_accuracy_std']:.4f}")
    print(f"  Degree error: {mle['degree_rel_error_mean']:.4f} ± {mle['degree_rel_error_std']:.4f}")
    print(f"  Path error: {mle['path_rel_error_mean']:.4f} ± {mle['path_rel_error_std']:.4f}")
    print(f"  Cluster error: {mle['cluster_rel_error_mean']:.4f} ± {mle['cluster_rel_error_std']:.4f}")

    print(f"\nAll experiments completed successfully!")
    print(f"Figures saved in: {FIGURES_DIR}")
    print(f"Results saved in: {RESULTS_DIR}")


if __name__ == '__main__':
    main()
