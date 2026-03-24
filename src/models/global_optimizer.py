"""
演化+自组织串联的全局拓扑优化器，RK4 离散与约束处理，与 TIFS 计划 6.1 一致。

单步流程: 演化动力学 RK4 → 自组织动力学 RK4 → 约束处理
"""

import numpy as np
import time
from .robustness import (
    compute_R, compute_R_components, compute_gradient_R, compute_R_s_only
)


DEFAULT_PARAMS = {
    'alpha': 0.20,
    'beta': 0.10,
    'sigma': 0.05,
    'alpha_L': 0.4,
    'alpha_G': 0.6,
    'lambda_L': 0.15,
    'lambda_G': 0.08,
    'w1': 0.3,
    'w2': 0.4,
    'w3': 0.3,
    'k_max': 15,
    'dt': 0.05,
    'max_steps': 200,
    'min_steps': 30,
    'convergence_threshold': 0.0005,
    'gradient_sample_ratio': 0.1,
    'gradient_epsilon': 1e-5,
    'seed': 42,
}


def _symmetrize_and_clip(A):
    """对称化并 clip 到 [0, 1]。"""
    A = (A + A.T) / 2.0
    np.fill_diagonal(A, 0.0)
    np.clip(A, 0.0, 1.0, out=A)
    return A


def _apply_degree_constraint(A, k_max):
    """度约束：对超过 k_max 度的节点按边权降序保留前 k_max 条边。"""
    n = A.shape[0]
    for i in range(n):
        row = A[i].copy()
        nonzero_idx = np.where(row > 0)[0]
        if len(nonzero_idx) > k_max:
            sorted_idx = nonzero_idx[np.argsort(-row[nonzero_idx])]
            to_remove = sorted_idx[k_max:]
            for j in to_remove:
                A[i, j] = 0.0
                A[j, i] = 0.0
    return A


def _apply_connectivity_constraint(A, weight=0.1):
    """连通性约束：若图不连通则在连通分量之间添加边。"""
    import networkx as nx
    binary = (A > 0).astype(int)
    G = nx.from_numpy_array(binary)
    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return A

    main = components[0]
    for comp in components[1:]:
        i = list(main)[0]
        j = list(comp)[0]
        A[i, j] = weight
        A[j, i] = weight
        main = main.union(comp)
    return A


def _apply_constraints(A, k_max):
    """依次施加约束：非负 → 对称 → 度约束 → 连通性。"""
    A = _symmetrize_and_clip(A)
    A = _apply_degree_constraint(A, k_max)
    A = _apply_connectivity_constraint(A)
    return A


def _evolution_rhs(A, grad_R, params, rng):
    """演化动力学右端: dA/dt = α∇R - βA + σξ"""
    alpha = params['alpha']
    beta = params['beta']
    sigma = params['sigma']
    n = A.shape[0]
    noise = rng.randn(n, n)
    noise = (noise + noise.T) / 2.0
    np.fill_diagonal(noise, 0.0)
    return alpha * grad_R - beta * A + sigma * noise


def _self_org_rhs(A, grad_R, params):
    """自组织动力学右端: dA/dt = α_L * F_L(A) + α_G * F_G(A)"""
    alpha_L = params['alpha_L']
    alpha_G = params['alpha_G']
    lambda_L = params['lambda_L']
    lambda_G = params['lambda_G']

    n = A.shape[0]
    common = A @ A.T
    degrees = np.sum(A, axis=1)
    max_deg = np.maximum.outer(degrees, degrees)
    max_deg = np.maximum(max_deg, 1.0)
    F_L = common / (max_deg + 1e-8) - lambda_L * A
    np.fill_diagonal(F_L, 0.0)
    F_L = (F_L + F_L.T) / 2.0

    F_G = grad_R - lambda_G * A
    np.fill_diagonal(F_G, 0.0)
    F_G = (F_G + F_G.T) / 2.0

    return alpha_L * F_L + alpha_G * F_G


def _compute_cached_gradient(A, params, rng):
    """计算梯度并缓存。"""
    weights = (params['w1'], params['w2'], params['w3'])
    return compute_gradient_R(
        A,
        epsilon=params['gradient_epsilon'],
        sample_ratio=params['gradient_sample_ratio'],
        weights=weights,
        seed=rng.randint(0, 2**31),
    )


