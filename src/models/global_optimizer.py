"""
演化+自组织串联的全局拓扑优化器，RK4 离散与约束处理，与 TIFS 计划 6.1 一致。

单步流程: 演化动力学 RK4 → 自组织动力学 RK4 → 约束处理

【MLE 与优化关系】问题日志 9.2：
- MLE 拟合的是无梯度驱动的被动演化，用于「拓扑演化预测」验证。
- 优化使用梯度驱动的主动演化，采用固定参数，不依赖 MLE 估计。
"""

import numpy as np
import time
from scipy import sparse
from scipy.sparse.csgraph import connected_components
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
    # Updated default from weight auto-tune pilot (ED-MAIN-BASE).
    'w1': 0.25,
    'w2': 0.55,
    'w3': 0.20,
    # Online adaptive-weight controller (kept for ablation only; mainline uses fixed weights).
    'adaptive_weights_enabled': False,
    'adaptive_update_every': 5,
    'adaptive_warmup_steps': 10,
    'adaptive_eta': 0.12,
    'adaptive_min_weight': 0.10,
    'adaptive_max_weight': 0.70,
    'k_max': 15,
    'dt': 0.05,
    'max_steps': 200,
    'min_steps': 30,
    'convergence_threshold': 0.0005,
    'gradient_sample_ratio': 0.1,
    'gradient_epsilon': 1e-5,
    # 默认使用 full，使优化目标与 R= w1*R_s + w2*R_c + w3*R_r 的梯度方向一致；
    # R_s_only / R_s_R_r 保留用于消融与速度-精度权衡分析。
    'gradient_mode': 'full',  # 'R_s_only'|'R_s_R_r'|'full'
    # 分级近似：在 full 主目标下，周期性 full + 高频轻量梯度（默认 R_s_R_r）。
    'gradient_tiered_enabled': True,
    'gradient_tiered_warmup_steps': 10,
    'gradient_tiered_full_every': 8,
    'gradient_tiered_fast_mode': 'R_s_R_r',
    'gradient_sampling_mode': 'structured',  # 'structured'|'random'
    'gradient_hub_ratio': 0.2,
    'gradient_bridge_ratio': 0.4,
    # 软约束惩罚（训练期）与轻量硬约束（间歇+末段）。
    'degree_penalty_lambda': 0.03,
    'disconnect_penalty_lambda': 0.08,
    'constraint_enforce_every': 5,
    'final_repair_window': 8,
    # 两阶段权重调度（更稳定，可复现）。
    'two_phase_weight_schedule': True,
    'phase_switch_ratio': 0.4,
    'phase1_weights': (0.20, 0.60, 0.20),
    'phase2_weights': (0.35, 0.35, 0.30),
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


def _apply_connectivity_constraint(A, weight=0.1, max_repairs=None):
    """连通性约束：若图不连通则在连通分量之间添加边。

    Returns:
        (A, repairs_added)
    """
    import networkx as nx
    binary = (A > 0).astype(int)
    G = nx.from_numpy_array(binary)
    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return A, 0

    repairs_added = 0
    if max_repairs is None:
        max_repairs = len(components) - 1
    max_repairs = max(0, int(max_repairs))
    if max_repairs == 0:
        return A, 0

    main = components[0]
    for comp in components[1:]:
        if repairs_added >= max_repairs:
            break
        i = list(main)[0]
        j = list(comp)[0]
        A[i, j] = weight
        A[j, i] = weight
        main = main.union(comp)
        repairs_added += 1
    return A, repairs_added


def _apply_constraints(A, k_max, repair_weight=0.1, repair_budget_remaining=None):
    """依次施加约束：非负 → 对称 → 度约束 → 连通性。"""
    A = _symmetrize_and_clip(A)
    A = _apply_degree_constraint(A, k_max)
    A, repairs_added = _apply_connectivity_constraint(
        A,
        weight=repair_weight,
        max_repairs=repair_budget_remaining,
    )
    return A, int(repairs_added)


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


def _compute_constraint_penalty(A, k_max, degree_lambda=0.0, disconnect_lambda=0.0):
    """训练期软约束惩罚，避免每步都靠硬修复。"""
    binary = (A > 0).astype(np.int32)
    degrees = np.sum(binary, axis=1).astype(np.float64)
    overflow = np.maximum(0.0, degrees - float(k_max))
    degree_pen = 0.0
    if float(k_max) > 0:
        degree_pen = float(np.mean(overflow / float(k_max)))

    n_comp, _ = connected_components(
        csgraph=sparse.csr_matrix(binary), directed=False, return_labels=True
    )
    disconnect_pen = float(max(0, n_comp - 1)) / float(max(1, A.shape[0]))
    total_pen = float(degree_lambda) * degree_pen + float(disconnect_lambda) * disconnect_pen
    return total_pen, degree_pen, disconnect_pen


