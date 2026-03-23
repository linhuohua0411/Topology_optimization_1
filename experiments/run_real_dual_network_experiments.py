#!/usr/bin/env python3
"""
在真实以太坊(106节点)+波卡(100节点)双网络拓扑上运行完整TIFS级实验。
包括: 拓扑画像/MLE参数估计/优化有效性/攻击场景/基线对比/参数稳定性/可迁移性。
"""

import sys, os, json, time
import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.robustness import compute_R, compute_R_components, _laplacian_second_eigenvalue
from models.global_optimizer import run_optimization, get_edge_changes, DEFAULT_PARAMS, mle_estimate_params
from models.baselines import resinet_optimize, fpsblo_optimize, static_optimize, attack_simulation_optimize

rcParams['font.family'] = 'DejaVu Sans'
rcParams['figure.dpi'] = 150
rcParams['savefig.dpi'] = 300
rcParams['savefig.bbox'] = 'tight'

FIGURES_DIR = os.path.join(os.path.dirname(__file__), 'figures')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'metrics')
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
WEIGHTS = (0.3, 0.4, 0.3)
N_REPEATS = 5


def load_snapshots(data_dir):
    """加载所有 JSON 快照并构建邻接矩阵序列。"""
    snap_files = sorted([f for f in os.listdir(data_dir) if f.startswith('snapshot_') and f.endswith('.json')])
    matrices = []
    metas = []
    for sf in snap_files:
        with open(os.path.join(data_dir, sf)) as f:
            snap = json.load(f)
        edges = snap['edges']
        n = snap['n_nodes']
        A = np.zeros((n, n), dtype=np.float64)
        for e in edges:
            i, j = e[0], e[1]
            if i < n and j < n:
                A[i, j] = 1.0
                A[j, i] = 1.0
        matrices.append(A)
        metas.append(snap)
    return matrices, metas


def graph_stats(A):
    G = nx.from_numpy_array((A > 0).astype(int))
    deg = np.sum(A > 0, axis=1)
    s = {
        'n_nodes': A.shape[0], 'n_edges': int(np.sum(A > 0) / 2),
        'mean_deg': float(np.mean(deg)), 'std_deg': float(np.std(deg)),
        'max_deg': int(np.max(deg)), 'min_deg': int(np.min(deg)),
        'clustering': float(nx.average_clustering(G)),
        'lambda2': float(_laplacian_second_eigenvalue(A)),
        'connected': nx.is_connected(G),
        'global_efficiency': float(nx.global_efficiency(G)),
    }
    if nx.is_connected(G):
        s['avg_path'] = float(nx.average_shortest_path_length(G))
        s['avg_path_lcc'] = s['avg_path']
        s['diameter'] = nx.diameter(G)
        s['n_components'] = 1
        s['lcc_ratio'] = 1.0
    else:
        lcc = max(nx.connected_components(G), key=len)
        Gl = G.subgraph(lcc).copy()
        s['avg_path'] = float('inf')
        s['avg_path_lcc'] = float(nx.average_shortest_path_length(Gl))
        s['diameter'] = nx.diameter(Gl)
        s['lcc_ratio'] = len(lcc) / A.shape[0]
        s['n_components'] = nx.number_connected_components(G)
    comps = compute_R_components(A, WEIGHTS)
    s.update(comps)
    return s


def attack(A, atype, frac, seed=42):
    rng = np.random.RandomState(seed)
    n = A.shape[0]
    nr = max(1, int(n * frac))
    G = nx.from_numpy_array((A > 0).astype(int))
    if atype == 'random':
        rm = rng.choice(n, size=nr, replace=False).tolist()
    else:
        rm = np.argsort(-np.sum(A > 0, axis=1))[:nr].tolist()
    G.remove_nodes_from(rm)
    if len(G) == 0:
        return {
            'lcc_ratio': 0.0,
            'lcc_size': 0,
            'avg_path': float('inf'),
            'n_components': 0,
            'global_efficiency': 0.0,
        }
    comps = list(nx.connected_components(G))
    lcc = max(comps, key=len)
    Gl = G.subgraph(lcc).copy()
    return {
        'lcc_ratio': len(lcc) / n,
        'lcc_size': len(lcc),
        'avg_path': float(nx.average_shortest_path_length(Gl)) if len(Gl) > 1 else 0,
        'n_components': len(comps),
        'global_efficiency': float(nx.global_efficiency(G)),
    }


