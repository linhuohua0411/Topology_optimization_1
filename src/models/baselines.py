"""
基线对比方法实现，用于论文 4.3 节的方法对比实验。

1. ResiNet 简化版: 基于度保持的边重连 (greedy hill-climbing)
2. FPSblo-EP 简化版: 基于最远点采样的层次覆盖优化
3. 静态优化: 基于度分布和聚类系数的贪心优化
4. 攻击仿真方法: 蒙特卡洛攻击仿真 + 贪心边重连
"""

import numpy as np
import networkx as nx
from .robustness import compute_R, compute_R_components


def resinet_optimize(A0, max_rewires=500, seed=42, weights=None, time_limit=None):
    """ResiNet 简化版: 度保持的贪心边重连。

    每次选择一条边 (u,v) 和一条非边 (u,w)，交换使得 R 增大。
    time_limit: 可选，秒数，超时则提前停止。
    """
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    rng = np.random.RandomState(seed)
    n = A0.shape[0]
    A = A0.copy()
    best_R = compute_R(A, weights)
    A_best = A.copy()
    history = [{'step': 0, 'R': best_R}]

    import time
    t0 = time.time()

    for step in range(1, max_rewires + 1):
        if time_limit is not None and (time.time() - t0) >= time_limit:
            break
        edges = []
        non_edges = []
        for i in range(n):
            for j in range(i + 1, n):
                if A[i, j] > 0:
                    edges.append((i, j))
                else:
                    non_edges.append((i, j))

        if len(edges) == 0 or len(non_edges) == 0:
            break

        improved = False
        n_tries = min(50, len(edges))
        for _ in range(n_tries):
            e_idx = rng.randint(len(edges))
            ne_idx = rng.randint(len(non_edges))
            u, v = edges[e_idx]
            x, y = non_edges[ne_idx]

            A_trial = A.copy()
            A_trial[u, v] = 0
            A_trial[v, u] = 0
            A_trial[x, y] = 1.0
            A_trial[y, x] = 1.0

            G_trial = nx.from_numpy_array((A_trial > 0).astype(int))
            if not nx.is_connected(G_trial):
                continue

            r_trial = compute_R(A_trial, weights)
            if r_trial > best_R:
                A = A_trial
                best_R = r_trial
                A_best = A.copy()
                improved = True
                break

        history.append({'step': step, 'R': best_R, 'time': time.time() - t0})

        if step % 50 == 0 and not improved:
            break

    return A_best, history


def fpsblo_optimize(A0, n_landmarks=10, max_iters=100, seed=42, weights=None, time_limit=None):
    """FPSblo-EP 简化版: 基于最远点采样的层次覆盖优化。

    选择标记节点（landmarks），优化标记节点之间的连接以提升全局鲁棒性。
    time_limit: 可选，秒数，超时则提前停止。
    """
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    rng = np.random.RandomState(seed)
    n = A0.shape[0]
    A = A0.copy()

    G = nx.from_numpy_array((A > 0).astype(int))
    dist_matrix = dict(nx.all_pairs_shortest_path_length(G))

    landmarks = [rng.randint(n)]
    for _ in range(n_landmarks - 1):
        max_min_dist = -1
        best_node = -1
        for node in range(n):
            if node in landmarks:
                continue
            min_dist = min(dist_matrix.get(node, {}).get(lm, float('inf'))
                          for lm in landmarks)
            if min_dist > max_min_dist:
                max_min_dist = min_dist
                best_node = node
        if best_node >= 0:
            landmarks.append(best_node)

    best_R = compute_R(A, weights)
    A_best = A.copy()
    history = [{'step': 0, 'R': best_R}]

    import time
    t0 = time.time()

    for step in range(1, max_iters + 1):
        if time_limit is not None and (time.time() - t0) >= time_limit:
            break
        improved = False
        for i_idx in range(len(landmarks)):
            for j_idx in range(i_idx + 1, len(landmarks)):
                li, lj = landmarks[i_idx], landmarks[j_idx]
                if A[li, lj] < 0.5:
                    A_trial = A.copy()
                    low_edges = []
                    for j in range(n):
                        if A[li, j] > 0 and j != lj:
                            low_edges.append((li, j, A[li, j]))
                    if not low_edges:
                        continue
                    low_edges.sort(key=lambda x: x[2])
                    rm = low_edges[0]
                    A_trial[rm[0], rm[1]] = 0
                    A_trial[rm[1], rm[0]] = 0
                    A_trial[li, lj] = 1.0
                    A_trial[lj, li] = 1.0

                    G_t = nx.from_numpy_array((A_trial > 0).astype(int))
                    if nx.is_connected(G_t):
                        r_trial = compute_R(A_trial, weights)
                        if r_trial > best_R:
                            A = A_trial
                            best_R = r_trial
                            A_best = A.copy()
                            improved = True

        history.append({'step': step, 'R': best_R, 'time': time.time() - t0})
        if not improved:
            break

    return A_best, history


