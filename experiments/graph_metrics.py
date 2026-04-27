#!/usr/bin/env python3
"""
Graph metrics helpers for experiment runners.
"""

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components, shortest_path


def _binary_adj(A):
    if A.size == 0:
        return A
    B = (A > 0).astype(np.float64)
    np.fill_diagonal(B, 0.0)
    return B


def compute_graph_stats(A, weights=None):
    B = _binary_adj(A)
    n = B.shape[0]
    if n == 0:
        return {
            "n_nodes": 0,
            "n_edges": 0,
            "n_components": 0,
            "lcc_ratio": 0.0,
            "avg_path_length": 0.0,
            "max_degree": 0.0,
            "mean_degree": 0.0,
        }

    G = sparse.csr_matrix(B)
    n_components, labels = connected_components(G, directed=False)
    counts = np.bincount(labels) if n_components > 0 else np.array([0])
    lcc_size = int(np.max(counts)) if counts.size else 0
    lcc_ratio = float(lcc_size / n)

    degrees = np.asarray(B.sum(axis=1)).ravel()
    mean_degree = float(np.mean(degrees)) if degrees.size else 0.0
    max_degree = float(np.max(degrees)) if degrees.size else 0.0

    if lcc_size <= 1:
        apl = 0.0
    else:
        lcc_label = int(np.argmax(counts))
        idx = np.where(labels == lcc_label)[0]
        D = shortest_path(G[idx][:, idx], directed=False, unweighted=True)
        mask = np.isfinite(D) & (D > 0)
        apl = float(np.mean(D[mask])) if np.any(mask) else 0.0

    n_edges = int(np.sum(B) / 2)
    return {
        "n_nodes": int(n),
        "n_edges": n_edges,
        "n_components": int(n_components),
        "lcc_ratio": lcc_ratio,
        "avg_path_length": apl,
        "max_degree": max_degree,
        "mean_degree": mean_degree,
    }


def _remove_nodes(B, nodes):
    C = B.copy()
    for u in nodes:
        C[u, :] = 0.0
        C[:, u] = 0.0
    return C


def attack_graph(A, attack_type="random", frac=0.1, seed=None):
    B = _binary_adj(A)
    n = B.shape[0]
    if n == 0:
        return {
            "lcc_ratio": 0.0,
            "avg_path_length": 0.0,
            "n_components": 0,
        }

    k = int(max(1, round(frac * n)))
    rng = np.random.RandomState(0 if seed is None else int(seed))

    if attack_type == "targeted":
        deg = np.asarray(B.sum(axis=1)).ravel()
        nodes = np.argsort(-deg)[:k]
    elif attack_type == "adaptive":
        C = B.copy()
        nodes = []
        for _ in range(k):
            deg = np.asarray(C.sum(axis=1)).ravel()
            idx = int(np.argmax(deg))
            nodes.append(idx)
            C[idx, :] = 0.0
            C[:, idx] = 0.0
        C = B.copy()
        B_attacked = _remove_nodes(C, nodes)
        return compute_graph_stats(B_attacked)
    else:
        nodes = rng.choice(n, size=k, replace=False)

    B_attacked = _remove_nodes(B, nodes)
    return compute_graph_stats(B_attacked)
