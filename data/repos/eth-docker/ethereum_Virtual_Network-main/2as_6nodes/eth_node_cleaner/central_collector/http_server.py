#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HTTP服务器模块
提供数据接收和查询的API端点
"""

import json
import time
import logging
from datetime import datetime
from aiohttp import web
from typing import Dict, Any, Callable

from .models import CollectedData


class HTTPServer:
    """HTTP服务器"""
    
    def __init__(self, config, data_cache, data_queue):
        self.config = config
        self.data_cache = data_cache
        self.data_queue = data_queue
        self.logger = logging.getLogger(__name__)
        
        # 创建应用
        self.app = web.Application()
        self.runner = None
        self.site = None
        
        # 设置路由
        self._setup_routes()
        
        # 统计信息
        self.request_count = 0
        self.last_request_time = None
    
    def _setup_routes(self):
        """设置HTTP路由"""
        # 数据接收端点
        self.app.router.add_post('/api/v1/monitoring/data', self._handle_monitoring_data)
        self.app.router.add_post('/api/v1/monitoring/heartbeat', self._handle_heartbeat)
        self.app.router.add_get('/api/v1/monitoring/status', self._handle_status)
        
        # 数据提供端点
        self.app.router.add_get('/api/v1/monitoring/beacon/blocks', self._handle_beacon_blocks)
        self.app.router.add_get('/api/v1/monitoring/beacon/fork_events', self._handle_fork_events)
        self.app.router.add_get('/api/v1/monitoring/beacon/network_health', self._handle_network_health)
        self.app.router.add_get('/api/v1/monitoring/beacon/attack_indicators', self._handle_attack_indicators)
        
        # 健康检查
        self.app.router.add_get('/health', self._handle_health)
    
    async def start(self):
        """启动HTTP服务器"""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(
                self.runner, 
                self.config.http_host, 
                self.config.http_port
            )
            await self.site.start()
            
            self.logger.info(
                f"HTTP服务器已启动: http://{self.config.http_host}:{self.config.http_port}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"启动HTTP服务器失败: {e}")
            return False
    
    async def stop(self):
        """停止HTTP服务器"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        self.logger.info("HTTP服务器已停止")
    
    # ===== 数据接收端点 =====
    
    async def _handle_monitoring_data(self, request: web.Request) -> web.Response:
        """处理监控数据推送"""
        try:
            self.request_count += 1
            self.last_request_time = time.time()
            
            data = await request.json()
            
            # 验证数据格式（node_id 为可选字段）
            required_fields = ['container_id', 'timestamp', 'data_type', 'data']
            if not all(field in data for field in required_fields):
                return web.json_response(
                    {'error': 'Missing required fields', 'required': required_fields}, 
                    status=400
                )
            
            # 创建监控数据对象
            # 处理时间戳 - 支持Unix时间戳和ISO格式
            timestamp = data['timestamp']
            if isinstance(timestamp, (int, float)):
                timestamp_dt = datetime.fromtimestamp(timestamp)
            else:
                try:
                    timestamp_dt = datetime.fromisoformat(timestamp)
                except ValueError:
                    timestamp_dt = datetime.utcnow()
            
            monitoring_data = CollectedData(
                container_id=data['container_id'],
                node_id=data.get('node_id', ''),
                timestamp=timestamp_dt,
                data_type=data['data_type'],
                data=data['data'],
                agent_version=data.get('agent_version', 'unknown'),
                local_ip=data.get('local_ip')
            )
            
            # 加入处理队列
            await self.data_queue.put(monitoring_data)
            
            return web.json_response({'status': 'success'})
            
        except Exception as e:
            self.logger.error(f"处理监控数据错误: {e}")
            return web.json_response(
                {'error': str(e)}, 
                status=500
            )
    
    async def _handle_heartbeat(self, request: web.Request) -> web.Response:
        """处理心跳请求"""
        try:
            data = await request.json()
            container_id = data.get('container_id')
            
            if not container_id:
                return web.json_response(
                    {'error': 'Missing container_id'}, 
                    status=400
                )
            
            # 更新心跳时间（内存缓存）
            self.data_cache.container_data[container_id] = {
                'last_heartbeat': time.time(),
                'status': 'active',
                **data
            }
            
            # 调试：检查data_processor是否存在
            if not hasattr(self, '_data_processor'):
                self.logger.warning("⚠️ HTTP服务器缺少_data_processor属性，心跳数据无法写入PostgreSQL")
            elif not self._data_processor:
                self.logger.warning("⚠️ _data_processor为None，心跳数据无法写入PostgreSQL")
            else:
                # 将心跳数据传递给数据处理器写入PostgreSQL
                self.logger.info(f"💗 开始处理心跳: {container_id}")
                await self._data_processor.process_heartbeat(data)
                self.logger.info(f"✅ 心跳处理完成: {container_id}")
            
            return web.json_response({
                'status': 'success',
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"处理心跳错误: {e}", exc_info=True)
            return web.json_response(
                {'error': str(e)}, 
                status=500
            )
    
    async def _handle_status(self, request: web.Request) -> web.Response:
        """处理状态查询"""
        return web.json_response({
            'status': 'running',
            'queue_size': self.data_queue.qsize(),
            'active_containers': self.data_cache.get_active_containers(),
            'cached_blocks': self.data_cache.get_beacon_blocks_count(),
            'last_updated': self.data_cache.last_updated,
            'request_count': self.request_count,
            'last_request_time': self.last_request_time
        })
    
    # ===== 数据查询端点 =====
    
    async def _handle_beacon_blocks(self, request: web.Request) -> web.Response:
        """提供beacon区块数据"""
        try:
            limit = int(request.query.get('limit', 10))
            
            # 从缓存返回数据
            blocks = self.data_cache.beacon_blocks[-limit:] if self.data_cache.beacon_blocks else []
            
            return web.json_response({
                'blocks': blocks,
                'total': len(blocks),
                'timestamp': time.time(),
                'data_source': 'central_collector'
            })
            
        except Exception as e:
            self.logger.error(f"处理beacon区块请求失败: {e}")
            return web.json_response({
                'blocks': [],
                'total': 0,
                'error': str(e)
            }, status=500)
    
    async def _handle_fork_events(self, request: web.Request) -> web.Response:
        """提供分叉事件数据"""
        return web.json_response({
            'active_forks': self.data_cache.fork_events,
            'resolved_forks': [],
            'timestamp': time.time()
        })
    
    async def _handle_network_health(self, request: web.Request) -> web.Response:
        """提供网络健康状态"""
        active_containers = self.data_cache.get_active_containers()
        
        return web.json_response({
            'current_health': {
                'status': 'healthy' if active_containers > 0 else 'warning',
                'active_containers': active_containers,
                'last_activity': self.data_cache.last_updated,
                'data_source': 'central_collector'
            },
            'timestamp': time.time()
        })
    
    async def _handle_attack_indicators(self, request: web.Request) -> web.Response:
        """提供攻击指标数据"""
        return web.json_response({
            'indicators': self.data_cache.attack_indicators,
            'timestamp': time.time()
        })
    
    async def _handle_health(self, request: web.Request) -> web.Response:
        """健康检查端点"""
        return web.json_response({
            'status': 'healthy',
            'service': 'central_data_collector',
            'timestamp': time.time()
        }) 