def run_single_network_experiments(net_name, data_dir, results):
    """对单个网络运行全部实验。"""
    print(f"\n{'#'*70}")
    print(f"# {net_name.upper()} EXPERIMENTS")
    print(f"{'#'*70}")

    matrices, metas = load_snapshots(data_dir)
    if not matrices:
        print(f"  No data found in {data_dir}")
        return None, None, None
    A0 = matrices[0]
    n = A0.shape[0]
    print(f"  Loaded {len(matrices)} snapshots, {n} nodes")
    results[f'{net_name}_data_source'] = {
        'type': 'json_snapshots',
        'path': data_dir,
        'n_snapshots': len(matrices),
        'n_nodes': int(n),
    }

    # 1. Baseline topology profile
    print(f"\n--- 1. Topology Profile ---")
    s0 = graph_stats(A0)
    print(f"  Nodes={s0['n_nodes']} Edges={s0['n_edges']} Deg={s0['mean_deg']:.1f}±{s0['std_deg']:.1f}")
    print(f"  Clustering={s0['clustering']:.4f} λ₂={s0['lambda2']:.4f} Path={s0['avg_path']:.3f}")
    print(f"  R={s0['R']:.6f} R_s={s0['R_s']:.4f} R_c={s0['R_c']:.4f} R_r={s0['R_r']:.4f}")
    results[f'{net_name}_baseline'] = s0

    # 2. MLE
    print(f"\n--- 2. MLE Parameter Estimation ---")
    n_mle = min(len(matrices), 20)
    est, loss = mle_estimate_params(matrices[:n_mle], dt_obs=300.0, n_restarts=5, max_iter=100, seed=42)
    print(f"  MLE loss={loss:.4f} params={est}")
    results[f'{net_name}_mle'] = {'params': est, 'loss': loss, 'n_snapshots': n_mle}

    # 3. Optimization
    print(f"\n--- 3. Optimization ---")
    params = DEFAULT_PARAMS.copy()
    params.update({'max_steps': 150, 'min_steps': 30, 'gradient_sample_ratio': 0.10, 'k_max': min(s0['max_deg'], 50)})
    A_star, history = run_optimization(A0, params, verbose=True)
    s_star = graph_stats(A_star)
    imp = (s_star['R'] - s0['R']) / max(s0['R'], 1e-6) * 100
    print(f"  R: {s0['R']:.4f} → {s_star['R']:.4f} ({imp:+.2f}%)")
    print(f"  Path: {s0['avg_path']:.3f} → {s_star['avg_path']:.3f}")
    print(f"  Clust: {s0['clustering']:.4f} → {s_star['clustering']:.4f}")
    results[f'{net_name}_opt'] = {'before': s0, 'after': s_star, 'imp_pct': imp,
                                   'steps': len(history)-1, 'time_s': history[-1]['time']}
    results[f'{net_name}_history'] = history

    # 4. Attack scenarios
    print(f"\n--- 4. Attack Scenarios ---")
    results[f'{net_name}_attack_pre_state'] = {
        'baseline': {
            'is_connected': bool(s0['connected']),
            'lcc_ratio': float(s0.get('lcc_ratio', 1.0)),
            'n_components': int(s0.get('n_components', 1)),
            'global_efficiency': float(s0.get('global_efficiency', 0.0)),
        },
        'optimized': {
            'is_connected': bool(s_star['connected']),
            'lcc_ratio': float(s_star.get('lcc_ratio', 1.0)),
            'n_components': int(s_star.get('n_components', 1)),
            'global_efficiency': float(s_star.get('global_efficiency', 0.0)),
        },
    }
    attacks = [('random', 0.05), ('random', 0.10), ('random', 0.15),
               ('targeted', 0.03), ('targeted', 0.05), ('targeted', 0.10)]
    atk_res = []
    for at, fr in attacks:
        b = [attack(A0, at, fr, s) for s in range(N_REPEATS)]
        o = [attack(A_star, at, fr, s) for s in range(N_REPEATS)]
        r = {
            'type': at, 'frac': fr,
            'base_lcc': float(np.mean([x['lcc_ratio'] for x in b])),
            'opt_lcc': float(np.mean([x['lcc_ratio'] for x in o])),
            'base_path': float(np.mean([x['avg_path'] for x in b])),
            'opt_path': float(np.mean([x['avg_path'] for x in o])),
            'base_components': float(np.mean([x['n_components'] for x in b])),
            'opt_components': float(np.mean([x['n_components'] for x in o])),
            'base_lcc_size': float(np.mean([x['lcc_size'] for x in b])),
            'opt_lcc_size': float(np.mean([x['lcc_size'] for x in o])),
            'base_efficiency': float(np.mean([x['global_efficiency'] for x in b])),
            'opt_efficiency': float(np.mean([x['global_efficiency'] for x in o])),
        }
        lcc_d = (r['opt_lcc'] - r['base_lcc']) / max(r['base_lcc'], 1e-6) * 100
        print(f"  {at} {fr*100:.0f}%: LCC {r['base_lcc']:.4f}→{r['opt_lcc']:.4f}({lcc_d:+.1f}%) Path {r['base_path']:.2f}→{r['opt_path']:.2f}")
        atk_res.append(r)
    results[f'{net_name}_attack'] = atk_res

    # 5. Baseline comparison
    print(f"\n--- 5. Baseline Comparison ---")
    R0 = s0['R']
    comp = {'Ours': {'R': s_star['R'], 'imp': imp, 'time': history[-1]['time'],
                     'R_s': s_star['R_s'], 'R_c': s_star['R_c'], 'R_r': s_star['R_r']}}
    for mname, mfunc, mkw in [
        ('ResiNet', resinet_optimize, {'max_rewires': 300}),
        ('FPSblo-EP', fpsblo_optimize, {'n_landmarks': 15, 'max_iters': 80}),
        ('Static', static_optimize, {'max_iters': 300}),
        ('AttackSim', attack_simulation_optimize, {'n_attacks': 30, 'max_rewires': 100}),
    ]:
        t0 = time.time()
        Am, _ = mfunc(A0, seed=42, weights=WEIGHTS, **mkw)
        tm = time.time() - t0
        cm = compute_R_components(Am, WEIGHTS)
        mi = (cm['R'] - R0) / max(R0, 1e-6) * 100
        comp[mname] = {'R': cm['R'], 'imp': mi, 'time': tm, 'R_s': cm['R_s'], 'R_c': cm['R_c'], 'R_r': cm['R_r']}
        print(f"  {mname}: R={cm['R']:.4f} ({mi:+.2f}%) time={tm:.1f}s")
    print(f"  Ours: R={s_star['R']:.4f} ({imp:+.2f}%) time={history[-1]['time']:.1f}s")
    results[f'{net_name}_comparison'] = comp

    # 6. Stability
    print(f"\n--- 6. Parameter Stability (5 runs) ---")
    stab = []
    for ri in range(N_REPEATS):
        p = params.copy(); p['seed'] = 42 + ri; p['max_steps'] = 80
        As, h = run_optimization(A0, p, verbose=False)
        cs = compute_R_components(As, WEIGHTS)
        si = (cs['R'] - R0) / max(R0, 1e-6) * 100
        stab.append({'run': ri, 'imp': si, 'R': cs['R'], 'time': h[-1]['time']})
        print(f"  Run {ri}: R imp={si:.2f}% time={h[-1]['time']:.1f}s")
    sm, ss = np.mean([x['imp'] for x in stab]), np.std([x['imp'] for x in stab])
    print(f"  Mean: {sm:.2f}% ± {ss:.2f}%")
    results[f'{net_name}_stability'] = stab

    return A0, A_star, history


