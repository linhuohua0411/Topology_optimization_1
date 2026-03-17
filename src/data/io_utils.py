"""
邻接矩阵与边列表互转、CSV 读写、清洗。与 plan 6.2 数据格式约定一致。
约定：nodes.csv（节点ID、角色、客户端等），edges_tk.csv（时间戳 tk 时的边列表）。
"""

import numpy as np
import pandas as pd
import os


def edges_to_adjacency(edges, n_nodes, weighted=False):
    """边列表 -> 邻接矩阵 A (对称, n_nodes x n_nodes)。

    Parameters
    ----------
    edges : list of tuples
        [(src, dst), ...] 或 [(src, dst, weight), ...]
    n_nodes : int
    weighted : bool
        若 True 且 edges 含第三列则用作权重，否则权重为 1。
    """
    A = np.zeros((n_nodes, n_nodes), dtype=np.float64)
    for e in edges:
        i, j = int(e[0]), int(e[1])
        if i == j or i >= n_nodes or j >= n_nodes:
            continue
        w = float(e[2]) if weighted and len(e) > 2 else 1.0
        A[i, j] = w
        A[j, i] = w
    return A


def adjacency_to_edges(A, threshold=0.01):
    """邻接矩阵 A -> 边列表 [(i, j, weight), ...]，只返回上三角。"""
    edges = []
    n = A.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            if A[i, j] > threshold:
                edges.append((i, j, float(A[i, j])))
    return edges


def load_edges_csv(path):
    """加载 edges_tk.csv，返回 (edges, timestamp)。

    CSV 格式: src,dst[,weight][,timestamp]
    """
    df = pd.read_csv(path)
    cols = [c.strip().lower() for c in df.columns]
    df.columns = cols

    src_col = 'src' if 'src' in cols else cols[0]
    dst_col = 'dst' if 'dst' in cols else cols[1]

    timestamp = None
    if 'timestamp' in cols:
        timestamps = df['timestamp'].unique()
        if len(timestamps) == 1:
            timestamp = timestamps[0]

    weight_col = 'weight' if 'weight' in cols else None

    edges = []
    for _, row in df.iterrows():
        e = [int(row[src_col]), int(row[dst_col])]
        if weight_col:
            e.append(float(row[weight_col]))
        edges.append(tuple(e))
    return edges, timestamp


def save_edges_csv(edges, path, timestamp=None):
    """保存边列表为 edges_tk.csv。"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    has_weight = len(edges) > 0 and len(edges[0]) > 2
    rows = []
    for e in edges:
        row = {'src': int(e[0]), 'dst': int(e[1])}
        if has_weight:
            row['weight'] = float(e[2])
        if timestamp is not None:
            row['timestamp'] = timestamp
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def generate_topology(n_nodes, model='ba', seed=42, **kwargs):
    """生成合成拓扑的邻接矩阵。

    Parameters
    ----------
    model : str
        'ba' (Barabási-Albert), 'ws' (Watts-Strogatz), 'er' (Erdős-Rényi)
    """
    import networkx as nx
    rng = np.random.RandomState(seed)

    if model == 'ba':
        m = kwargs.get('m', 3)
        G = nx.barabasi_albert_graph(n_nodes, m, seed=seed)
    elif model == 'ws':
        k = kwargs.get('k', 6)
        p = kwargs.get('p', 0.3)
        G = nx.watts_strogatz_graph(n_nodes, k, p, seed=seed)
    elif model == 'er':
        p = kwargs.get('p', 0.06)
        G = nx.erdos_renyi_graph(n_nodes, p, seed=seed)
    else:
        raise ValueError(f"Unknown model: {model}")

    A = nx.to_numpy_array(G, dtype=np.float64)
    return A


def generate_temporal_topology(A0, n_snapshots=30, change_rate=0.05, seed=42):
    """从初始拓扑 A0 生成时序拓扑快照序列 {A(t_k)}。

    在每个时间步随机添加/删除少量边来模拟拓扑演化。
    """
    rng = np.random.RandomState(seed)
    n = A0.shape[0]
    snapshots = [A0.copy()]

    A_current = A0.copy()
    for t in range(1, n_snapshots):
        n_edges = int(np.sum(A_current > 0) / 2)
        n_changes = max(1, int(n_edges * change_rate))

        for _ in range(n_changes):
            i, j = rng.randint(0, n, size=2)
            if i == j:
                continue
            if A_current[i, j] > 0 and rng.random() < 0.5:
                A_current[i, j] = 0
                A_current[j, i] = 0
            elif A_current[i, j] == 0:
                A_current[i, j] = 1.0
                A_current[j, i] = 1.0

        snapshots.append(A_current.copy())

    return snapshots
