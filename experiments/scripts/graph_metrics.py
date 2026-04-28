#!/usr/bin/env python3
"""Graph metrics and attack simulation helpers for ED scripts."""

from __future__ import annotations

import random
from typing import Any

import networkx as nx
import numpy as np


def compute_graph_stats(A: np.ndarray, _weights: tuple[float, float, float] | None = None) -> dict[str, Any]:
    """Return connectedness metrics expected by run_eth_docker_experiments.py."""
    n = int(A.shape[0])
    if n == 0:
        return {"lcc_ratio": 0.0, "avg_path_length": 0.0, "n_components": 0, "max_degree": 0}

    G = nx.from_numpy_array((A > 0.0).astype(np.int8))
    comps = list(nx.connected_components(G))
    if not comps:
        return {"lcc_ratio": 0.0, "avg_path_length": 0.0, "n_components": 0, "max_degree": 0}

    lcc_nodes = max(comps, key=len)
    lcc_ratio = float(len(lcc_nodes) / max(1, n))
    if len(lcc_nodes) <= 1:
        apl = 0.0
    else:
        H = G.subgraph(lcc_nodes).copy()
        apl = float(nx.average_shortest_path_length(H))

    deg = np.sum((A > 0.0).astype(np.int8), axis=1)
    max_degree = int(np.max(deg)) if len(deg) else 0
    return {
        "lcc_ratio": lcc_ratio,
        "avg_path_length": apl,
        "n_components": int(len(comps)),
        "max_degree": max_degree,
    }


def _remove_nodes_attack(A: np.ndarray, nodes_to_drop: list[int]) -> np.ndarray:
    B = np.asarray(A, dtype=np.float64).copy()
    for node in nodes_to_drop:
        B[node, :] = 0.0
        B[:, node] = 0.0
    return B


def attack_graph(A: np.ndarray, attack_type: str, frac: float, seed: int = 0) -> dict[str, Any]:
    """Simulate one attack and return graph stats."""
    n = int(A.shape[0])
    if n == 0:
        return {"lcc_ratio": 0.0, "avg_path_length": 0.0, "n_components": 0}

    frac = float(max(0.0, min(1.0, frac)))
    k = max(1, int(round(n * frac)))
    rng = random.Random(int(seed))

    if attack_type == "targeted":
        deg = np.sum((A > 0.0).astype(np.int8), axis=1)
        nodes = np.argsort(-deg)[:k].tolist()
    elif attack_type in ("random", "link_down", "tc_netem"):
        idxs = list(range(n))
        rng.shuffle(idxs)
        nodes = idxs[:k]
    else:
        nodes = []

    B = _remove_nodes_attack(A, nodes) if nodes else np.asarray(A, dtype=np.float64).copy()
    return compute_graph_stats(B)
