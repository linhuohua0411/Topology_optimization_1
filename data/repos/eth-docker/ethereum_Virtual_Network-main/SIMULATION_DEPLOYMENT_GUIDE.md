# 以太坊虚拟化网络仿真系统 — 部署指南与功能说明

## 目录

1. [系统概述](#1-系统概述)
2. [部署方式](#2-部署方式)
3. [四大仿真功能详解](#3-四大仿真功能详解)
4. [控制 API 接口文档](#4-控制-api-接口文档)
5. [数据库表结构与拓扑分析](#5-数据库表结构与拓扑分析)
6. [配置参数说明](#6-配置参数说明)
7. [两种拓扑的差异对比](#7-两种拓扑的差异对比)

---

## 1. 系统概述

本系统在 BIRD 软路由构建的虚拟化广域网络上运行以太坊 PoS 公有链网络。为使虚拟网络更接近真实公链测试网，系统包含以下**自动运行**的仿真模块：

| 模块 | 功能 | 触发方式 |
|------|------|----------|
| `TxGenerator` | 随机发送 ETH 转账交易 | 每 15~45 秒自动发送一笔 |
| `ChaosAgent` | 节点随机上下线 | 每 180~480 秒随机下线一个节点 |
| `ContractAgent` | 随机部署和调用智能合约 | 每 30~60 秒调用一次合约；每 180~420 秒部署新合约 |
| `WanChaosAgent` | WAN 链路随机整形（调整网速） | 每 90~240 秒随机改变一条 WAN 链路参数 |
| `ControlApi` | HTTP 控制接口 | 被动监听，供研究员手动触发 |

**核心特性：部署即自动运行。** 启动 docker-compose 后，`eth_simulation` 容器自动初始化并并行运行上述所有模块，无需任何手动干预。

### 架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                    eth_simulation 容器                            │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │
│  │TxGenerator│ │ChaosAgent│ │ContractAgt│ │ WanChaosAgent    │  │
│  │(功能1)    │ │(功能2)   │ │(功能3)    │ │ (功能4)          │  │
│  └─────┬────┘ └─────┬────┘ └─────┬─────┘ └────────┬─────────┘  │
│        │            │            │                 │             │
│  ┌─────▼────────────▼────────────▼─────────────────▼─────────┐  │
│  │                     Reporter                               │  │
│  │    (数据上报到 PostgreSQL + central_collector)              │  │
│  └────────────────────────────────────────────────────────────┘  │
│        │                                                         │
│  ┌─────▼────────────────────────────────────────────────────┐   │
│  │              ControlApi (HTTP :8890)                       │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
         │                    │ (Docker exec)          │
         ▼                    ▼                        ▼
   ┌──────────┐    ┌───────────────────┐    ┌─────────────────┐
   │ Geth RPC │    │ 以太坊 POS 节点    │    │ BIRD 路由器     │
   │ (交易/合约)│   │ (ip link up/down) │    │ (tc qdisc)      │
   └──────────┘    └───────────────────┘    └─────────────────┘
```

---

## 2. 部署方式

### 2.1 前置要求

- Docker Engine 24+
- Docker Compose v2+
- 操作系统：Linux (amd64)
- 资源要求：
  - **2as_6nodes**：4 核 CPU / 8GB 内存 / 30GB 磁盘
  - **12as_100nodes**：16+ 核 CPU / 32GB+ 内存 / 100GB+ 磁盘

### 2.2 一键部署（2as_6nodes 为例）

```bash
cd 2as_6nodes

# 1. 构建基础镜像（必须先构建）
docker compose build 39e016aa9e819f203ebc1809245a5818 f1d53a66de3c35d8a921558f3b4bdbbd

# 2. 构建所有服务
docker compose build

# 3. 启动整个网络
docker compose up -d

# 4. 查看状态
docker compose ps
```

### 2.3 启动后自动发生的事情

1. **BIRD 路由器启动** → BGP/OSPF 开始收敛 → 广域网路由表建立
2. **以太坊节点启动** → Geth 开始 peer 发现 → Lighthouse 开始共识
3. **PostgreSQL / Redis / Neo4j 启动** → 数据库就绪
4. **eth_simulation 容器启动**（等待 PG 健康后）→ 自动执行以下流程：
   - 连接 Geth RPC，等待链产生区块（区块号 ≥ 1）
   - 编译 Solidity 合约（SimpleCounter、SimpleToken）
   - 部署基线合约到链上
   - 并行启动 5 个模块（交易、混沌、合约、WAN、API）
   - 所有模块**不间断运行**，直到容器停止

### 2.4 12as_100nodes 部署

与 2as_6nodes 完全相同的流程，只是在 `12as_100nodes` 目录下执行。该拓扑的 `docker-compose.yml` 可能拆分为多个文件：

```bash
cd 12as_100nodes
docker compose build
docker compose up -d
```

### 2.5 验证部署成功

```bash
# 查看仿真日志
docker logs eth_simulation --tail 20

# 应该看到类似：
# ✅ 4 个代理已启动，开始仿真
# 📤 交易发送 [1] ...
# ✅ 交易确认: ... 区块#N Gas=21000 状态=成功
# ⬇️  下线节点 ...
# 🌐 已对 ... 应用 WAN profile ...
```

---

## 3. 四大仿真功能详解

### 3.1 功能1：随机交易发送（TxGenerator）

**文件**: `eth_simulation/tx_generator.py`

**工作原理**:
1. 连接到配置的 Geth RPC 端点
2. 从 `eth_accounts` 获取已解锁账户列表
3. 每隔 **15~45 秒**（随机）执行：
   - 随机选择一个有余额的账户作为发送方
   - 随机选择一个其他账户作为接收方
   - 生成随机金额（0.001~0.01 ETH）
   - 通过 `eth_sendTransaction` 发送交易
   - 异步等待收据（最多 60 秒）
   - 上报到 PostgreSQL `transactions` 表和 `central_collector`
4. 每 10 笔交易自动刷新账户余额

**拓扑可见性**:
- 监控采集间隔 30 秒，交易间隔 15~45 秒
- 每次采集周期内至少有 **1~2 笔新交易**
- `transaction_network_topology` 视图可查询地址间转账关系图

### 3.2 功能2：节点随机上下线（ChaosAgent）

**文件**: `eth_simulation/chaos_agent.py`

**工作原理**:
1. 通过 Docker SDK 获取目标以太坊节点容器列表
2. 每隔 **180~480 秒**（随机）执行一次下线操作：

   **下线流程**:
   ```
   a. 自动发现容器内主网络接口（通过 ip route show default 找到默认路由设备）
   b. 保存完整网络配置：
      - IP 地址和子网掩码（ip -o -4 addr show）
      - 默认网关和网关设备（ip route show default）
      - ARP 邻居表（ip neigh show）
   c. 执行 ip link set <接口> down （不是停止容器！）
   d. 验证接口确实已变为 DOWN 状态
   e. 设定随机恢复时间（60~120 秒）
   f. 上报事件到 node_chaos_events 表和 topology_changes 表
   ```

   **上线恢复流程**:
   ```
   a. 执行 ip link set <接口> up
   b. 检查 IP 地址是否仍在，若丢失则重新添加（ip addr add）
   c. 删除旧默认路由，添加新默认路由（ip route replace default via <网关>）
   d. 恢复 ARP 邻居表（ip neigh replace ... nud reachable）
   e. 验证：接口状态=UP、默认路由存在、网关可 ping
   f. 验证 Geth RPC 可达，若 peer 数为 0 则主动 admin_addPeer
   g. 上报恢复事件
   ```

**关键设计**:
- 使用 `ip link set` 而非容器停止/冻结，更真实地模拟网络故障
- 同时下线节点数不超过配置上限（2as: 1个, 12as: 30个），防止链共识崩溃
- BootNode 和 BeaconSetup 永远不会被下线（在排除列表中）
- 下线时间 60~120 秒 ≥ 2 个监控采集周期（30秒），确保**拓扑变化可被捕获**
- 恢复后主动添加 Geth peer，加速区块链网络重连

**研究员手动控制接口**:
```bash
# 指定某个节点下线
curl -X POST http://localhost:8890/api/v1/chaos/nodes/down \
  -H "Content-Type: application/json" \
  -d '{"container_name": "as152h-Ethereum-POS-4-10.152.0.71", "duration_seconds": 90}'

# 指定某个节点上线
curl -X POST http://localhost:8890/api/v1/chaos/nodes/up \
  -H "Content-Type: application/json" \
  -d '{"container_name": "as152h-Ethereum-POS-4-10.152.0.71"}'

# 查看所有节点状态
curl http://localhost:8890/api/v1/chaos/nodes
```

### 3.3 功能3：随机合约部署与调用（ContractAgent）

**文件**: `eth_simulation/contract_agent.py`

**工作原理**:
1. 启动时编译两种 Solidity 合约（使用内置 solc 0.8.20）：
   - **SimpleCounter**: 计数器合约（increment / incrementBy / decrement / reset）
   - **SimpleToken**: ERC20 代币合约（transfer / mint / burn）
2. 部署基线合约并执行首次调用
3. 运行期间双循环：
   - **合约调用循环**：每 **30~60 秒** 随机选择一个已部署合约执行操作
     - Counter: increment、incrementBy(1~10)、decrement
     - Token: transfer(1~100 STT)、mint(100~1000 STT)、burn(1~10 STT)
   - **合约部署循环**：每 **180~420 秒** 随机部署一个新合约实例
4. 所有部署和调用事件上报到 `contracts` 和 `contract_events` 表

**拓扑可见性**:
- `contract_interaction_topology` 视图展示合约-方法-调用次数关系图
- `contract_interaction_hourly` 视图按小时聚合合约活动变化

### 3.4 功能4：WAN 链路随机整形（WanChaosAgent）

**文件**: `eth_simulation/wan_chaos_agent.py`

**工作原理**:
1. 扫描 Docker 容器，找到 BIRD 路由器的 IXP 接口（`ix*` 前缀接口）
2. 每隔 **90~240 秒**（随机）执行：
   - 随机选择一条未被修改的 WAN 链路
   - 保存当前 qdisc 基线状态
   - 生成随机 WAN profile：
     - 带宽：5~250 Mbit（12as: 5~300 Mbit）
     - 延迟：15~180 ms（12as: 15~220 ms）
     - 抖动：3~30 ms（12as: 3~35 ms）
     - 丢包：0~2.5%
   - 应用双层 tc qdisc：
     ```
     tc qdisc replace dev <接口> root handle 1: tbf rate <带宽>mbit burst <突发>kbit latency 60ms
     tc qdisc replace dev <接口> parent 1:1 handle 10: netem delay <延迟>ms <抖动>ms distribution normal loss <丢包>%
     ```
   - 持续 **120~300 秒** 后自动恢复基线状态
3. 同时修改的链路数不超过上限（2as: 2条, 12as: 6条）

**研究员手动控制接口**:
```bash
# 指定 WAN 参数
curl -X POST http://localhost:8890/api/v1/wan/apply \
  -H "Content-Type: application/json" \
  -d '{"container_name": "as151brd-router0-10.151.0.254", "interface": "ix100",
       "bandwidth_mbit": 10, "delay_ms": 200, "jitter_ms": 50, "loss_pct": 5.0,
       "duration_seconds": 180}'

# 查看当前活跃的 WAN 配置
curl http://localhost:8890/api/v1/wan/active

# 重置某条链路
curl -X POST http://localhost:8890/api/v1/wan/reset \
  -H "Content-Type: application/json" \
  -d '{"container_name": "as151brd-router0-10.151.0.254", "interface": "ix100"}'
```

---

## 4. 控制 API 接口文档

`eth_simulation` 容器在端口 **8890** 上提供 HTTP 控制接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 健康检查 |
| GET | `/api/v1/status` | 所有模块的统计信息 |
| GET | `/api/v1/chaos/nodes` | 列出所有节点及状态 (up/down) |
| POST | `/api/v1/chaos/nodes/down` | 指定节点下线 |
| POST | `/api/v1/chaos/nodes/up` | 指定节点上线 |
| GET | `/api/v1/wan/targets` | 列出所有可操作的 WAN 链路 |
| GET | `/api/v1/wan/active` | 列出当前活跃的 WAN 配置 |
| POST | `/api/v1/wan/apply` | 应用 WAN 配置 |
| POST | `/api/v1/wan/reset` | 重置 WAN 配置 |

---

## 5. 数据库表结构与拓扑分析

### 5.1 核心数据表

| 表名 | 用途 | 写入模块 |
|------|------|----------|
| `transactions` | 所有交易记录 | TxGenerator |
| `contracts` | 已部署合约 | ContractAgent |
| `contract_events` | 合约调用事件 | ContractAgent |
| `node_chaos_events` | 节点上下线完整历史 | ChaosAgent |
| `wan_chaos_events` | WAN 扰动完整历史 | WanChaosAgent |
| `topology_changes` | 统一拓扑变化记录 | All |
| `node_failures` | 节点当前状态（最新） | ChaosAgent |

### 5.2 拓扑分析视图

| 视图名 | 用途 |
|--------|------|
| `transaction_network_topology` | 交易网络拓扑图（地址间转账关系） |
| `transaction_topology_hourly` | 按小时聚合的交易拓扑快照 |
| `contract_interaction_topology` | 合约交互拓扑（合约-方法调用关系） |
| `contract_interaction_hourly` | 按小时合约交互变化 |
| `node_updown_timeline` | 节点上下线时间线（含事件间隔） |
| `wan_bandwidth_timeline` | WAN 带宽变化时间线 |
| `simulation_events_timeline` | 综合仿真事件统一时间线 |

### 5.3 查询示例

```sql
-- 查看交易网络拓扑
SELECT from_address, to_address, tx_count, total_value_wei
FROM transaction_network_topology;

-- 查看节点上下线时间线
SELECT container_name, event_type, trigger, seconds_since_prev_event, event_time
FROM node_updown_timeline ORDER BY event_time;

-- 查看 WAN 带宽变化
SELECT container_name, interface, bandwidth_mbit, delay_ms, loss_pct, event_time
FROM wan_bandwidth_timeline ORDER BY event_time;

-- 查看所有仿真事件的统一时间线
SELECT timestamp, event_source, event_type, target
FROM simulation_events_timeline ORDER BY timestamp DESC LIMIT 20;
```

---

## 6. 配置参数说明

所有参数均可通过 docker-compose.yml 中的**环境变量**覆盖。

### 6.1 交易配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ETH_RPC_URL` | 见 config.py | Geth RPC 端点 |
| `TX_MIN_INTERVAL` | 15 | 交易最小间隔（秒） |
| `TX_MAX_INTERVAL` | 45 | 交易最大间隔（秒） |
| `UNLOCKED_ACCOUNTS` | 见 config.py | 已解锁账户列表（逗号分隔） |

### 6.2 混沌配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CHAOS_DOWN_MIN` | 60 | 节点下线最短时间（秒） |
| `CHAOS_DOWN_MAX` | 120 | 节点下线最长时间（秒） |
| `CHAOS_UP_MIN` | 180 | 两次下线事件最短间隔（秒） |
| `CHAOS_UP_MAX` | 480 | 两次下线事件最长间隔（秒） |
| `CHAOS_INTERFACE` | （空=自动发现） | 目标网络接口名 |
| `CHAOS_TARGET_PATTERNS` | 见 config.py | 目标容器名前缀（逗号分隔） |

### 6.3 合约配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CONTRACT_DEPLOYER` | 见 config.py | 合约部署者账户 |
| `CONTRACT_CALL_MIN_INTERVAL` | 30 | 合约调用最小间隔（秒） |
| `CONTRACT_CALL_MAX_INTERVAL` | 60 | 合约调用最大间隔（秒） |
| `CONTRACT_DEPLOY_MIN_INTERVAL` | 180 | 新合约部署最小间隔（秒） |
| `CONTRACT_DEPLOY_MAX_INTERVAL` | 420 | 新合约部署最大间隔（秒） |

### 6.4 WAN 混沌配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `WAN_TARGET_PATTERNS` | `brd-` | BIRD 路由器容器名匹配模式 |
| `WAN_INTERFACE_PREFIXES` | `ix` | IXP 接口名前缀 |
| `WAN_EVENT_MIN_INTERVAL` | 90 | 两次 WAN 扰动最短间隔（秒） |
| `WAN_EVENT_MAX_INTERVAL` | 240 | 两次 WAN 扰动最长间隔（秒） |
| `WAN_DURATION_MIN` | 120 | WAN 扰动最短持续时间（秒） |
| `WAN_DURATION_MAX` | 300 | WAN 扰动最长持续时间（秒） |

---

## 7. 两种拓扑的差异对比

两种拓扑共享**完全相同的核心代码**（10 个 Python 模块 + 7 个 SQL 文件），仅 `config.py` 中的默认参数不同：

| 参数 | 2as_6nodes | 12as_100nodes |
|------|-----------|---------------|
| 验证者节点数 | 4 | 107 |
| AS 数量 | 2 (AS151, AS152) | 12 (AS101-AS112) |
| IXP 数量 | 1 (IX100) | 4 (IX51-IX54) |
| 同时下线上限 | 1 | 30 |
| 混沌接口 | `net0` | 自动发现 |
| WAN 并发链路上限 | 2 | 6 |
| 最大带宽 | 250 Mbit | 300 Mbit |
| 最大延迟 | 180 ms | 220 ms |

所有差异通过环境变量在 `docker-compose.yml` 中覆盖，核心逻辑完全一致。
