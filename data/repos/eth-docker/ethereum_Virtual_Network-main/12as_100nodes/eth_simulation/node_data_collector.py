#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
节点数据主动采集器（Node Data Collector）

【架构问题的根源与解决】
═══════════════════════════════════════════════════════════════
问题：
  eth_node_monitoring 和 eth_node_cleaner 都是独立容器，
  它们无法直接"看到"节点容器内部的 P2P 连接状态。
  Neo4j 里的拓扑数据必须有人主动采集并推送，否则是空的。

解决：
  本模块定期轮询每个以太坊节点暴露的 HTTP API：
    Geth  HTTP RPC (:8545) → admin_peers, admin_nodeInfo
    Lighthouse HTTP (:8000) → /eth/v1/node/peers, /eth/v1/node/identity
                              /eth/v1/beacon/states/head/validators
  将采集到的数据整理为 p2p_topology 格式，POST 到 eth_node_cleaner:8888
  eth_node_cleaner 再写入 Neo4j → eth_node_monitoring 从 Neo4j 读取
═══════════════════════════════════════════════════════════════

关键说明：
  - Geth 以 --http.addr 0.0.0.0:8545 启动，同一 Docker 网络可直接访问
  - Lighthouse 以 --http-address <节点IP>:8000 启动，同样可外部访问
  - 本采集器运行在 eth_simulation 容器中（接入 net_151 + net_152 网络）
  - 采集间隔：默认 30 秒（可通过 NODE_COLLECT_INTERVAL 环境变量调整）
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

from config import SimulationConfig
from reporter import Reporter

logger = logging.getLogger("node_data_collector")


# ─── 节点描述 ──────────────────────────────────────────────────

@dataclass
class EthNode:
    """描述一个以太坊节点的访问地址"""
    name: str                      # 节点名称（日志用）
    ip: str                        # 节点 IP
    geth_rpc_port: int = 8545      # Geth JSON-RPC 端口
    lighthouse_port: int = 8000    # Lighthouse HTTP API 端口
    has_validator: bool = True     # 是否有验证者密钥

    @property
    def geth_url(self) -> str:
        return f"http://{self.ip}:{self.geth_rpc_port}"

    @property
    def lighthouse_url(self) -> str:
        return f"http://{self.ip}:{self.lighthouse_port}"


# ─── 采集器主类 ────────────────────────────────────────────────

