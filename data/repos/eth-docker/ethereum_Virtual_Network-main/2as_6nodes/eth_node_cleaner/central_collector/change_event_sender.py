"""
变化事件发送器模块

负责将检测到的拓扑变化事件发送到不同的存储系统：
- PostgreSQL: 持久化存储变化事件
- Redis: 实时事件流和通知
"""

import json
import logging
import uuid
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ChangeEventSender:
    """变化事件发送器 - 向PostgreSQL和Redis发送拓扑变化事件"""
    
    def __init__(self, redis_client, postgresql_client):
        """
        初始化变化事件发送器
        
        Args:
            redis_client: Redis客户端
            postgresql_client: PostgreSQL客户端
        """
        self.redis_client = redis_client
        self.postgresql_client = postgresql_client
        
        logger.info("变化事件发送器初始化完成")
    
    async def send_topology_changes(self, changes: List[dict]):
        """
        批量发送拓扑变化事件
        
        Args:
            changes: 变化事件列表
        """
        if not changes:
            return
        
        execution_changes = []
        consensus_changes = []
        
        # 按层级分类变化事件
        for change in changes:
            if change.get('layer') == 'execution':
                execution_changes.append(change)
            elif change.get('layer') == 'consensus':
                consensus_changes.append(change)
        
        # 分别发送执行层和共识层变化
        if execution_changes:
            await self.send_execution_changes(execution_changes)
        
        if consensus_changes:
            await self.send_consensus_changes(consensus_changes)
        
        # 更新Redis事件流
        await self.update_redis_change_stream(changes)
        
        logger.info(f"成功发送 {len(changes)} 个拓扑变化事件")
    
    async def send_execution_changes(self, changes: List[dict]):
        """
        发送执行层变化事件到PostgreSQL
        
        Args:
            changes: 执行层变化事件列表
        """
        try:
            for change in changes:
                await self.send_execution_change_event(change)
        except Exception as e:
            logger.error(f"发送执行层变化事件失败: {e}")
    
    async def send_consensus_changes(self, changes: List[dict]):
        """
        发送共识层变化事件到PostgreSQL
        
        Args:
            changes: 共识层变化事件列表
        """
        try:
            for change in changes:
                await self.send_consensus_change_event(change)
        except Exception as e:
            logger.error(f"发送共识层变化事件失败: {e}")
    
    async def send_execution_change_event(self, change_event: dict):
        """
        发送单个执行层变化事件到PostgreSQL
        
        Args:
            change_event: 执行层变化事件
        """
        try:
            # 生成唯一事件ID
            event_id = str(uuid.uuid4())
            
            # 准备PostgreSQL插入数据
            sql_data = self._prepare_execution_change_data(change_event, event_id)
            
            # 首先插入到主变化表，获取生成的ID
            main_id = await self._insert_execution_topology_change(sql_data)
            
            # 使用主表ID插入到子表
            if change_event.get('change_type') in ['node_added', 'node_removed', 'node_updated']:
                await self._insert_execution_node_change(sql_data, main_id)
            elif change_event.get('change_type') in ['link_added', 'link_removed']:
                await self._insert_execution_link_change(sql_data, main_id)
            
            logger.debug(f"执行层变化事件已发送: {event_id}")
            
        except Exception as e:
            logger.error(f"发送执行层变化事件失败: {e}")
    
    async def send_consensus_change_event(self, change_event: dict):
        """
        发送单个共识层变化事件到PostgreSQL
        
        Args:
            change_event: 共识层变化事件
        """
        try:
            # 生成唯一事件ID
            event_id = str(uuid.uuid4())
            
            # 准备PostgreSQL插入数据
            sql_data = self._prepare_consensus_change_data(change_event, event_id)
            
            # 首先插入到主变化表，获取生成的ID
            main_id = await self._insert_consensus_topology_change(sql_data)
            
            # 使用主表ID插入到子表
            change_type = change_event.get('change_type') or ''
            if change_type.startswith('validator_'):
                await self._insert_consensus_validator_change(sql_data, main_id)
            elif change_type in ['node_added', 'node_removed', 'node_updated']:
                await self._insert_consensus_node_change(sql_data, main_id)
            elif change_type in ['link_added', 'link_removed']:
                await self._insert_consensus_link_change(sql_data, main_id)
            
            logger.debug(f"共识层变化事件已发送: {event_id}")
            
        except Exception as e:
            logger.error(f"发送共识层变化事件失败: {e}")
    
    def _prepare_execution_change_data(self, change_event: dict, event_id: str) -> dict:
        """准备执行层变化数据"""
        # 确保时间戳是 datetime 对象，不是字符串
        timestamp = change_event.get('timestamp')
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        elif timestamp is None:
            timestamp = datetime.now()
            
        return {
            'event_id': event_id,
            'timestamp': timestamp,
            'change_type': change_event.get('change_type'),
            'source_node': change_event.get('source_node') or change_event.get('node_id'),
            'target_node': change_event.get('target_node'),
            'change_data': json.dumps(change_event.get('change_data', {})),
            'impact_score': change_event.get('impact_score', 0.0),
            'metadata': json.dumps({
                'layer': 'execution',
                'detector_version': '4.2.0',
                'original_event': change_event
            })
        }
    
    def _prepare_consensus_change_data(self, change_event: dict, event_id: str) -> dict:
        """准备共识层变化数据"""
        # 确保时间戳是 datetime 对象，不是字符串
        timestamp = change_event.get('timestamp')
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        elif timestamp is None:
            timestamp = datetime.now()
            
        return {
            'event_id': event_id,
            'timestamp': timestamp,
            'change_type': change_event.get('change_type'),
            'source_node': change_event.get('source_node') or change_event.get('node_id'),
            'target_node': change_event.get('target_node'),
            'validator_index': change_event.get('validator_index'),
            'change_data': json.dumps(change_event.get('change_data', {})),
            'consensus_impact': json.dumps(change_event.get('consensus_impact', {})),
            'metadata': json.dumps({
                'layer': 'consensus',
                'detector_version': '4.2.0',
                'original_event': change_event
            })
        }
    
    async def _insert_execution_topology_change(self, data: dict):
        """插入执行层主变化表并返回生成的ID"""
        # 临时修复：使用现有的snapshot ID (1)，而不是时间戳
        # TODO: 未来应该在插入前创建snapshot记录
        snapshot_id = 1  # 使用现有的snapshot ID
        
        sql = """
        INSERT INTO eth_execution_topology_changes 
        (event_id, timestamp, change_type, after_snapshot_id, diff_data, metadata, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """
        
        result = await self.postgresql_client.fetchval(
            sql,
            data['event_id'],
            data['timestamp'],
            data['change_type'],
            snapshot_id,
            data['change_data'],
            data['metadata'],
            'topology_change_detector'
        )
        return result
    
    async def _insert_execution_node_change(self, data: dict, change_event_id: int):
        """插入执行层节点变化表"""
        sql = """
        INSERT INTO eth_execution_node_changes 
        (change_event_id, node_id, change_type, old_data, new_data, timestamp)
        VALUES ($1, $2, $3, $4, $5, $6)
        """
        
        # 解析change_data中的old_data和new_data
        change_data = json.loads(data['change_data']) if isinstance(data['change_data'], str) else data['change_data']
        
        await self.postgresql_client.execute(
            sql,
            change_event_id,
            data['source_node'],
            data['change_type'],
            json.dumps(change_data.get('old_value')),
            json.dumps(change_data.get('new_value')),
            data['timestamp']
        )
    
    async def _insert_execution_link_change(self, data: dict, change_event_id: int):
        """插入执行层连接变化表"""
        sql = """
        INSERT INTO eth_execution_link_changes 
        (change_event_id, change_type, source_node_id, target_node_id, old_data, new_data, timestamp)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        
        # 解析change_data中的old_data和new_data
        change_data = json.loads(data['change_data']) if isinstance(data['change_data'], str) else data['change_data']
        
        await self.postgresql_client.execute(
            sql,
            change_event_id,
            data['change_type'],
            data['source_node'],
            data['target_node'],
            json.dumps(change_data.get('peer_info')),
            json.dumps(change_data.get('peer_info')),
            data['timestamp']
        )
    
    async def _insert_consensus_topology_change(self, data: dict):
        """插入共识层主变化表并返回生成的ID"""
        # 临时修复：使用现有的snapshot ID (1)，而不是时间戳
        # TODO: 未来应该在插入前创建snapshot记录
        snapshot_id = 1  # 使用现有的snapshot ID
        
        sql = """
        INSERT INTO eth_consensus_topology_changes 
        (event_id, timestamp, change_type, after_snapshot_id, diff_data, metadata, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """
        
        result = await self.postgresql_client.fetchval(
            sql,
            data['event_id'],
            data['timestamp'],
            data['change_type'],
            snapshot_id,
            data['change_data'],
            data['metadata'],
            'topology_change_detector'
        )
        return result
    
    async def _insert_consensus_node_change(self, data: dict, change_event_id: int):
        """插入共识层节点变化表"""
        sql = """
        INSERT INTO eth_consensus_node_changes 
        (change_event_id, node_id, change_type, old_data, new_data, timestamp)
        VALUES ($1, $2, $3, $4, $5, $6)
        """
        
        # 解析change_data中的old_data和new_data
        change_data = json.loads(data['change_data']) if isinstance(data['change_data'], str) else data['change_data']
        
        await self.postgresql_client.execute(
            sql,
            change_event_id,
            data['source_node'],
            data['change_type'],
            json.dumps(change_data.get('old_value')),
            json.dumps(change_data.get('new_value')),
            data['timestamp']
        )
    
    async def _insert_consensus_link_change(self, data: dict, change_event_id: int):
        """插入共识层连接变化表"""
        sql = """
        INSERT INTO eth_consensus_link_changes 
        (change_event_id, change_type, source_node_id, target_node_id, old_data, new_data, timestamp)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        
        # 解析change_data中的old_data和new_data
        change_data = json.loads(data['change_data']) if isinstance(data['change_data'], str) else data['change_data']
        
        await self.postgresql_client.execute(
            sql,
            change_event_id,
            data['change_type'],
            data['source_node'],
            data['target_node'],
            json.dumps(change_data.get('peer_info')),
            json.dumps(change_data.get('peer_info')),
            data['timestamp']
        )
    
    async def _insert_consensus_validator_change(self, data: dict, change_event_id: int):
        """插入共识层验证器变化（复用节点变化表，添加validator_index）"""
        # 验证器变化记录到节点变化表，在change_data中包含validator信息
        await self._insert_consensus_node_change(data, change_event_id)
    
    async def update_redis_change_stream(self, changes: List[dict]):
        """
        更新Redis变化流
        
        Args:
            changes: 变化事件列表
        """
        try:
            for change in changes:
                # 添加到Redis Stream
                stream_key = "topology:changes"
                await self.redis_client.xadd(
                    stream_key,
                    {
                        'event_type': 'topology_change',
                        'layer': change.get('layer', 'unknown'),
                        'change_type': change.get('change_type'),
                        'node_id': change.get('node_id') or change.get('source_node'),
                        'data': json.dumps(change),
                        'timestamp': change.get('timestamp', datetime.now().isoformat())
                    }
                )
                
                # 发布到特定频道
                channel = f"topology:changes:{change.get('layer', 'unknown')}"
                await self.redis_client.publish(channel, json.dumps(change))
            
            logger.debug(f"已更新Redis变化流: {len(changes)} 个事件")
            
        except Exception as e:
            logger.error(f"更新Redis变化流失败: {e}")
    
    async def send_heartbeat_event(self, change_summary: dict):
        """
        发送变化检测心跳事件
        
        Args:
            change_summary: 变化检测摘要信息
        """
        try:
            heartbeat_data = {
                'timestamp': datetime.now().isoformat(),
                'detector_status': 'active',
                'changes_detected': change_summary.get('total_changes', 0),
                'execution_changes': change_summary.get('execution_changes', 0),
                'consensus_changes': change_summary.get('consensus_changes', 0),
                'last_detection_time': change_summary.get('detection_time'),
                'detector_version': '4.2.0'
            }
            
            # 发送到Redis
            await self.redis_client.setex(
                'topology:detector:heartbeat',
                300,  # 5分钟过期
                json.dumps(heartbeat_data)
            )
            
            # 发布心跳事件
            await self.redis_client.publish(
                'topology:detector:status',
                json.dumps(heartbeat_data)
            )
            
        except Exception as e:
            logger.error(f"发送心跳事件失败: {e}") 