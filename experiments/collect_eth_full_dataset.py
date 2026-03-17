#!/usr/bin/env python3
"""
以太坊私有链全量拓扑采集器（TIFS级别数据集）。
目标：采集 40 个快照，每 3 分钟一次，覆盖 ~2 小时。
使用批量 SSH 命令加速采集。
"""

import sys, os, json, time, re
import numpy as np
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from ssh_helper import get_ssh_client

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'private_eth')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_batch_peers_script(containers):
    """构建一次性获取所有节点 peers 的 shell 脚本。"""
    lines = ['#!/bin/bash']
    for nid in sorted(containers.keys()):
        cname = containers[nid]['name']
        lines.append(
            f'echo "NODE_{nid}_START"'
            f' && docker exec {cname} curl -sf -m 5 -X POST http://localhost:8545'
            f' -H "Content-Type: application/json"'
            f' -d \'{{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}}\''
            f' 2>/dev/null'
            f' && echo "" && echo "NODE_{nid}_END"'
        )
    return '\n'.join(lines)


def parse_batch_output(output, containers):
    """解析批量采集的输出。"""
    ip_to_nid = {info['ip']: nid for nid, info in containers.items()}
    all_edges = set()
    peer_counts = {}
    failed = []

    current_nid = None
    current_json = ''

    for line in output.split('\n'):
        line = line.strip()
        m = re.match(r'NODE_(\d+)_START', line)
        if m:
            current_nid = int(m.group(1))
            current_json = ''
            continue
        m2 = re.match(r'NODE_(\d+)_END', line)
        if m2:
            nid = int(m2.group(1))
            if current_json:
                try:
                    data = json.loads(current_json)
                    peers = data.get('result', [])
                    peer_counts[nid] = len(peers)
                    for p in peers:
                        remote = p.get('network', {}).get('remoteAddress', '')
                        peer_ip = remote.rsplit(':', 1)[0] if ':' in remote else remote
                        if peer_ip in ip_to_nid:
                            peer_nid = ip_to_nid[peer_ip]
                            all_edges.add((min(nid, peer_nid), max(nid, peer_nid)))
                except (json.JSONDecodeError, KeyError):
                    failed.append(nid)
            else:
                failed.append(nid)
            current_nid = None
            current_json = ''
            continue
        if current_nid is not None:
            current_json += line

    return all_edges, peer_counts, failed


def discover_containers(ssh):
    """发现容器。"""
    _, stdout, _ = ssh.exec_command('docker ps --format "{{.Names}}"', timeout=15)
    output = stdout.read().decode()
    containers = {}
    for name in output.strip().split('\n'):
        m = re.match(r'as\d+h-Ethereum-POS-(\d+)-([\d.]+)', name.strip())
        if m:
            containers[int(m.group(1))] = {'name': name.strip(), 'ip': m.group(2)}
    return containers


def collect_snapshot_fast(ssh, containers, idx):
    """快速采集一个拓扑快照（复用同一 SSH 连接逐节点查询）。"""
    timestamp = datetime.now(timezone.utc).isoformat()
    ip_to_nid = {info['ip']: nid for nid, info in containers.items()}
    all_edges = set()
    peer_counts = {}
    failed = []

    for nid in sorted(containers.keys()):
        cname = containers[nid]['name']
        cmd = (f"docker exec {cname} curl -sf -m 5 -X POST http://localhost:8545 "
               f"-H 'Content-Type: application/json' "
               f"""-d '{{"jsonrpc":"2.0","method":"admin_peers","params":[],"id":1}}' 2>/dev/null""")
        try:
            _, stdout, _ = ssh.exec_command(cmd, timeout=10)
            output = stdout.read().decode('utf-8', errors='replace')
            if output.strip():
                data = json.loads(output)
                peers = data.get('result', [])
                peer_counts[nid] = len(peers)
                for p in peers:
                    remote = p.get('network', {}).get('remoteAddress', '')
                    peer_ip = remote.rsplit(':', 1)[0] if ':' in remote else remote
                    if peer_ip in ip_to_nid:
                        peer_nid = ip_to_nid[peer_ip]
                        all_edges.add((min(nid, peer_nid), max(nid, peer_nid)))
            else:
                failed.append(nid)
        except Exception:
            failed.append(nid)

    node_ids = sorted(containers.keys())
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)
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