def _compute_cached_gradient(A, params, rng, step=0):
    """计算梯度并缓存。gradient_mode 见 robustness.compute_gradient_R。"""
    weights = (params['w1'], params['w2'], params['w3'])
    gmode = params.get('gradient_mode', 'full')
    if (
        params.get('gradient_tiered_enabled', False)
        and gmode == 'full'
    ):
        warmup = int(params.get('gradient_tiered_warmup_steps', 10))
        full_every = max(1, int(params.get('gradient_tiered_full_every', 8)))
        fast_mode = params.get('gradient_tiered_fast_mode', 'R_s_R_r')
        if step > warmup and (step % full_every != 0):
            gmode = fast_mode
    return compute_gradient_R(
        A,
        epsilon=params['gradient_epsilon'],
        sample_ratio=params['gradient_sample_ratio'],
        weights=weights,
        seed=rng.randint(0, 2**31),
        gradient_mode=gmode,
        sampling_mode=params.get('gradient_sampling_mode', 'structured'),
        hub_ratio=float(params.get('gradient_hub_ratio', 0.2)),
        bridge_ratio=float(params.get('gradient_bridge_ratio', 0.4)),
    )


def _softmax(vec):
    arr = np.asarray(vec, dtype=float)
    arr = arr - np.max(arr)
    exp = np.exp(arr)
    denom = float(np.sum(exp))
    if denom <= 0.0:
        return np.array([1.0 / len(arr)] * len(arr), dtype=float)
    return exp / denom


def _project_weights_with_bounds(w, w_min=0.10, w_max=0.70):
    """Project weights to simplex with lower/upper bounds."""
    w = np.asarray(w, dtype=float)
    w = np.clip(w, w_min, w_max)
    s = float(np.sum(w))
    if s <= 0.0:
        return np.array([1.0 / 3.0] * 3, dtype=float)
    w = w / s
    for _ in range(8):
        w = np.clip(w, w_min, w_max)
        s = float(np.sum(w))
        if s <= 0.0:
            w = np.array([1.0 / 3.0] * 3, dtype=float)
            break
        w = w / s
        if np.all(w >= w_min - 1e-9) and np.all(w <= w_max + 1e-9):
            break
    return w


def _adaptive_weight_update(params, prev_comps, curr_comps):
    """
    Online adaptive update for (w1,w2,w3):
    - If a component improves slowly, increase its weight.
    - If it improves fast, slightly decrease to focus bottlenecks.
    """
    eta = float(params.get('adaptive_eta', 0.12))
    w_min = float(params.get('adaptive_min_weight', 0.10))
    w_max = float(params.get('adaptive_max_weight', 0.70))
    eps = 1e-9

    d_rs = float(curr_comps['R_s'] - prev_comps['R_s'])
    d_rc = float(curr_comps['R_c'] - prev_comps['R_c'])
    d_rr = float(curr_comps['R_r'] - prev_comps['R_r'])
    deltas = np.array([d_rs, d_rc, d_rr], dtype=float)

    # Smaller improvement => larger bonus.
    inv = 1.0 / (np.abs(deltas) + eps)
    inv = inv / float(np.sum(inv))
    signs = np.sign(deltas)
    feedback = inv - 0.15 * signs

    w_vec = np.array([params['w1'], params['w2'], params['w3']], dtype=float)
    logits = np.log(np.maximum(w_vec, eps)) + eta * feedback
    w_new = _softmax(logits)
    w_new = _project_weights_with_bounds(w_new, w_min=w_min, w_max=w_max)

    params['w1'], params['w2'], params['w3'] = float(w_new[0]), float(w_new[1]), float(w_new[2])


