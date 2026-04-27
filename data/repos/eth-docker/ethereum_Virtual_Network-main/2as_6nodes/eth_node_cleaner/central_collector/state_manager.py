"""
状态管理器模块

负责管理拓扑状态的缓存和持久化：
- Redis状态缓存管理
- 历史状态查询优化
- 状态变化追踪
"""

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class StateManager:
    """状态管理器 - 管理拓扑状态缓存和历史查询"""
    
    def __init__(self, redis_client, postgresql_client):
        """
        初始化状态管理器
        
        Args:
            redis_client: Redis客户端
            postgresql_client: PostgreSQL客户端
        """
        self.redis_client = redis_client
        self.postgresql_client = postgresql_client
        
        # 缓存配置
        self.state_ttl = 3600  # 状态缓存1小时过期
        self.history_ttl = 86400  # 历史数据缓存24小时过期
        
        logger.info("状态管理器初始化完成")
    
    async def save_execution_state(self, node_id: str, state: dict):
        """
        保存执行层状态到Redis
        
        Args:
            node_id: 节点ID
            state: 节点状态数据
        """
        try:
            cache_key = f"topology:execution_state:{node_id}"
            
            # 添加时间戳
            state_with_timestamp = {
                **state,
                'last_updated': datetime.now().isoformat(),
                'cache_version': '4.2.0'
            }
            
            # 保存到Redis
            await self.redis_client.setex(
                cache_key, 
                self.state_ttl, 
                json.dumps(state_with_timestamp)
            )
            
            # 更新节点列表
            await self._update_active_nodes_list('execution', node_id)
            
            logger.debug(f"执行层状态已保存: {node_id}")
            
        except Exception as e:
            logger.error(f"保存执行层状态失败 {node_id}: {e}")
    
    async def get_execution_state(self, node_id: str) -> dict:
        """
        从Redis获取执行层状态
        
        Args:
            node_id: 节点ID
            
        Returns:
            dict: 节点状态数据，如果不存在则返回空字典
        """
        try:
            cache_key = f"topology:execution_state:{node_id}"
            state_data = await self.redis_client.get(cache_key)
            
            if state_data:
                return json.loads(state_data)
            
            # 如果Redis中没有，尝试从PostgreSQL获取最近状态
            return await self._get_recent_state_from_db(node_id, 'execution')
            
        except Exception as e:
            logger.error(f"获取执行层状态失败 {node_id}: {e}")
            return {}
    
    async def save_consensus_state(self, node_id: str, state: dict):
        """
        保存共识层状态到Redis
        
        Args:
            node_id: 节点ID
            state: 节点状态数据
        """
        try:
            cache_key = f"topology:consensus_state:{node_id}"
            
            # 添加时间戳和验证器摘要
            state_with_metadata = {
                **state,
                'last_updated': datetime.now().isoformat(),
                'cache_version': '4.2.0',
                'validator_count': len(state.get('validators', [])),
                'peer_count': len(state.get('peers', []))
            }
            
            # 保存到Redis
            await self.redis_client.setex(
                cache_key, 
                self.state_ttl, 
                json.dumps(state_with_metadata)
            )
            
            # 更新节点列表
            await self._update_active_nodes_list('consensus', node_id)
            
            # 更新验证器索引
            if state.get('validators'):
                await self._update_validator_index(node_id, state['validators'])
            
            logger.debug(f"共识层状态已保存: {node_id}")
            
        except Exception as e:
            logger.error(f"保存共识层状态失败 {node_id}: {e}")
    
    async def get_consensus_state(self, node_id: str) -> dict:
        """
        从Redis获取共识层状态
        
        Args:
            node_id: 节点ID
            
        Returns:
            dict: 节点状态数据，如果不存在则返回空字典
        """
        try:
            cache_key = f"topology:consensus_state:{node_id}"
            state_data = await self.redis_client.get(cache_key)
            
            if state_data:
                return json.loads(state_data)
            
            # 如果Redis中没有，尝试从PostgreSQL获取最近状态
            return await self._get_recent_state_from_db(node_id, 'consensus')
            
        except Exception as e:
            logger.error(f"获取共识层状态失败 {node_id}: {e}")
            return {}
    
    async def get_all_execution_states(self) -> Dict[str, dict]:
        """
        获取所有执行层节点状态
        
        Returns:
            Dict[str, dict]: 所有执行层节点状态，键为node_id
        """
        try:
            # 获取活跃节点列表
            active_nodes = await self._get_active_nodes_list('execution')
            
            states = {}
            for node_id in active_nodes:
                state = await self.get_execution_state(node_id)
                if state:
                    states[node_id] = state
            
            return states
            
        except Exception as e:
            logger.error(f"获取所有执行层状态失败: {e}")
            return {}
    
    async def get_all_consensus_states(self) -> Dict[str, dict]:
        """
        获取所有共识层节点状态
        
        Returns:
            Dict[str, dict]: 所有共识层节点状态，键为node_id
        """
        try:
            # 获取活跃节点列表
            active_nodes = await self._get_active_nodes_list('consensus')
            
            states = {}
            for node_id in active_nodes:
                state = await self.get_consensus_state(node_id)
                if state:
                    states[node_id] = state
            
            return states
            
        except Exception as e:
            logger.error(f"获取所有共识层状态失败: {e}")
            return {}
    
    async def cleanup_expired_states(self):
        """清理过期状态缓存"""
        try:
            # Redis的TTL会自动清理过期数据，但我们需要清理活跃节点列表
            execution_nodes = await self._get_active_nodes_list('execution')
            consensus_nodes = await self._get_active_nodes_list('consensus')
            
            # 检查并移除不存在的节点
            valid_execution_nodes = []
            for node_id in execution_nodes:
                cache_key = f"topology:execution_state:{node_id}"
                if await self.redis_client.exists(cache_key):
                    valid_execution_nodes.append(node_id)
            
            valid_consensus_nodes = []
            for node_id in consensus_nodes:
                cache_key = f"topology:consensus_state:{node_id}"
                if await self.redis_client.exists(cache_key):
                    valid_consensus_nodes.append(node_id)
            
            # 更新活跃节点列表
            if valid_execution_nodes != execution_nodes:
                await self._set_active_nodes_list('execution', valid_execution_nodes)
            
            if valid_consensus_nodes != consensus_nodes:
                await self._set_active_nodes_list('consensus', valid_consensus_nodes)
            
            logger.debug("状态缓存清理完成")
            
        except Exception as e:
            logger.error(f"清理过期状态失败: {e}")
    
    async def get_state_statistics(self) -> dict:
        """
        获取状态管理器统计信息
        
        Returns:
            dict: 统计信息
        """
        try:
            execution_nodes = await self._get_active_nodes_list('execution')
            consensus_nodes = await self._get_active_nodes_list('consensus')
            
            # 获取验证器统计
            validator_stats = await self._get_validator_statistics()
            
            stats = {
                'execution_nodes_count': len(execution_nodes),
                'consensus_nodes_count': len(consensus_nodes),
                'total_validators': validator_stats.get('total_validators', 0),
                'active_validators': validator_stats.get('active_validators', 0),
                'cache_version': '4.2.0',
                'last_updated': datetime.now().isoformat()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取状态统计失败: {e}")
            return {}
    
    async def _update_active_nodes_list(self, layer: str, node_id: str):
        """更新活跃节点列表"""
        cache_key = f"topology:active_nodes:{layer}"
        await self.redis_client.sadd(cache_key, node_id)
        await self.redis_client.expire(cache_key, self.state_ttl)
    
    async def _get_active_nodes_list(self, layer: str) -> List[str]:
        """获取活跃节点列表"""
        cache_key = f"topology:active_nodes:{layer}"
        nodes = await self.redis_client.smembers(cache_key)
        return [node.decode() if isinstance(node, bytes) else node for node in nodes]
    
    async def _set_active_nodes_list(self, layer: str, nodes: List[str]):
        """设置活跃节点列表"""
        cache_key = f"topology:active_nodes:{layer}"
        await self.redis_client.delete(cache_key)
        if nodes:
            await self.redis_client.sadd(cache_key, *nodes)
            await self.redis_client.expire(cache_key, self.state_ttl)
    
    async def _update_validator_index(self, node_id: str, validators: List[dict]):
        """更新验证器索引"""
        try:
            for validator in validators:
                validator_index = validator.get('validator_index')
                if validator_index is not None:
                    # 保存验证器到节点的映射
                    cache_key = f"topology:validator_to_node:{validator_index}"
                    await self.redis_client.setex(cache_key, self.state_ttl, node_id)
                    
                    # 保存验证器状态摘要
                    validator_summary = {
                        'validator_index': validator_index,
                        'status': validator.get('status'),
                        'node_id': node_id,
                        'last_updated': datetime.now().isoformat()
                    }
                    summary_key = f"topology:validator_summary:{validator_index}"
                    await self.redis_client.setex(
                        summary_key, 
                        self.state_ttl, 
                        json.dumps(validator_summary)
                    )
        except Exception as e:
            logger.error(f"更新验证器索引失败: {e}")
    
    async def _get_validator_statistics(self) -> dict:
        """获取验证器统计信息"""
        try:
            # 从Redis获取验证器摘要
            validator_keys = []
            async for key in self.redis_client.scan_iter(match="topology:validator_summary:*"):
                validator_keys.append(key)
            
            total_validators = len(validator_keys)
            active_validators = 0
            
            for key in validator_keys[:100]:  # 限制检查数量避免性能问题
                summary_data = await self.redis_client.get(key)
                if summary_data:
                    summary = json.loads(summary_data)
                    if summary.get('status') == 'active_ongoing':
                        active_validators += 1
            
            return {
                'total_validators': total_validators,
                'active_validators': active_validators
            }
            
        except Exception as e:
            logger.error(f"获取验证器统计失败: {e}")
            return {}
    
    async def _get_recent_state_from_db(self, node_id: str, layer: str) -> dict:
        """
        从PostgreSQL获取最近的节点状态
        
        Args:
            node_id: 节点ID
            layer: 层级 ('execution' 或 'consensus')
            
        Returns:
            dict: 最近的状态数据
        """
        try:
            # 这里可以实现从PostgreSQL查询最近状态的逻辑
            # 暂时返回空字典，避免增加复杂性
            return {}
            
        except Exception as e:
            logger.error(f"从数据库获取最近状态失败 {node_id}: {e}")
            return {} 