def evolve_step(A, params, rng=None, timing_acc=None):
    """单步：演化动力学 RK4 -> 自组织动力学 RK4 -> 约束。返回 A_next。
    timing_acc: 可选，可变 dict，将记录 gradient_s, evolution_constraints_s。
    """
    if rng is None:
        rng = np.random.RandomState(params.get('seed', 42))

    dt = params['dt']
    k_max = params['k_max']

    t0 = time.time()
    grad_R = _compute_cached_gradient(A, params, rng)
    t_grad = time.time() - t0

    k1 = _evolution_rhs(A, grad_R, params, rng)
    k2 = _evolution_rhs(_symmetrize_and_clip(A + 0.5 * dt * k1), grad_R, params, rng)
    k3 = _evolution_rhs(_symmetrize_and_clip(A + 0.5 * dt * k2), grad_R, params, rng)
    k4 = _evolution_rhs(_symmetrize_and_clip(A + dt * k3), grad_R, params, rng)
    A_evo = A + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    A_evo = _symmetrize_and_clip(A_evo)

    s1 = _self_org_rhs(A_evo, grad_R, params)
    s2 = _self_org_rhs(_symmetrize_and_clip(A_evo + 0.5 * dt * s1), grad_R, params)
    s3 = _self_org_rhs(_symmetrize_and_clip(A_evo + 0.5 * dt * s2), grad_R, params)
    s4 = _self_org_rhs(_symmetrize_and_clip(A_evo + dt * s3), grad_R, params)
    A_step = A_evo + (dt / 6.0) * (s1 + 2 * s2 + 2 * s3 + s4)

    t_evo_start = time.time()
    A_next = _apply_constraints(A_step, k_max)
    t_evo = time.time() - t_evo_start
    if timing_acc is not None:
        timing_acc['gradient_s'] = timing_acc.get('gradient_s', 0) + t_grad
        timing_acc['evolution_constraints_s'] = timing_acc.get('evolution_constraints_s', 0) + t_evo
    return A_next


def run_optimization(A0, params=None, verbose=True, profile_timing=False):
    """从 A0 运行优化，返回 (A_star, history)。

    history: list of dicts with keys 'step', 'R', 'R_s', 'R_c', 'R_r', 'time'
    """
    if params is None:
        params = DEFAULT_PARAMS.copy()
    else:
        p = DEFAULT_PARAMS.copy()
        p.update(params)
        params = p

    rng = np.random.RandomState(params['seed'])
    weights = (params['w1'], params['w2'], params['w3'])
    max_steps = params['max_steps']
    min_steps = params['min_steps']
    conv_thresh = params['convergence_threshold']

    A = A0.copy()
    comps = compute_R_components(A, weights)
    best_R = comps['R']
    A_star = A.copy()
    history = [{
        'step': 0,
        'R': comps['R'],
        'R_s': comps['R_s'],
        'R_c': comps['R_c'],
        'R_r': comps['R_r'],
        'time': 0.0,
    }]

    if verbose:
        print(f"Step 0: R={comps['R']:.6f} (R_s={comps['R_s']:.4f}, "
              f"R_c={comps['R_c']:.4f}, R_r={comps['R_r']:.4f})")

    t_start = time.time()
    prev_R = comps['R']
    timing_acc = {} if profile_timing else None
    t_rob_total = 0.0

    for step in range(1, max_steps + 1):
        A = evolve_step(A, params, rng, timing_acc=timing_acc)
        t_rob = time.time()
        comps = compute_R_components(A, weights)
        if profile_timing:
            t_rob_total += time.time() - t_rob
        elapsed = time.time() - t_start

        history.append({
            'step': step,
            'R': comps['R'],
            'R_s': comps['R_s'],
            'R_c': comps['R_c'],
            'R_r': comps['R_r'],
            'time': elapsed,
        })

        if comps['R'] > best_R:
            best_R = comps['R']
            A_star = A.copy()

        if verbose and step % 10 == 0:
            print(f"Step {step}: R={comps['R']:.6f} (best={best_R:.6f}) "
                  f"[{elapsed:.1f}s]")

        if step >= min_steps and abs(comps['R'] - prev_R) < conv_thresh:
            if verbose:
                print(f"Converged at step {step} (ΔR={abs(comps['R'] - prev_R):.6f})")
            break

        time_limit = params.get('time_limit')
        if time_limit is not None and elapsed >= time_limit:
            if verbose:
                print(f"Time limit reached at step {step} ({elapsed:.1f}s)")
            break

        prev_R = comps['R']

    total_time = time.time() - t_start
    if verbose:
        final_comps = compute_R_components(A_star, weights)
        print(f"\nOptimization complete: best R={best_R:.6f} "
              f"(total time={total_time:.1f}s)")
        print(f"  R_s={final_comps['R_s']:.4f}, R_c={final_comps['R_c']:.4f}, "
              f"R_r={final_comps['R_r']:.4f}")

    if profile_timing and timing_acc:
        n_steps = len(history) - 1
        timing_acc['robustness_s'] = t_rob_total
        timing_acc['n_steps'] = n_steps
        return A_star, history, timing_acc
    return A_star, history


