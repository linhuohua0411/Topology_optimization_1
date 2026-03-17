#!/usr/bin/env python3
"""
以太坊100节点私有链拓扑采集器。
通过 docker exec + Geth admin_peers RPC 采集所有节点的邻居关系。
"""

import sys
import os
import json
import time
import subprocess
import re
import numpy as np
from datetime import datetime, timezone


NODE_CONTAINERS = {}


def discover_containers():
    """发现所有以太坊 POS 节点容器。"""
    result = subprocess.run(
        ['docker', 'ps', '--format', '{{.Names}}'],
        capture_output=True, text=True
    )
    containers = {}
    for name in result.stdout.strip().split('\n'):
        match = re.match(r'as\d+h-Ethereum-POS-(\d+)-([\d.]+)', name)
        if match:
            node_id = int(match.group(1))
            ip = match.group(2)
            containers[node_id] = {'name': name, 'ip': ip}
    return containers


def get_peers(container_name):
    """通过 docker exec 调用 Geth admin_peers RPC。"""
    try:
        result = subprocess.run(
            ['docker', 'exec', container_name,
             'curl', '-sf', '-X', 'POST', 'http://localhost:8545',
             '-H', 'Content-Type: application/json',
             '-d', '{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return data.get('result', [])
    except Exception as e:
        pass
    return []


def get_node_info(container_name):
    """获取节点自身的 enode 信息。"""
    try:
        result = subprocess.run(
            ['docker', 'exec', container_name,
             'curl', '-sf', '-X', 'POST', 'http://localhost:8545',
             '-H', 'Content-Type: application/json',
             '-d', '{"jsonrpc":"2.0","method":"admin_nodeInfo","params":[],"id":1}'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return data.get('result', {})
    except Exception:
        pass
    return {}


def get_block_number(container_name):
    """获取当前区块高度。"""
    try:
        result = subprocess.run(
            ['docker', 'exec', container_name,
             'curl', '-sf', '-X', 'POST', 'http://localhost:8545',
             '-H', 'Content-Type: application/json',
             '-d', '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return int(data.get('result', '0x0'), 16)
    except Exception:
        pass
    return -1


def extract_ip_from_remote_address(remote_addr):
    """从 remoteAddress 提取 IP。"""
    if ':' in remote_addr:
        return remote_addr.rsplit(':', 1)[0]
    return remote_addr


def collect_topology_snapshot(containers):
    """采集一次全网拓扑快照，返回 (edges, node_info, timestamp)。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    ip_to_node_id = {}
    for nid, info in containers.items():
        ip_to_node_id[info['ip']] = nid

    all_edges = set()
    node_peer_counts = {}
    failed_nodes = []

    for nid in sorted(containers.keys()):
        cname = containers[nid]['name']
        peers = get_peers(cname)
        if peers is None:
            peers = []
            failed_nodes.append(nid)

        node_peer_counts[nid] = len(peers)

        for p in peers:
            remote = p.get('network', {}).get('remoteAddress', '')
            peer_ip = extract_ip_from_remote_address(remote)
            if peer_ip in ip_to_node_id:
                peer_nid = ip_to_node_id[peer_ip]
                edge = (min(nid, peer_nid), max(nid, peer_nid))
                all_edges.add(edge)

    return {
        'timestamp': timestamp,
        'edges': list(all_edges),
        'peer_counts': node_peer_counts,
        'n_nodes': len(containers),
        'n_edges': len(all_edges),
        'failed_nodes': failed_nodes,
    }


def snapshot_to_adjacency(snapshot, containers):
    """将快照转换为邻接矩阵。"""
    node_ids = sorted(containers.keys())
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
    A = np.zeros((n, n), dtype=np.float64)
    for (i_id, j_id) in snapshot['edges']:
        if i_id in id_to_idx and j_id in id_to_idx:
            i = id_to_idx[i_id]
            j = id_to_idx[j_id]
            A[i, j] = 1.0
            A[j, i] = 1.0
    return A, node_ids


def save_snapshot(snapshot, output_dir, idx=0):
    """保存快照到文件。"""
    os.makedirs(output_dir, exist_ok=True)
    ts = snapshot['timestamp'].replace(':', '-').replace('+', '_')
    fname = f'snapshot_{idx:04d}_{ts}.json'
    path = os.path.join(output_dir, fname)
    with open(path, 'w') as f:
        json.dump(snapshot, f, indent=2, default=str)
    return path


def collect_multiple_snapshots(n_snapshots=30, interval_seconds=300, output_dir=None):
    """采集多个时序拓扑快照。"""
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')

    print("Discovering containers...")
    containers = discover_containers()
    print(f"Found {len(containers)} Ethereum POS nodes")

    node_ids = sorted(containers.keys())
    print(f"Node IDs: {node_ids[0]}-{node_ids[-1]}")

    first_container = containers[node_ids[0]]['name']
    block = get_block_number(first_container)
    print(f"Current block height: {block}")

    snapshots = []
    matrices = []

    for i in range(n_snapshots):
        print(f"\n--- Snapshot {i+1}/{n_snapshots} ---")
        t0 = time.time()
        snapshot = collect_topology_snapshot(containers)
        t1 = time.time()

        A, _ = snapshot_to_adjacency(snapshot, containers)
        matrices.append(A)
        snapshots.append(snapshot)

        path = save_snapshot(snapshot, output_dir, idx=i)
        degrees = np.sum(A > 0, axis=1)
        print(f"  Time: {snapshot['timestamp']}")
        print(f"  Nodes: {snapshot['n_nodes']}, Edges: {snapshot['n_edges']}")
        print(f"  Mean degree: {np.mean(degrees):.1f}, Max: {np.max(degrees)}, Min: {np.min(degrees)}")
        print(f"  Failed nodes: {len(snapshot['failed_nodes'])}")
        print(f"  Collection took {t1-t0:.1f}s, saved to {path}")

        if i < n_snapshots - 1:
            wait = max(0, interval_seconds - (t1 - t0))
            if wait > 0:
                print(f"  Waiting {wait:.0f}s for next snapshot...")
                time.sleep(wait)

    np.savez(os.path.join(output_dir, 'adjacency_matrices.npz'),
             matrices=np.array(matrices),
             node_ids=np.array(node_ids))
    print(f"\nAll {n_snapshots} snapshots collected and saved to {output_dir}")

    return matrices, snapshots, containers


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', type=int, default=1, help='Number of snapshots')
    parser.add_argument('--interval', type=int, default=300, help='Interval in seconds')
    parser.add_argument('--output', type=str, default=None, help='Output directory')
    args = parser.parse_args()

    collect_multiple_snapshots(args.snapshots, args.interval, args.output)
