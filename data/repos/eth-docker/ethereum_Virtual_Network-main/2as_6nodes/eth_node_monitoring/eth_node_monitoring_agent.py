#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eth_node_monitoring_agent.py — 以太坊节点内置监控 Agent

【设计原则】
- 部署在每一个以太坊节点容器内（与 Geth + Lighthouse 共存）
- 纯 Python 标准库，无需额外 pip install
- 采集本节点的执行层（Geth）和共识层（Lighthouse）P2P 状态
- 定期向中央收集器（eth_node_cleaner:8888）上报数据和心跳
- 节点下线时 Agent 随之停止，中央收集器检测心跳超时后
  触发 Neo4j 拓扑数据清理，保证拓扑图实时准确

【采集内容】
  Geth    localhost:8545  → admin_peers, admin_nodeInfo, eth_blockNumber
  Lighthouse <NODE_IP>:8000 → /eth/v1/node/peers, /node/identity, /node/syncing
                              /eth/v1/beacon/states/head/validators (有验证者时)

【触发离线清理的双重机制】
  1. Agent 心跳停止 → eth_node_cleaner._heartbeat_checker 60s 超时 → 清理 Neo4j
  2. eth_node_cleaner.EthNetworkTopologyManager ping 检测每6s一次 → 18s 判定下线
  两个机制互为备份，保证拓扑图与真实网络一致
"""

import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ─── 日志配置 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ETH-AGENT] %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("eth_node_monitoring_agent")


# ─── 配置（全部来自环境变量，容器化友好） ──────────────────────

CENTRAL_COLLECTOR_URL = os.getenv("CENTRAL_COLLECTOR_URL", "http://eth_node_cleaner:8888")
COLLECT_INTERVAL      = int(os.getenv("NODE_COLLECT_INTERVAL", "30"))
HEARTBEAT_INTERVAL    = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
GETH_RPC_PORT         = int(os.getenv("GETH_RPC_PORT", "8545"))
LIGHTHOUSE_PORT       = int(os.getenv("LIGHTHOUSE_PORT", "8000"))
HAS_VALIDATOR         = os.getenv("HAS_VALIDATOR", "true").lower() == "true"
AGENT_VERSION         = "1.0.0"

# CONTAINER_NAME 由 docker-compose 注入，格式: as151h-Ethereum-POS-3-10.151.0.73
CONTAINER_NAME = os.getenv("CONTAINER_NAME", socket.gethostname())
# NODE_IP 可以显式设置，也可以从 CONTAINER_NAME 自动解析，或从网卡获取
NODE_IP = os.getenv("NODE_IP", "")


# ─── IP 自动检测 ───────────────────────────────────────────────

def detect_node_ip() -> str:
    """
    按优先级检测本节点的 IP 地址（动态读取环境变量）：
    1. 环境变量 NODE_IP
    2. 从 CONTAINER_NAME 解析（格式末尾含 IP）
    3. 从 net0 网卡读取
    4. fallback: 127.0.0.1
    """
    # 1. 显式设置（动态读取，支持运行时修改）
    env_ip = os.getenv("NODE_IP", "")
    if env_ip:
        return env_ip

    # 2. 从容器名解析（e.g. as151h-Ethereum-POS-3-10.151.0.73）
    container_name = os.getenv("CONTAINER_NAME", socket.gethostname())
    m = re.search(r'(\d+\.\d+\.\d+\.\d+)$', container_name)
    if m:
        return m.group(1)

    # 3. 从 net0 网卡（以太坊节点都在 net0 上）
    try:
        out = subprocess.check_output(
            ["ip", "-4", "addr", "show", "net0"],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode()
        m2 = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)/', out)
        if m2:
            return m2.group(1)
    except Exception:
        pass

    # 4. 兜底
    return "127.0.0.1"


# ─── HTTP 工具（纯 stdlib） ────────────────────────────────────

def http_post(url: str, data: dict, timeout: int = 8) -> bool:
    """向 central_collector 发 POST 请求，返回是否成功"""
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"POST 失败 {url}: {e}")
        return False


def http_get(url: str, timeout: int = 5) -> dict:
    """GET 请求，返回解析后的 JSON dict，失败返回 {}"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass
    return {}


def rpc_call(url: str, method: str, params=None, timeout: int = 5):
    """Geth JSON-RPC 单次调用"""
    payload = {"jsonrpc": "2.0", "method": method,
                "params": params or [], "id": 1}
    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            return result.get("result")
    except Exception:
        return None


# ─── 采集函数 ──────────────────────────────────────────────────

