#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
区块链数据处理器 - 专门处理区块生产和分叉检测
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import redis.asyncio as redis


@dataclass
class BlockInfo:
    """区块信息"""
    slot: int
    hash: str
    parent_hash: str
    proposer: str
    timestamp: float
    node_id: str
    attestation_count: int = 0
    production_latency: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'slot': self.slot,
            'hash': self.hash,
            'parent_hash': self.parent_hash,
            'proposer': self.proposer,
            'timestamp': self.timestamp,
            'node_id': self.node_id,
            'attestation_count': self.attestation_count,
            'production_latency': self.production_latency
        }


@dataclass
class ForkEvent:
    """分叉事件"""
    fork_id: str
    detection_time: float
    slot: int
    competing_blocks: List[str]  # 竞争区块的哈希列表
    detector_node: str
    confidence: float  # 分叉置信度 0-1
    fork_type: str  # 'minor', 'major', 'critical'
    resolution_status: str = 'active'  # 'active', 'resolved', 'orphaned'
    
    def to_dict(self) -> Dict:
        return {
            'fork_id': self.fork_id,
            'detection_time': self.detection_time,
            'slot': self.slot,
            'competing_blocks': self.competing_blocks,
            'detector_node': self.detector_node,
            'confidence': self.confidence,
            'fork_type': self.fork_type,
            'resolution_status': self.resolution_status
        }


