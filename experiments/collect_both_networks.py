#!/usr/bin/env python3
"""
统一拓扑采集器：同时采集以太坊(108节点)和波卡(100节点)拓扑。
以太坊使用 admin_peers RPC，波卡使用 ss(TCP连接表) + P2P端口30333。
"""

import sys, os, json, time, re
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import get_ssh_client

ETH_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')
DOT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_dot')
os.makedirs(ETH_DIR, exist_ok=True)
os.makedirs(DOT_DIR, exist_ok=True)

BATCH = 20


def discover_eth_containers(ssh):
    """发现以太坊节点容器。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}" | grep Ethereum-POS | sort', timeout=15)
    containers = {}
    for name in stdout.read().decode().strip().split('\n'):
        m = re.match(r'as\d+h-Ethereum-POS-(\d+)-([\d.]+)', name.strip())
        if m:
            containers[int(m.group(1))] = {'name': name.strip(), 'ip': m.group(2)}
    return containers


def discover_dot_containers(ssh):
    """发现波卡节点容器及其 IP。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}" | grep polkadot | sort', timeout=15)
    names = [n.strip() for n in stdout.read().decode().strip().split('\n') if n.strip()]
    containers = {}
    for idx, name in enumerate(sorted(names)):
        _, stdout2, _ = ssh.exec_command(
            f'docker exec {name} hostname -I 2>/dev/null', timeout=5)
        ip = stdout2.read().decode().strip().split()[0] if stdout2 else ''
        containers[idx] = {'name': name, 'ip': ip}
    return containers


