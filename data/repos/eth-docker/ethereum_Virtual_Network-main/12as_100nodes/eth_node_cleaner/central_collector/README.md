# 独立中央数据收集器

## 概述

这是从后端服务中提取的独立中央数据收集器，运行在 `eth_node_cleaner` 容器中，为以太坊监控系统提供统一的数据收集和处理服务。

## 功能特性

- 🌐 HTTP API服务（端口8888）
- 📊 多种数据类型支持（peers、blocks、status、metrics）
- 💾 灵活的数据存储（Neo4j、Redis、文件）
- 🔄 实时数据缓存和处理
- 🏗️ 容器化部署，易于扩展

## API端点

### 数据接收端点
- `POST /api/v1/monitoring/data` - 接收监控数据
- `POST /api/v1/monitoring/heartbeat` - 接收心跳
- `GET /api/v1/monitoring/status` - 查询服务状态

### 数据查询端点
- `GET /api/v1/monitoring/beacon/blocks` - 获取beacon区块数据
- `GET /api/v1/monitoring/beacon/fork_events` - 获取分叉事件
- `GET /api/v1/monitoring/beacon/network_health` - 获取网络健康状态
- `GET /api/v1/monitoring/beacon/attack_indicators` - 获取攻击指标

## 配置

通过环境变量配置：

```bash
# HTTP服务配置
HTTP_PORT=8888

# 数据库连接（可选）
NEO4J_URI=bolt://neo4j:7688
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

# 日志配置
LOG_LEVEL=INFO

# 缓存配置
CACHE_TTL=300
MAX_BEACON_BLOCKS=100
```

## 数据处理

### P2P数据（peers）
- 存储到Neo4j图数据库
- 区分执行层和共识层节点
- 维护节点间的连接关系
- 自动清理过期连接

### 区块数据（blocks）
- 文件存储：按日期组织，便于归档
- Neo4j存储：创建区块节点和关系
- Redis存储：缓存最新区块信息

### 状态数据（status）
- 存储到Redis，支持过期时间
- 发布状态更新事件
- 更新容器数据缓存

### 性能指标（metrics）
- 存储到Redis
- 支持时序数据查询

## 部署说明

### 1. 容器内运行
中央数据收集器集成在 `eth_node_cleaner` 容器中：

```yaml
eth_node_cleaner:
  image: eth_node_cleaner:latest
  networks:
    - net_151_net0
    - net_152_net0
    - net_ix_ix100
  ports:
    - "8888:8888"
  environment:
    - NEO4J_URI=bolt://neo4j:7688
    - REDIS_HOST=redis
```

### 2. 监控代理配置
监控代理应配置为向 `eth_node_cleaner:8888` 发送数据：

```python
CENTRAL_COLLECTOR_URL = "http://eth_node_cleaner:8888/api/v1/monitoring"
```

### 3. 后端服务集成
后端服务通过HTTP API访问数据：

```python
async with aiohttp.ClientSession() as session:
    async with session.get("http://eth_node_cleaner:8888/api/v1/monitoring/beacon/blocks") as resp:
        data = await resp.json()
        blocks = data['blocks']
```

## 数据格式

### 监控数据推送格式
```json
{
    "container_id": "container_123",
    "node_id": "node_456",
    "timestamp": "2024-01-01T12:00:00",
    "data_type": "peers",
    "data": {
        "peers": [
            {
                "id": "peer_789",
                "direction": "inbound",
                "state": "connected",
                "client_version": "geth/v1.10.0"
            }
        ]
    },
    "agent_version": "1.0.0",
    "local_ip": "10.0.0.1"
}
```

### 心跳格式
```json
{
    "container_id": "container_123",
    "node_id": "node_456",
    "status": "active"
}
```

## 监控和维护

### 健康检查
```bash
curl http://eth_node_cleaner:8888/api/v1/monitoring/status
```

### 日志查看
```bash
docker logs eth_node_cleaner -f | grep CentralDataCollector
```

### 数据目录
- 区块数据：`/data/blocks/`
- 日志文件：容器标准输出

## 故障排查

1. **端口占用**：确保8888端口未被其他服务占用
2. **网络连接**：确保容器在正确的网络中
3. **数据库连接**：检查Neo4j和Redis的连接配置
4. **数据格式**：确保推送的数据符合预期格式

## 与后端版本的差异

1. **独立部署**：可以独立于后端服务运行
2. **直接存储**：不依赖后端的拓扑和区块链服务
3. **增强处理**：P2P和区块数据处理功能更完整
4. **灵活配置**：数据库连接可选，支持纯缓存模式 