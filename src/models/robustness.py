"""
鲁棒性评估与梯度近似模块（高性能版本）。
实现 R = w1*R_s + w2*R_c + w3*R_r，以及数值差分梯度。

【梯度近似说明】问题日志 9.1/9.6：
- 目标 R = w1*R_s + w2*R_c + w3*R_r，但完整梯度计算昂贵（R_c 含全图最短路）。
- 默认 gradient_mode='R_s_only'：仅对 R_s 做差分，作为 R 的代理梯度，以加速。
- R_r 通过 R_degree（含于 R_s）与自组织项 F_L 间接优化。
- gradient_mode='R_s_R_r' 或 'full' 用于消融实验，说明近似带来的取舍。
"""

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import shortest_path


def _laplacian_second_eigenvalue(A):
    """计算拉普拉斯矩阵的代数连通度 λ₂(L)。"""
    n = A.shape[0]
    if n < 2:
        return 0.0
    degrees = np.sum(A, axis=1)
    L = np.diag(degrees) - A
    eigenvalues = np.linalg.eigvalsh(L)
    eigenvalues.sort()
    return max(0.0, float(eigenvalues[1]))


def _clustering_coefficient_numpy(A):
    """用矩阵运算高效计算平均聚类系数。

    C_i = 2 * triangles_i / (k_i * (k_i - 1))，其中 triangles 通过 A^3 对角线获得。
    """
    binary = (A > 0).astype(np.float64)
    degrees = binary.sum(axis=1)
    A2 = binary @ binary
    triangles = np.diag(A2 @ binary) / 2.0

    mask = degrees >= 2
    c = np.zeros(len(degrees))
    denom = degrees[mask] * (degrees[mask] - 1) / 2.0
    c[mask] = triangles[mask] / np.maximum(denom, 1e-10)
    return float(np.mean(c))


def _compute_R_conn(A):
    """R_conn = λ₂(L) / N"""
    return _laplacian_second_eigenvalue(A) / A.shape[0]


def _compute_R_degree(A):
    """R_degree = exp(-CV), CV = σ_k / k̄"""
    degrees = np.sum(A, axis=1)
    mean_k = np.mean(degrees)
    if mean_k < 1e-10:
        return 0.0
    return float(np.exp(-np.std(degrees) / mean_k))


def _compute_R_clust(A):
    """R_clust = min(1, C_actual / C_random)"""
    c_actual = _clustering_coefficient_numpy(A)
    n = A.shape[0]
    m = np.sum(A > 0) / 2
    c_random = 2.0 * m / (n * (n - 1)) if n > 1 else 0.0
    if c_random < 1e-10:
        return 0.0
    return min(1.0, c_actual / c_random)


def compute_R_s(A):
    """静态鲁棒性 R_s = (R_conn + R_degree + R_clust) / 3"""
    r_conn = _compute_R_conn(A)
    r_degree = _compute_R_degree(A)
    r_clust = _compute_R_clust(A)
    return (r_conn + r_degree + r_clust) / 3.0, {
        'R_conn': r_conn,
        'R_degree': r_degree,
        'R_clust': r_clust,
    }


def compute_R_c(A, max_pairs=2000, seed=None):
    """连接鲁棒性 (逆距离效率): R_c = 2/(N(N-1)) * Σ_{i<j} 1/d_ij"""
    n = A.shape[0]
    binary_A = (A > 0).astype(np.float64)
    dist_matrix = shortest_path(sparse.csr_matrix(binary_A), method='D', directed=False)

    total_pairs = n * (n - 1) // 2
    if total_pairs <= max_pairs:
        inv_sum = 0.0
        count = 0
        for i in range(n):
            for j in range(i + 1, n):
                d = dist_matrix[i, j]
                if np.isfinite(d) and d > 0:
                    inv_sum += 1.0 / d
                count += 1
        return inv_sum / count if count > 0 else 0.0
    else:
        rng = np.random.RandomState(seed if seed is not None else 0)
        pairs_i = rng.randint(0, n, size=max_pairs)
        pairs_j = rng.randint(0, n, size=max_pairs)
        inv_sum = 0.0
        count = 0
        for k in range(max_pairs):
            i, j = pairs_i[k], pairs_j[k]
            if i == j:
                continue
            d = dist_matrix[i, j]
            if np.isfinite(d) and d > 0:
                inv_sum += 1.0 / d
            count += 1
        return inv_sum / count if count > 0 else 0.0


