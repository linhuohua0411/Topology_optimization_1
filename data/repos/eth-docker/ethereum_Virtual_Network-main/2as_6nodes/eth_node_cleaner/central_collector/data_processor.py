#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据处理器模块 - v3.0.0
负责处理来自监控代理的不同类型数据，并将其异步地路由到正确的数据库。
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import time # Added for time.time()

import asyncpg
from neo4j import AsyncGraphDatabase, AsyncDriver
from redis import asyncio as aioredis

from .models import CollectedData
from .config import CollectorConfig
from .blockchain_processor import BlockchainProcessor
from .topology_change_detector import TopologyChangeDetector
from .change_event_sender import ChangeEventSender
from .state_manager import StateManager
from .node_manager import NodeManager
from .data_utils import hex_to_int, status_to_int, validate_node_id, extract_ip_from_p2p_addresses


class DataProcessor:
    """数据处理器 - 异步版本 (v4.2.0 - 集成拓扑变化检测)"""
    
    def __init__(self, config: CollectorConfig, data_cache):
        self.config = config
        self.data_cache = data_cache
        self.logger = logging.getLogger(__name__)
        
        # 异步数据库客户端
        self.redis_client: Optional[aioredis.Redis] = None
        self.neo4j_driver: Optional[AsyncDriver] = None
        self.pg_pool: Optional[asyncpg.Pool] = None
        
        # 区块链处理器
        self.blockchain_processor: Optional[BlockchainProcessor] = None
        
        # v4.2.0: 新增拓扑变化检测组件
        self.topology_change_detector: Optional[TopologyChangeDetector] = None
        self.change_event_sender: Optional[ChangeEventSender] = None
        self.state_manager: Optional[StateManager] = None
        
        # 节点生命周期管理器（延迟初始化，在 initialize_connections 后创建）
        self.node_manager: Optional[NodeManager] = None
    
    async def initialize_connections(self):
        """异步初始化所有数据库连接。"""
        # Redis连接
        if self.config.redis_host:
            try:
                self.redis_client = aioredis.Redis(
                    host=self.config.redis_host, port=self.config.redis_port or 6379,
                    password=self.config.redis_password, decode_responses=True
                )
                await self.redis_client.ping()
                self.logger.info("✅ Redis连接初始化成功")
                self.blockchain_processor = BlockchainProcessor(self.redis_client)
                self.logger.info("✅ 区块链处理器已初始化")
            except Exception as e:
                self.logger.warning(f"⚠️ Redis连接初始化失败: {e}")

        # Neo4j连接
        if self.config.neo4j_uri:
            try:
                self.neo4j_driver = AsyncGraphDatabase.driver(
                    self.config.neo4j_uri,
                                            auth=(self.config.neo4j_username, self.config.neo4j_password)
                )
                await self.neo4j_driver.verify_connectivity()
                self.logger.info("✅ Neo4j连接初始化成功")
            except Exception as e:
                self.logger.warning(f"⚠️ Neo4j连接初始化失败: {e}")

        # PostgreSQL连接
        if self.config.postgresql_dsn:
            try:
                self.pg_pool = await asyncpg.create_pool(
                    dsn=self.config.postgresql_dsn, min_size=5, max_size=20
                )
                self.logger.info("✅ PostgreSQL连接池初始化成功")
            except Exception as e:
                self.logger.warning(f"⚠️ PostgreSQL连接初始化失败: {e}")
        
        # v4.2.0: 初始化拓扑变化检测组件
        if self.redis_client and self.pg_pool:
            try:
                self.state_manager = StateManager(self.redis_client, self.pg_pool)
                self.topology_change_detector = TopologyChangeDetector(self.redis_client, self.pg_pool)
                self.change_event_sender = ChangeEventSender(self.redis_client, self.pg_pool)
                self.logger.info("✅ 拓扑变化检测组件初始化成功")
            except Exception as e:
                self.logger.warning(f"⚠️ 拓扑变化检测组件初始化失败: {e}")
        
        # 初始化节点管理器
        self.node_manager = NodeManager(
            self.neo4j_driver,
            self.pg_pool,
            self.redis_client,
            self.change_event_sender
        )
    
    async def process_data(self, data: CollectedData):
        """处理数据的主入口（路由器）。"""
        self.logger.info(f"接收到数据类型: '{data.data_type}' from {data.container_id}")
        
        # v3.5: 增加对新数据类型的路由
        data_type_handlers = {
            "p2p_topology": self._process_p2p_topology,
            "execution_links": self._process_execution_links,
            "transactions": self._process_transactions,
            "contracts": self._process_contracts,
            "metrics": self._process_metrics,
            "beacon_state": self._process_beacon_state,
            "beacon_blocks": self._process_beacon_blocks,    # 新增
            "attestations": self._process_attestations,      # 新增证明处理
            "fork_event": self._process_fork_event,
            "node_snapshots": self._process_node_snapshots,  # 新增
            "network_topology_change": self._process_network_topology_change,  # v4.2.0 新增
        }
        
        handler = data_type_handlers.get(data.data_type)
        if handler:
            try:
                await handler(data)
            except Exception as e:
                self.logger.error(f"处理数据失败 [{data.data_type}]: {e}", exc_info=True)
        else:
            self.logger.warning(f"未找到数据类型 '{data.data_type}' 的处理器，跳过。")

    async def process_heartbeat(self, heartbeat_data: Dict[str, Any]):
        """处理代理心跳数据，写入PostgreSQL"""
        if not self.pg_pool:
            self.logger.warning("PostgreSQL未连接，跳过心跳数据处理")
            return
            
        container_id = heartbeat_data.get("container_id")
        node_id = heartbeat_data.get("node_id")
        status = heartbeat_data.get("status", "active")
        agent_type = heartbeat_data.get("agent_type", "monitoring")
        
        try:
            async with self.pg_pool.acquire() as conn:
                # 1. 写入心跳记录
                await conn.execute("""
                    INSERT INTO agent_heartbeats (
                        container_id, node_id, heartbeat_time, status, agent_type, agent_version, monitoring_capabilities, local_ip
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, 
                    container_id,
                    node_id,
                    datetime.utcnow(),
                    status,
                    agent_type,
                    heartbeat_data.get("agent_version", "unknown"),
                    json.dumps(heartbeat_data.get("monitoring_capabilities", {})),
                    heartbeat_data.get("local_ip")  # 新增：提取local_ip字段
                )
                
                # 2. active_agents是一个视图，会自动从agent_heartbeats表中获取数据，无需单独插入
                # 视图会自动显示最近5分钟内的心跳记录
                pass
                
            self.logger.info(f"成功处理心跳数据: {container_id} ({agent_type})")
        except Exception as e:
            self.logger.error(f"写入心跳数据失败: {e}", exc_info=True)

    # --- 数据处理方法 ---

    async def _process_execution_links(self, data: CollectedData):
        """处理基于真实连接的执行层拓扑数据。"""
        if not self.neo4j_driver:
            self.logger.error("Neo4j驱动未初始化，无法处理执行层链接！")
            return
        
        links = data.data
        if not isinstance(links, list) or not links:
            return

        async with self.neo4j_driver.session() as session:
            tx = None
            try:
                tx = await session.begin_transaction()
                
                # 使用单个查询和UNWIND来高效处理所有链接
                query = """
                UNWIND $links AS link
                // 使用 IP 作为唯一标识来合并源节点和目标节点
                MERGE (source:ExecNode {ip: link.source_ip})
                MERGE (target:ExecNode {ip: link.target_ip})
                ON CREATE SET 
                    target.node_id = link.target_id,
                    target.name = link.target_name,
                    target.last_seen = datetime()
                ON MATCH SET 
                    target.node_id = link.target_id,
                    target.name = link.target_name,
                    target.last_seen = datetime()

                // 合并关系
                MERGE (source)-[r:EXEC_PEERS_WITH {direction: link.direction}]->(target)
                """
                await tx.run(query, links=links)
                await tx.commit()
                self.logger.info(f"成功处理了 {len(links)} 条来自 {data.container_id} 的执行层连接。")

            except Exception as e:
                self.logger.error(f"处理执行层连接时发生数据库事务错误: {e}", exc_info=True)
                if tx:
                    await tx.rollback()

    async def _process_p2p_topology(self, data: CollectedData):
        """处理P2P拓扑数据并存储到Neo4j。"""
        self.logger.info(f"开始处理P2P拓扑数据，来源: {data.container_id}")
        
        if not self.neo4j_driver:
            self.logger.error("Neo4j驱动未初始化，无法处理P2P拓扑数据")
            return
        
        topology = data.data
        
        # v3.9: 精简的数据摘要信息
        if isinstance(topology, dict):
            exec_peers = len(topology.get("execution_layer", {}).get("peers", []))
            cons_peers = len(topology.get("consensus_layer", {}).get("peers", []))
            validators = len(topology.get("consensus_layer", {}).get("validators", []))
            self.logger.info(f"🔗 应用层P2P拓扑摘要: 执行层有效连接={exec_peers}, 共识层有效连接={cons_peers}, 验证器={validators}")
            self.logger.info(f"💡 说明: 此为真实P2P协议连接状态，网络层IP可达性由EthNetworkTopologyManager监控")
        else:
            self.logger.debug(f"收到非字典类型的拓扑数据: {type(topology)}")
            return
        
        # v3.8: 增加严格的数据结构校验和隔离处理
        async with self.neo4j_driver.session() as session:
            tx = None
            try:
                tx = await session.begin_transaction()

                # --- 处理执行层 ---
                exec_layer = topology.get("execution_layer")
                if isinstance(exec_layer, dict):
                    exec_node = exec_layer.get("node")
                    if isinstance(exec_node, dict):
                        node_id = exec_node.get("node_id")
                        self.logger.info(f"执行层节点数据: node_id={node_id}, 类型={type(node_id)}")
                        if validate_node_id(node_id):  # 使用工具函数验证节点ID
                            await self._update_exec_node(tx, exec_node, container_id=data.container_id)
                            await self._update_peers(tx, node_id, exec_layer.get("peers", []), "ExecNode", "EXEC_PEERS_WITH")
                        else:
                            self.logger.warning(f"执行层节点缺少有效的 'node_id'，跳过。数据: {exec_node}")
                    elif exec_node:
                        self.logger.warning(f"执行层节点数据格式无效，跳过。数据: {exec_node}")
                elif exec_layer is not None:
                    self.logger.warning(f"收到的 'execution_layer' 不是一个字典，跳过处理。类型: {type(exec_layer)}")

                # --- 处理共识层 ---
                cons_layer = topology.get("consensus_layer")
                if isinstance(cons_layer, dict):
                    cons_node = cons_layer.get("node")
                    if isinstance(cons_node, dict):
                        node_id = cons_node.get("node_id")
                        self.logger.info(f"共识层节点数据: node_id={node_id}, 类型={type(node_id)}")
                        if validate_node_id(node_id):  # 使用工具函数验证节点ID
                            await self._update_cons_node(tx, cons_node, container_id=data.container_id)
                            await self._update_peers(tx, node_id, cons_layer.get("peers", []), "ConsNode", "CONS_PEERS_WITH")
                            
                            validators = cons_layer.get("validators", [])
                            if validators:
                                await self._update_validators(tx, node_id, validators)
                        else:
                            self.logger.warning(f"共识层节点缺少有效的 'node_id'，跳过。数据: {cons_node}")
                    elif cons_node:
                        self.logger.warning(f"共识层节点数据格式无效，跳过。数据: {cons_node}")
                elif cons_layer is not None:
                    self.logger.warning(f"收到的 'consensus_layer' 不是一个字典，跳过处理。类型: {type(cons_layer)}")

                # --- 处理配对关系 ---
                exec_node = topology.get("execution_layer", {}).get("node")
                cons_node = topology.get("consensus_layer", {}).get("node")
                
                # 使用与上面一致的严格检查
                exec_node_id = None
                cons_node_id = None
                
                if isinstance(exec_node, dict):
                    exec_id = exec_node.get("node_id")
                    if validate_node_id(exec_id):
                        exec_node_id = exec_id
                        
                if isinstance(cons_node, dict):
                    cons_id = cons_node.get("node_id")
                    if validate_node_id(cons_id):
                        cons_node_id = cons_id
                
                if exec_node_id and cons_node_id:
                    await tx.run("""
                        MATCH (e:ExecNode {node_id: $exec_id})
                        MATCH (c:ConsNode {node_id: $cons_id})
                        MERGE (e)-[:PAIRED_WITH]->(c)
                    """, exec_id=exec_node_id, cons_id=cons_node_id)
                
                await tx.commit()
                self.logger.info(f"成功处理了来自 {data.container_id} 的P2P拓扑数据。")
                
                # v4.2.0: 执行拓扑变化检测
                await self._detect_topology_changes(topology)
                
            except Exception as e:
                if tx:
                    await tx.rollback()
                self.logger.error(f"处理P2P拓扑数据时发生数据库事务错误: {e}", exc_info=True)
                raise
    
    async def cleanup_stale_nodes(self):
        """
        清理长时间未上报的节点（用于处理docker pause场景）
        当节点被pause时，监控程序也被暂停，无法上报数据，导致last_seen不更新
        此方法定期检查并删除长时间未更新的节点
        """
        if not self.neo4j_driver:
            return
        
        stale_timeout = getattr(self.config, 'node_stale_timeout_seconds', 180)
        
        try:
            async with self.neo4j_driver.session() as session:
                # 清理执行层过期节点
                exec_result = await session.run("""
                    MATCH (n:ExecNode)
                    WHERE n.last_seen IS NULL 
                       OR n.last_seen < datetime() - duration({seconds: $timeout})
                    RETURN n.node_id AS node_id, n.ip AS ip
                """, {"timeout": stale_timeout})
                
                exec_stale_nodes = []
                async for record in exec_result:
                    node_id = record.get("node_id")
                    ip = record.get("ip")
                    if node_id:
                        exec_stale_nodes.append((node_id, ip))
                
                # 清理共识层过期节点
                cons_result = await session.run("""
                    MATCH (n:ConsNode)
                    WHERE n.last_seen IS NULL 
                       OR n.last_seen < datetime() - duration({seconds: $timeout})
                    RETURN n.node_id AS node_id, n.ip AS ip
                """, {"timeout": stale_timeout})
                
                cons_stale_nodes = []
                async for record in cons_result:
                    node_id = record.get("node_id")
                    ip = record.get("ip")
                    if node_id:
                        cons_stale_nodes.append((node_id, ip))
                
                # 删除过期节点
                if exec_stale_nodes or cons_stale_nodes:
                    async with session.begin_transaction() as tx:
                        for node_id, ip in exec_stale_nodes:
                            await tx.run(
                                "MATCH (n:ExecNode {node_id: $node_id}) DETACH DELETE n",
                                node_id=node_id
                            )
                            self.logger.warning(
                                f"🗑️ 删除长时间未上报的执行层节点: {node_id} (IP: {ip}) "
                                f"[可能原因: docker pause导致监控程序无法上报]"
                            )
                        
                        for node_id, ip in cons_stale_nodes:
                            await tx.run(
                                "MATCH (n:ConsNode {node_id: $node_id}) DETACH DELETE n",
                                node_id=node_id
                            )
                            self.logger.warning(
                                f"🗑️ 删除长时间未上报的共识层节点: {node_id} (IP: {ip}) "
                                f"[可能原因: docker pause导致监控程序无法上报]"
                            )
                        
                        await tx.commit()
                    
                    total_removed = len(exec_stale_nodes) + len(cons_stale_nodes)
                    self.logger.info(
                        f"✅ 清理完成: 删除了 {total_removed} 个长时间未上报的节点 "
                        f"(执行层: {len(exec_stale_nodes)}, 共识层: {len(cons_stale_nodes)})"
                    )
                    
        except Exception as e:
            self.logger.error(f"清理过期节点失败: {e}", exc_info=True)

    async def _detect_topology_changes(self, topology: dict):
        """
        检测拓扑变化并发送变化事件 (v4.2.0)
        
        Args:
            topology: 完整的拓扑数据
        """
        if not self.topology_change_detector or not self.change_event_sender:
            self.logger.debug("变化检测组件未初始化，跳过变化检测")
            return
        
        try:
            all_changes = []
            
            # 检测执行层变化
            exec_layer = topology.get("execution_layer")
            if exec_layer:
                exec_changes = await self.topology_change_detector.detect_execution_topology_changes(exec_layer)
                all_changes.extend(exec_changes)
            
            # 检测共识层变化
            cons_layer = topology.get("consensus_layer")
            if cons_layer:
                cons_changes = await self.topology_change_detector.detect_consensus_topology_changes(cons_layer)
                all_changes.extend(cons_changes)
            
            # 发送变化事件
            if all_changes:
                await self.change_event_sender.send_topology_changes(all_changes)
                self.logger.info(f"🔍 检测到 {len(all_changes)} 个应用层P2P拓扑变化事件")
                self.logger.info(f"💡 变化类型: P2P协议连接状态变化，区别于网络层IP可达性变化")
            
            # 发送检测器心跳
            change_summary = {
                'total_changes': len(all_changes),
                'execution_changes': len([c for c in all_changes if c.get('layer') == 'execution']),
                'consensus_changes': len([c for c in all_changes if c.get('layer') == 'consensus']),
                'detection_time': datetime.now().isoformat()
            }
            await self.change_event_sender.send_heartbeat_event(change_summary)
            
        except Exception as e:
            self.logger.error(f"拓扑变化检测失败: {e}", exc_info=True)

    async def _process_network_topology_change(self, data: CollectedData):
        """
        处理网络拓扑变化事件 (v4.2.0)
        来自EthNetworkTopologyManager的网络可达性变化事件
        """
        self.logger.info(f"接收到网络拓扑变化事件，来源: {data.container_id}")
        
        try:
            change_event = data.data
            
            # 验证事件数据
            if not isinstance(change_event, dict):
                self.logger.warning(f"无效的网络拓扑变化事件格式: {type(change_event)}")
                return
            
            # 提取关键信息
            change_type = change_event.get('change_type')
            layer = change_event.get('layer')
            node_id = change_event.get('node_id')
            
            self.logger.info(f"网络拓扑变化: {change_type}, 层级: {layer}, 节点: {node_id}")
            
            # 如果是节点不可达事件，直接发送到变化检测系统
            if change_type == 'node_unreachable' and self.change_event_sender:
                # 构造标准化的变化事件
                standardized_event = {
                    'change_type': 'node_removed',
                    'layer': layer,
                    'node_id': node_id,
                    'source_node': node_id,
                    'change_data': change_event.get('change_data', {}),
                    'impact_score': change_event.get('impact_score', 0.8),
                    'timestamp': change_event.get('timestamp', datetime.now().isoformat()),
                    'source': 'network_topology_manager'
                }
                
                # 发送到变化记录系统
                if layer == 'execution':
                    await self.change_event_sender.send_execution_change_event(standardized_event)
                elif layer == 'consensus':
                    await self.change_event_sender.send_consensus_change_event(standardized_event)
                
                self.logger.info(f"网络拓扑变化事件已记录到PostgreSQL: {node_id}")
                
            else:
                self.logger.debug(f"跳过处理变化类型: {change_type}")
                
        except Exception as e:
            self.logger.error(f"处理网络拓扑变化事件失败: {e}", exc_info=True)

    async def _update_exec_node(self, tx, node_data: Dict[str, Any], container_id: Optional[str] = None):
        """在Neo4j中创建或更新执行层节点。"""
        # 确保node_id不为null
        if not node_data.get("node_id"):
            self.logger.warning(f"_update_exec_node: node_id为空，跳过更新。数据: {node_data}")
            return
            
        q = """
        MERGE (n:ExecNode {node_id: $node_id})
        SET n.client_info = $client_info,
            n.client_type = $client_type,
            n.client_version = $client_version,
            n.os_arch = $os_arch,
            n.ip = $ip,
            n.network_id = $network_id,
            n.container_id = coalesce($container_id, n.container_id),
            n.last_seen = datetime()
        """
        params = node_data.copy()
        params['container_id'] = container_id
        await tx.run(q, **params)

    async def _update_cons_node(self, tx, node_data: Dict[str, Any], container_id: Optional[str] = None):
        """在Neo4j中创建或更新共识层节点。"""
        # 确保node_id不为null
        if not node_data.get("node_id"):
            self.logger.warning(f"_update_cons_node: node_id为空，跳过更新。数据: {node_data}")
            return
            
        # 提取IP地址（从p2p_addresses中获取）
        ip_address = extract_ip_from_p2p_addresses(node_data.get('p2p_addresses', []))
        
        q = """
        MERGE (n:ConsNode {node_id: $node_id})
        SET n.client_info = $client_info,
            n.client_type = $client_type,
            n.client_version = $client_version,
            n.enr = $enr,
            n.os_arch = $os_arch,
            n.ip = $ip,
            n.p2p_addresses = $p2p_addresses,
            n.sync_status = $sync_status,
            n.container_id = coalesce($container_id, n.container_id),
            n.last_seen = datetime()
        """
        # sync_status is a dict, need to convert it to string or properties
        params = node_data.copy()
        params['sync_status'] = json.dumps(params.get('sync_status', {}))
        params['ip'] = ip_address
        params['container_id'] = container_id
        await tx.run(q, **params)
    
    async def _update_peers(self, tx, source_node_id: str, peers: List[Dict], node_label: str, rel_type: str):
        """更新节点的对等关系 - 优化连接方向处理"""
        if not peers: return
        
        # 确保source_node_id不为null
        if not source_node_id:
            self.logger.warning(f"_update_peers: source_node_id为空，跳过更新。node_label={node_label}, rel_type={rel_type}")
            return

        # 删除该节点发起的旧关系
        del_q = f"""
        MATCH (n:{node_label} {{node_id: $source_node_id}})-[r:{rel_type}]->(p)
        DELETE r
        """
        await tx.run(del_q, source_node_id=source_node_id)
        
        # 处理每个peer连接，根据方向创建正确的关系
        for peer in peers:
            if not peer.get('peer_id'):
                continue
                
            # 创建目标节点（如果不存在）
            create_target_q = f"""
            MERGE (target:{node_label} {{node_id: $peer_id}})
            ON CREATE SET target.ip = $ip, target.last_seen = datetime()
            """
            await tx.run(create_target_q, peer_id=peer['peer_id'], ip=peer.get('ip', ''))
            
            # 根据连接方向创建关系
            if peer.get('direction') == 'outbound':
                # outbound: 我主动连接对方 source -> target
                rel_q = f"""
                MATCH (source:{node_label} {{node_id: $source_id}})
                MATCH (target:{node_label} {{node_id: $target_id}})
                MERGE (source)-[r:{rel_type}]->(target)
                SET r.direction = 'outbound', r.last_updated = datetime()
                """
                await tx.run(rel_q, source_id=source_node_id, target_id=peer['peer_id'])
            elif peer.get('direction') == 'inbound':
                # inbound: 对方连接我 target -> source
                rel_q = f"""
                MATCH (source:{node_label} {{node_id: $source_id}})
                MATCH (target:{node_label} {{node_id: $target_id}})
                MERGE (target)-[r:{rel_type}]->(source)
                SET r.direction = 'inbound', r.last_updated = datetime()
                """
                await tx.run(rel_q, source_id=source_node_id, target_id=peer['peer_id'])
        
    async def _update_validators(self, tx, cons_node_id: str, validators: List[Dict]):
        """更新验证器节点及其与共识节点的关系。"""
        # 确保cons_node_id不为null
        if not cons_node_id:
            self.logger.warning(f"_update_validators: cons_node_id为空，跳过更新。validators数量={len(validators)}")
            return
        
        # 详细日志
        self.logger.info(f"更新验证器: 共识节点ID={cons_node_id[:20]}..., 验证器数量={len(validators)}")
        
        if not validators:
            self.logger.info(f"节点 {cons_node_id[:20]}... 没有管理任何验证器")
            return
            
        # FAR_FUTURE_EPOCH 转换（Ethereum uint64 max = 18446744073709551615）
        # Neo4j/PostgreSQL 均使用有符号 64 位整数，超出范围设为 None
        FAR_FUTURE = 18446744073709551615
        
        # 处理每个验证器
        for validator in validators:
            if not validator.get('validator_index') and validator.get('validator_index') != 0:
                self.logger.warning(f"跳过无效验证器数据: {validator}")
                continue
            
            # 清理溢出值后再传参（Neo4j 也无法存储 uint64 max）
            safe_validator = dict(validator)
            for epoch_field in ('exit_epoch', 'activation_epoch'):
                val = safe_validator.get(epoch_field)
                if val is not None and val >= FAR_FUTURE:
                    safe_validator[epoch_field] = None
            for int_field in ('balance', 'effective_balance'):
                val = safe_validator.get(int_field)
                if val is not None:
                    safe_validator[int_field] = int(val)
                
            q = """
            MATCH (c:ConsNode {node_id: $cons_node_id})
            MERGE (v:Validator {validator_index: $validator_index})
            SET v.public_key = $public_key,
                v.status = $status,
                v.balance = $balance,
                v.effective_balance = $effective_balance,
                v.activation_epoch = $activation_epoch,
                v.exit_epoch = $exit_epoch,
                v.slashed = $slashed,
                v.last_seen = datetime()
            MERGE (c)-[:MANAGES_VALIDATOR]->(v)
            """
            try:
                await tx.run(q, cons_node_id=cons_node_id, **safe_validator)
            except Exception as e:
                self.logger.error(f"更新验证器 {validator.get('validator_index')} 失败: {e}")
                
        # 写入到PostgreSQL的validators表
        await self._write_validators_to_postgres(cons_node_id, validators)
        
        self.logger.info(f"成功更新了节点 {cons_node_id[:20]}... 的 {len(validators)} 个验证器")

    async def _write_validators_to_postgres(self, cons_node_id: str, validators: List[Dict]):
        """将验证者数据写入PostgreSQL的validators表"""
        if not self.pg_pool or not validators:
            return
            
        try:
            async with self.pg_pool.acquire() as conn:
                validator_records = []
                for validator in validators:
                    if not validator.get('validator_index') and validator.get('validator_index') != 0:
                        continue
                        
                    # FAR_FUTURE_EPOCH (18446744073709551615) 表示"永不退出"，
                    # PostgreSQL BIGINT 最大值为 9223372036854775807，需要截断
                    FAR_FUTURE = 18446744073709551615
                    exit_ep = validator.get('exit_epoch')
                    act_ep  = validator.get('activation_epoch')
                    exit_ep = None if (exit_ep is None or exit_ep >= FAR_FUTURE) else int(exit_ep)
                    act_ep  = None if (act_ep  is None or act_ep  >= FAR_FUTURE) else int(act_ep)
                    validator_records.append((
                        validator.get('validator_index'),
                        validator.get('public_key', ''),
                        validator.get('status', 'active'),
                        int(validator.get('effective_balance', 0)),
                        validator.get('slashed', False),
                        act_ep,
                        exit_ep,
                        validator.get('withdrawal_credentials', ''),
                        json.dumps(validator.get('current_duties', {})),
                        int(validator.get('balance', 0)),
                        cons_node_id,
                        datetime.utcnow()
                    ))
                
                if validator_records:
                    await conn.executemany("""
                        INSERT INTO validators (
                            validator_index, pubkey, status, effective_balance, slashed,
                            activation_epoch, exit_epoch, withdrawal_credentials, current_duties,
                            balance, managed_by_node, last_seen
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (validator_index) DO UPDATE SET
                            status = EXCLUDED.status,
                            effective_balance = EXCLUDED.effective_balance,
                            balance = EXCLUDED.balance,
                            current_duties = EXCLUDED.current_duties,
                            managed_by_node = EXCLUDED.managed_by_node,
                            last_seen = EXCLUDED.last_seen
                    """, validator_records)
                    
                    self.logger.info(f"成功写入 {len(validator_records)} 个验证者记录到PostgreSQL")
                    
        except Exception as e:
            self.logger.error(f"写入验证者数据到PostgreSQL失败: {e}", exc_info=True)

    async def _process_transactions(self, data: CollectedData):
        """处理交易数据，批量写入PostgreSQL和Neo4j。"""
        block_number = data.data.get("block_number")
        transactions = data.data.get("transactions", [])
        if not transactions: return

        # 1. 写入PostgreSQL的transactions表
        if self.pg_pool:
            records_to_insert = []
            for tx in transactions:
                # 使用工具函数处理十六进制字符串转换
                value_int = hex_to_int(tx.get("value", "0x0"))
                gas_int = hex_to_int(tx.get("gas", "0x0"))
                gas_price_int = hex_to_int(tx.get("gas_price", "0x0"))
                status_int = status_to_int(tx.get("status", 0))
                
                records_to_insert.append((
                    tx.get("hash"),
                    block_number,
                    tx.get("from"),
                    tx.get("to"),
                    value_int,
                    gas_int,
                    gas_price_int,
                    gas_int,  # gas_used = gas for now
                    status_int,
                    tx.get("input", ""),
                    tx.get("input", "")[:10] if tx.get("input") else "",  # method_id
                    tx.get("contract_address") if tx.get("contract_creation") else None,
                    datetime.utcnow(),
                    0,  # transaction_index placeholder
                    0   # nonce placeholder
                ))

            async with self.pg_pool.acquire() as conn:
                try:
                    await conn.executemany("""
                        INSERT INTO transactions (
                            tx_hash, block_number, from_address, to_address, 
                            value, gas_limit, gas_price, gas_used, status, 
                            input_data, method_id, contract_address, timestamp,
                            transaction_index, nonce
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                        ON CONFLICT (tx_hash) DO UPDATE SET
                            status = EXCLUDED.status,
                            gas_used = EXCLUDED.gas_used,
                            contract_address = EXCLUDED.contract_address
                    """, records_to_insert)
                    self.logger.info(f"成功处理了区块 {block_number} 的 {len(records_to_insert)} 条交易。")
                except Exception as e:
                    self.logger.error(f"写入交易数据到PostgreSQL失败: {e}", exc_info=True)

        # 2. 写入Neo4j (交易网络拓扑)
        if self.neo4j_driver:
            async with self.neo4j_driver.session() as session:
                try:
                    # 过滤掉from或to地址为null的交易
                    valid_transactions = []
                    for tx in transactions:
                        from_addr = tx.get("from")
                        to_addr = tx.get("to")
                        if from_addr != "null" and to_addr != "null":
                            valid_transactions.append(tx)
                        else:
                            self.logger.warning(f"跳过无效交易: from={from_addr}, to={to_addr}, hash={tx.get('hash', 'unknown')}")
                    
                    if not valid_transactions:
                        self.logger.info(f"区块 {block_number} 没有有效的交易地址，跳过Neo4j写入")
                        return
                    
                    # 创建交易网络拓扑
                    await session.run("""
                        UNWIND $transactions as tx
                        MERGE (from_addr:Address {address: tx.from})
                        MERGE (to_addr:Address {address: tx.to})
                        MERGE (transaction:Transaction {
                            hash: tx.hash,
                            block_number: $block_number,
                            value: tx.value,
                            gas: tx.gas,
                            status: tx.status
                        })
                        MERGE (from_addr)-[:SENT]->(transaction)
                        MERGE (transaction)-[:RECEIVED_BY]->(to_addr)
                        MERGE (from_addr)-[r:TRANSACTED_WITH]->(to_addr)
                        ON CREATE SET r.count = 1, r.total_value = tx.value
                        ON MATCH SET r.count = r.count + 1, r.total_value = r.total_value + tx.value
                    """, transactions=valid_transactions, block_number=block_number)
                    self.logger.info(f"成功创建了区块 {block_number} 的 {len(valid_transactions)} 条交易网络拓扑。")
                except Exception as e:
                    self.logger.error(f"写入交易网络拓扑到Neo4j失败: {e}", exc_info=True)
    async def _process_contracts(self, data: CollectedData):
        """处理合约数据，写入PostgreSQL和Neo4j。"""
        block_number = data.data.get("block_number")
        contracts = data.data.get("contracts", [])
        contract_calls = data.data.get("contract_calls", [])
        events = data.data.get("events", [])

        # 1. 写入PostgreSQL
        if self.pg_pool and (contracts or events):
            async with self.pg_pool.acquire() as conn:
                # 1.1 批量写入合约创建记录到contracts表
                if contracts:
                    contract_records = []
                    for c in contracts:
                        contract_records.append((
                            c.get("address"),
                            c.get("creator"),
                            block_number,
                            c.get("creation_tx"),
                            c.get("bytecode_hash"),
                            c.get("contract_type", "Unknown"),
                            c.get("is_verified", False),
                            datetime.utcnow()
                        ))
                    
                    try:
                        await conn.executemany("""
                            INSERT INTO contracts (
                                contract_address, deployer_address, block_number, 
                                tx_hash, bytecode, contract_type, is_verified, created_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (contract_address) DO UPDATE SET
                                is_verified = EXCLUDED.is_verified,
                                contract_type = EXCLUDED.contract_type
                        """, contract_records)
                        self.logger.info(f"成功写入 {len(contract_records)} 条合约创建记录到PostgreSQL。")
                    except Exception as e:
                        self.logger.error(f"写入合约创建记录到PostgreSQL失败: {e}", exc_info=True)

                # 1.2 批量写入事件到现有的contract_events表（保持兼容性）
                if events:
                    event_records = [
                        (block_number, e.get("event_signature"), e.get("address"), json.dumps(e.get("args")), datetime.utcnow())
                        for e in events
                    ]
                    try:
                        await conn.executemany("""
                            INSERT INTO contract_events (block_number, event_name, contract_address, args, timestamp)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT DO NOTHING
                        """, event_records)
                        self.logger.info(f"成功写入 {len(event_records)} 条合约事件到PostgreSQL。")
                    except Exception as e:
                        self.logger.error(f"写入合约事件到PostgreSQL失败: {e}", exc_info=True)

                # 1.3 更新交易表中的合约创建地址
                if contracts:
                    update_records = [(c.get("address"), c.get("creation_tx")) for c in contracts]
                    try:
                        await conn.executemany("""
                            UPDATE transactions SET contract_address = $1 WHERE tx_hash = $2
                        """, update_records)
                        self.logger.info(f"成功更新 {len(update_records)} 条交易的合约地址。")
                    except Exception as e:
                        self.logger.error(f"更新交易合约地址失败: {e}", exc_info=True)

        # 2. 写入Neo4j (合约调用关系)
        if self.neo4j_driver and contract_calls:
            async with self.neo4j_driver.session() as session:
                try:
                    # 过滤掉from或to地址为null的合约调用
                    valid_calls = []
                    for call in contract_calls:
                        from_addr = call.get("from")
                        to_addr = call.get("to")
                        if from_addr and to_addr and from_addr != "null" and to_addr != "null":
                            valid_calls.append(call)
                        else:
                            self.logger.warning(f"跳过无效合约调用: from={from_addr}, to={to_addr}")
                    
                    if not valid_calls:
                        self.logger.info(f"没有有效的合约调用地址，跳过Neo4j写入")
                        return
                    
                    await session.run("""
                        UNWIND $calls as call
                        MERGE (caller:Address {address: call.from})
                        MERGE (contract:Contract {address: call.to})
                        MERGE (caller)-[r:CALLED_CONTRACT]->(contract)
                        ON CREATE SET r.call_count = 1, r.methods = [call.method]
                        ON MATCH SET r.call_count = r.call_count + 1, 
                                     r.methods = CASE WHEN NOT call.method IN r.methods THEN r.methods + call.method ELSE r.methods END
                    """, calls=valid_calls)
                    self.logger.info(f"成功更新/创建了 {len(valid_calls)} 条合约调用关系到Neo4j。")
                except Exception as e:
                    self.logger.error(f"写入合约调用关系到Neo4j失败: {e}", exc_info=True)


    async def _process_metrics(self, data: CollectedData):
        """处理性能指标数据，写入Redis Sorted Sets 以进行时序存储。"""
        if not self.redis_client: return
        
        metrics = data.data
        container_id = data.container_id
        timestamp = data.timestamp.timestamp() # Use Unix timestamp as score

        try:
            # 使用Redis Pipeline来批量执行命令，提高效率
            async with self.redis_client.pipeline() as pipe:
                for metric_type, values in metrics.items():
                    for key, value in values.items():
                        redis_key = f"metrics:{container_id}:{metric_type}:{key}"
                        member = json.dumps({"timestamp": timestamp, "value": value})
                        
                        # 添加新数据点
                        pipe.zadd(redis_key, {member: timestamp})
                        
                        # 清理旧数据（保留24小时）
                        cleanup_threshold = timestamp - (24 * 3600)
                        pipe.zremrangebyscore(redis_key, '-inf', cleanup_threshold)
                
                await pipe.execute()
            self.logger.info(f"成功写入来自 {container_id} 的性能指标到Redis。")
            
        except Exception as e:
            self.logger.error(f"写入性能指标到Redis失败: {e}", exc_info=True)


    async def _process_beacon_state(self, data: CollectedData):
        """处理常规信標鏈状态数据，写入Redis。"""
        if not self.redis_client: return
        
        state = data.data
        container_id = data.container_id
        
        try:
            async with self.redis_client.pipeline() as pipe:
                # 1. 存储顶层状态信息
                state_key = f"beacon:state:{container_id}"
                pipe.hset(state_key, mapping={
                    "latest_slot": state.get("latest_slot", 0),
                    "tracked_blocks_count": state.get("tracked_blocks_count", 0),
                    "last_update": data.timestamp.isoformat()
                })
                
                # 2. 存储最近区块快照
                blocks_key = f"beacon:latest_blocks:{container_id}"
                if state.get("latest_blocks"):
                    # 从列表头部插入，并保留最新的50个
                    pipe.lpush(blocks_key, *[json.dumps(b) for b in state["latest_blocks"]])
                    pipe.ltrim(blocks_key, 0, 49)

                # 3. 存储提议者信息
                proposers_key = f"beacon:proposers:{container_id}"
                if state.get("proposers_by_epoch"):
                    pipe.set(proposers_key, json.dumps(state.get("proposers_by_epoch")))

                await pipe.execute()
            self.logger.info(f"成功处理了来自 {container_id} 的信标链状态更新。")
        except Exception as e:
            self.logger.error(f"写入信标链状态到Redis失败: {e}", exc_info=True)

    
    async def _process_fork_event(self, data: CollectedData):
        """处理分叉事件，写入PostgreSQL并发布到Redis Pub/Sub。"""
        fork_event = data.data
        self.logger.warning(f"侦测到分叉事件: {data.container_id}, slot: {fork_event.get('slot')}")
        
        # 1. 写入PostgreSQL
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO fork_events (
                            fork_id, detection_time, slot, fork_type, 
                            resolution_status, details
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (fork_id) DO UPDATE SET
                            resolution_status = EXCLUDED.resolution_status,
                            details = EXCLUDED.details;
                    """,
                        fork_event.get("fork_id"),
                        datetime.fromtimestamp(fork_event.get("detection_time")),
                        fork_event.get("slot"),
                        fork_event.get("fork_type"),
                        fork_event.get("resolution_status"),
                        json.dumps(fork_event)
                    )
                self.logger.info(f"成功将分叉事件 {fork_event.get('fork_id')} 写入PostgreSQL。")
            except Exception as e:
                self.logger.error(f"写入分叉事件到PostgreSQL失败: {e}", exc_info=True)
        
        # 2. 发布到Redis Pub/Sub
        if self.redis_client:
            try:
                alert_payload = {
                    "event_type": "fork_detected",
                    "fork_id": fork_event.get("fork_id"),
                    "slot": fork_event.get("slot"),
                    "confidence": fork_event.get("confidence"),
                    "witness_node": data.container_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.redis_client.publish("fork_alerts", json.dumps(alert_payload))
                self.logger.info(f"已将分叉事件 {fork_event.get('fork_id')} 发布到Redis频道 'fork_alerts'。")
            except Exception as e:
                self.logger.error(f"发布分叉事件到Redis失败: {e}", exc_info=True)

    async def _process_node_snapshots(self, data: CollectedData):
        """处理节点快照数据，写入PostgreSQL。"""
        if not self.pg_pool:
            self.logger.warning("PostgreSQL未连接，跳过节点快照数据处理")
            return
            
        snapshot_data = data.data
        
        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO node_snapshots (node_id, timestamp, data)
                    VALUES ($1, $2, $3)
                """, 
                    data.node_id,
                    data.timestamp,
                    json.dumps(snapshot_data)
                )
            self.logger.info(f"成功写入节点快照数据: {data.node_id}")
        except Exception as e:
            self.logger.error(f"写入节点快照数据失败: {e}", exc_info=True)

    async def _process_beacon_blocks(self, data: CollectedData):
        """处理信标链区块数据，写入PostgreSQL和Redis。"""
        if not data.data:
            return
            
        # 处理单个区块或区块列表
        blocks = data.data if isinstance(data.data, list) else [data.data]
        
        # 1. 写入PostgreSQL的beacon_blocks表
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    for block in blocks:
                        try:
                            # 插入到Foundation层期望的beacon_blocks表
                            await conn.execute("""
                                INSERT INTO beacon_blocks (
                                    slot, hash, parent_hash, proposer_index, timestamp,
                                    state_root, attestations, attestation_count, discovery_time,
                                    source_node_ip, potential_fork, fork_confidence, competing_blocks,
                                    block_number
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                                ON CONFLICT (hash) DO UPDATE SET
                                    attestation_count = EXCLUDED.attestation_count,
                                    potential_fork = EXCLUDED.potential_fork,
                                    fork_confidence = EXCLUDED.fork_confidence,
                                    competing_blocks = EXCLUDED.competing_blocks
                            """, 
                                block.get('slot', 0),
                                block.get('hash', ''),
                                block.get('parent_hash', ''),
                                block.get('proposer_index', -1),
                                block.get('timestamp', time.time()),
                                block.get('state_root', ''),
                                block.get('attestations', ''),
                                block.get('attestation_count', 0),
                                block.get('discovery_time', time.time()),
                                data.local_ip or '127.0.0.1',
                                block.get('potential_fork', False),
                                block.get('fork_confidence', 0.0),
                                json.dumps(block.get('competing_blocks', [])),
                                block.get('slot', 0)  # block_number = slot
                            )
                            
                            # 使用区块链处理器进行分叉检测
                            if self.blockchain_processor:
                                await self.blockchain_processor.process_block_data(block, data.node_id)
                                
                        except Exception as e:
                            self.logger.error(f"写入单个区块失败: {e}, 区块数据: {block}")
                            continue
                            
                    self.logger.info(f"成功写入 {len(blocks)} 个信标链区块到PostgreSQL")
                    
            except Exception as e:
                self.logger.error(f"处理信标链区块数据失败: {e}", exc_info=True)
        
        # 2. 写入Redis缓存
        if self.redis_client:
            try:
                async with self.redis_client.pipeline() as pipe:
                    for block in blocks:
                        block_key = f"beacon:block:{block.get('hash', 'unknown')}"
                        pipe.hset(block_key, mapping={
                            'slot': block.get('slot', 0),
                            'hash': block.get('hash', ''),
                            'parent_hash': block.get('parent_hash', ''),
                            'proposer': block.get('proposer_index', ''),
                            'node_id': data.node_id,
                            'timestamp': data.timestamp.isoformat()
                        })
                        pipe.expire(block_key, 3600)  # 1小时过期
                    await pipe.execute()
                self.logger.info(f"成功缓存 {len(blocks)} 个信标链区块")
            except Exception as e:
                self.logger.error(f"缓存信标链区块数据失败: {e}", exc_info=True)

    async def _process_attestations(self, data: CollectedData):
        """处理证明数据，写入PostgreSQL的attestations表。"""
        if not data.data:
            return
            
        # 处理单个证明或证明列表
        attestations = data.data if isinstance(data.data, list) else [data.data]
        
        # 写入PostgreSQL的attestations表
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    attestation_records = []
                    for att in attestations:
                        try:
                            attestation_records.append((
                                att.get('attestation_id', f"att_{att.get('slot', 0)}_{att.get('committee_index', 0)}"),
                                att.get('slot', 0),
                                att.get('committee_index', 0),
                                att.get('beacon_block_root', ''),
                                att.get('source_epoch', 0),
                                att.get('target_epoch', 0),
                                att.get('validator_indices', []),
                                att.get('aggregation_bits', ''),
                                att.get('signature', ''),
                                att.get('inclusion_slot'),
                                att.get('inclusion_delay'),
                                att.get('is_included', False),
                                att.get('validation_status', 'pending'),
                                att.get('processing_time', 0.0),
                                data.timestamp
                            ))
                        except Exception as e:
                            self.logger.error(f"处理单个证明数据失败: {e}, 证明数据: {att}")
                            continue
                    
                    if attestation_records:
                        await conn.executemany("""
                            INSERT INTO attestations (
                                attestation_id, slot, committee_index, beacon_block_root,
                                source_epoch, target_epoch, validator_indices, aggregation_bits,
                                signature, inclusion_slot, inclusion_delay, is_included,
                                validation_status, processing_time, timestamp
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                            ON CONFLICT (attestation_id) DO UPDATE SET
                                inclusion_slot = EXCLUDED.inclusion_slot,
                                inclusion_delay = EXCLUDED.inclusion_delay,
                                is_included = EXCLUDED.is_included,
                                validation_status = EXCLUDED.validation_status,
                                processing_time = EXCLUDED.processing_time
                        """, attestation_records)
                        
                        self.logger.info(f"成功写入 {len(attestation_records)} 条证明记录到PostgreSQL")
                    
            except Exception as e:
                self.logger.error(f"处理证明数据失败: {e}", exc_info=True)

    # ===== 故障节点处理方法（委托给 NodeManager） =====
    
    async def mark_node_inactive_in_neo4j(self, node_id: str, container_id: str):
        """在Neo4j中删除故障节点及其所有关系（使用DETACH DELETE）"""
        await self.node_manager.mark_node_inactive_in_neo4j(node_id, container_id)
    
    async def delete_nodes_by_container(self, container_id: str):
        """根据容器ID删除Neo4j中关联的执行层与共识层节点"""
        await self.node_manager.delete_nodes_by_container(container_id)
    
    async def delete_nodes_by_ip(self, ip_address: str, container_id: str):
        """根据IP地址删除Neo4j中的所有相关节点（执行层和共识层）"""
        await self.node_manager.delete_nodes_by_ip(ip_address, container_id)
    
    async def record_node_failure_in_postgres(self, container_id: str, node_id: str):
        """在PostgreSQL中记录节点故障事件"""
        await self.node_manager.record_node_failure_in_postgres(container_id, node_id)
    
    async def cleanup_node_state_in_redis(self, node_id: str):
        """清理Redis中的节点状态缓存"""
        await self.node_manager.cleanup_node_state_in_redis(node_id)
    
    async def send_node_removed_event(self, node_id: str, container_id: str):
        """发送节点移除事件到拓扑变化系统"""
        await self.node_manager.send_node_removed_event(node_id, container_id)

    async def close(self):
        """关闭所有数据库连接。"""
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            self.logger.info("Neo4j连接已关闭")
        if self.pg_pool:
            await self.pg_pool.close()
            self.logger.info("PostgreSQL连接池已关闭")
        if self.redis_client:
            await self.redis_client.close()
            self.logger.info("Redis连接已关闭") 