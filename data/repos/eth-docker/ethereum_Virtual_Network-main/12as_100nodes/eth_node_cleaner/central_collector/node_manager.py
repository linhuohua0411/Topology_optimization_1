#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
节点生命周期管理器
负责节点的删除、故障记录、状态清理等操作
"""

import logging
from typing import Optional
from datetime import datetime

import asyncpg
from neo4j import AsyncDriver
from redis import asyncio as aioredis

from .change_event_sender import ChangeEventSender


class NodeManager:
    """节点生命周期管理器"""
    
    def __init__(
        self,
        neo4j_driver: Optional[AsyncDriver],
        pg_pool: Optional[asyncpg.Pool],
        redis_client: Optional[aioredis.Redis],
        change_event_sender: Optional[ChangeEventSender]
    ):
        self.neo4j_driver = neo4j_driver
        self.pg_pool = pg_pool
        self.redis_client = redis_client
        self.change_event_sender = change_event_sender
        self.logger = logging.getLogger(__name__)
    
    async def mark_node_inactive_in_neo4j(self, node_id: str, container_id: str):
        """在Neo4j中删除故障节点及其所有关系（使用DETACH DELETE）"""
        if not self.neo4j_driver:
            return
        
        try:
            async with self.neo4j_driver.session() as session:
                exec_deleted = False
                cons_deleted = False
                
                # 先检查执行层节点是否存在，然后删除
                exec_check = await session.run("""
                    MATCH (n:ExecNode {node_id: $node_id})
                    RETURN n.node_id AS node_id
                    LIMIT 1
                """, node_id=node_id)
                
                exec_exists = False
                async for record in exec_check:
                    if record.get("node_id"):
                        exec_exists = True
                        break
                
                if exec_exists:
                    # 删除执行层节点及其所有关系（包括入边和出边）
                    await session.run("""
                        MATCH (n:ExecNode {node_id: $node_id})
                        DETACH DELETE n
                    """, node_id=node_id)
                    exec_deleted = True
                    self.logger.info(f"🗑️ 已删除执行层节点及其所有关系: {node_id} (容器: {container_id})")
                
                # 先检查共识层节点是否存在，然后删除
                cons_check = await session.run("""
                    MATCH (n:ConsNode {node_id: $node_id})
                    RETURN n.node_id AS node_id
                    LIMIT 1
                """, node_id=node_id)
                
                cons_exists = False
                async for record in cons_check:
                    if record.get("node_id"):
                        cons_exists = True
                        break
                
                if cons_exists:
                    # 删除共识层节点及其所有关系（包括入边和出边）
                    await session.run("""
                        MATCH (n:ConsNode {node_id: $node_id})
                        DETACH DELETE n
                    """, node_id=node_id)
                    cons_deleted = True
                    self.logger.info(f"🗑️ 已删除共识层节点及其所有关系: {node_id} (容器: {container_id})")
                
                if exec_deleted or cons_deleted:
                    self.logger.info(f"✅ 已删除故障节点: {node_id} (执行层: {exec_deleted}, 共识层: {cons_deleted}, 容器: {container_id})")
                else:
                    self.logger.warning(f"⚠️ 未找到节点 {node_id}，无法删除 (容器: {container_id})")
        except Exception as e:
            self.logger.error(f"删除节点失败: {e}", exc_info=True)
    
    async def delete_nodes_by_ip(self, ip_address: str, container_id: str):
        """根据IP地址删除Neo4j中的所有相关节点（执行层和共识层）"""
        if not self.neo4j_driver or not ip_address:
            return
        
        try:
            async with self.neo4j_driver.session() as session:
                exec_deleted = False
                cons_deleted = False
                
                # 删除执行层节点（根据IP地址）
                exec_check = await session.run("""
                    MATCH (n:ExecNode {ip: $ip})
                    RETURN n.node_id AS node_id, n.ip AS ip
                    LIMIT 10
                """, ip=ip_address)
                
                exec_nodes = []
                async for record in exec_check:
                    node_id = record.get("node_id")
                    if node_id:
                        exec_nodes.append(node_id)
                
                if exec_nodes:
                    # 删除所有匹配的执行层节点及其所有关系
                    await session.run("""
                        MATCH (n:ExecNode {ip: $ip})
                        DETACH DELETE n
                    """, ip=ip_address)
                    exec_deleted = True
                    self.logger.info(f"🗑️ 已根据IP删除执行层节点: {ip_address} (节点数: {len(exec_nodes)}, 容器: {container_id})")
                
                # 删除共识层节点（根据IP地址）
                cons_check = await session.run("""
                    MATCH (n:ConsNode {ip: $ip})
                    RETURN n.node_id AS node_id, n.ip AS ip
                    LIMIT 10
                """, ip=ip_address)
                
                cons_nodes = []
                async for record in cons_check:
                    node_id = record.get("node_id")
                    if node_id:
                        cons_nodes.append(node_id)
                
                if cons_nodes:
                    # 删除所有匹配的共识层节点及其所有关系
                    await session.run("""
                        MATCH (n:ConsNode {ip: $ip})
                        DETACH DELETE n
                    """, ip=ip_address)
                    cons_deleted = True
                    self.logger.info(f"🗑️ 已根据IP删除共识层节点: {ip_address} (节点数: {len(cons_nodes)}, 容器: {container_id})")
                
                if exec_deleted or cons_deleted:
                    self.logger.info(f"✅ 已根据IP删除故障节点: {ip_address} (执行层: {len(exec_nodes)}, 共识层: {len(cons_nodes)}, 容器: {container_id})")
                else:
                    self.logger.debug(f"未找到IP {ip_address} 对应的节点 (容器: {container_id})")
        except Exception as e:
            self.logger.error(f"根据IP删除节点失败: {e}", exc_info=True)
    
    async def delete_nodes_by_container(self, container_id: str):
        """根据容器ID删除Neo4j中的执行层和共识层节点"""
        if not self.neo4j_driver or not container_id:
            return
        
        try:
            async with self.neo4j_driver.session() as session:
                exec_deleted = 0
                cons_deleted = 0
                
                exec_result = await session.run("""
                    MATCH (n:ExecNode {container_id: $container_id})
                    WITH collect(n) AS nodes
                    FOREACH (node IN nodes | DETACH DELETE node)
                    RETURN size(nodes) AS deleted_count
                """, container_id=container_id)
                exec_record = await exec_result.single()
                if exec_record:
                    exec_deleted = exec_record.get("deleted_count", 0)
                
                cons_result = await session.run("""
                    MATCH (n:ConsNode {container_id: $container_id})
                    WITH collect(n) AS nodes
                    FOREACH (node IN nodes | DETACH DELETE node)
                    RETURN size(nodes) AS deleted_count
                """, container_id=container_id)
                cons_record = await cons_result.single()
                if cons_record:
                    cons_deleted = cons_record.get("deleted_count", 0)
                
                if exec_deleted or cons_deleted:
                    self.logger.info(
                        f"🗑️ 已根据容器ID删除节点: {container_id} "
                        f"(执行层: {exec_deleted}, 共识层: {cons_deleted})"
                    )
                else:
                    self.logger.debug(f"未找到容器 {container_id} 对应的节点记录")
        except Exception as e:
            self.logger.error(f"根据容器ID删除节点失败: {e}", exc_info=True)
    
    async def record_node_failure_in_postgres(self, container_id: str, node_id: str):
        """在PostgreSQL中记录节点故障事件"""
        if not self.pg_pool:
            return
        
        try:
            async with self.pg_pool.acquire() as conn:
                # 检查是否存在 node_failures 表，如果不存在则跳过
                try:
                    await conn.execute("""
                        INSERT INTO node_failures (
                            container_id, node_id, failure_time, failure_type, status
                        ) VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (container_id, node_id) DO UPDATE SET
                            failure_time = EXCLUDED.failure_time,
                            status = EXCLUDED.status
                    """, 
                        container_id,
                        node_id,
                        datetime.utcnow(),
                        'heartbeat_timeout',
                        'inactive'
                    )
                    self.logger.info(f"已记录节点故障事件: {container_id} (node_id: {node_id})")
                except asyncpg.exceptions.UndefinedTableError:
                    # 如果表不存在，只记录警告，不抛出异常
                    self.logger.warning(f"node_failures 表不存在，跳过记录节点故障事件: {container_id}")
                except Exception as e:
                    self.logger.error(f"记录节点故障事件失败: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"记录节点故障事件失败: {e}", exc_info=True)
    
    async def cleanup_node_state_in_redis(self, node_id: str):
        """清理Redis中的节点状态缓存"""
        if not self.redis_client:
            return
        
        try:
            # 清理执行层状态
            exec_state_key = f"topology:execution_state:{node_id}"
            await self.redis_client.delete(exec_state_key)
            
            # 清理共识层状态
            cons_state_key = f"topology:consensus_state:{node_id}"
            await self.redis_client.delete(cons_state_key)
            
            # 从活跃节点列表中移除
            await self.redis_client.srem("topology:active_nodes:execution", node_id)
            await self.redis_client.srem("topology:active_nodes:consensus", node_id)
            
            self.logger.info(f"已清理Redis中的节点状态: {node_id}")
        except Exception as e:
            self.logger.error(f"清理Redis节点状态失败: {e}", exc_info=True)
    
    async def send_node_removed_event(self, node_id: str, container_id: str):
        """发送节点移除事件到拓扑变化系统"""
        if not self.change_event_sender:
            return
        
        try:
            # 尝试确定节点层级 - 查询Neo4j来确定节点类型
            node_layers = []
            if self.neo4j_driver:
                async with self.neo4j_driver.session() as session:
                    # 检查是否是执行层节点
                    exec_result = await session.run("""
                        MATCH (n:ExecNode {node_id: $node_id})
                        RETURN n.node_id AS node_id
                        LIMIT 1
                    """, node_id=node_id)
                    
                    async for record in exec_result:
                        if record.get("node_id"):
                            node_layers.append('execution')
                            break
                    
                    # 检查是否是共识层节点
                    cons_result = await session.run("""
                        MATCH (n:ConsNode {node_id: $node_id})
                        RETURN n.node_id AS node_id
                        LIMIT 1
                    """, node_id=node_id)
                    
                    async for record in cons_result:
                        if record.get("node_id"):
                            node_layers.append('consensus')
                            break
            
            # 如果没有找到节点，默认发送到两个层级
            if not node_layers:
                node_layers = ['execution', 'consensus']
                self.logger.warning(f"未在Neo4j中找到节点 {node_id}，将向所有层级发送移除事件")
            
            # 构造变化事件
            change_event = {
                'change_type': 'node_removed',
                'node_id': node_id,
                'source_node': node_id,
                'layer': node_layers[0] if len(node_layers) == 1 else 'unknown',
                'change_data': {
                    'container_id': container_id,
                    'reason': 'heartbeat_timeout',
                    'removed_at': datetime.now().isoformat()
                },
                'impact_score': 0.8,
                'timestamp': datetime.now().isoformat(),
                'source': 'heartbeat_checker'
            }
            
            # 发送到相应的层级
            for layer in node_layers:
                if layer == 'execution':
                    await self.change_event_sender.send_execution_change_event(change_event)
                elif layer == 'consensus':
                    await self.change_event_sender.send_consensus_change_event(change_event)
            
            self.logger.info(f"已发送节点移除事件: {node_id} (层级: {', '.join(node_layers)})")
        except Exception as e:
            self.logger.error(f"发送节点移除事件失败: {e}", exc_info=True)

