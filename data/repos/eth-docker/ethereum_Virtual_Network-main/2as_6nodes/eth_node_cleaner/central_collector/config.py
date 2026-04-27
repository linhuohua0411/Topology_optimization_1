#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
中央数据收集器配置模块 (v4.3.0 统一配置键名标准)

更新内容：
- 使用标准环境变量映射
- 与Foundation层配置键名保持一致
- 添加向后兼容性支持
- 统一配置获取方式
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CollectorConfig:
    """中央数据收集器配置 - v4.3.0 使用标准环境变量"""
    
    # HTTP服务配置
    http_port: int
    http_host: str
    
    # 性能配置
    max_beacon_blocks: int
    cache_ttl: int
    log_level: str
    
    # 数据库配置 - 使用标准键名
    neo4j_uri: Optional[str]
    neo4j_username: Optional[str]  # 统一使用username
    neo4j_password: Optional[str]
    
    redis_host: Optional[str]
    redis_port: Optional[int]
    redis_password: Optional[str]
    
    postgresql_dsn: Optional[str]  # 统一使用postgresql前缀
    
    @classmethod
    def from_env(cls) -> 'CollectorConfig':
        """从环境变量加载配置的类方法"""
        return load_collector_config()
    
    @property 
    def max_queue_size(self) -> int:
        """获取队列最大大小，默认1000"""
        return 1000


def load_collector_config() -> CollectorConfig:
    """加载收集器配置 - v4.3.0 使用标准环境变量映射"""
    
    # HTTP服务配置
    http_port = int(os.getenv('COLLECTOR_PORT', '8888'))
    http_host = os.getenv('COLLECTOR_HOST', '0.0.0.0')
    
    # 性能配置
    max_beacon_blocks = int(os.getenv('COLLECTOR_MAX_BEACON_BLOCKS', 
                                    os.getenv('MAX_BEACON_BLOCKS', '100')))  # 向后兼容
    cache_ttl = int(os.getenv('COLLECTOR_CACHE_TTL',
                            os.getenv('CACHE_TTL', '300')))  # 向后兼容
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    # 数据库配置 - 使用标准环境变量映射
    # Neo4j配置 - 支持标准和旧环境变量
    neo4j_uri = (os.getenv('NEO4J_URI') or 
                os.getenv('neo4j_uri'))  # 向后兼容
    neo4j_username = (os.getenv('NEO4J_USERNAME') or 
                     os.getenv('NEO4J_USER') or  # 向后兼容
                     os.getenv('neo4j_user'))    # 向后兼容
    neo4j_password = (os.getenv('NEO4J_PASSWORD') or
                     os.getenv('neo4j_password'))  # 向后兼容
    
    # Redis配置 - 使用标准环境变量
    redis_host = os.getenv('REDIS_HOST')
    redis_port_str = os.getenv('REDIS_PORT')
    redis_port = int(redis_port_str) if redis_port_str else None
    redis_password = os.getenv('REDIS_PASSWORD')
    
    # PostgreSQL配置 - 使用标准环境变量
    postgresql_dsn = (os.getenv('POSTGRESQL_DSN') or
                     os.getenv('POSTGRES_DSN'))  # 向后兼容
    
    return CollectorConfig(
        http_port=http_port,
        http_host=http_host,
        max_beacon_blocks=max_beacon_blocks,
        cache_ttl=cache_ttl,
        log_level=log_level,
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_password=redis_password,
        postgresql_dsn=postgresql_dsn
    )


# 向后兼容性函数
def get_config():
    """向后兼容：获取配置的旧接口"""
    return load_collector_config()


# 导出配置实例
config = load_collector_config() 