def get_edge_changes(A0, A_star, threshold=0.01):
    """比较两个邻接矩阵，输出边变更方案。"""
    edges_to_add = []
    edges_to_remove = []
    edges_to_modify = []
    n = A0.shape[0]

    for i in range(n):
        for j in range(i + 1, n):
            old = A0[i, j]
            new = A_star[i, j]
            if old < threshold and new >= threshold:
                edges_to_add.append((i, j, float(new)))
            elif old >= threshold and new < threshold:
                edges_to_remove.append((i, j))
            elif abs(old - new) > threshold:
                edges_to_modify.append((i, j, float(old), float(new)))

    return {
        'edges_to_add': edges_to_add,
        'edges_to_remove': edges_to_remove,
        'edges_to_modify': edges_to_modify,
    }


def mle_estimate_params(snapshots, dt_obs=1.0, n_restarts=3, max_iter=50, seed=42):
    """基于时序拓扑快照的 MLE 参数估计。

    用一阶 Euler 近似动力学方程，最小化预测与观测之间的误差。
    """
    from scipy.optimize import minimize

    rng = np.random.RandomState(seed)
    n = snapshots[0].shape[0]
    T = len(snapshots) - 1

    def neg_log_likelihood(theta):
        alpha, beta, alpha_L, alpha_G, lambda_L, lambda_G = theta
        if any(t < 0 for t in theta):
            return 1e10

        total_err = 0.0
        A_pred = snapshots[0].copy()

        for t in range(T):
            degrees = np.sum(A_pred, axis=1)
            common = A_pred @ A_pred.T
            max_deg = np.maximum.outer(degrees, degrees)
            max_deg = np.maximum(max_deg, 1.0)
            F_L = common / (max_deg + 1e-8) - lambda_L * A_pred
            F_G = -lambda_G * A_pred

            dA = (alpha * (-beta * A_pred) +
                  alpha_L * F_L + alpha_G * F_G)
            dA = (dA + dA.T) / 2.0
            np.fill_diagonal(dA, 0.0)

            A_pred = A_pred + dt_obs * dA
            A_pred = np.clip(A_pred, 0, 1)
            A_pred = (A_pred + A_pred.T) / 2.0
            np.fill_diagonal(A_pred, 0.0)

            err = np.sum((A_pred - snapshots[t + 1]) ** 2)
            total_err += err

        return total_err / T

    best_result = None
    best_loss = float('inf')

    for restart in range(n_restarts):
        x0 = np.abs(rng.randn(6)) * 0.1 + 0.05
        x0 = np.clip(x0, 0.01, 1.0)

        try:
            result = minimize(
                neg_log_likelihood, x0,
                method='Nelder-Mead',
                options={'maxiter': max_iter, 'xatol': 1e-4, 'fatol': 1e-4}
            )
            if result.fun < best_loss:
                best_loss = result.fun
                best_result = result
        except Exception:
            continue

    if best_result is None:
        return DEFAULT_PARAMS.copy(), float('inf')

    theta = best_result.x
    estimated = {
        'alpha': float(np.clip(theta[0], 0.01, 1.0)),
        'beta': float(np.clip(theta[1], 0.01, 1.0)),
        'alpha_L': float(np.clip(theta[2], 0.01, 1.0)),
        'alpha_G': float(np.clip(theta[3], 0.01, 1.0)),
        'lambda_L': float(np.clip(theta[4], 0.01, 1.0)),
        'lambda_G': float(np.clip(theta[5], 0.01, 1.0)),
    }
    return estimated, best_loss