class BlockchainProcessor:
    """
    区块链数据处理器
    
    功能：
    1. 实时区块生产追踪
    2. 分叉检测和追踪
    3. 区块传播时间分析
    4. 验证者行为监控
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.logger = logging.getLogger(__name__)
        self.redis_client = redis_client
        
        # 区块缓存
        self.recent_blocks: Dict[int, List[BlockInfo]] = {}  # slot -> blocks
        self.block_by_hash: Dict[str, BlockInfo] = {}
        self.max_blocks_per_slot = 10
        self.max_cached_slots = 100
        
        # 分叉追踪
        self.active_forks: Dict[str, ForkEvent] = {}
        self.fork_history: List[ForkEvent] = []
        self.max_fork_history = 1000
        
        # 区块传播追踪
        self.block_first_seen: Dict[str, float] = {}  # hash -> first_seen_time
        self.block_propagation: Dict[str, List[Tuple[str, float]]] = {}  # hash -> [(node_id, time)]
        
        # 验证者统计
        self.proposer_stats: Dict[str, Dict] = {}  # proposer -> stats
        
        self.logger.info("区块链处理器初始化完成")
    
    async def process_block_data(self, data: Dict, node_id: str) -> None:
        """处理区块数据"""
        try:
            # 创建区块信息
            block = BlockInfo(
                slot=data.get('slot', 0),
                hash=data.get('hash', ''),
                parent_hash=data.get('parent_hash', ''),
                proposer=data.get('proposer', ''),
                timestamp=data.get('timestamp', time.time()),
                node_id=node_id,
                attestation_count=data.get('attestation_count', 0)
            )
            
            # 计算生产延迟
            if block.slot > 0:
                expected_time = self._calculate_expected_slot_time(block.slot)
                block.production_latency = block.timestamp - expected_time
            
            # 追踪区块传播
            await self._track_block_propagation(block)
            
            # 检测分叉
            await self._detect_fork(block)
            
            # 更新缓存
            await self._update_block_cache(block)
            
            # 更新验证者统计
            await self._update_proposer_stats(block)
            
            # 存储到Redis
            if self.redis_client:
                await self._store_block_to_redis(block)
                await self._publish_block_event(block)
            
            self.logger.debug(f"处理区块: slot={block.slot}, hash={block.hash[:8]}...")
            
        except Exception as e:
            self.logger.error(f"处理区块数据失败: {e}")
    
    async def _track_block_propagation(self, block: BlockInfo) -> None:
        """追踪区块传播"""
        block_hash = block.hash
        current_time = time.time()
        
        # 记录首次发现时间
        if block_hash not in self.block_first_seen:
            self.block_first_seen[block_hash] = current_time
            self.block_propagation[block_hash] = []
        
        # 记录节点发现时间
        self.block_propagation[block_hash].append((block.node_id, current_time))
        
        # 计算传播延迟
        propagation_delay = current_time - self.block_first_seen[block_hash]
        
        # 存储传播信息到Redis
        if self.redis_client and propagation_delay > 0:
            propagation_key = f"block:propagation:{block_hash}"
            await self.redis_client.zadd(
                propagation_key,
                {block.node_id: propagation_delay}
            )
            await self.redis_client.expire(propagation_key, 3600)  # 1小时过期
    
    async def _detect_fork(self, block: BlockInfo) -> None:
        """检测分叉"""
        slot = block.slot
        
        # 获取该slot的所有区块
        if slot not in self.recent_blocks:
            self.recent_blocks[slot] = []
        
        slot_blocks = self.recent_blocks[slot]
        
        # 检查是否有不同的区块
        different_blocks = [b for b in slot_blocks if b.hash != block.hash]
        
        if different_blocks:
            # 发现分叉！
            competing_hashes = list(set([b.hash for b in different_blocks] + [block.hash]))
            
            # 创建分叉事件
            fork_event = ForkEvent(
                fork_id=f"fork_{slot}_{int(time.time())}",
                detection_time=time.time(),
                slot=slot,
                competing_blocks=competing_hashes,
                detector_node=block.node_id,
                confidence=self._calculate_fork_confidence(len(competing_hashes)),
                fork_type=self._determine_fork_type(slot, len(competing_hashes))
            )
            
            # 更新活跃分叉
            self.active_forks[fork_event.fork_id] = fork_event
            self.fork_history.append(fork_event)
            
            # 限制历史记录大小
            if len(self.fork_history) > self.max_fork_history:
                self.fork_history = self.fork_history[-self.max_fork_history:]
            
            # 发布分叉事件
            if self.redis_client:
                await self._publish_fork_event(fork_event)
            
            self.logger.warning(
                f"检测到分叉! slot={slot}, 竞争区块数={len(competing_hashes)}, "
                f"类型={fork_event.fork_type}"
            )
    
    async def _update_block_cache(self, block: BlockInfo) -> None:
        """更新区块缓存"""
        slot = block.slot
        
        # 添加到slot列表
        if slot not in self.recent_blocks:
            self.recent_blocks[slot] = []
        
        # 检查是否已存在
        if not any(b.hash == block.hash for b in self.recent_blocks[slot]):
            self.recent_blocks[slot].append(block)
        
        # 限制每个slot的区块数
        if len(self.recent_blocks[slot]) > self.max_blocks_per_slot:
            self.recent_blocks[slot] = self.recent_blocks[slot][-self.max_blocks_per_slot:]
        
        # 添加到哈希索引
        self.block_by_hash[block.hash] = block
        
        # 清理旧slot
        if len(self.recent_blocks) > self.max_cached_slots:
            oldest_slots = sorted(self.recent_blocks.keys())[:len(self.recent_blocks) - self.max_cached_slots]
            for old_slot in oldest_slots:
                # 清理哈希索引
                for old_block in self.recent_blocks[old_slot]:
                    self.block_by_hash.pop(old_block.hash, None)
                # 删除slot
                del self.recent_blocks[old_slot]
    
    async def _update_proposer_stats(self, block: BlockInfo) -> None:
        """更新验证者统计"""
        proposer = block.proposer
        
        if proposer not in self.proposer_stats:
            self.proposer_stats[proposer] = {
                'total_blocks': 0,
                'avg_latency': 0.0,
                'avg_attestations': 0.0,
                'first_seen': time.time(),
                'last_seen': time.time()
            }
        
        stats = self.proposer_stats[proposer]
        stats['total_blocks'] += 1
        stats['last_seen'] = time.time()
        
        # 更新平均延迟
        stats['avg_latency'] = (
            (stats['avg_latency'] * (stats['total_blocks'] - 1) + block.production_latency) /
            stats['total_blocks']
        )
        
        # 更新平均认证数
        stats['avg_attestations'] = (
            (stats['avg_attestations'] * (stats['total_blocks'] - 1) + block.attestation_count) /
            stats['total_blocks']
        )
        
        # 存储到Redis
        if self.redis_client:
            await self.redis_client.hset(
                f"proposer:stats:{proposer}",
                mapping={
                    'total_blocks': stats['total_blocks'],
                    'avg_latency': stats['avg_latency'],
                    'avg_attestations': stats['avg_attestations'],
                    'first_seen': stats['first_seen'],
                    'last_seen': stats['last_seen']
                }
            )
    
    async def _store_block_to_redis(self, block: BlockInfo) -> None:
        """存储区块到Redis"""
        # 存储最新区块
        await self.redis_client.hset(
            f"block:latest:{block.node_id}",
            mapping=block.to_dict()
        )
        
        # 添加到区块队列
        await self.redis_client.lpush(
            "blocks:queue",
            json.dumps(block.to_dict())
        )
        await self.redis_client.ltrim("blocks:queue", 0, 999)  # 保留最近1000个
        
        # 存储到slot索引
        await self.redis_client.sadd(f"blocks:slot:{block.slot}", block.hash)
        await self.redis_client.expire(f"blocks:slot:{block.slot}", 3600)
    
    async def _publish_block_event(self, block: BlockInfo) -> None:
        """发布区块事件"""
        event = {
            'type': 'new_block',
            'timestamp': time.time(),
            'data': block.to_dict()
        }
        
        await self.redis_client.publish(
            'blockchain:events',
            json.dumps(event)
        )
    
    async def _publish_fork_event(self, fork: ForkEvent) -> None:
        """发布分叉事件"""
        # 存储到活跃分叉集合
        await self.redis_client.hset(
            "forks:active",
            fork.fork_id,
            json.dumps(fork.to_dict())
        )
        
        # 发布事件
        event = {
            'type': 'fork_detected',
            'timestamp': time.time(),
            'data': fork.to_dict()
        }
        
        await self.redis_client.publish(
            'blockchain:events',
            json.dumps(event)
        )
        
        # 使用Redis Streams记录
        await self.redis_client.xadd(
            'forks:stream',
            {'event': json.dumps(fork.to_dict())},
            maxlen=10000  # 保留最近10000个事件
        )
    
    def _calculate_expected_slot_time(self, slot: int) -> float:
        """计算slot的预期时间"""
        # 假设每个slot 12秒，从某个基准时间开始
        genesis_time = 1606824023  # 示例：2020-12-01 12:00:23 UTC
        slot_duration = 12  # 秒
        return genesis_time + (slot * slot_duration)
    
    def _calculate_fork_confidence(self, competing_blocks: int) -> float:
        """计算分叉置信度"""
        # 竞争区块越多，置信度越高
        return min(1.0, competing_blocks / 5.0)
    
    def _determine_fork_type(self, slot: int, competing_blocks: int) -> str:
        """确定分叉类型"""
        if competing_blocks >= 4:
            return 'critical'
        elif competing_blocks >= 3:
            return 'major'
        else:
            return 'minor'
    
    async def get_fork_summary(self) -> Dict:
        """获取分叉摘要"""
        active_count = len(self.active_forks)
        
        # 统计不同类型的分叉
        fork_types = {'minor': 0, 'major': 0, 'critical': 0}
        for fork in self.active_forks.values():
            fork_types[fork.fork_type] += 1
        
        return {
            'active_forks': active_count,
            'fork_types': fork_types,
            'total_detected': len(self.fork_history),
            'recent_forks': [
                f.to_dict() for f in self.fork_history[-10:]
            ]
        }
    
    async def resolve_fork(self, fork_id: str, winning_hash: str) -> None:
        """解决分叉"""
        if fork_id in self.active_forks:
            fork = self.active_forks[fork_id]
            fork.resolution_status = 'resolved'
            
            # 更新Redis
            if self.redis_client:
                # 从活跃分叉中移除
                await self.redis_client.hdel("forks:active", fork_id)
                
                # 添加到已解决分叉
                await self.redis_client.hset(
                    "forks:resolved",
                    fork_id,
                    json.dumps({
                        **fork.to_dict(),
                        'winning_hash': winning_hash,
                        'resolution_time': time.time()
                    })
                )
            
            # 从活跃分叉中移除
            del self.active_forks[fork_id]
            
            self.logger.info(f"分叉已解决: {fork_id}, 获胜区块: {winning_hash[:8]}...") 