def generate_dual_figures(results, A0_eth, As_eth, h_eth, A0_dot, As_dot, h_dot):
    """生成双网络对比论文图表。"""
    print(f"\n{'='*70}")
    print("Generating Dual-Network Figures")
    print(f"{'='*70}")

    # Fig: Evolution curves side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    for ax, h, title in [(ax1, h_eth, 'Ethereum (106 nodes)'), (ax2, h_dot, 'Polkadot (100 nodes)')]:
        steps = [x['step'] for x in h]
        ax.plot(steps, [x['R'] for x in h], 'k-', lw=2, label='R')
        ax.plot(steps, [x['R_s'] for x in h], 'b--', lw=1.5, label='$R_s$')
        ax.plot(steps, [x['R_c'] for x in h], 'r-.', lw=1.5, label='$R_c$')
        ax.plot(steps, [x['R_r'] for x in h], 'g:', lw=1.5, label='$R_r$')
        ax.set_xlabel('Step'); ax.set_ylabel('Robustness'); ax.set_title(title)
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_evolution.png')); plt.close()
    print("  Saved: fig_dual_evolution.png")

    # Fig: Degree distributions
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    for row, (A0, As, name) in enumerate([(A0_eth, As_eth, 'Ethereum'), (A0_dot, As_dot, 'Polkadot')]):
        for col, (A, label) in enumerate([(A0, 'Before'), (As, 'After')]):
            ax = axes[row][col]
            deg = np.sum(A > 0, axis=1).astype(int)
            ax.hist(deg, bins=max(10, deg.max()-deg.min()+1), alpha=0.7,
                    color='steelblue' if col == 0 else 'coral', edgecolor='black')
            ax.set_xlabel('Degree'); ax.set_ylabel('Count')
            ax.set_title(f'{name} - {label}'); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_degree.png')); plt.close()
    print("  Saved: fig_dual_degree.png")

    # Fig: Attack comparison
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for row, net in enumerate(['eth', 'dot']):
        nname = 'Ethereum' if net == 'eth' else 'Polkadot'
        atk = results.get(f'{net}_attack', [])
        for col, at in enumerate(['random', 'targeted']):
            ax = axes[row][col]
            sub = [r for r in atk if r['type'] == at]
            if not sub: continue
            fracs = [r['frac']*100 for r in sub]
            x = np.arange(len(fracs)); w = 0.35
            ax.bar(x-w/2, [r['base_lcc'] for r in sub], w, label='Baseline', color='steelblue', capsize=3)
            ax.bar(x+w/2, [r['opt_lcc'] for r in sub], w, label='Optimized', color='coral', capsize=3)
            ax.set_xlabel('Removal %'); ax.set_ylabel('LCC Ratio')
            ax.set_title(f'{nname} - {at.title()} Attack')
            ax.set_xticks(x); ax.set_xticklabels([f'{f:.0f}%' for f in fracs])
            ax.legend(); ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_attack.png')); plt.close()
    print("  Saved: fig_dual_attack.png")

    # Fig: Comparison bar
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    colors = ['coral', 'steelblue', 'mediumpurple', 'forestgreen', 'goldenrod']
    for idx, net in enumerate(['eth', 'dot']):
        ax = axes[idx]
        nname = 'Ethereum' if net == 'eth' else 'Polkadot'
        comp = results.get(f'{net}_comparison', {})
        if not comp: continue
        methods = list(comp.keys())
        x = np.arange(len(methods))
        ax.bar(x, [comp[m]['imp'] for m in methods], color=colors[:len(methods)], edgecolor='black')
        ax.set_ylabel('Improvement (%)'); ax.set_title(f'{nname}')
        ax.set_xticks(x); ax.set_xticklabels(methods, rotation=30, ha='right', fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_comparison.png')); plt.close()
    print("  Saved: fig_dual_comparison.png")

    # Fig: Radar for both networks
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), subplot_kw=dict(polar=True))
    cats = ['$R_s$', '$R_c$', '$R_r$']
    angles = np.linspace(0, 2*np.pi, len(cats), endpoint=False).tolist() + [0]
    for ax, net, nname in [(ax1, 'eth', 'Ethereum'), (ax2, 'dot', 'Polkadot')]:
        comp = results.get(f'{net}_comparison', {})
        if not comp: continue
        for mi, (m, c) in enumerate(zip(list(comp.keys()), colors)):
            vals = [comp[m]['R_s'], comp[m]['R_c'], comp[m]['R_r']] + [comp[m]['R_s']]
            ax.plot(angles, vals, 'o-', lw=2, label=m, color=c)
            ax.fill(angles, vals, alpha=0.1, color=c)
        ax.set_xticks(angles[:-1]); ax.set_xticklabels(cats, fontsize=11)
        ax.set_title(nname, pad=20); ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_radar.png')); plt.close()
    print("  Saved: fig_dual_radar.png")

    # Fig: R breakdown before/after for both
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    for ax, net, nname in [(ax1, 'eth', 'Ethereum'), (ax2, 'dot', 'Polkadot')]:
        opt = results.get(f'{net}_opt', {})
        if not opt: continue
        bef, aft = opt['before'], opt['after']
        labels = ['$R_s$', '$R_c$', '$R_r$', 'R']
        bv = [bef['R_s'], bef['R_c'], bef['R_r'], bef['R']]
        av = [aft['R_s'], aft['R_c'], aft['R_r'], aft['R']]
        x = np.arange(len(labels)); w = 0.35
        ax.bar(x-w/2, bv, w, label='Before', color='steelblue', alpha=0.8)
        ax.bar(x+w/2, av, w, label='After', color='coral', alpha=0.8)
        for i, (b, a) in enumerate(zip(bv, av)):
            pct = (a-b)/max(b,1e-6)*100
            ax.annotate(f'{pct:+.1f}%', xy=(i+w/2, a), fontsize=8, ha='center', va='bottom', color='darkred')
        ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylabel('Score')
        ax.set_title(nname); ax.legend(); ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_breakdown.png')); plt.close()
    print("  Saved: fig_dual_breakdown.png")

    # Fig: Topology temporal evolution
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    for ax, net, nname in [(ax1, 'eth', 'Ethereum'), (ax2, 'dot', 'Polkadot')]:
        ddir = os.path.join(os.path.dirname(__file__), '..', 'data', f'private_{net}')
        mats, mts = load_snapshots(ddir)
        edges = [int(np.sum(m > 0)/2) for m in mats]
        ax.plot(range(len(edges)), edges, 'b-o', markersize=3, lw=1.5)
        ax.set_xlabel('Snapshot Index'); ax.set_ylabel('Number of Edges')
        ax.set_title(f'{nname} Topology Evolution'); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, 'fig_dual_temporal.png')); plt.close()
    print("  Saved: fig_dual_temporal.png")