class NodeDataCollector:
    """
    定期从每个以太坊节点的 HTTP API 采集 P2P 拓扑数据，
    并推送到 eth_node_cleaner 的中央收集器。
    """

    def __init__(self, config: SimulationConfig, reporter: Reporter):
        self.config = config
        self.reporter = reporter
        self.running = False
        self.collect_interval = int(
            __import__('os').getenv('NODE_COLLECT_INTERVAL', '30')
        )

        # 目标节点列表（从配置中构建，可通过环境变量扩展）
        self.nodes: List[EthNode] = self._build_node_list()

        # 统计
        self.stats = {
            "collections": 0,
            "successes": 0,
            "failures": 0,
            "last_collection_time": 0.0,
        }

    def _build_node_list(self) -> List[EthNode]:
        """根据配置构建目标节点列表"""
        import os
        # 支持通过环境变量自定义（格式: "name:ip:geth_port:lh_port:has_validator"）
        custom = os.getenv("ETH_NODES")
        if custom:
            nodes = []
            for entry in custom.split(";"):
                parts = entry.strip().split(":")
                if len(parts) >= 2:
                    nodes.append(EthNode(
                        name=parts[0],
                        ip=parts[1],
                        geth_rpc_port=int(parts[2]) if len(parts) > 2 else 8545,
                        lighthouse_port=int(parts[3]) if len(parts) > 3 else 8000,
                        has_validator=parts[4].lower() != "false" if len(parts) > 4 else True,
                    ))
            if nodes:
                logger.info(f"从环境变量加载了 {len(nodes)} 个自定义节点")
                return nodes

        # 默认: 2as_6nodes 拓扑的节点列表
        default_nodes = [
            EthNode("BootNode",  "10.151.0.72", has_validator=False),
            EthNode("POS-3",     "10.151.0.73", has_validator=True),
            EthNode("POS-4",     "10.152.0.71", has_validator=True),
            EthNode("POS-5",     "10.152.0.72", has_validator=True),
            EthNode("POS-6",     "10.152.0.73", has_validator=True),
        ]
        logger.info(f"使用默认节点列表（{len(default_nodes)} 个节点）")
        return default_nodes

    # ── 主循环 ─────────────────────────────────────────────────

    async def run(self):
        """主循环：定期采集所有节点数据"""
        self.running = True
        logger.info(f"🔍 节点数据采集器启动，间隔 {self.collect_interval}s，目标 {len(self.nodes)} 个节点")

        # 初始等待：让以太坊网络先稳定
        await asyncio.sleep(30)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8),
            connector=aiohttp.TCPConnector(limit=20)
        ) as session:
            while self.running:
                start = time.time()
                self.stats["collections"] += 1

                # 并发采集所有节点
                tasks = [
                    self._collect_and_report(session, node)
                    for node in self.nodes
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                ok = sum(1 for r in results if r is True)
                fail = len(results) - ok
                self.stats["successes"] += ok
                self.stats["failures"] += fail
                self.stats["last_collection_time"] = time.time()

                elapsed = time.time() - start
                logger.info(
                    f"📊 采集轮次 #{self.stats['collections']}: "
                    f"成功={ok}/{len(self.nodes)} 失败={fail} 耗时={elapsed:.1f}s"
                )

                await asyncio.sleep(max(0, self.collect_interval - elapsed))

    async def _collect_and_report(self, session: aiohttp.ClientSession,
                                   node: EthNode) -> bool:
        """采集单个节点的完整拓扑数据并上报"""
        try:
            # 1. 采集执行层（Geth）数据
            exec_data = await self._collect_geth_data(session, node)

            # 2. 采集共识层（Lighthouse）数据
            cons_data = await self._collect_lighthouse_data(session, node)

            # 3. 如果两个都失败，说明节点不可达
            if exec_data is None and cons_data is None:
                logger.debug(f"  {node.name} ({node.ip}): 节点不可达，跳过")
                return False

            # 4. 构建 p2p_topology 格式的数据
            topology = self._build_topology_payload(node, exec_data, cons_data)

            # 5. 上报到 eth_node_cleaner:8888
            await self.reporter.send(
                data_type="p2p_topology",
                data=topology,
            )

            logger.info(
                f"  ✅ {node.name} ({node.ip}): "
                f"exec_peers={len(topology.get('execution_layer', {}).get('peers', []))} "
                f"cons_peers={len(topology.get('consensus_layer', {}).get('peers', []))} "
                f"validators={len(topology.get('consensus_layer', {}).get('validators', []))}"
            )
            return True

        except Exception as e:
            logger.error(f"  ❌ {node.name} ({node.ip}) 采集失败: {e}")
            return False

    # ── Geth 数据采集 ──────────────────────────────────────────

    async def _collect_geth_data(self, session: aiohttp.ClientSession,
                                   node: EthNode) -> Optional[Dict]:
        """从 Geth JSON-RPC 采集执行层数据"""
        try:
            # 批量 RPC 请求（减少网络往返）
            batch = [
                {"jsonrpc": "2.0", "method": "admin_nodeInfo",  "params": [], "id": 1},
                {"jsonrpc": "2.0", "method": "admin_peers",     "params": [], "id": 2},
                {"jsonrpc": "2.0", "method": "eth_blockNumber",  "params": [], "id": 3},
                {"jsonrpc": "2.0", "method": "net_peerCount",    "params": [], "id": 4},
            ]
            async with session.post(
                node.geth_url,
                json=batch,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    return None
                results = await resp.json()

            # 解析结果（按 id 索引）
            by_id = {r["id"]: r.get("result") for r in results if "id" in r}

            node_info = by_id.get(1, {}) or {}
            raw_peers = by_id.get(2, []) or []
            block_hex = by_id.get(3, "0x0") or "0x0"
            peer_count = by_id.get(4, "0x0") or "0x0"

            # 解析 admin_nodeInfo
            node_id = node_info.get("id", "")
            enode = node_info.get("enode", "")
            protocols = node_info.get("protocols", {})
            eth_proto = protocols.get("eth", {})

            # 解析 admin_peers 的 P2P 连接
            peers = []
            for p in (raw_peers or []):
                peer_id = p.get("id", "")
                peer_enode = p.get("enode", "")
                peer_ip = self._extract_ip_from_enode(peer_enode) or p.get("network", {}).get("remoteAddress", "").split(":")[0]
                # 判断连接方向（inbound=对方连我，outbound=我连对方）
                inbound = p.get("network", {}).get("inbound", False)
                peers.append({
                    "peer_id": peer_id,
                    "ip": peer_ip,
                    "enode": peer_enode,
                    "direction": "inbound" if inbound else "outbound",
                    "caps": p.get("caps", []),
                    "name": p.get("name", ""),
                })

            return {
                "node_id": node_id,
                "ip": node.ip,
                "enode": enode,
                "client_type": "geth",
                "client_version": node_info.get("name", ""),
                "client_info": node_info.get("name", ""),
                "os_arch": "",
                "network_id": str(eth_proto.get("network", self.config.eth_chain_id)),
                "block_number": int(block_hex, 16) if block_hex else 0,
                "peer_count": int(peer_count, 16) if peer_count else 0,
                "peers": peers,
            }

        except asyncio.TimeoutError:
            logger.debug(f"  {node.name} Geth RPC 超时")
            return None
        except Exception as e:
            logger.debug(f"  {node.name} Geth RPC 异常: {e}")
            return None

    # ── Lighthouse 数据采集 ───────────────────────────────────

    async def _collect_lighthouse_data(self, session: aiohttp.ClientSession,
                                        node: EthNode) -> Optional[Dict]:
        """从 Lighthouse HTTP API 采集共识层数据"""
        try:
            # 并发请求多个 Lighthouse 端点
            identity_task = self._lh_get(session, node, "/eth/v1/node/identity")
            peers_task = self._lh_get(session, node, "/eth/v1/node/peers")
            syncing_task = self._lh_get(session, node, "/eth/v1/node/syncing")

            tasks = [identity_task, peers_task, syncing_task]
            if node.has_validator:
                tasks.append(self._lh_get(session, node,
                                          "/eth/v1/beacon/states/head/validators?status=active"))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            identity_data = results[0] if not isinstance(results[0], Exception) else None
            peers_data    = results[1] if not isinstance(results[1], Exception) else None
            syncing_data  = results[2] if not isinstance(results[2], Exception) else None
            validators_data = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else None

            if identity_data is None and peers_data is None:
                return None

            # 解析 identity
            identity = (identity_data or {}).get("data", {})
            peer_id = identity.get("peer_id", "")
            enr = identity.get("enr", "")
            p2p_addresses = identity.get("p2p_addresses", [])

            # 解析 peers
            raw_peers = (peers_data or {}).get("data", []) or []
            peers = []
            for p in raw_peers:
                peer_addr = p.get("last_seen_p2p_address", "")
                peer_ip = self._extract_ip_from_multiaddr(peer_addr)
                peers.append({
                    "peer_id": p.get("peer_id", ""),
                    "ip": peer_ip,
                    "p2p_address": peer_addr,
                    "direction": p.get("direction", "unknown").lower(),
                    "state": p.get("state", ""),
                })

            # 解析同步状态
            sync = (syncing_data or {}).get("data", {})
            sync_status = {
                "is_syncing": sync.get("is_syncing", False),
                "head_slot": sync.get("head_slot", "0"),
                "sync_distance": sync.get("sync_distance", "0"),
            }

            # 解析验证者（最多取前 50 个）
            validators = []
            raw_vals = (validators_data or {}).get("data", []) or []
            for v in raw_vals[:50]:
                idx = v.get("index")
                val = v.get("validator", {})
                balance = v.get("balance", 0)
                validators.append({
                    "validator_index": int(idx) if idx is not None else 0,
                    "public_key": val.get("pubkey", ""),
                    "status": v.get("status", "unknown"),
                    "balance": int(balance) if balance else 0,
                    "effective_balance": int(val.get("effective_balance", 0)),
                    "activation_epoch": int(val.get("activation_epoch", 0)),
                    "exit_epoch": int(val.get("exit_epoch", 18446744073709551615)),
                    "slashed": val.get("slashed", False),
                    "current_duties": {},
                    "withdrawal_credentials": val.get("withdrawal_credentials", ""),
                })

            return {
                "node_id": peer_id,
                "ip": node.ip,
                "peer_id": peer_id,
                "enr": enr,
                "p2p_addresses": p2p_addresses,
                "client_type": "lighthouse",
                "client_version": "",
                "client_info": f"lighthouse@{node.ip}",
                "os_arch": "",
                "sync_status": sync_status,
                "peers": peers,
                "validators": validators,
            }

        except Exception as e:
            logger.debug(f"  {node.name} Lighthouse API 异常: {e}")
            return None

    async def _lh_get(self, session: aiohttp.ClientSession,
                       node: EthNode, path: str) -> Optional[Dict]:
        """执行一次 Lighthouse HTTP GET 请求"""
        try:
            async with session.get(f"{node.lighthouse_url}{path}") as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception:
            return None

    # ── 数据格式化 ─────────────────────────────────────────────

    def _build_topology_payload(self, node: EthNode,
                                  exec_data: Optional[Dict],
                                  cons_data: Optional[Dict]) -> Dict:
        """
        将采集的原始数据整理为 eth_node_cleaner 期望的 p2p_topology 格式。
        参见 DataProcessor._process_p2p_topology() 的处理逻辑。
        """
        payload = {}

        if exec_data:
            payload["execution_layer"] = {
                "node": {
                    "node_id":        exec_data.get("node_id", ""),
                    "ip":             exec_data.get("ip", ""),
                    "client_type":    exec_data.get("client_type", "geth"),
                    "client_version": exec_data.get("client_version", ""),
                    "client_info":    exec_data.get("client_info", ""),
                    "os_arch":        "",
                    "network_id":     exec_data.get("network_id", ""),
                    "enode":          exec_data.get("enode", ""),
                    "block_number":   exec_data.get("block_number", 0),
                    "peer_count":     exec_data.get("peer_count", 0),
                },
                "peers": exec_data.get("peers", []),
            }

        if cons_data:
            payload["consensus_layer"] = {
                "node": {
                    "node_id":        cons_data.get("node_id", ""),
                    "ip":             cons_data.get("ip", ""),
                    "client_type":    cons_data.get("client_type", "lighthouse"),
                    "client_version": cons_data.get("client_version", ""),
                    "client_info":    cons_data.get("client_info", ""),
                    "os_arch":        "",
                    "enr":            cons_data.get("enr", ""),
                    "p2p_addresses":  cons_data.get("p2p_addresses", []),
                    "sync_status":    cons_data.get("sync_status", {}),
                },
                "peers":      cons_data.get("peers", []),
                "validators": cons_data.get("validators", []),
            }

        return payload

    # ── 工具函数 ───────────────────────────────────────────────

    @staticmethod
    def _extract_ip_from_enode(enode: str) -> str:
        """
        从 enode URL 提取 IP 地址。
        格式: enode://<pubkey>@<ip>:<port>
        """
        if not enode:
            return ""
        m = re.search(r'@(\d+\.\d+\.\d+\.\d+):', enode)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_ip_from_multiaddr(addr: str) -> str:
        """
        从 libp2p multiaddr 提取 IP。
        格式: /ip4/<ip>/tcp/<port>/p2p/<peer_id>
        """
        if not addr:
            return ""
        m = re.search(r'/ip4/(\d+\.\d+\.\d+\.\d+)/', addr)
        return m.group(1) if m else ""

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "target_nodes": [n.ip for n in self.nodes],
            "collect_interval_seconds": self.collect_interval,
        }