def compute_R_r(A):
    """恢复鲁棒性 (τ 代理):
    τ_i = 1/(1 + k_i), τ_max = max(τ_i), R_r = mean(exp(-τ_i/τ_max))
    """
    degrees = np.sum(A, axis=1)
    tau = 1.0 / (1.0 + degrees)
    tau_max = np.max(tau)
    if tau_max < 1e-10:
        return 1.0
    return float(np.mean(np.exp(-tau / tau_max)))


def compute_R(A, weights=None):
    """总鲁棒性 R(A) = w1*R_s + w2*R_c + w3*R_r。返回 float ∈ [0,1]。"""
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    w1, w2, w3 = weights
    r_s, _ = compute_R_s(A)
    r_c = compute_R_c(A)
    r_r = compute_R_r(A)
    return w1 * r_s + w2 * r_c + w3 * r_r


def compute_R_components(A, weights=None):
    """返回 dict：R, R_s, R_c, R_r 及子项。"""
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    w1, w2, w3 = weights
    r_s, sub = compute_R_s(A)
    r_c = compute_R_c(A)
    r_r = compute_R_r(A)
    r_total = w1 * r_s + w2 * r_c + w3 * r_r
    return {
        'R': r_total,
        'R_s': r_s,
        'R_c': r_c,
        'R_r': r_r,
        'R_conn': sub['R_conn'],
        'R_degree': sub['R_degree'],
        'R_clust': sub['R_clust'],
        'weights': weights,
    }


def compute_R_s_only(A, weights=None):
    """仅计算 R_s 标量值（用于梯度加速）。"""
    r_s, _ = compute_R_s(A)
    return r_s


def compute_gradient_R(A, epsilon=1e-5, sample_ratio=0.1, weights=None, seed=None,
                       gradient_mode='R_s_only'):
    """鲁棒性梯度近似。gradient_mode 控制差分范围，用于消融（问题日志 9.1）。

    gradient_mode:
      'R_s_only' (默认): 仅 R_s，加速；R_c/R_r 通过 F_L 间接优化。
      'R_s_R_r': R_s + R_r，R_r 仅依赖度、计算便宜。
      'full': R_s + R_c + R_r，R_c 含最短路、计算昂贵。
    对候选边对采样 sample_ratio 比例。返回 N×N 对称梯度矩阵。
    """
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    w1, w2, w3 = weights[0], weights[1], weights[2]
    n = A.shape[0]
    grad = np.zeros((n, n), dtype=np.float64)

    r_s_base = compute_R_s_only(A)
    r_r_base = compute_R_r(A) if gradient_mode in ('R_s_R_r', 'full') else 0.0
    r_c_base = compute_R_c(A) if gradient_mode == 'full' else 0.0

    rng = np.random.RandomState(seed if seed is not None else 0)
    total_pairs = n * (n - 1) // 2
    n_sample = max(1, int(total_pairs * sample_ratio))

    triu_i, triu_j = np.triu_indices(n, k=1)
    if n_sample < total_pairs:
        indices = rng.choice(total_pairs, size=n_sample, replace=False)
        sample_i = triu_i[indices]
        sample_j = triu_j[indices]
    else:
        sample_i = triu_i
        sample_j = triu_j

    for k in range(len(sample_i)):
        i, j = sample_i[k], sample_j[k]
        A[i, j] += epsilon
        A[j, i] += epsilon

        r_s_pert = compute_R_s_only(A)
        g = w1 * (r_s_pert - r_s_base) / epsilon

        if gradient_mode in ('R_s_R_r', 'full'):
            r_r_pert = compute_R_r(A)
            g += w3 * (r_r_pert - r_r_base) / epsilon
        if gradient_mode == 'full':
            r_c_pert = compute_R_c(A)
            g += w2 * (r_c_pert - r_c_base) / epsilon

        A[i, j] -= epsilon
        A[j, i] -= epsilon

        grad[i, j] = g
        grad[j, i] = g

    return grad
