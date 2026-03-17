#!/usr/bin/env python3
"""
波卡100节点私有链全量拓扑采集器。
通过 Substrate RPC system_peers 接口采集。
"""

import sys, os, json, time, re
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import get_ssh_client

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_dot')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def discover_polkadot_containers(ssh):
    """发现所有波卡节点容器及其 IP。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}" | grep polkadot | sort', timeout=15)
    output = stdout.read().decode()
    containers = {}
    idx = 0
    for name in sorted(output.strip().split('\n')):
        name = name.strip()
        if not name:
            continue
        _, stdout2, _ = ssh.exec_command(
            f'docker inspect -f "{{{{.NetworkSettings.Networks}}}}" {name} 2>/dev/null '
            f'| grep -oP "\\d+\\.\\d+\\.\\d+\\.\\d+" | head -1',
            timeout=10
        )
        ip = stdout2.read().decode().strip()
        if ip:
            containers[idx] = {'name': name, 'ip': ip}
            idx += 1
    return containers


def discover_polkadot_containers_simple(ssh):
    """简单发现方式：列出所有波卡节点容器。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}" | grep polkadot | sort', timeout=15)
    output = stdout.read().decode()
    containers = {}
    idx = 0
    for name in sorted(output.strip().split('\n')):
        name = name.strip()
        if not name:
            continue
        containers[idx] = {'name': name, 'ip': ''}
        idx += 1
    return containers


def get_system_peers(ssh, container_name):
    """获取波卡节点的 peers（通过 system_peers RPC）。"""
    cmd = (f"docker exec {container_name} curl -sf -m 10 -X POST http://localhost:9933 "
           f"-H 'Content-Type: application/json' "
           f"""-d '{{"jsonrpc":"2.0","method":"system_peers","params":[],"id":1}}' 2>/dev/null""")
    try:
        _, stdout, _ = ssh.exec_command(cmd, timeout=15)
        output = stdout.read().decode('utf-8', errors='replace')
        if output.strip():
            data = json.loads(output)
            return data.get('result', [])
    except Exception:
        pass
    return None


