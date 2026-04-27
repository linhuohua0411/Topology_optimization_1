# 中央数据收集器集成方案

## 概述

将中央数据收集器集成到 `eth_node_cleaner` 容器中，实现了：
1. 保持原有的网络拓扑管理功能
2. 新增中央数据收集器功能（8888端口）
3. 解决容器网络隔离问题

## 架构设计

```
eth_node_cleaner容器
├── eth_node_cleaner.py     # 原有功能：网络拓扑管理
├── central_collector/      # 新增功能：中央数据收集器
│   ├── __init__.py
│   ├── collector.py        # 核心收集器
│   ├── data_cache.py       # 数据缓存
│   ├── http_server.py      # HTTP服务
│   ├── config.py           # 配置管理
│   ├── models.py           # 数据模型
│   └── data_processor.py   # 数据处理
└── main.py                 # 统一启动脚本
```

## 主要特性

### 1. 双进程架构
- 进程1：运行原有的网络拓扑管理器
- 进程2：运行中央数据收集器（8888端口）

### 2. 网络配置
容器连接到所有必要的网络：
- `net_151_net0`：AS151网络
- `net_152_net0`：AS152网络
- `net_ix_ix100`：IXP核心网络

### 3. 数据处理能力
- **内存缓存**：快速数据访问
- **Neo4j集成**（可选）：存储P2P拓扑数据
- **Redis集成**（可选）：存储状态和指标数据

## API端点

### 数据接收端点
- `POST /api/v1/monitoring/data` - 接收监控数据
- `POST /api/v1/monitoring/heartbeat` - 接收心跳
- `GET /api/v1/monitoring/status` - 查询收集器状态

### 数据查询端点
- `GET /api/v1/monitoring/beacon/blocks` - 获取beacon区块
- `GET /api/v1/monitoring/beacon/fork_events` - 获取分叉事件
- `GET /api/v1/monitoring/beacon/network_health` - 获取网络健康状态
- `GET /api/v1/monitoring/beacon/attack_indicators` - 获取攻击指标

### 健康检查
- `GET /health` - 服务健康检查

## 容器配置

### 环境变量
```yaml
environment:
  - NEO4J_URI=bolt://eth_neo4j:7688
  - NEO4J_USER=neo4j
  - NEO4J_PASSWORD=1qaz@WSX
  - REDIS_HOST=redis
  - REDIS_PORT=6379
  - COLLECTOR_PORT=8888
  - LOG_LEVEL=INFO
```

### 端口映射
- `8888:8888` - 中央数据收集器HTTP服务

## 使用方式

### 1. 构建和启动
```bash
# 构建镜像
docker-compose build eth_node_cleaner

# 启动服务
docker-compose up -d eth_node_cleaner
```

### 2. 容器内代理访问
容器内的监控代理现在可以通过容器名访问：
```python
# 代理配置
collector_endpoint = "http://eth_node_cleaner:8888/api/v1/monitoring/data"
```

### 3. 后端服务访问
后端服务可以通过HTTP API获取数据：
```python
# BeaconDataSource改为HTTP调用
response = await session.get("http://localhost:8888/api/v1/monitoring/beacon/blocks")
blocks = response.json()
```

## 测试

使用提供的测试脚本验证功能：
```bash
python test_collector.py
```

## 优势

1. **解决网络隔离**：容器在同一网络中，可以直接通信
2. **复用基础设施**：利用现有容器，减少资源消耗
3. **保持兼容性**：API接口不变，后端只需改变调用方式
4. **灵活部署**：可选的数据库连接，按需配置

## 注意事项

1. 确保 `eth_node_cleaner` 容器连接到所有以太坊节点所在的网络
2. 数据库连接是可选的，不配置也能正常运行（仅内存缓存）
3. 日志级别可通过 `LOG_LEVEL` 环境变量调整 