def collect_geth(node_ip: str) -> dict:
    """采集 Geth 执行层数据"""
    geth_url = f"http://localhost:{GETH_RPC_PORT}"

    node_info   = rpc_call(geth_url, "admin_nodeInfo")
    raw_peers   = rpc_call(geth_url, "admin_peers") or []
    block_hex   = rpc_call(geth_url, "eth_blockNumber") or "0x0"
    peer_count  = rpc_call(geth_url, "net_peerCount")   or "0x0"

    if node_info is None:
        return {}

    # 解析节点信息
    node_id = node_info.get("id", "")
    enode   = node_info.get("enode", "")
    proto   = node_info.get("protocols", {})

    # 解析对等连接
    peers = []
    for p in raw_peers:
        peer_enode = p.get("enode", "")
        m = re.search(r'@(\d+\.\d+\.\d+\.\d+):', peer_enode)
        peer_ip = m.group(1) if m else p.get("network", {}).get("remoteAddress", "").split(":")[0]
        inbound = p.get("network", {}).get("inbound", False)
        peers.append({
            "peer_id":   p.get("id", ""),
            "ip":        peer_ip,
            "enode":     peer_enode,
            "direction": "inbound" if inbound else "outbound",
            "caps":      p.get("caps", []),
            "name":      p.get("name", ""),
        })

    return {
        "node_id":        node_id,
        "ip":             node_ip,
        "enode":          enode,
        "client_type":    "geth",
        "client_version": node_info.get("name", ""),
        "client_info":    node_info.get("name", ""),
        "os_arch":        "",
        "network_id":     str(proto.get("eth", {}).get("network", 1337)),
        "block_number":   int(block_hex, 16) if block_hex else 0,
        "peer_count":     int(peer_count, 16) if peer_count else 0,
        "peers":          peers,
    }


def collect_lighthouse(node_ip: str) -> dict:
    """采集 Lighthouse 共识层数据"""
    lh_base = f"http://{node_ip}:{LIGHTHOUSE_PORT}"

    identity  = http_get(f"{lh_base}/eth/v1/node/identity")
    peers_raw = http_get(f"{lh_base}/eth/v1/node/peers")
    syncing   = http_get(f"{lh_base}/eth/v1/node/syncing")
    vals_raw  = http_get(f"{lh_base}/eth/v1/beacon/states/head/validators?status=active") \
                if HAS_VALIDATOR else {}

    if not identity:
        return {}

    id_data = identity.get("data", {})
    peer_id = id_data.get("peer_id", "")

    # 解析对等连接
    peers = []
    for p in (peers_raw.get("data") or []):
        addr = p.get("last_seen_p2p_address", "")
        m = re.search(r'/ip4/(\d+\.\d+\.\d+\.\d+)/', addr)
        peers.append({
            "peer_id":   p.get("peer_id", ""),
            "ip":        m.group(1) if m else "",
            "p2p_address": addr,
            "direction": p.get("direction", "unknown").lower(),
            "state":     p.get("state", ""),
        })

    # 解析同步状态
    sync = syncing.get("data", {}) or {}
    sync_status = {
        "is_syncing":    sync.get("is_syncing", False),
        "head_slot":     sync.get("head_slot", "0"),
        "sync_distance": sync.get("sync_distance", "0"),
    }

    # 解析验证者（最多50个）
    validators = []
    for v in (vals_raw.get("data") or [])[:50]:
        val  = v.get("validator", {})
        idx  = v.get("index")
        validators.append({
            "validator_index":       int(idx) if idx is not None else 0,
            "public_key":            val.get("pubkey", ""),
            "status":                v.get("status", "unknown"),
            "balance":               int(v.get("balance", 0)),
            "effective_balance":     int(val.get("effective_balance", 0)),
            "activation_epoch":      int(val.get("activation_epoch", 0)),
            "exit_epoch":            int(val.get("exit_epoch", 18446744073709551615)),
            "slashed":               val.get("slashed", False),
            "current_duties":        {},
            "withdrawal_credentials": val.get("withdrawal_credentials", ""),
        })

    return {
        "node_id":       peer_id,
        "ip":            node_ip,
        "peer_id":       peer_id,
        "enr":           id_data.get("enr", ""),
        "p2p_addresses": id_data.get("p2p_addresses", []),
        "client_type":   "lighthouse",
        "client_version": "",
        "client_info":   f"lighthouse@{node_ip}",
        "os_arch":       "",
        "sync_status":   sync_status,
        "peers":         peers,
        "validators":    validators,
    }


# ─── 上报函数 ──────────────────────────────────────────────────

