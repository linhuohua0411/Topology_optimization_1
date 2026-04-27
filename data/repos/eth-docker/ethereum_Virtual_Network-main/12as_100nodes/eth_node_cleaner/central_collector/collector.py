#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
中央数据收集器核心模块 - v3.0.0
"""

import asyncio
import time
import logging
from typing import Optional, List

from .models import DataCache, CollectedData
from .config import CollectorConfig, load_collector_config
from .http_server import HTTPServer
from .data_processor import DataProcessor


class CentralDataCollector:
    """
    中央数据收集器 - 独立版本
    
    功能：
    1. 提供8888端口的HTTP服务接收代理数据
    2. 管理来自容器代理的数据推送
    3. 将数据路由到异步数据处理器
    """
    
    def __init__(self, config: Optional[CollectorConfig] = None):
        self.config = config or load_collector_config()
        self.logger = self._setup_logger()
        
        self.data_cache = DataCache() # 主要用于心跳和状态缓存
        self.data_queue = asyncio.Queue(maxsize=1000)  # 设置固定大小
        
        self.data_processor = DataProcessor(self.config, self.data_cache)
        self.http_server = HTTPServer(self.config, self.data_cache, self.data_queue)
        # 让HTTP服务器可以访问数据处理器
        self.http_server._data_processor = self.data_processor
        
        self.running = False
        self.background_tasks = []
        
        self.logger.info(f"🏗️ 中央数据收集器初始化完成 - 端口: {self.config.http_port}")
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('CentralDataCollector')
        logger.setLevel(getattr(logging, self.config.log_level))
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def start(self):
        """启动中央数据收集器"""
        try:
            self.running = True
            self.logger.info(f"🚀 启动中央数据收集器服务...")
            
            # 1. 初始化数据库连接
            await self.data_processor.initialize_connections()

            # 2. 启动HTTP服务器
            success = await self.http_server.start()
            if not success:
                self.running = False
                return False
            
            # 3. 启动后台任务
            processor_task = asyncio.create_task(self._data_processing_loop())
            self.background_tasks.append(processor_task)
            
            heartbeat_task = asyncio.create_task(self._heartbeat_checker())
            self.background_tasks.append(heartbeat_task)
            
            self.logger.info("✅ 中央数据收集器启动成功")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 启动中央数据收集器失败: {e}", exc_info=True)
            self.running = False
            return False
    
    async def stop(self):
        """停止中央数据收集器"""
        try:
            self.running = False
            
            # 停止HTTP服务器
            await self.http_server.stop()
            
            # 关闭数据库连接
            await self.data_processor.close()

            # 取消后台任务
            for task in self.background_tasks:
                task.cancel()
            
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
            self.logger.info("✅ 中央数据收集器已停止")
            
        except Exception as e:
            self.logger.error(f"停止中央数据收集器失败: {e}")
    
    # ===== 后台任务 =====
    
    async def _data_processing_loop(self):
        """数据处理任务循环"""
        while self.running:
            try:
                data = await self.data_queue.get()
                await self.data_processor.process_data(data)
                self.data_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"数据处理任务错误: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _heartbeat_checker(self):
        """心跳检查任务，更新DataCache中的节点状态。"""
        while self.running:
            try:
                await asyncio.sleep(30)
                current_time = time.time()
                inactive_containers = []
                
                for container_id, container_data in self.data_cache.container_data.items():
                    last_heartbeat = container_data.get('last_heartbeat', 0)
                    if current_time - last_heartbeat > 60:
                        container_data['status'] = 'inactive'
                        inactive_containers.append(container_id)
                
                if inactive_containers:
                    self.logger.warning(f"检测到不活跃容器: {', '.join(inactive_containers)}")
                    await self._handle_inactive_containers(inactive_containers)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"心跳检查任务错误: {e}")
    
    async def _handle_inactive_containers(self, inactive_containers: List[str]):
        """处理不活跃容器，更新相关数据库"""
        for container_id in inactive_containers:
            container_data = self.data_cache.container_data.get(container_id)
            if not container_data:
                continue
                
            node_id = container_data.get('node_id')
            local_ip = container_data.get('local_ip')
            
            try:
                await self.data_processor.delete_nodes_by_container(container_id)

                if not node_id and not local_ip:
                    self.logger.warning(
                        f"容器 {container_id} 缺少 node_id 和 local_ip，仅执行容器级别的Neo4j清理"
                    )
                    continue

                if node_id:
                    await self.data_processor.mark_node_inactive_in_neo4j(node_id, container_id)
                if local_ip:
                    await self.data_processor.delete_nodes_by_ip(local_ip, container_id)
                
                if node_id:
                    await self.data_processor.record_node_failure_in_postgres(container_id, node_id)
                
                if node_id:
                    await self.data_processor.cleanup_node_state_in_redis(node_id)
                
                if node_id:
                    await self.data_processor.send_node_removed_event(node_id, container_id)
                
                self.logger.info(f"✅ 已处理故障容器 {container_id} (node_id: {node_id or 'N/A'}, IP: {local_ip or 'N/A'})")
            except Exception as e:
                self.logger.error(f"处理故障容器 {container_id} 的数据库更新失败: {e}", exc_info=True)
    
    # ===== 外部API方法 =====
    
    def get_health_status(self) -> dict:
        """获取健康状态"""
        return {
            'status': 'healthy' if self.running else 'stopped',
            'active_containers': self.data_cache.get_active_containers(),
            'last_activity': self.data_cache.last_updated, # Assuming last_activity is now in DataCache
            'queue_size': self.data_queue.qsize(),
            'data_available': self.data_cache.get_beacon_blocks_count() > 0
        }
    
    def get_cache_info(self) -> dict:
        """获取缓存信息"""
        return {
            'beacon_blocks_count': self.data_cache.get_beacon_blocks_count(),
            'active_containers': self.data_cache.get_active_containers(),
            'last_updated': self.data_cache.last_updated,
            'total_collected_data': self.data_cache.total_collected_data # Assuming this is in DataCache
        } 