def collect_snapshot(ssh_unused, containers, idx):
    """采集一个拓扑快照（每批次重新建立 SSH 连接避免通道耗尽）。"""
    timestamp = datetime.now(timezone.utc).isoformat()

    peer_id_to_idx = {}
    all_edges = set()
    peer_counts = {}
    failed = []

    node_ids_list = sorted(containers.keys())
    BATCH = 20

    for batch_start in range(0, len(node_ids_list), BATCH):
        batch = node_ids_list[batch_start:batch_start + BATCH]
        ssh = get_ssh_client()
        try:
            for nid in batch:
                cname = containers[nid]['name']
                cmd = (f"docker exec {cname} curl -sf -m 10 -X POST http://localhost:9933 "
                       f"-H 'Content-Type: application/json' "
                       f"""-d '{{"jsonrpc":"2.0","method":"system_localPeerId","params":[],"id":1}}' 2>/dev/null""")
                try:
                    _, stdout, _ = ssh.exec_command(cmd, timeout=15)
                    output = stdout.read().decode().strip()
                    if output:
                        data = json.loads(output)
                        local_id = data.get('result', '')
                        if local_id:
                            peer_id_to_idx[local_id] = nid
                except Exception:
                    pass
        finally:
            ssh.close()

    for batch_start in range(0, len(node_ids_list), BATCH):
        batch = node_ids_list[batch_start:batch_start + BATCH]
        ssh = get_ssh_client()
        try:
            for nid in batch:
                cname = containers[nid]['name']
                peers = get_system_peers(ssh, cname)
                if peers is None:
                    failed.append(nid)
                    peer_counts[nid] = 0
                    continue

                peer_counts[nid] = len(peers)
                for p in peers:
                    peer_id = p.get('peerId', '')
                    if peer_id in peer_id_to_idx:
                        peer_nid = peer_id_to_idx[peer_id]
                        edge = (min(nid, peer_nid), max(nid, peer_nid))
                        all_edges.add(edge)
        finally:
            ssh.close()

    n = len(containers)
    node_ids = sorted(containers.keys())
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    A = np.zeros((n, n), dtype=np.float64)
    for (i_id, j_id) in all_edges:
        if i_id in id_to_idx and j_id in id_to_idx:
            A[id_to_idx[i_id], id_to_idx[j_id]] = 1.0
            A[id_to_idx[j_id], id_to_idx[i_id]] = 1.0

    snapshot = {
        'idx': idx,
        'timestamp': timestamp,
        'edges': sorted(list(all_edges)),
        'peer_counts': {str(k): v for k, v in peer_counts.items()},
        'n_nodes': n,
        'n_edges': len(all_edges),
        'failed_nodes': failed,
    }
    return A, snapshot


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', type=int, default=40)
    parser.add_argument('--interval', type=int, default=180)
    args = parser.parse_args()

    N = args.snapshots
    interval = args.interval

    print(f"{'='*70}")
    print(f"TIFS Full Dataset Collection: Polkadot Private Chain")
    print(f"Snapshots: {N}, Interval: {interval}s (~{N*interval/60:.0f} min total)")
    print(f"{'='*70}")

    ssh = get_ssh_client()
    containers = discover_polkadot_containers_simple(ssh)
    n = len(containers)
    print(f"Found {n} Polkadot nodes")
    if n > 0:
        names = [containers[i]['name'] for i in sorted(containers.keys())[:5]]
        print(f"Sample: {names}")
    ssh.close()

    if n == 0:
        print("ERROR: No Polkadot containers found!")
        return

    matrices = []
    snapshots_meta = []
    edge_counts = []

    for i in range(N):
        t0 = time.time()
        ssh = get_ssh_client()
        A, snapshot = collect_snapshot(ssh, containers, i)

        if i > 0:
            diff = int(np.sum(np.abs(A - matrices[-1])) / 2)
            snapshot['edge_diff_from_prev'] = diff
        else:
            snapshot['edge_diff_from_prev'] = 0

        ssh.close()
        matrices.append(A)
        snapshots_meta.append(snapshot)
        edge_counts.append(snapshot['n_edges'])

        degrees = np.sum(A > 0, axis=1)
        elapsed = time.time() - t0
        ts_short = snapshot['timestamp'][11:19]
        print(f"  [{i+1:3d}/{N}] {ts_short} | "
              f"edges={snapshot['n_edges']:5d} | "
              f"deg={np.mean(degrees):5.1f}±{np.std(degrees):4.1f} | "
              f"Δedge={snapshot['edge_diff_from_prev']:3d} | "
              f"fail={len(snapshot['failed_nodes'])} | "
              f"{elapsed:.1f}s")

        snap_path = os.path.join(OUTPUT_DIR, f'snapshot_{i:04d}.json')
        with open(snap_path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)

        if i < N - 1:
            wait = max(0, interval - elapsed)
            if wait > 0:
                time.sleep(wait)

    node_ids = sorted(containers.keys())
    np.savez(os.path.join(OUTPUT_DIR, 'adjacency_matrices_full.npz'),
             matrices=np.array(matrices),
             node_ids=np.array(node_ids))

    import pandas as pd
    rows = []
    for snap in snapshots_meta:
        for (src, dst) in snap['edges']:
            rows.append({'snapshot': snap['idx'], 'timestamp': snap['timestamp'],
                         'src': src, 'dst': dst})
    pd.DataFrame(rows).to_csv(
        os.path.join(OUTPUT_DIR, 'edges_timeseries_full.csv'), index=False)

    summary = {
        'total_snapshots': N,
        'interval_seconds': interval,
        'n_nodes': n,
        'edge_counts': edge_counts,
        'start_time': snapshots_meta[0]['timestamp'],
        'end_time': snapshots_meta[-1]['timestamp'],
        'total_unique_edges': int(len(set().union(
            *[set(map(tuple, s['edges'])) for s in snapshots_meta]
        ))),
        'edge_changes': [s['edge_diff_from_prev'] for s in snapshots_meta],
    }
    with open(os.path.join(OUTPUT_DIR, 'collection_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Collection Complete!")
    print(f"  Snapshots: {N}, Nodes: {n}")
    print(f"  Edge count range: {min(edge_counts)}-{max(edge_counts)}")
    print(f"  Total unique edges: {summary['total_unique_edges']}")
    print(f"  Data saved to: {OUTPUT_DIR}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