def evolve_step(
    A,
    params,
    rng=None,
    timing_acc=None,
    repair_budget_state=None,
    step=0,
    enforce_constraints=True,
):
    """单步：演化动力学 RK4 -> 自组织动力学 RK4 -> 约束。返回 A_next。
    timing_acc: 可选，可变 dict，将记录 gradient_s, evolution_constraints_s。
    """
    if rng is None:
        rng = np.random.RandomState(params.get('seed', 42))

    dt = params['dt']
    k_max = params['k_max']

    t0 = time.time()
    grad_R = _compute_cached_gradient(A, params, rng, step=step)
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
    repair_budget_remaining = None
    if repair_budget_state is not None:
        repair_budget_remaining = repair_budget_state.get('remaining')
    if enforce_constraints:
        A_next, repairs_added = _apply_constraints(
            A_step,
            k_max,
            repair_weight=float(params.get('connectivity_repair_weight', 0.1)),
            repair_budget_remaining=repair_budget_remaining,
        )
    else:
        A_next = _symmetrize_and_clip(A_step)
        repairs_added = 0
    if repair_budget_state is not None and repair_budget_remaining is not None:
        repair_budget_state['remaining'] = max(0, int(repair_budget_remaining) - int(repairs_added))
    t_evo = time.time() - t_evo_start
    if timing_acc is not None:
        timing_acc['gradient_s'] = timing_acc.get('gradient_s', 0) + t_grad
        timing_acc['evolution_constraints_s'] = timing_acc.get('evolution_constraints_s', 0) + t_evo
    return A_next, int(repairs_added)


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
        'w1': float(params['w1']),
        'w2': float(params['w2']),
        'w3': float(params['w3']),
        'time': 0.0,
    }]

    if verbose:
        print(f"Step 0: R={comps['R']:.6f} (R_s={comps['R_s']:.4f}, "
              f"R_c={comps['R_c']:.4f}, R_r={comps['R_r']:.4f})")

    t_start = time.time()
    prev_R = comps['R']
    timing_acc = {} if profile_timing else None
    t_rob_total = 0.0

    adaptive_on = bool(params.get('adaptive_weights_enabled', False))
    adaptive_every = max(1, int(params.get('adaptive_update_every', 5)))
    adaptive_warmup = max(0, int(params.get('adaptive_warmup_steps', 10)))
    repair_penalty_lambda = float(params.get('connectivity_repair_penalty_lambda', 0.0))
    degree_penalty_lambda = float(params.get('degree_penalty_lambda', 0.0))
    disconnect_penalty_lambda = float(params.get('disconnect_penalty_lambda', 0.0))
    repair_budget_total = params.get('connectivity_repair_budget')
    if repair_budget_total is None:
        ratio = float(params.get('connectivity_repair_budget_ratio', 0.0))
        if ratio > 0.0:
            min_budget = int(params.get('connectivity_repair_budget_min', 0))
            repair_budget_total = max(min_budget, int(round(ratio * A.shape[0])))
    repair_budget_state = {'remaining': int(repair_budget_total)} if repair_budget_total is not None else {'remaining': None}
    cumulative_repairs = 0
    best_adjusted_R = best_R - repair_penalty_lambda * cumulative_repairs
    two_phase_on = bool(params.get('two_phase_weight_schedule', False))
    phase_switch_ratio = float(params.get('phase_switch_ratio', 0.4))
    phase_switch_step = max(1, int(round(phase_switch_ratio * max_steps)))
    phase1 = tuple(float(x) for x in params.get('phase1_weights', (0.20, 0.60, 0.20)))
    phase2 = tuple(float(x) for x in params.get('phase2_weights', (0.35, 0.35, 0.30)))
    enforce_every = max(1, int(params.get('constraint_enforce_every', 5)))
    final_repair_window = max(1, int(params.get('final_repair_window', 8)))

    for step in range(1, max_steps + 1):
        if two_phase_on:
            if step <= phase_switch_step:
                params['w1'], params['w2'], params['w3'] = phase1
            else:
                params['w1'], params['w2'], params['w3'] = phase2

        enforce_constraints = (step % enforce_every == 0) or (step > max_steps - final_repair_window)
        A, repairs_added = evolve_step(
            A,
            params,
            rng,
            timing_acc=timing_acc,
            repair_budget_state=repair_budget_state,
            step=step,
            enforce_constraints=enforce_constraints,
        )
        cumulative_repairs += int(repairs_added)
        t_rob = time.time()
        weights = (params['w1'], params['w2'], params['w3'])
        comps = compute_R_components(A, weights)
        c_pen, deg_pen, disc_pen = _compute_constraint_penalty(
            A,
            params['k_max'],
            degree_lambda=degree_penalty_lambda,
            disconnect_lambda=disconnect_penalty_lambda,
        )
        adjusted_R = comps['R'] - repair_penalty_lambda * cumulative_repairs - c_pen
        if profile_timing:
            t_rob_total += time.time() - t_rob
        elapsed = time.time() - t_start

        history.append({
            'step': step,
            'R': comps['R'],
            'R_s': comps['R_s'],
            'R_c': comps['R_c'],
            'R_r': comps['R_r'],
            'w1': float(params['w1']),
            'w2': float(params['w2']),
            'w3': float(params['w3']),
            'repair_added': int(repairs_added),
            'repair_cumulative': int(cumulative_repairs),
            'degree_penalty': float(deg_pen),
            'disconnect_penalty': float(disc_pen),
            'constraint_penalty': float(c_pen),
            'R_adjusted': float(adjusted_R),
            'time': elapsed,
        })

        if adjusted_R > best_adjusted_R:
            best_R = comps['R']
            best_adjusted_R = adjusted_R
            A_star = A.copy()

        if verbose and step % 10 == 0:
            print(f"Step {step}: R={comps['R']:.6f} (best={best_R:.6f}) "
                  f"[{elapsed:.1f}s]")

        if step >= min_steps and abs(adjusted_R - prev_R) < conv_thresh:
            if verbose:
                print(f"Converged at step {step} (ΔR_adj={abs(adjusted_R - prev_R):.6f})")
            break

        time_limit = params.get('time_limit')
        if time_limit is not None and elapsed >= time_limit:
            if verbose:
                print(f"Time limit reached at step {step} ({elapsed:.1f}s)")
            break

        if (not two_phase_on) and adaptive_on and step >= adaptive_warmup and (step % adaptive_every == 0):
            _adaptive_weight_update(params, history[-2], history[-1])

        prev_R = adjusted_R

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
