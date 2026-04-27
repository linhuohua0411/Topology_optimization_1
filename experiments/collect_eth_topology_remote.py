#!/usr/bin/env python3
"""
远程采集以太坊100节点私有链拓扑：通过 paramiko 在服务器上执行 docker exec + admin_peers。
"""

import sys
import os
import json
import time
import re
import numpy as np
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import get_ssh_client, SERVER_HOST

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def discover_containers_remote(ssh):
    """远程发现以太坊 POS 容器。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}"', timeout=15)
    output = stdout.read().decode()
    containers = {}
    for name in output.strip().split('\n'):
        match = re.match(r'as\d+h-Ethereum-POS-(\d+)-([\d.]+)', name.strip())
        if match:
            node_id = int(match.group(1))
            ip = match.group(2)
            containers[node_id] = {'name': name.strip(), 'ip': ip}
    return containers


def get_peers_remote(ssh, container_name):
    """远程获取节点的 peers。"""
    cmd = (f'docker exec {container_name} curl -sf -X POST http://localhost:8545 '
           f'-H "Content-Type: application/json" '
           f'-d \'{{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}}\' 2>/dev/null')
    try:
        _, stdout, _ = ssh.exec_command(cmd, timeout=15)
        output = stdout.read().decode()
        if output:
            data = json.loads(output)
            return data.get('result', [])
    except Exception:
        pass
    return []


def get_block_number_remote(ssh, container_name):
    """远程获取区块高度。"""
    cmd = (f'docker exec {container_name} curl -sf -X POST http://localhost:8545 '
           f'-H "Content-Type: application/json" '
           f'-d \'{{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}}\' 2>/dev/null')
    try:
        _, stdout, _ = ssh.exec_command(cmd, timeout=10)
        output = stdout.read().decode()
        if output:
            data = json.loads(output)
            return int(data.get('result', '0x0'), 16)
    except Exception:
        pass
    return -1


def collect_single_snapshot(containers, snapshot_idx=0):
    """采集一次全网拓扑快照。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    ip_to_node_id = {info['ip']: nid for nid, info in containers.items()}

    all_edges = set()
    node_peer_counts = {}
    failed_nodes = []

    ssh = get_ssh_client()
    try:
        for nid in sorted(containers.keys()):
            cname = containers[nid]['name']
            peers = get_peers_remote(ssh, cname)
            if peers is None:
                peers = []
                failed_nodes.append(nid)

            node_peer_counts[nid] = len(peers)

            for p in peers:
                remote = p.get('network', {}).get('remoteAddress', '')
                peer_ip = remote.rsplit(':', 1)[0] if ':' in remote else remote
                if peer_ip in ip_to_node_id:
                    peer_nid = ip_to_node_id[peer_ip]
                    edge = (min(nid, peer_nid), max(nid, peer_nid))
                    all_edges.add(edge)
    finally:
        ssh.close()

    return {
        'timestamp': timestamp,
        'edges': sorted(list(all_edges)),
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


def main():
    """采集多个拓扑快照。"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', type=int, default=5)
    parser.add_argument('--interval', type=int, default=120)
    args = parser.parse_args()

    print(f"=== Ethereum Private Chain Topology Collector ===")
    print(f"Snapshots: {args.snapshots}, Interval: {args.interval}s")

    ssh = get_ssh_client()
    containers = discover_containers_remote(ssh)
    node_ids = sorted(containers.keys())
    print(f"Found {len(containers)} Ethereum POS nodes (IDs: {node_ids[0]}-{node_ids[-1]})")

    block = get_block_number_remote(ssh, containers[node_ids[0]]['name'])
    print(f"Current block height: {block}")
    ssh.close()

    matrices = []
    snapshots = []

    for i in range(args.snapshots):
        print(f"\n--- Snapshot {i+1}/{args.snapshots} ---")
        t0 = time.time()
        snapshot = collect_single_snapshot(containers, i)
        t1 = time.time()

        A, _ = snapshot_to_adjacency(snapshot, containers)
        matrices.append(A)
        snapshots.append(snapshot)

        degrees = np.sum(A > 0, axis=1)
        print(f"  Time: {snapshot['timestamp']}")
        print(f"  Nodes: {snapshot['n_nodes']}, Edges: {snapshot['n_edges']}")
        print(f"  Mean degree: {np.mean(degrees):.1f}, Max: {int(np.max(degrees))}, "
              f"Min: {int(np.min(degrees))}")
        print(f"  Failed: {len(snapshot['failed_nodes'])}")
        print(f"  Collection took {t1-t0:.1f}s")

        ts = snapshot['timestamp'].replace(':', '-').replace('+', '_')
        snap_path = os.path.join(OUTPUT_DIR, f'snapshot_{i:04d}_{ts}.json')
        with open(snap_path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)

        if i < args.snapshots - 1:
            wait = max(0, args.interval - (t1 - t0))
            if wait > 0:
                print(f"  Waiting {wait:.0f}s...")
                time.sleep(wait)

    np.savez(os.path.join(OUTPUT_DIR, 'adjacency_matrices.npz'),
             matrices=np.array(matrices),
             node_ids=np.array(node_ids))

    edges_data = []
    for i, snap in enumerate(snapshots):
        for (src, dst) in snap['edges']:
            edges_data.append({'snapshot': i, 'timestamp': snap['timestamp'],
                               'src': src, 'dst': dst})
    import pandas as pd
    pd.DataFrame(edges_data).to_csv(
        os.path.join(OUTPUT_DIR, 'edges_timeseries.csv'), index=False)

    print(f"\n=== Collection complete ===")
    print(f"Matrices shape: ({len(matrices)}, {matrices[0].shape[0]}, {matrices[0].shape[1]})")
    print(f"Data saved to: {OUTPUT_DIR}")

    return matrices, snapshots, containers


if __name__ == '__main__':
    main()
