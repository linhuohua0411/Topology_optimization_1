#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据上报模块
向 central_collector 的 HTTP API 发送监控数据，同时直接写入 PostgreSQL。
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import asyncpg

logger = logging.getLogger("reporter")


class Reporter:
    """向 central_collector 汇报数据的异步客户端"""

    def __init__(self, collector_url: str, pg_dsn: str,
                 container_id: str = "eth_simulation",
                 node_id: str = "eth_simulation_agent"):
        self.collector_url = collector_url.rstrip("/")
        self.pg_dsn = pg_dsn
        self.container_id = container_id
        self.node_id = node_id
        self.pg_pool: Optional[asyncpg.Pool] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        """初始化连接"""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        for attempt in range(10):
            try:
                self.pg_pool = await asyncpg.create_pool(
                    dsn=self.pg_dsn, min_size=2, max_size=8
                )
                logger.info("✅ Reporter PostgreSQL 连接成功")
                return
            except Exception as e:
                logger.warning(f"PostgreSQL 连接失败（尝试 {attempt+1}/10）: {e}")
                await asyncio.sleep(5)
        logger.error("⚠️ PostgreSQL 多次连接失败，将以降级模式运行（仅 HTTP 上报）")

    async def stop(self):
        if self._session:
            await self._session.close()
        if self.pg_pool:
            await self.pg_pool.close()

    async def send(self, data_type: str, data: Any) -> bool:
        """向 central_collector 发送数据"""
        payload = {
            "container_id": self.container_id,
            "node_id": self.node_id,
            "timestamp": time.time(),
            "data_type": data_type,
            "data": data,
            "agent_version": "1.0.0"
        }
        try:
            async with self._session.post(
                f"{self.collector_url}/api/v1/monitoring/data",
                json=payload
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"✅ 上报成功: {data_type}")
                    return True
                else:
                    logger.warning(f"⚠️ 上报返回 {resp.status}: {data_type}")
                    return False
        except Exception as e:
            logger.debug(f"⚠️ 上报失败（central_collector 可能尚未就绪）: {e}")
            return False

    # ── 交易上报 ─────────────────────────────────────────────────

    async def report_transaction(self, tx_data: Dict):
        """上报交易到 central_collector + 直接写 PostgreSQL"""
        await self.send("transactions", {
            "block_number": tx_data.get("block_number", 0),
            "transactions": [tx_data]
        })
        await self._write_tx_to_pg(tx_data)

    async def _write_tx_to_pg(self, tx: Dict):
        """直接将交易写入 PostgreSQL transactions 表"""
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO transactions (
                        tx_hash, block_number, from_address, to_address,
                        value, gas_limit, gas_price, gas_used, status,
                        input_data, method_id, timestamp, transaction_index, nonce
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                    ON CONFLICT (tx_hash) DO UPDATE SET
                        status = EXCLUDED.status,
                        gas_used = EXCLUDED.gas_used,
                        block_number = EXCLUDED.block_number
                """,
                    tx.get("hash", ""),
                    tx.get("block_number", 0),
                    tx.get("from", ""),
                    tx.get("to", ""),
                    int(tx.get("value", 0)),
                    int(tx.get("gas", 21000)),
                    int(tx.get("gas_price", 1000000000)),
                    int(tx.get("gas_used", 21000)),
                    1 if tx.get("status") == 1 else 0,
                    tx.get("input", "0x"),
                    tx.get("input", "0x")[:10] if tx.get("input") else "0x",
                    datetime.utcfromtimestamp(tx.get("timestamp", time.time())),
                    tx.get("transaction_index", 0),
                    tx.get("nonce", 0)
                )
            logger.debug(f"✅ 交易写入 PG: {tx.get('hash', 'N/A')[:20]}")
        except Exception as e:
            logger.error(f"❌ 交易写入 PG 失败: {e}")

    # ── 拓扑变化（混沌事件）上报 ─────────────────────────────────

    async def report_chaos_event(self, event_type: str, container_name: str,
                                 node_ip: str, details: Dict):
        """上报节点上/下线事件"""
        event = {
            "change_type": event_type,          # "node_link_down" / "node_link_up"
            "layer": details.get("layer", "execution"),
            "node_id": container_name,
            "node_ip": node_ip,
            "change_data": {
                "reason": "chaos_simulation",
                "interface": details.get("interface", "unknown"),
                "saved_config": details.get("saved_config", {}),
                "restored_config": details.get("restored_config", {}),
                "trigger": details.get("trigger", "random"),
                "old_value": {"status": "active"} if event_type == "node_link_down" else {"status": "down"},
                "new_value": {"status": "down"} if event_type == "node_link_down" else {"status": "active"},
            },
            "timestamp": datetime.now().isoformat(),
            "source": "ChaosAgent",
            "impact_score": 0.9
        }
        await self.send("network_topology_change", event)
        await self._write_chaos_to_pg(event_type, container_name, node_ip, details)
        await self._write_chaos_event_history(event_type, container_name, node_ip, details)
        await self._write_topology_change_to_pg(
            layer=event["layer"],
            source_node=container_name,
            target_node=details.get("interface"),
            action=event_type,
            metadata={
                "node_ip": node_ip,
                "details": details,
            }
        )

    async def _write_chaos_to_pg(self, event_type: str, container_name: str,
                                  node_ip: str, details: Dict):
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO node_failures (
                        container_id, node_id, failure_time, failure_type, status, details
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (container_id, node_id) DO UPDATE SET
                        failure_time = EXCLUDED.failure_time,
                        failure_type = EXCLUDED.failure_type,
                        status = EXCLUDED.status,
                        details = EXCLUDED.details
                """,
                    container_name,
                    node_ip,
                    datetime.utcnow(),
                    event_type,
                    "down" if event_type == "node_link_down" else "active",
                    json.dumps(details)
                )
        except Exception as e:
            logger.error(f"❌ 混沌事件写入 PG 失败: {e}")

    async def _write_chaos_event_history(self, event_type: str, container_name: str,
                                          node_ip: str, details: Dict):
        """写入 node_chaos_events 历史表（每条事件独立记录，不覆盖）"""
        if not self.pg_pool:
            return
        try:
            saved = details.get("saved_config", {})
            restored = details.get("restored_config", {})
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO node_chaos_events (
                        event_type, container_name, node_ip, interface, trigger,
                        ip_with_prefix, gateway, gateway_dev,
                        down_duration_seconds, gateway_ping_ok, restored_neighbors,
                        details, event_time
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                    event_type,
                    container_name,
                    node_ip,
                    details.get("interface", ""),
                    details.get("trigger", "random"),
                    saved.get("ip", restored.get("ip", "")),
                    saved.get("gateway", restored.get("gateway", "")),
                    saved.get("gateway_dev", restored.get("gateway_dev", "")),
                    details.get("down_duration_seconds"),
                    restored.get("gateway_ping_ok"),
                    restored.get("restored_neighbors", 0),
                    json.dumps(details),
                    datetime.utcnow(),
                )
        except Exception as e:
            logger.error(f"❌ node_chaos_events 写入失败: {e}")

    async def report_wan_event(self, event_type: str, container_name: str,
                               interface: str, details: Dict):
        """上报 WAN 链路扰动/恢复事件"""
        event = {
            "change_type": event_type,
            "layer": "network",
            "node_id": container_name,
            "node_ip": details.get("node_ip"),
            "change_data": {
                "reason": details.get("reason", "wan_chaos"),
                "interface": interface,
                "profile": details.get("profile", {}),
                "baseline": details.get("baseline", {}),
                "trigger": details.get("trigger", "random"),
                "old_value": details.get("old_value"),
                "new_value": details.get("new_value"),
            },
            "timestamp": datetime.now().isoformat(),
            "source": "WanChaosAgent",
            "impact_score": details.get("impact_score", 0.7),
        }
        await self.send("network_topology_change", event)
        await self._write_topology_change_to_pg(
            layer="network",
            source_node=container_name,
            target_node=interface,
            action=event_type,
            metadata=details,
        )
        await self._write_wan_event_history(event_type, container_name, interface, details)

    async def _write_wan_event_history(self, event_type: str, container_name: str,
                                        interface: str, details: Dict):
        """写入 wan_chaos_events 历史表（每条事件独立记录）"""
        if not self.pg_pool:
            return
        try:
            profile = details.get("profile", {})
            baseline = details.get("baseline", {})
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO wan_chaos_events (
                        event_type, container_name, interface, trigger,
                        bandwidth_mbit, delay_ms, jitter_ms, loss_pct,
                        baseline_bandwidth_mbit, baseline_delay_ms,
                        baseline_jitter_ms, baseline_loss_pct,
                        duration_seconds, details, event_time
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                """,
                    event_type,
                    container_name,
                    interface,
                    details.get("trigger", "random"),
                    profile.get("bandwidth_mbit"),
                    profile.get("delay_ms"),
                    profile.get("jitter_ms"),
                    profile.get("loss_pct"),
                    baseline.get("bandwidth_mbit") if isinstance(baseline, dict) else None,
                    baseline.get("delay_ms") if isinstance(baseline, dict) else None,
                    baseline.get("jitter_ms") if isinstance(baseline, dict) else None,
                    baseline.get("loss_pct") if isinstance(baseline, dict) else None,
                    details.get("duration_seconds"),
                    json.dumps(details),
                    datetime.utcnow(),
                )
        except Exception as e:
            logger.error(f"❌ wan_chaos_events 写入失败: {e}")

    # ── 合约上报 ─────────────────────────────────────────────────

    async def report_contract_deployed(self, contract_name: str,
                                        address: str, deployer: str,
                                        block_number: int, tx_hash: str):
        """上报合约部署事件"""
        await self.send("contracts", {
            "block_number": block_number,
            "contracts": [{
                "address": address,
                "creator": deployer,
                "creation_tx": tx_hash,
                "contract_type": contract_name,
                "is_verified": True,
            }],
            "contract_calls": [],
            "events": []
        })
        await self._write_contract_to_pg(contract_name, address, deployer,
                                          block_number, tx_hash)

    async def report_contract_call(self, contract_address: str, method: str,
                                    caller: str, tx_hash: str,
                                    block_number: int, event_args: Dict):
        """上报合约调用事件"""
        await self.send("contracts", {
            "block_number": block_number,
            "contracts": [],
            "contract_calls": [{
                "from": caller,
                "to": contract_address,
                "method": method,
                "tx_hash": tx_hash,
            }],
            "events": [{
                "address": contract_address,
                "event_signature": method,
                "args": event_args,
            }]
        })
        await self._write_contract_event_to_pg(contract_address, method,
                                                block_number, event_args, tx_hash)

    async def _write_contract_to_pg(self, name: str, address: str, deployer: str,
                                     block_number: int, tx_hash: str):
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO contracts (
                        contract_address, deployer_address, block_number,
                        tx_hash, contract_name, contract_type, is_verified, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT (contract_address) DO NOTHING
                """,
                    address, deployer, block_number, tx_hash,
                    name, name, True, datetime.utcnow()
                )
            logger.info(f"✅ 合约写入 PG: {name} @ {address[:12]}...")
        except Exception as e:
            logger.error(f"❌ 合约写入 PG 失败: {e}")

    async def _write_contract_event_to_pg(self, contract_address: str,
                                           event_name: str, block_number: int,
                                           args: Dict, tx_hash: str):
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO contract_events (block_number, event_name, contract_address, args, timestamp)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT DO NOTHING
                """,
                    block_number,
                    event_name,
                    contract_address,
                    json.dumps(args),
                    datetime.utcnow()
                )
        except Exception as e:
            logger.error(f"❌ 合约事件写入 PG 失败: {e}")

    async def _write_topology_change_to_pg(self, layer: str, source_node: str,
                                           target_node: Optional[str], action: str,
                                           metadata: Dict):
        if not self.pg_pool:
            return
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO topology_changes (timestamp, layer, source_node, target_node, action, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    datetime.utcnow(),
                    layer,
                    source_node,
                    target_node,
                    action,
                    json.dumps(metadata),
                )
        except Exception as e:
            logger.error(f"❌ topology_changes 写入失败: {e}")

    # ── 心跳 ─────────────────────────────────────────────────────

    async def send_heartbeat(self):
        try:
            async with self._session.post(
                f"{self.collector_url}/api/v1/monitoring/heartbeat",
                json={
                    "container_id": self.container_id,
                    "node_id": self.node_id,
                    "status": "active",
                    "agent_type": "simulation",
                    "agent_version": "1.0.0",
                    "monitoring_capabilities": {
                        "tx_generation": True,
                        "chaos": True,
                        "contracts": True
                    }
                }
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