def collect_eth_snapshot(containers, snapshot_idx):
    """采集以太坊拓扑快照。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    ip_to_nid = {info['ip']: nid for nid, info in containers.items()}
    all_edges = set()
    peer_counts = {}
    failed = []
    node_ids = sorted(containers.keys())

    for batch_start in range(0, len(node_ids), BATCH):
        batch = node_ids[batch_start:batch_start + BATCH]
        ssh = get_ssh_client()
        try:
            for nid in batch:
                cname = containers[nid]['name']
                cmd = (f"docker exec {cname} curl -sf -m 5 -X POST http://localhost:8545 "
                       f"-H 'Content-Type: application/json' "
                       f"""-d '{{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}}' 2>/dev/null""")
                try:
                    _, stdout, _ = ssh.exec_command(cmd, timeout=10)
                    output = stdout.read().decode('utf-8', errors='replace').strip()
                    if output:
                        data = json.loads(output)
                        peers = data.get('result', [])
                        peer_counts[nid] = len(peers)
                        for p in peers:
                            remote = p.get('network', {}).get('remoteAddress', '')
                            peer_ip = remote.rsplit(':', 1)[0] if ':' in remote else remote
                            if peer_ip in ip_to_nid:
                                pnid = ip_to_nid[peer_ip]
                                all_edges.add((min(nid, pnid), max(nid, pnid)))
                    else:
                        failed.append(nid)
                except Exception:
                    failed.append(nid)
        finally:
            ssh.close()

    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    A = np.zeros((n, n), dtype=np.float64)
    for (i_id, j_id) in all_edges:
        if i_id in id_to_idx and j_id in id_to_idx:
            A[id_to_idx[i_id], id_to_idx[j_id]] = 1.0
            A[id_to_idx[j_id], id_to_idx[i_id]] = 1.0

    return A, {
        'idx': snapshot_idx, 'timestamp': timestamp, 'network': 'ethereum',
        'edges': sorted(list(all_edges)),
        'peer_counts': {str(k): v for k, v in peer_counts.items()},
        'n_nodes': n, 'n_edges': len(all_edges), 'failed_nodes': failed,
    }


def collect_dot_snapshot(containers, snapshot_idx):
    """采集波卡拓扑快照（通过 TCP 连接表）。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    ip_to_nid = {info['ip']: nid for nid, info in containers.items()}
    all_edges = set()
    peer_counts = {}
    failed = []
    node_ids = sorted(containers.keys())

    for batch_start in range(0, len(node_ids), BATCH):
        batch = node_ids[batch_start:batch_start + BATCH]
        ssh = get_ssh_client()
        try:
            for nid in batch:
                cname = containers[nid]['name']
                my_ip = containers[nid]['ip']
                cmd = f"docker exec {cname} ss -tn state established 2>/dev/null | grep 30333"
                try:
                    _, stdout, _ = ssh.exec_command(cmd, timeout=10)
                    output = stdout.read().decode('utf-8', errors='replace').strip()
                    peers_found = set()
                    for line in output.split('\n'):
                        if not line.strip():
                            continue
                        parts = line.split()
                        if len(parts) >= 4:
                            local = parts[3]
                            remote = parts[4] if len(parts) > 4 else ''
                            for addr in [local, remote]:
                                ip_part = addr.rsplit(':', 1)[0] if ':' in addr else addr
                                if ip_part != my_ip and ip_part in ip_to_nid:
                                    peer_nid = ip_to_nid[ip_part]
                                    if peer_nid != nid:
                                        peers_found.add(peer_nid)
                                        all_edges.add((min(nid, peer_nid), max(nid, peer_nid)))
                    peer_counts[nid] = len(peers_found)
                except Exception:
                    failed.append(nid)
        finally:
            ssh.close()

    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    A = np.zeros((n, n), dtype=np.float64)
    for (i_id, j_id) in all_edges:
        if i_id in id_to_idx and j_id in id_to_idx:
            A[id_to_idx[i_id], id_to_idx[j_id]] = 1.0
            A[id_to_idx[j_id], id_to_idx[i_id]] = 1.0

    return A, {
        'idx': snapshot_idx, 'timestamp': timestamp, 'network': 'polkadot',
        'edges': sorted(list(all_edges)),
        'peer_counts': {str(k): v for k, v in peer_counts.items()},
        'n_nodes': n, 'n_edges': len(all_edges), 'failed_nodes': failed,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', type=int, default=40)
    parser.add_argument('--interval', type=int, default=300)
    args = parser.parse_args()

    N = args.snapshots
    interval = args.interval

    print(f"{'='*70}")
    print(f"TIFS Full Dataset: Ethereum + Polkadot Dual-Network Collection")
    print(f"Snapshots: {N}, Interval: {interval}s (~{N*interval/60:.0f} min)")
    print(f"{'='*70}")

    ssh = get_ssh_client()
    eth_containers = discover_eth_containers(ssh)
    print(f"ETH: {len(eth_containers)} nodes (IDs {min(eth_containers)}–{max(eth_containers)})")
    ssh.close()

    ssh = get_ssh_client()
    dot_containers = discover_dot_containers(ssh)
    print(f"DOT: {len(dot_containers)} nodes")
    ssh.close()

    eth_matrices, dot_matrices = [], []
    eth_snaps, dot_snaps = [], []

    for i in range(N):
        t0 = time.time()
        print(f"\n--- Snapshot {i+1}/{N} ---")

        A_eth, s_eth = collect_eth_snapshot(eth_containers, i)
        eth_matrices.append(A_eth)
        eth_snaps.append(s_eth)
        deg_eth = np.sum(A_eth > 0, axis=1)

        A_dot, s_dot = collect_dot_snapshot(dot_containers, i)
        dot_matrices.append(A_dot)
        dot_snaps.append(s_dot)
        deg_dot = np.sum(A_dot > 0, axis=1)

        if i > 0:
            eth_diff = int(np.sum(np.abs(A_eth - eth_matrices[i-1])) / 2)
            dot_diff = int(np.sum(np.abs(A_dot - dot_matrices[i-1])) / 2)
        else:
            eth_diff = dot_diff = 0
        s_eth['edge_diff'] = eth_diff
        s_dot['edge_diff'] = dot_diff

        elapsed = time.time() - t0
        ts = s_eth['timestamp'][11:19]
        print(f"  ETH: edges={s_eth['n_edges']:5d} deg={np.mean(deg_eth):5.1f}±{np.std(deg_eth):4.1f} Δ={eth_diff:3d} fail={len(s_eth['failed_nodes'])}")
        print(f"  DOT: edges={s_dot['n_edges']:5d} deg={np.mean(deg_dot):5.1f}±{np.std(deg_dot):4.1f} Δ={dot_diff:3d} fail={len(s_dot['failed_nodes'])}")
        print(f"  [{ts}] {elapsed:.1f}s")

        with open(os.path.join(ETH_DIR, f'snapshot_{i:04d}.json'), 'w') as f:
            json.dump(s_eth, f, indent=2, default=str)
        with open(os.path.join(DOT_DIR, f'snapshot_{i:04d}.json'), 'w') as f:
            json.dump(s_dot, f, indent=2, default=str)

        if i < N - 1:
            wait = max(0, interval - elapsed)
            if wait > 0:
                time.sleep(wait)

    eth_node_ids = sorted(eth_containers.keys())
    dot_node_ids = sorted(dot_containers.keys())

    np.savez(os.path.join(ETH_DIR, 'adjacency_matrices_full.npz'),
             matrices=np.array(eth_matrices), node_ids=np.array(eth_node_ids))
    np.savez(os.path.join(DOT_DIR, 'adjacency_matrices_full.npz'),
             matrices=np.array(dot_matrices), node_ids=np.array(dot_node_ids))

    import pandas as pd
    for snaps, odir, name in [(eth_snaps, ETH_DIR, 'eth'), (dot_snaps, DOT_DIR, 'dot')]:
        rows = []
        for s in snaps:
            for (src, dst) in s['edges']:
                rows.append({'snapshot': s['idx'], 'timestamp': s['timestamp'], 'src': src, 'dst': dst})
        pd.DataFrame(rows).to_csv(os.path.join(odir, 'edges_timeseries_full.csv'), index=False)

        summary = {
            'network': name, 'total_snapshots': N, 'interval_seconds': interval,
            'n_nodes': snaps[0]['n_nodes'],
            'edge_counts': [s['n_edges'] for s in snaps],
            'start_time': snaps[0]['timestamp'], 'end_time': snaps[-1]['timestamp'],
            'edge_changes': [s.get('edge_diff', 0) for s in snaps],
        }
        with open(os.path.join(odir, 'collection_summary.json'), 'w') as f:
            json.dump(summary, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Collection Complete!")
    print(f"  ETH: {len(eth_matrices)} snapshots, {eth_matrices[0].shape[0]} nodes, "
          f"edge range {min(s['n_edges'] for s in eth_snaps)}-{max(s['n_edges'] for s in eth_snaps)}")
    print(f"  DOT: {len(dot_matrices)} snapshots, {dot_matrices[0].shape[0]} nodes, "
          f"edge range {min(s['n_edges'] for s in dot_snaps)}-{max(s['n_edges'] for s in dot_snaps)}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
