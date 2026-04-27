"""
拓扑变化检测器模块

负责检测以太坊P2P网络拓扑的实时变化，包括：
- 执行层拓扑变化检测
- 共识层拓扑变化检测（含验证器）
- 变化类型识别和影响评估
"""

import json
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class TopologyChangeDetector:
    """拓扑变化检测器 - 检测P2P网络拓扑变化"""
    
    def __init__(self, redis_client, postgresql_client):
        """
        初始化拓扑变化检测器
        
        Args:
            redis_client: Redis客户端，用于状态缓存
            postgresql_client: PostgreSQL客户端，用于历史数据查询
        """
        self.redis_client = redis_client
        self.postgresql_client = postgresql_client
        self.execution_state_cache = {}  # 执行层状态缓存
        self.consensus_state_cache = {}  # 共识层状态缓存
        
        logger.info("拓扑变化检测器初始化完成")
    
    async def detect_execution_topology_changes(self, current_data: dict) -> List[dict]:
        """
        检测执行层拓扑变化
        
        Args:
            current_data: 当前执行层拓扑数据
            
        Returns:
            List[dict]: 检测到的变化事件列表
        """
        try:
            if not current_data or 'node' not in current_data:
                return []
            
            node_id = current_data['node'].get('node_id')
            if not node_id:
                return []
            
            # 获取历史状态
            previous_state = await self._get_execution_state(node_id)
            
            # 生成当前状态
            current_state = self._extract_execution_state(current_data)
            
            # 检测变化
            changes = []
            
            # 检测节点状态变化
            node_changes = self._detect_node_changes(
                previous_state.get('node', {}), 
                current_state.get('node', {}),
                'execution'
            )
            changes.extend(node_changes)
            
            # 检测连接变化
            peer_changes = self._detect_peer_changes(
                previous_state.get('peers', []), 
                current_state.get('peers', []),
                'execution',
                node_id
            )
            changes.extend(peer_changes)
            
            # 保存当前状态
            await self._save_execution_state(node_id, current_state)
            
            logger.debug(f"执行层拓扑变化检测完成: {node_id}, 发现 {len(changes)} 个变化")
            return changes
            
        except Exception as e:
            logger.error(f"执行层拓扑变化检测失败: {e}")
            return []
    
    async def detect_consensus_topology_changes(self, current_data: dict) -> List[dict]:
        """
        检测共识层拓扑变化（含验证器）
        
        Args:
            current_data: 当前共识层拓扑数据
            
        Returns:
            List[dict]: 检测到的变化事件列表
        """
        try:
            if not current_data or 'node' not in current_data:
                return []
            
            node_id = current_data['node'].get('node_id')
            if not node_id:
                return []
            
            # 获取历史状态
            previous_state = await self._get_consensus_state(node_id)
            
            # 生成当前状态
            current_state = self._extract_consensus_state(current_data)
            
            # 检测变化
            changes = []
            
            # 检测节点状态变化
            node_changes = self._detect_node_changes(
                previous_state.get('node', {}), 
                current_state.get('node', {}),
                'consensus'
            )
            changes.extend(node_changes)
            
            # 检测连接变化
            peer_changes = self._detect_peer_changes(
                previous_state.get('peers', []), 
                current_state.get('peers', []),
                'consensus',
                node_id
            )
            changes.extend(peer_changes)
            
            # 检测验证器变化
            validator_changes = self._detect_validator_changes(
                previous_state.get('validators', []), 
                current_state.get('validators', []),
                node_id
            )
            changes.extend(validator_changes)
            
            # 保存当前状态
            await self._save_consensus_state(node_id, current_state)
            
            logger.debug(f"共识层拓扑变化检测完成: {node_id}, 发现 {len(changes)} 个变化")
            return changes
            
        except Exception as e:
            logger.error(f"共识层拓扑变化检测失败: {e}")
            return []
    
    def _extract_execution_state(self, data: dict) -> dict:
        """提取执行层状态信息"""
        node_info = data.get('node', {})
        peers_info = data.get('peers', [])
        
        # 标准化节点信息
        node_state = {
            'node_id': node_info.get('node_id'),
            'client_type': node_info.get('client_type'),
            'client_version': node_info.get('client_version'),
            'ip': node_info.get('ip'),
            'ports': node_info.get('ports', {}),
            'network_id': node_info.get('network_id'),
            'protocols': node_info.get('protocols', {})
        }
        
        # 标准化对等节点信息
        peers_state = []
        for peer in peers_info:
            peer_state = {
                'peer_id': peer.get('peer_id'),
                'ip': peer.get('ip'),
                'direction': peer.get('direction')
            }
            peers_state.append(peer_state)
        
        return {
            'node': node_state,
            'peers': peers_state,
            'timestamp': datetime.now().isoformat()
        }
    
    def _extract_consensus_state(self, data: dict) -> dict:
        """提取共识层状态信息"""
        node_info = data.get('node', {})
        peers_info = data.get('peers', [])
        validators_info = data.get('validators', [])
        
        # 标准化节点信息
        node_state = {
            'node_id': node_info.get('node_id'),
            'client_type': node_info.get('client_type'),
            'client_version': node_info.get('client_version'),
            'p2p_addresses': node_info.get('p2p_addresses', []),
            'sync_status': node_info.get('sync_status', {}),
            'subscribed_subnets': node_info.get('subscribed_subnets', {})
        }
        
        # 标准化对等节点信息
        peers_state = []
        for peer in peers_info:
            peer_state = {
                'peer_id': peer.get('peer_id'),
                'ip': peer.get('ip'),
                'direction': peer.get('direction')
            }
            peers_state.append(peer_state)
        
        # 标准化验证器信息
        validators_state = []
        for validator in validators_info:
            validator_state = {
                'validator_index': validator.get('validator_index'),
                'public_key': validator.get('public_key'),
                'status': validator.get('status'),
                'balance': validator.get('balance'),
                'effective_balance': validator.get('effective_balance'),
                'current_duties': validator.get('current_duties', {})
            }
            validators_state.append(validator_state)
        
        return {
            'node': node_state,
            'peers': peers_state,
            'validators': validators_state,
            'timestamp': datetime.now().isoformat()
        }
    
    def _detect_node_changes(self, previous_node: dict, current_node: dict, layer: str) -> List[dict]:
        """检测节点状态变化"""
        changes = []
        
        if not previous_node:
            # 新节点
            changes.append({
                'change_type': 'node_added',
                'layer': layer,
                'node_id': current_node.get('node_id'),
                'change_data': {
                    'new_node': current_node
                },
                'impact_score': 0.7,
                'timestamp': datetime.now().isoformat()
            })
        else:
            # 检测属性变化
            significant_fields = ['client_version', 'ip', 'status']
            for field in significant_fields:
                if previous_node.get(field) != current_node.get(field):
                    changes.append({
                        'change_type': 'node_updated',
                        'layer': layer,
                        'node_id': current_node.get('node_id'),
                        'change_data': {
                            'field': field,
                            'old_value': previous_node.get(field),
                            'new_value': current_node.get(field)
                        },
                        'impact_score': 0.3,
                        'timestamp': datetime.now().isoformat()
                    })
        
        return changes
    
    def _detect_peer_changes(self, previous_peers: List[dict], current_peers: List[dict], 
                           layer: str, node_id: str) -> List[dict]:
        """检测对等节点连接变化"""
        changes = []
        
        # 转换为集合以便比较
        previous_peer_ids = {peer.get('peer_id') for peer in previous_peers if peer.get('peer_id')}
        current_peer_ids = {peer.get('peer_id') for peer in current_peers if peer.get('peer_id')}
        
        # 新增的连接
        added_peers = current_peer_ids - previous_peer_ids
        for peer_id in added_peers:
            peer_info = next((p for p in current_peers if p.get('peer_id') == peer_id), {})
            changes.append({
                'change_type': 'link_added',
                'layer': layer,
                'source_node': node_id,
                'target_node': peer_id,
                'change_data': {
                    'peer_info': peer_info
                },
                'impact_score': 0.5,
                'timestamp': datetime.now().isoformat()
            })
        
        # 删除的连接
        removed_peers = previous_peer_ids - current_peer_ids
        for peer_id in removed_peers:
            peer_info = next((p for p in previous_peers if p.get('peer_id') == peer_id), {})
            changes.append({
                'change_type': 'link_removed',
                'layer': layer,
                'source_node': node_id,
                'target_node': peer_id,
                'change_data': {
                    'peer_info': peer_info
                },
                'impact_score': 0.5,
                'timestamp': datetime.now().isoformat()
            })
        
        return changes
    
    def _detect_validator_changes(self, previous_validators: List[dict], current_validators: List[dict], 
                                node_id: str) -> List[dict]:
        """检测验证器变化"""
        changes = []
        
        # 转换为字典以便比较
        # 转换为字典以便比较（注意：validator_index=0是合法值，不能用布尔过滤）
        previous_vals = {v.get('validator_index'): v for v in previous_validators if v.get('validator_index') is not None}
        current_vals = {v.get('validator_index'): v for v in current_validators if v.get('validator_index') is not None}
        
        # 新增的验证器
        added_validators = set(current_vals.keys()) - set(previous_vals.keys())
        for val_index in added_validators:
            val_info = current_vals[val_index]
            changes.append({
                'change_type': 'validator_added',
                'layer': 'consensus',
                'node_id': node_id,
                'validator_index': val_index,
                'change_data': {
                    'validator_info': val_info
                },
                'consensus_impact': {
                    'type': 'validator_activation',
                    'impact_score': 0.8
                },
                'timestamp': datetime.now().isoformat()
            })
        
        # 删除的验证器
        removed_validators = set(previous_vals.keys()) - set(current_vals.keys())
        for val_index in removed_validators:
            val_info = previous_vals[val_index]
            changes.append({
                'change_type': 'validator_removed',
                'layer': 'consensus',
                'node_id': node_id,
                'validator_index': val_index,
                'change_data': {
                    'validator_info': val_info
                },
                'consensus_impact': {
                    'type': 'validator_exit',
                    'impact_score': 0.8
                },
                'timestamp': datetime.now().isoformat()
            })
        
        # 验证器状态变化
        common_validators = set(previous_vals.keys()) & set(current_vals.keys())
        for val_index in common_validators:
            prev_val = previous_vals[val_index]
            curr_val = current_vals[val_index]
            
            # 检测状态变化
            if prev_val.get('status') != curr_val.get('status'):
                changes.append({
                    'change_type': 'validator_status_changed',
                    'layer': 'consensus',
                    'node_id': node_id,
                    'validator_index': val_index,
                    'change_data': {
                        'old_status': prev_val.get('status'),
                        'new_status': curr_val.get('status'),
                        'validator_info': curr_val
                    },
                    'consensus_impact': {
                        'type': 'status_change',
                        'impact_score': 0.6
                    },
                    'timestamp': datetime.now().isoformat()
                })
        
        return changes
    
    async def _get_execution_state(self, node_id: str) -> dict:
        """从Redis获取执行层历史状态"""
        try:
            cache_key = f"topology:execution_state:{node_id}"
            state_data = await self.redis_client.get(cache_key)
            if state_data:
                return json.loads(state_data)
            return {}
        except Exception as e:
            logger.error(f"获取执行层状态失败: {e}")
            return {}
    
    async def _save_execution_state(self, node_id: str, state: dict):
        """保存执行层状态到Redis"""
        try:
            cache_key = f"topology:execution_state:{node_id}"
            await self.redis_client.setex(cache_key, 3600, json.dumps(state))  # 1小时过期
        except Exception as e:
            logger.error(f"保存执行层状态失败: {e}")
    
    async def _get_consensus_state(self, node_id: str) -> dict:
        """从Redis获取共识层历史状态"""
        try:
            cache_key = f"topology:consensus_state:{node_id}"
            state_data = await self.redis_client.get(cache_key)
            if state_data:
                return json.loads(state_data)
            return {}
        except Exception as e:
            logger.error(f"获取共识层状态失败: {e}")
            return {}
    
    async def _save_consensus_state(self, node_id: str, state: dict):
        """保存共识层状态到Redis"""
        try:
            cache_key = f"topology:consensus_state:{node_id}"
            await self.redis_client.setex(cache_key, 3600, json.dumps(state))  # 1小时过期
        except Exception as e:
            logger.error(f"保存共识层状态失败: {e}") 