def get_block_number(ssh, container_name):
    """获取区块高度。"""
    cmd = (f'docker exec {container_name} curl -sf -m 5 -X POST http://localhost:8545 '
           f'-H "Content-Type: application/json" '
           f"""-d '{{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}}' 2>/dev/null""")
    try:
        _, stdout, _ = ssh.exec_command(cmd, timeout=10)
        data = json.loads(stdout.read().decode())
        return int(data.get('result', '0x0'), 16)
    except Exception:
        return -1


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshots', type=int, default=40)
    parser.add_argument('--interval', type=int, default=180)
    args = parser.parse_args()

    N = args.snapshots
    interval = args.interval

    print(f"{'='*70}")
    print(f"TIFS Full Dataset Collection: Ethereum Private Chain")
    print(f"Snapshots: {N}, Interval: {interval}s (~{N*interval/60:.0f} min total)")
    print(f"{'='*70}")

    ssh = get_ssh_client()
    containers = discover_containers(ssh)
    node_ids = sorted(containers.keys())
    n = len(node_ids)
    print(f"Found {n} Ethereum POS nodes (IDs: {node_ids[0]}-{node_ids[-1]})")

    block0 = get_block_number(ssh, containers[node_ids[0]]['name'])
    print(f"Starting block height: {block0}")
    ssh.close()

    matrices = []
    snapshots_meta = []
    edge_counts_over_time = []

    for i in range(N):
        t0 = time.time()
        ssh = get_ssh_client()

        A, snapshot = collect_snapshot_fast(ssh, containers, i)

        if i == 0 or (i + 1) == N:
            block = get_block_number(ssh, containers[node_ids[0]]['name'])
            snapshot['block_height'] = block
        ssh.close()

        matrices.append(A)
        snapshots_meta.append(snapshot)

        degrees = np.sum(A > 0, axis=1)
        elapsed = time.time() - t0
        edge_counts_over_time.append(snapshot['n_edges'])

        if i > 0:
            A_prev = matrices[i - 1]
            diff = np.sum(np.abs(A - A_prev)) / 2
            snapshot['edge_diff_from_prev'] = int(diff)
        else:
            snapshot['edge_diff_from_prev'] = 0

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

    np.savez(os.path.join(OUTPUT_DIR, 'adjacency_matrices_full.npz'),
             matrices=np.array(matrices),
             node_ids=np.array(node_ids))

    import pandas as pd
    rows = []
    for snap in snapshots_meta:
        for (src, dst) in snap['edges']:
            rows.append({
                'snapshot': snap['idx'], 'timestamp': snap['timestamp'],
                'src': src, 'dst': dst
            })
    pd.DataFrame(rows).to_csv(
        os.path.join(OUTPUT_DIR, 'edges_timeseries_full.csv'), index=False)

    summary = {
        'total_snapshots': N,
        'interval_seconds': interval,
        'n_nodes': n,
        'node_ids': node_ids,
        'edge_counts': edge_counts_over_time,
        'start_time': snapshots_meta[0]['timestamp'],
        'end_time': snapshots_meta[-1]['timestamp'],
        'start_block': snapshots_meta[0].get('block_height', -1),
        'end_block': snapshots_meta[-1].get('block_height', -1),
        'total_unique_edges': int(len(set().union(
            *[set(map(tuple, s['edges'])) for s in snapshots_meta]
        ))),
        'edge_changes': [s['edge_diff_from_prev'] for s in snapshots_meta],
    }
    with open(os.path.join(OUTPUT_DIR, 'collection_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Collection Complete!")
    print(f"  Snapshots: {N}")
    print(f"  Duration: {snapshots_meta[0]['timestamp']} -> {snapshots_meta[-1]['timestamp']}")
    print(f"  Blocks: {summary['start_block']} -> {summary['end_block']}")
    print(f"  Edge count range: {min(edge_counts_over_time)}-{max(edge_counts_over_time)}")
    print(f"  Total unique edges seen: {summary['total_unique_edges']}")
    print(f"  Total edge changes: {sum(summary['edge_changes'])}")
    print(f"  Data saved to: {OUTPUT_DIR}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
