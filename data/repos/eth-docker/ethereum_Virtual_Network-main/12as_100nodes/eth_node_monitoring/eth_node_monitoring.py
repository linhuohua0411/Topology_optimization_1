#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
以太坊节点实时监控程序 (eth_node_monitoring)

功能：
1. 订阅 Redis Pub/Sub 频道，实时接收拓扑变化事件
2. 读取 Redis Stream（topology:changes），展示历史变化流
3. 定期查询 Neo4j 获取当前拓扑快照
4. 对接 PostgreSQL 获取历史变化记录
5. 通过 HTTP API（端口9999）对外提供实时监控数据
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
from aiohttp import web
from neo4j import AsyncGraphDatabase, AsyncDriver
from redis import asyncio as aioredis

# ─── 日志配置 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('eth_node_monitoring')


# ─── 配置加载 ─────────────────────────────────────────────────────────────────
class MonitoringConfig:
    """监控程序配置（从环境变量加载）"""

    def __init__(self):
        self.http_port = int(os.getenv('MONITORING_PORT', '9999'))
        self.http_host = os.getenv('MONITORING_HOST', '0.0.0.0')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

        # Neo4j
        self.neo4j_uri = os.getenv('NEO4J_URI', 'bolt://eth_neo4j:7687')
        self.neo4j_username = os.getenv('NEO4J_USERNAME', os.getenv('NEO4J_USER', 'neo4j'))
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', '1qaz@WSX')

        # Redis
        self.redis_host = os.getenv('REDIS_HOST', 'eth_redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_password = os.getenv('REDIS_PASSWORD')

        # PostgreSQL
        self.postgresql_dsn = (
            os.getenv('POSTGRESQL_DSN') or
            os.getenv('POSTGRES_DSN') or
            'postgresql://postgres:password@eth_postgresql:5432/ethereum_monitor'
        )

        # 采集参数
        self.topology_poll_interval = int(os.getenv('TOPOLOGY_POLL_INTERVAL', '10'))
        self.max_recent_events = int(os.getenv('MAX_RECENT_EVENTS', '200'))
        self.stream_read_count = int(os.getenv('STREAM_READ_COUNT', '50'))


# ─── 状态存储 ─────────────────────────────────────────────────────────────────
class MonitoringState:
    """监控状态内存缓存"""

    def __init__(self):
        self.start_time = time.time()
        self.recent_events: List[Dict[str, Any]] = []
        self.topology_snapshot: Dict[str, Any] = {}
        self.node_statistics: Dict[str, Any] = {}
        self.last_topology_update: float = 0
        self.last_stream_id: str = '0'
        self.pubsub_event_count: int = 0
        self.stream_event_count: int = 0
        self.errors: List[str] = []

    def add_event(self, event: Dict[str, Any], max_events: int = 200):
        """添加变化事件（自动截断旧事件）"""
        self.recent_events.insert(0, {
            **event,
            '_received_at': datetime.now().isoformat()
        })
        if len(self.recent_events) > max_events:
            self.recent_events = self.recent_events[:max_events]

    def to_summary(self) -> Dict[str, Any]:
        return {
            'uptime_seconds': int(time.time() - self.start_time),
            'total_events_received': self.pubsub_event_count + self.stream_event_count,
            'pubsub_events': self.pubsub_event_count,
            'stream_events': self.stream_event_count,
            'last_topology_update': self.last_topology_update,
            'error_count': len(self.errors),
        }


# ─── 核心监控类 ───────────────────────────────────────────────────────────────
class EthNodeMonitoring:
    """以太坊节点实时监控主类"""

    def __init__(self):
        self.config = MonitoringConfig()
        logger.setLevel(getattr(logging, self.config.log_level))

        self.state = MonitoringState()
        self.redis_client: Optional[aioredis.Redis] = None
        self.neo4j_driver: Optional[AsyncDriver] = None
        self.pg_pool: Optional[asyncpg.Pool] = None

        self.running = False
        self.background_tasks: List[asyncio.Task] = []

        # HTTP
        self.app = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None

    # ── 路由设置 ──────────────────────────────────────────────────────────────

    def _setup_routes(self):
        self.app.router.add_get('/health', self._handle_health)
        self.app.router.add_get('/api/v1/monitoring/topology', self._handle_topology)
        self.app.router.add_get('/api/v1/monitoring/events', self._handle_events)
        self.app.router.add_get('/api/v1/monitoring/statistics', self._handle_statistics)
        self.app.router.add_get('/api/v1/monitoring/nodes', self._handle_nodes)
        self.app.router.add_get('/api/v1/monitoring/changes/execution', self._handle_exec_changes)
        self.app.router.add_get('/api/v1/monitoring/changes/consensus', self._handle_cons_changes)
        self.app.router.add_get('/api/v1/monitoring/validators', self._handle_validators)
        self.app.router.add_get('/api/v1/monitoring/stream/latest', self._handle_stream_latest)

    # ── 数据库初始化 ──────────────────────────────────────────────────────────

    async def _init_connections(self):
        """初始化数据库连接（带重试）"""

        # Redis
        for attempt in range(30):
            try:
                self.redis_client = aioredis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    password=self.config.redis_password,
                    decode_responses=True
                )
                await self.redis_client.ping()
                logger.info("✅ Redis连接成功")
                break
            except Exception as e:
                logger.warning(f"Redis连接失败 (尝试 {attempt+1}/30): {e}")
                await asyncio.sleep(3)
        else:
            logger.error("❌ Redis连接多次失败，继续以无Redis模式运行")
            self.redis_client = None

        # Neo4j（若URI未配置则跳过）
        if not self.config.neo4j_uri or not self.config.neo4j_uri.startswith(('bolt', 'neo4j')):
            logger.warning("⚠️ Neo4j URI未配置或无效，跳过Neo4j连接")
        else:
            for attempt in range(30):
                try:
                    self.neo4j_driver = AsyncGraphDatabase.driver(
                        self.config.neo4j_uri,
                        auth=(self.config.neo4j_username, self.config.neo4j_password)
                    )
                    await self.neo4j_driver.verify_connectivity()
                    logger.info("✅ Neo4j连接成功")
                    break
                except Exception as e:
                    logger.warning(f"Neo4j连接失败 (尝试 {attempt+1}/30): {e}")
                    await asyncio.sleep(3)
            else:
                logger.error("❌ Neo4j连接多次失败，继续以无Neo4j模式运行")
                self.neo4j_driver = None

        # PostgreSQL
        for attempt in range(20):
            try:
                self.pg_pool = await asyncpg.create_pool(
                    dsn=self.config.postgresql_dsn, min_size=2, max_size=10
                )
                logger.info("✅ PostgreSQL连接成功")
                break
            except Exception as e:
                logger.warning(f"PostgreSQL连接失败 (尝试 {attempt+1}/20): {e}")
                await asyncio.sleep(3)
        else:
            logger.warning("⚠️ PostgreSQL连接多次失败，以无PG模式运行")
            self.pg_pool = None

    # ── 启动 / 停止 ───────────────────────────────────────────────────────────

    async def start(self):
        """启动监控程序"""
        logger.info("=" * 60)
        logger.info("🚀 以太坊节点实时监控程序启动")
        logger.info(f"   监控端口: {self.config.http_port}")
        logger.info(f"   Neo4j:    {self.config.neo4j_uri}")
        logger.info(f"   Redis:    {self.config.redis_host}:{self.config.redis_port}")
        logger.info("=" * 60)

        self.running = True
        await self._init_connections()

        # 启动 HTTP 服务
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.config.http_host, self.config.http_port)
        await site.start()
        logger.info(f"✅ HTTP服务已启动: http://{self.config.http_host}:{self.config.http_port}")

        # 启动后台任务
        tasks = [
            self._topology_poll_loop(),
            self._stream_reader_loop(),
            self._pubsub_listener_loop(),
            self._log_summary_loop(),
        ]
        for coro in tasks:
            self.background_tasks.append(asyncio.create_task(coro))

        logger.info("✅ 所有后台任务已启动")

    async def stop(self):
        """停止监控程序"""
        self.running = False
        for task in self.background_tasks:
            task.cancel()
        await asyncio.gather(*self.background_tasks, return_exceptions=True)

        if self.runner:
            await self.runner.cleanup()
        if self.neo4j_driver:
            await self.neo4j_driver.close()
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("✅ 监控程序已停止")

    # ── 后台任务 ──────────────────────────────────────────────────────────────

    async def _topology_poll_loop(self):
        """定期轮询 Neo4j 获取拓扑快照"""
        while self.running:
            try:
                await self._refresh_topology_snapshot()
                await asyncio.sleep(self.config.topology_poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"拓扑轮询异常: {e}")
                await asyncio.sleep(15)

    async def _stream_reader_loop(self):
        """从 Redis Stream 读取拓扑变化事件"""
        if not self.redis_client:
            logger.warning("Redis不可用，跳过Stream读取")
            return

        while self.running:
            try:
                entries = await self.redis_client.xread(
                    {'topology:changes': self.state.last_stream_id},
                    count=self.config.stream_read_count,
                    block=2000
                )
                if entries:
                    for stream_name, messages in entries:
                        for msg_id, fields in messages:
                            self.state.last_stream_id = msg_id
                            self.state.stream_event_count += 1

                            event = {
                                'source': 'redis_stream',
                                'stream_id': msg_id,
                                'event_type': fields.get('event_type', 'unknown'),
                                'layer': fields.get('layer', 'unknown'),
                                'change_type': fields.get('change_type', 'unknown'),
                                'node_id': fields.get('node_id', ''),
                                'timestamp': fields.get('timestamp', ''),
                            }
                            try:
                                event['detail'] = json.loads(fields.get('data', '{}'))
                            except Exception:
                                event['detail'] = {}

                            self.state.add_event(event, self.config.max_recent_events)
                            logger.info(
                                f"📨 Stream事件: {event['change_type']} | "
                                f"层级={event['layer']} | 节点={event['node_id'][:20] if event['node_id'] else 'N/A'}"
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream读取异常: {e}")
                await asyncio.sleep(5)

    async def _pubsub_listener_loop(self):
        """订阅 Redis Pub/Sub 频道，实时接收变化通知"""
        if not self.redis_client:
            logger.warning("Redis不可用，跳过Pub/Sub订阅")
            return

        channels = [
            'topology:changes:execution',
            'topology:changes:consensus',
            'fork_alerts',
            'topology:detector:status',
        ]

        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(*channels)
            logger.info(f"✅ 已订阅Redis频道: {channels}")

            while self.running:
                try:
                    message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0)
                    if message:
                        self.state.pubsub_event_count += 1
                        channel = message.get('channel', '')
                        try:
                            data = json.loads(message.get('data', '{}'))
                        except Exception:
                            data = {'raw': str(message.get('data', ''))}

                        event = {
                            'source': 'redis_pubsub',
                            'channel': channel,
                            'change_type': data.get('change_type', 'unknown'),
                            'layer': data.get('layer', 'unknown'),
                            'node_id': data.get('node_id') or data.get('source_node', ''),
                            'timestamp': data.get('timestamp', datetime.now().isoformat()),
                            'detail': data,
                        }
                        self.state.add_event(event, self.config.max_recent_events)
                        logger.info(
                            f"📡 PubSub事件: {channel} | {event['change_type']} | "
                            f"节点={str(event['node_id'])[:20]}"
                        )
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"PubSub消息处理异常: {e}")
                    await asyncio.sleep(1)

            await pubsub.unsubscribe()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"PubSub订阅异常: {e}")

    async def _log_summary_loop(self):
        """每60秒打印一次统计摘要"""
        while self.running:
            try:
                await asyncio.sleep(60)
                summary = self.state.to_summary()
                snap = self.state.node_statistics
                logger.info(
                    f"📊 监控摘要 | 运行时间={summary['uptime_seconds']}s "
                    f"| 总事件={summary['total_events_received']} "
                    f"| 执行层节点={snap.get('exec_node_count', 0)} "
                    f"| 共识层节点={snap.get('cons_node_count', 0)} "
                    f"| 验证者={snap.get('validator_count', 0)}"
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"摘要日志异常: {e}")

    # ── Neo4j 拓扑查询 ────────────────────────────────────────────────────────

    async def _refresh_topology_snapshot(self):
        """从 Neo4j 获取当前拓扑快照"""
        if not self.neo4j_driver:
            return

        try:
            async with self.neo4j_driver.session() as session:
                # 执行层节点
                exec_result = await session.run("""
                    MATCH (n:ExecNode)
                    RETURN n.node_id AS node_id, n.ip AS ip, n.client_type AS client_type,
                           n.client_version AS client_version, n.container_id AS container_id,
                           n.last_seen AS last_seen
                    ORDER BY n.ip
                """)
                exec_nodes = []
                async for record in exec_result:
                    exec_nodes.append({
                        'node_id': record.get('node_id', ''),
                        'ip': record.get('ip', ''),
                        'client_type': record.get('client_type', ''),
                        'client_version': record.get('client_version', ''),
                        'container_id': record.get('container_id', ''),
                        'last_seen': str(record.get('last_seen', '')),
                    })

                # 共识层节点
                cons_result = await session.run("""
                    MATCH (n:ConsNode)
                    RETURN n.node_id AS node_id, n.ip AS ip, n.client_type AS client_type,
                           n.client_version AS client_version, n.container_id AS container_id,
                           n.last_seen AS last_seen
                    ORDER BY n.ip
                """)
                cons_nodes = []
                async for record in cons_result:
                    cons_nodes.append({
                        'node_id': record.get('node_id', ''),
                        'ip': record.get('ip', ''),
                        'client_type': record.get('client_type', ''),
                        'client_version': record.get('client_version', ''),
                        'container_id': record.get('container_id', ''),
                        'last_seen': str(record.get('last_seen', '')),
                    })

                # 验证者
                val_result = await session.run("""
                    MATCH (v:Validator)
                    RETURN v.validator_index AS validator_index, v.public_key AS public_key,
                           v.status AS status, v.balance AS balance
                    ORDER BY v.validator_index
                    LIMIT 100
                """)
                validators = []
                async for record in val_result:
                    validators.append({
                        'validator_index': record.get('validator_index'),
                        'public_key': str(record.get('public_key', ''))[:20] + '...',
                        'status': record.get('status', ''),
                        'balance': record.get('balance'),
                    })

                # 执行层连接数
                exec_link_result = await session.run("""
                    MATCH ()-[r:EXEC_PEERS_WITH]->() RETURN count(r) AS cnt
                """)
                exec_link_rec = await exec_link_result.single()
                exec_links = exec_link_rec['cnt'] if exec_link_rec else 0

                # 共识层连接数
                cons_link_result = await session.run("""
                    MATCH ()-[r:CONS_PEERS_WITH]->() RETURN count(r) AS cnt
                """)
                cons_link_rec = await cons_link_result.single()
                cons_links = cons_link_rec['cnt'] if cons_link_rec else 0

            self.state.topology_snapshot = {
                'execution_nodes': exec_nodes,
                'consensus_nodes': cons_nodes,
                'validators': validators,
                'execution_link_count': exec_links,
                'consensus_link_count': cons_links,
                'snapshot_time': datetime.now().isoformat(),
            }
            self.state.node_statistics = {
                'exec_node_count': len(exec_nodes),
                'cons_node_count': len(cons_nodes),
                'validator_count': len(validators),
                'exec_link_count': exec_links,
                'cons_link_count': cons_links,
                'last_updated': datetime.now().isoformat(),
            }
            self.state.last_topology_update = time.time()

        except Exception as e:
            logger.error(f"拓扑快照刷新失败: {e}")
            self.state.errors.append(f"{datetime.now().isoformat()}: {e}")

    # ── PostgreSQL 查询 ───────────────────────────────────────────────────────

    async def _query_recent_pg_changes(self, table: str, limit: int = 50) -> List[Dict]:
        """从 PostgreSQL 查询最近的变化记录"""
        if not self.pg_pool:
            return []
        try:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT event_id, timestamp, change_type, source, diff_data, metadata
                    FROM {table}
                    ORDER BY timestamp DESC
                    LIMIT $1
                """, limit)
                return [
                    {
                        'event_id': str(r['event_id']),
                        'timestamp': r['timestamp'].isoformat() if r['timestamp'] else '',
                        'change_type': r['change_type'],
                        'source': r['source'],
                        'diff_data': r['diff_data'],
                        'metadata': r['metadata'],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"查询 {table} 失败: {e}")
            return []

    async def _query_validators_from_pg(self, limit: int = 50) -> List[Dict]:
        """从 PostgreSQL 查询验证者信息"""
        if not self.pg_pool:
            return []
        try:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT validator_index, pubkey, status, effective_balance,
                           slashed, activation_epoch, managed_by_node, last_seen
                    FROM validators
                    ORDER BY validator_index
                    LIMIT $1
                """, limit)
                return [
                    {
                        'validator_index': r['validator_index'],
                        'pubkey': str(r['pubkey'])[:20] + '...' if r['pubkey'] else '',
                        'status': r['status'],
                        'effective_balance': r['effective_balance'],
                        'slashed': r['slashed'],
                        'activation_epoch': r['activation_epoch'],
                        'managed_by_node': str(r['managed_by_node'] or '')[:20],
                        'last_seen': r['last_seen'].isoformat() if r['last_seen'] else '',
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"查询validators失败: {e}")
            return []

    # ── HTTP 处理器 ───────────────────────────────────────────────────────────

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({
            'status': 'healthy',
            'service': 'eth_node_monitoring',
            'version': '1.0.0',
            'uptime': int(time.time() - self.state.start_time),
            'connections': {
                'redis': self.redis_client is not None,
                'neo4j': self.neo4j_driver is not None,
                'postgresql': self.pg_pool is not None,
            },
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_topology(self, request: web.Request) -> web.Response:
        return web.json_response({
            'topology': self.state.topology_snapshot,
            'last_updated': self.state.last_topology_update,
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_events(self, request: web.Request) -> web.Response:
        limit = int(request.query.get('limit', 50))
        layer = request.query.get('layer')
        events = self.state.recent_events
        if layer:
            events = [e for e in events if e.get('layer') == layer]
        return web.json_response({
            'events': events[:limit],
            'total': len(events),
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_statistics(self, request: web.Request) -> web.Response:
        return web.json_response({
            'summary': self.state.to_summary(),
            'node_statistics': self.state.node_statistics,
            'recent_errors': self.state.errors[-10:],
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_nodes(self, request: web.Request) -> web.Response:
        layer = request.query.get('layer', 'all')
        snap = self.state.topology_snapshot
        result = {}
        if layer in ('all', 'execution'):
            result['execution_nodes'] = snap.get('execution_nodes', [])
        if layer in ('all', 'consensus'):
            result['consensus_nodes'] = snap.get('consensus_nodes', [])
        result['timestamp'] = datetime.now().isoformat()
        return web.json_response(result)

    async def _handle_exec_changes(self, request: web.Request) -> web.Response:
        limit = int(request.query.get('limit', 50))
        changes = await self._query_recent_pg_changes('eth_execution_topology_changes', limit)
        return web.json_response({
            'changes': changes,
            'count': len(changes),
            'layer': 'execution',
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_cons_changes(self, request: web.Request) -> web.Response:
        limit = int(request.query.get('limit', 50))
        changes = await self._query_recent_pg_changes('eth_consensus_topology_changes', limit)
        return web.json_response({
            'changes': changes,
            'count': len(changes),
            'layer': 'consensus',
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_validators(self, request: web.Request) -> web.Response:
        limit = int(request.query.get('limit', 50))
        validators = await self._query_validators_from_pg(limit)
        if not validators:
            validators = self.state.topology_snapshot.get('validators', [])
        return web.json_response({
            'validators': validators,
            'count': len(validators),
            'source': 'postgresql' if self.pg_pool else 'neo4j_cache',
            'timestamp': datetime.now().isoformat(),
        })

    async def _handle_stream_latest(self, request: web.Request) -> web.Response:
        """从 Redis Stream 读取最新 N 条记录"""
        if not self.redis_client:
            return web.json_response({'error': 'Redis不可用', 'events': []}, status=503)
        limit = int(request.query.get('limit', 20))
        try:
            entries = await self.redis_client.xrevrange('topology:changes', count=limit)
            events = []
            for msg_id, fields in entries:
                event = {
                    'stream_id': msg_id,
                    'event_type': fields.get('event_type', ''),
                    'layer': fields.get('layer', ''),
                    'change_type': fields.get('change_type', ''),
                    'node_id': fields.get('node_id', ''),
                    'timestamp': fields.get('timestamp', ''),
                }
                try:
                    event['data'] = json.loads(fields.get('data', '{}'))
                except Exception:
                    event['data'] = {}
                events.append(event)
            return web.json_response({
                'events': events,
                'count': len(events),
                'timestamp': datetime.now().isoformat(),
            })
        except Exception as e:
            return web.json_response({'error': str(e), 'events': []}, status=500)


# ─── 主入口 ───────────────────────────────────────────────────────────────────

async def main():
    monitor = EthNodeMonitoring()
    await monitor.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("收到停止信号，正在关闭...")
    finally:
        await monitor.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