def static_optimize(A0, max_iters=200, seed=42, weights=None, time_limit=None):
    """静态优化: 基于度分布与聚类系数的贪心优化。

    目标: 降低度分布变异系数、提升聚类系数。
    通过边重连（从高度节点移除边并添加到低度节点间）实现。
    time_limit: 可选，秒数，超时则提前停止。
    """
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    rng = np.random.RandomState(seed)
    n = A0.shape[0]
    A = A0.copy()
    best_R = compute_R(A, weights)
    A_best = A.copy()
    history = [{'step': 0, 'R': best_R}]

    import time
    t0 = time.time()

    for step in range(1, max_iters + 1):
        if time_limit is not None and (time.time() - t0) >= time_limit:
            break
        degrees = np.sum(A > 0, axis=1)
        high_deg_nodes = np.argsort(-degrees)[:n // 5]
        low_deg_nodes = np.argsort(degrees)[:n // 5]

        improved = False
        for _ in range(20):
            hi = rng.choice(high_deg_nodes)
            neighbors = np.where(A[hi] > 0)[0]
            if len(neighbors) <= 1:
                continue
            remove_j = rng.choice(neighbors)

            lo = rng.choice(low_deg_nodes)
            non_neighbors = np.where(A[lo] == 0)[0]
            non_neighbors = non_neighbors[non_neighbors != lo]
            if len(non_neighbors) == 0:
                continue
            add_j = rng.choice(non_neighbors)

            A_trial = A.copy()
            A_trial[hi, remove_j] = 0
            A_trial[remove_j, hi] = 0
            A_trial[lo, add_j] = 1.0
            A_trial[add_j, lo] = 1.0

            G_t = nx.from_numpy_array((A_trial > 0).astype(int))
            if not nx.is_connected(G_t):
                continue

            r_trial = compute_R(A_trial, weights)
            if r_trial > best_R:
                A = A_trial
                best_R = r_trial
                A_best = A.copy()
                improved = True
                break

        history.append({'step': step, 'R': best_R, 'time': time.time() - t0})
        if step % 50 == 0 and not improved:
            break

    return A_best, history


def attack_simulation_optimize(A0, n_attacks=50, attack_fraction=0.1,
                                max_rewires=100, seed=42, weights=None, time_limit=None):
    """攻击仿真方法: 蒙特卡洛攻击仿真 + 贪心边重连。

    对每种攻击场景仿真，选择能在攻击后保持最高 LCC 的拓扑。
    time_limit: 可选，秒数，超时则提前停止。
    """
    if weights is None:
        weights = (0.3, 0.4, 0.3)
    rng = np.random.RandomState(seed)
    n = A0.shape[0]
    A = A0.copy()
    best_R = compute_R(A, weights)
    A_best = A.copy()
    history = [{'step': 0, 'R': best_R}]

    import time
    t0 = time.time()

    def attack_robustness(A_test, n_attacks_eval=10):
        lcc_scores = []
        n_t = A_test.shape[0]
        n_remove = max(1, int(n_t * attack_fraction))
        for _ in range(n_attacks_eval):
            G = nx.from_numpy_array((A_test > 0).astype(int))
            if rng.random() < 0.5:
                nodes_to_remove = rng.choice(n_t, size=n_remove, replace=False)
            else:
                degrees = np.sum(A_test > 0, axis=1)
                nodes_to_remove = np.argsort(-degrees)[:n_remove]
            G.remove_nodes_from(nodes_to_remove)
            if len(G) > 0:
                lcc = len(max(nx.connected_components(G), key=len)) / n_t
            else:
                lcc = 0.0
            lcc_scores.append(lcc)
        return np.mean(lcc_scores)

    for step in range(1, max_rewires + 1):
        if time_limit is not None and (time.time() - t0) >= time_limit:
            break
        edges = [(i, j) for i in range(n) for j in range(i+1, n) if A[i, j] > 0]
        non_edges = [(i, j) for i in range(n) for j in range(i+1, n) if A[i, j] == 0]

        if not edges or not non_edges:
            break

        best_score = attack_robustness(A)
        improved = False

        for _ in range(min(30, len(edges))):
            e_idx = rng.randint(len(edges))
            ne_idx = rng.randint(len(non_edges))
            u, v = edges[e_idx]
            x, y = non_edges[ne_idx]

            A_trial = A.copy()
            A_trial[u, v] = 0; A_trial[v, u] = 0
            A_trial[x, y] = 1.0; A_trial[y, x] = 1.0

            G_t = nx.from_numpy_array((A_trial > 0).astype(int))
            if not nx.is_connected(G_t):
                continue

            score = attack_robustness(A_trial, n_attacks_eval=5)
            if score > best_score:
                A = A_trial
                best_score = score
                r_new = compute_R(A, weights)
                if r_new > best_R:
                    best_R = r_new
                    A_best = A.copy()
                improved = True
                break

        history.append({'step': step, 'R': best_R, 'time': time.time() - t0})
        if step % 30 == 0 and not improved:
            break

    return A_best, history