def report_topology(node_ip: str, exec_data: dict, cons_data: dict):
    """上报 p2p_topology 到中央收集器"""
    payload = {
        "container_id": CONTAINER_NAME,
        "node_id":      exec_data.get("node_id") or cons_data.get("node_id") or node_ip,
        "timestamp":    time.time(),
        "data_type":    "p2p_topology",
        "agent_version": AGENT_VERSION,
        "local_ip":     node_ip,
        "data":         {},
    }

    if exec_data:
        payload["data"]["execution_layer"] = {
            "node":  {
                "node_id":        exec_data["node_id"],
                "ip":             exec_data["ip"],
                "client_type":    exec_data["client_type"],
                "client_version": exec_data["client_version"],
                "client_info":    exec_data["client_info"],
                "os_arch":        "",
                "network_id":     exec_data["network_id"],
                "enode":          exec_data["enode"],
            },
            "peers": exec_data["peers"],
        }

    if cons_data:
        payload["data"]["consensus_layer"] = {
            "node": {
                "node_id":       cons_data["node_id"],
                "ip":            cons_data["ip"],
                "client_type":   cons_data["client_type"],
                "client_version": cons_data["client_version"],
                "client_info":   cons_data["client_info"],
                "os_arch":       "",
                "enr":           cons_data["enr"],
                "p2p_addresses": cons_data["p2p_addresses"],
                "sync_status":   cons_data["sync_status"],
            },
            "peers":      cons_data["peers"],
            "validators": cons_data["validators"],
        }

    ok = http_post(
        f"{CENTRAL_COLLECTOR_URL}/api/v1/monitoring/data",
        payload
    )

    exec_peers = len(exec_data.get("peers", [])) if exec_data else 0
    cons_peers = len(cons_data.get("peers", [])) if cons_data else 0
    validators = len(cons_data.get("validators", [])) if cons_data else 0
    block      = exec_data.get("block_number", 0) if exec_data else 0

    if ok:
        logger.info(
            f"📡 拓扑上报成功: block=#{block} "
            f"exec_peers={exec_peers} cons_peers={cons_peers} validators={validators}"
        )
    else:
        logger.warning("⚠️ 拓扑上报失败（中央收集器可能尚未就绪，将继续重试）")


def send_heartbeat(node_ip: str):
    """向中央收集器发送心跳（保活信号）"""
    payload = {
        "container_id":             CONTAINER_NAME,
        "node_id":                  node_ip,
        "status":                   "active",
        "agent_type":               "eth_node_monitoring_agent",
        "agent_version":            AGENT_VERSION,
        "local_ip":                 node_ip,
        "monitoring_capabilities":  {
            "geth_rpc":        True,
            "lighthouse_http": True,
            "has_validator":   HAS_VALIDATOR,
        },
    }
    ok = http_post(
        f"{CENTRAL_COLLECTOR_URL}/api/v1/monitoring/heartbeat",
        payload
    )
    if ok:
        logger.debug("💗 心跳发送成功")


# ─── 等待服务就绪 ──────────────────────────────────────────────

def wait_for_geth(timeout_s: int = 300) -> bool:
    """等待 Geth JSON-RPC 就绪，返回是否在超时内就绪"""
    geth_url = f"http://localhost:{GETH_RPC_PORT}"
    logger.info(f"⏳ 等待 Geth 就绪 ({geth_url})...")
    start = time.time()
    while time.time() - start < timeout_s:
        result = rpc_call(geth_url, "eth_blockNumber", timeout=3)
        if result is not None:
            block = int(result, 16) if result else 0
            logger.info(f"✅ Geth 就绪，当前区块 #{block}")
            return True
        time.sleep(5)
    logger.error("❌ Geth 等待超时")
    return False


def wait_for_lighthouse(node_ip: str, timeout_s: int = 300) -> bool:
    """等待 Lighthouse HTTP API 就绪"""
    lh_url = f"http://{node_ip}:{LIGHTHOUSE_PORT}/eth/v1/node/syncing"
    logger.info(f"⏳ 等待 Lighthouse 就绪 ({lh_url})...")
    start = time.time()
    while time.time() - start < timeout_s:
        data = http_get(lh_url, timeout=3)
        if data:
            logger.info("✅ Lighthouse 就绪")
            return True
        time.sleep(5)
    logger.warning("⚠️ Lighthouse 等待超时（仅执行层监控）")
    return False


# ─── 主循环 ───────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info(f"🚀 eth_node_monitoring_agent 启动")
    logger.info(f"   容器: {CONTAINER_NAME}")
    logger.info(f"   中央收集器: {CENTRAL_COLLECTOR_URL}")
    logger.info(f"   采集间隔: {COLLECT_INTERVAL}s")
    logger.info(f"   有验证者: {HAS_VALIDATOR}")
    logger.info("=" * 60)

    # 1. 检测本节点 IP
    node_ip = detect_node_ip()
    logger.info(f"📍 本节点 IP: {node_ip}")

    # 2. 等待 Geth 就绪（最多5分钟）
    geth_ready = wait_for_geth(timeout_s=300)
    if not geth_ready:
        logger.error("Geth 无法就绪，Agent 退出")
        sys.exit(1)

    # 3. 等待 Lighthouse 就绪（最多5分钟，失败也继续）
    lh_ready = wait_for_lighthouse(node_ip, timeout_s=300)

    # 4. 主采集循环
    logger.info("🔁 开始主采集循环...")
    cycle = 0
    while True:
        cycle += 1
        try:
            # 采集执行层
            exec_data = collect_geth(node_ip)

            # 采集共识层
            cons_data = collect_lighthouse(node_ip) if lh_ready else {}

            if exec_data or cons_data:
                report_topology(node_ip, exec_data, cons_data)
            else:
                logger.warning(f"[周期#{cycle}] 采集到空数据，等待节点就绪...")

            # 发送心跳（保活）
            send_heartbeat(node_ip)

        except KeyboardInterrupt:
            logger.info("Agent 收到停止信号，退出")
            break
        except Exception as e:
            logger.error(f"采集循环异常: {e}")

        time.sleep(COLLECT_INTERVAL)


if __name__ == "__main__":
    main()
