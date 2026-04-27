#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional


@dataclass
class CollectedData:
    """收集到的数据结构"""
    container_id: str
    node_id: str
    timestamp: datetime
    data_type: str
    data: Dict[str, Any]
    agent_version: str = "unknown"
    local_ip: Optional[str] = None


@dataclass
class DataCache:
    """数据缓存结构"""
    beacon_blocks: List[Dict[str, Any]] = field(default_factory=list)
    fork_events: List[Dict[str, Any]] = field(default_factory=list)
    network_health: Dict[str, Any] = field(default_factory=dict)
    attack_indicators: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: float = 0
    container_data: Dict[str, Any] = field(default_factory=dict)
    total_collected_data: int = 0
    
    def clear(self):
        """清空缓存"""
        self.beacon_blocks.clear()
        self.fork_events.clear()
        self.network_health.clear()
        self.attack_indicators.clear()
        self.container_data.clear()
        self.last_updated = 0
    
    def get_active_containers(self) -> int:
        """获取活跃容器数量"""
        return len(self.container_data)
    
    def get_beacon_blocks_count(self) -> int:
        """获取缓存的区块数量"""
        return len(self.beacon_blocks) 