def main():
    total_t0 = time.time()
    print("="*70)
    print("TIFS Complete Experiments: Ethereum + Polkadot Dual-Network")
    print("="*70)

    results = {}
    eth_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')
    dot_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_dot')

    A0_eth, As_eth, h_eth = run_single_network_experiments('eth', eth_dir, results)
    A0_dot, As_dot, h_dot = run_single_network_experiments('dot', dot_dir, results)

    if all(x is not None for x in [A0_eth, As_eth, h_eth, A0_dot, As_dot, h_dot]):
        generate_dual_figures(results, A0_eth, As_eth, h_eth, A0_dot, As_dot, h_dot)
    else:
        print("Skip dual figures: missing ETH or DOT snapshots.")

    # Save results
    def ser(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, dict): return {k: ser(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [ser(v) for v in o]
        return o
    out_json = os.path.join(RESULTS_DIR, 'dual_network_results.json')
    with open(out_json, 'w') as f:
        json.dump(ser(results), f, indent=2, ensure_ascii=False)

    # Print summary tables
    total_time = time.time() - total_t0
    print(f"\n{'='*70}")
    print(f"SUMMARY (total time: {total_time:.0f}s / {total_time/60:.1f}min)")
    print(f"{'='*70}")

    for net, nname in [('eth', 'Ethereum'), ('dot', 'Polkadot')]:
        opt = results.get(f'{net}_opt', {})
        if not opt: continue
        b, a = opt['before'], opt['after']
        print(f"\n--- {nname} ({b['n_nodes']} nodes, {b['n_edges']} edges) ---")
        print(f"  R: {b['R']:.4f} → {a['R']:.4f} ({opt['imp_pct']:+.2f}%)")
        print(f"  Path: {b['avg_path']:.3f} → {a['avg_path']:.3f}")
        print(f"  Clust: {b['clustering']:.4f} → {a['clustering']:.4f}")

        comp = results.get(f'{net}_comparison', {})
        print(f"  Comparison:")
        for m, r in comp.items():
            print(f"    {m:<12} R={r['R']:.4f} ({r['imp']:+.2f}%) R_c={r['R_c']:.4f} t={r['time']:.1f}s")

        stab = results.get(f'{net}_stability', [])
        if stab:
            sm = np.mean([x['imp'] for x in stab])
            ss = np.std([x['imp'] for x in stab])
            print(f"  Stability: {sm:.2f}% ± {ss:.2f}%")

    print(f"\nAll figures saved to: {FIGURES_DIR}")
    print(f"Results saved to: {out_json}")
    print(f"Result file exists: {os.path.exists(out_json)}")


if __name__ == '__main__':
    main()
