# 以太坊虚拟网络仿真平台 — 完整技术参考手册

**版本**：v3.0（含真实环境测试结论）  
**测试服务器**：161.97.133.14（24核/62GB RAM）  
**最后更新**：2026-03-17

---

## 目录

1. [项目目标与核心价值](#1-项目目标与核心价值)
2. [整体架构原理](#2-整体架构原理)
3. [网络层设计（BIRD BGP/OSPF）](#3-网络层设计)
4. [以太坊层设计（Geth + Lighthouse PoS）](#4-以太坊层设计)
5. [监控层设计](#5-监控层设计)
6. [仿真层设计（eth_simulation）](#6-仿真层设计)
7. [数据层设计（Neo4j + Redis + PostgreSQL）](#7-数据层设计)
8. [两个拓扑方案对比](#8-两个拓扑方案对比)
9. [部署指南（手把手）](#9-部署指南)
10. [真实环境测试结论](#10-真实环境测试结论)
11. [已知问题与解决方案](#11-已知问题与解决方案)
12. [扩展与二次开发](#12-扩展与二次开发)

---

## 1. 项目目标与核心价值

### 1.1 为什么要构建这个平台？

真实的以太坊公有链测试网（如 Sepolia、Holesky）存在以下局限：
- 无法控制网络拓扑（节点分布由全球矿工决定）
- 无法模拟特定的网络攻击场景（如节点下线、网络分区）
- 无法实时获取完整的 P2P 连接图数据
- 测试成本高（需要真实 ETH 支付 Gas 费）

**本平台目标**：在单台物理服务器上，用 Docker 容器完整仿真一个真实互联网结构（多 AS + BGP 路由）上运行的以太坊 PoS 公有链，并配备完整的实时监控和仿真能力。

### 1.2 核心价值

| 价值点 | 说明 |
|--------|------|
| **完全可控** | 可随时修改拓扑、节点数量、网络参数 |
| **攻击场景仿真** | 通过 `ip link set <iface> down/up` 模拟网络故障 |
| **实时拓扑监控** | 毫秒级捕获 P2P 连接变化，存入图数据库 |
| **链上活动仿真** | 自动发交易、部署合约、调用合约 |
| **时序数据研究** | 记录完整的拓扑变化时序，支持鲁棒性分析 |

---

## 2. 整体架构原理

### 2.1 三层架构概述

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: 仿真与监控层                     │
│   eth_simulation (交易/混沌/合约)   eth_node_monitoring (API)│
│         eth_node_cleaner (中央收集)  neo4j/redis/postgresql  │
├─────────────────────────────────────────────────────────────┤
│                    Layer 2: 以太坊层                         │
│   Geth (执行层 :8545)   Lighthouse BN+VC (共识层 :8000)     │
│   每个以太坊节点容器内: Geth + Lighthouse + Agent(热部署)    │
├─────────────────────────────────────────────────────────────┤
│                    Layer 1: 网络路由层                       │
│   BIRD2 (BGP + OSPF)   IXP Route Server   Transit AS        │
│   tc qdisc (带宽/延迟限制)   Docker 虚拟网络桥接             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块间完整数据流

```
┌──────────────────────────────────────────────────────────────────────┐
│           每个以太坊节点容器（如 POS-3，10.101.0.73）                │
│                                                                      │
│  Geth :8545 ←──→ Engine API ←──→ Lighthouse BN :8000               │
│       ↑                                          ↑                   │
│  P2P devp2p                               P2P libp2p                │
│  连接50+节点                              连接75+节点                │
│                                                                      │
│  [热部署Agent]  eth_node_monitoring_agent.py (后台进程)             │
│       │  每30s: localhost:8545 → admin_peers, admin_nodeInfo        │
│       │  每30s: <node_ip>:8000 → /eth/v1/node/peers, validators    │
│       │  每30s: POST p2p_topology → eth_node_cleaner:8888          │
│       └  每30s: POST heartbeat → eth_node_cleaner:8888             │
└──────────────────────────────────────────────────────────────────────┘
         ↓ 实时数据推送
┌──────────────────────────────────────────────────────────────────────┐
│              eth_node_cleaner :8888（中央协调器）                    │
│                                                                      │
│  CentralDataCollector (asyncio HTTP Server)                         │
│    DataProcessor → 路由11种数据类型 → Neo4j / Redis / PostgreSQL    │
│    TopologyChangeDetector → 对比前后状态 → 生成变化事件             │
│    ChangeEventSender → XADD Redis Stream + PUBLISH Pub/Sub          │
│                                                                      │
│  EthNetworkTopologyManager (独立进程，每6s)                         │
│    ping 所有 Neo4j 中记录的节点 IP                                  │
│    不可达 → DETACH DELETE → 发布 node_removed 事件                  │
└──────────────────────────────────────────────────────────────────────┘
         ↓ Neo4j/Redis/PostgreSQL 写入
         ↓ Redis Pub/Sub 变化通知
┌──────────────────────────────────────────────────────────────────────┐
│              eth_node_monitoring :9999（只读仪表盘）                 │
│                                                                      │
│  后台任务1: 订阅 Redis Pub/Sub → 实时接收拓扑变化事件               │
│  后台任务2: XREAD Redis Stream → 读取历史变化流                     │
│  后台任务3: 每10s 轮询 Neo4j → 获取当前完整拓扑快照               │
│  后台任务4: 每60s 打印统计摘要                                      │
│  HTTP API: 9个端点对外提供监控数据                                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 节点下线检测的双重机制

```
节点网络接口 DOWN (ip link set <iface> down)
    │
    ├─── 机制一（快速，~12秒）：
    │    eth_node_cleaner 每6s ping → 连续2次失败 → 判定下线
    │    → Neo4j DETACH DELETE
    │    → Redis PUBLISH node_removed
    │    → eth_node_monitoring 实时感知
    │
    └─── 机制二（备份，~60秒）：
         Agent 进程收到 SIGINT 或随接口断开 → 心跳停止
         → eth_node_cleaner 60s 无心跳超时
         → 触发 _handle_inactive_containers()
         → 清理 Neo4j + Redis + 记录 node_failures 表

两种机制互为备份，任一触发都确保拓扑图实时清理。
```

---

## 3. 网络层设计

### 3.1 BIRD2 路由软件

每个路由器容器启动时执行 `start.sh`：

```bash
# 启动流程
interface_setup   # 将 Docker eth0 重命名为 net0/inet0 等，并设置 tc qdisc 流量整形
ip link add dummy0 type dummy && ip addr add 10.0.0.X/32 dev dummy0  # Router-ID loopback
bird -d            # 启动 BIRD2（读取 /etc/bird/bird.conf）
```

### 3.2 BIRD 路由策略（BGP Large Community）

```
# 路由标记（以 AS151 为例）
LOCAL_COMM    = (151, 0, 0)    # 本 AS 的路由
CUSTOMER_COMM = (151, 1, 0)    # 下游客户路由
PEER_COMM     = (151, 2, 0)    # 对等路由
PROVIDER_COMM = (151, 3, 0)    # 上游提供商路由

# 优先级（local_pref）
LOCAL:    40   # 最高优先级，使用本地路由
CUSTOMER: 30
PEER:     20
PROVIDER: 10   # 最低，仅在无更优路由时使用

# 出口策略：只将 LOCAL 和 CUSTOMER 路由广播给上游
export where bgp_large_community ~ [LOCAL_COMM, CUSTOMER_COMM];
```

### 3.3 流量整形（tc qdisc）

每个接口通过 `interface_setup` 脚本配置：

```bash
# TBF (Token Bucket Filter) 限速
tc qdisc add dev <iface> root handle 1:0 tbf rate ${bw}bit buffer 1000000 limit 1000
# netem 延迟和丢包模拟
tc qdisc add dev <iface> parent 1:0 handle 10: netem delay ${latency}ms loss ${loss}%
```

参数来自 `ifinfo.txt`：格式为 `接口名:网段:延迟(ms):带宽:丢包率`

### 3.4 跨 AS 通信路径（以 2as_6nodes 为例）

```
发送方: 10.151.0.73 (POS-3)
目标:   10.152.0.71 (POS-4)

路由过程:
  POS-3 → 查路由表 → 默认网关 10.151.0.254 (AS151 Router)
        → AS151 Router OSPF 知道此路由须走 BGP
        → 转发到 IXP ix100 (10.100.0.0/24)
        → AS152 Router (10.100.0.152) 接收
        → OSPF 路由到 net0 (10.152.0.0/24)
        → 直达 10.152.0.71 ✅
```

### 3.5 2as_6nodes 网络拓扑

```
Transit AS2 (r100: 10.100.0.2) ──BGP──┐
Transit AS21 (r100: 10.100.0.21) ─BGP─┤
                                       ▼
                            IXP ix100 (Route Server: 10.100.0.100)
                               │BGP          │BGP
                   ┌───────────┘             └───────────┐
        AS151 Router0                             AS152 Router0
        (10.100.0.151 / 10.151.0.254)        (10.100.0.152 / 10.152.0.254)
               │ OSPF Area 0                         │ OSPF Area 0
       10.151.0.0/24                         10.152.0.0/24
       ├─ .71 BeaconSetup                    ├─ .71 POS-4 (Validator+Miner)
       ├─ .72 BootNode (Geth:8545)           ├─ .72 POS-5 (Validator+Miner)
       └─ .73 POS-3 (Validator+Miner)        └─ .73 POS-6 (Validator+Miner)
```

### 3.6 12as_100nodes 网络拓扑

```
AS2 (Transit，连接4个IXP的串联骨干)
  r51─r52─r53─r54

AS21-24 (各IXP专用Transit)

    IXP ix51         IXP ix52         IXP ix53         IXP ix54
  10.51.0.0/24     10.52.0.0/24     10.53.0.0/24     10.54.0.0/24
  RS: .51           RS: .52          RS: .53          RS: .54
  ├─ AS101 (.101)   ├─ AS102 (.102)  ├─ AS103 (.103)  ├─ AS104 (.104)
  ├─ AS105 (.105)   ├─ AS106 (.106)  ├─ AS107 (.107)  ├─ AS108 (.108)
  └─ AS109 (.109)   └─ AS110 (.110)  └─ AS111 (.111)  └─ AS112 (.112)

每个 AS (以 AS101 为例):
  Router0: 10.101.0.254 (连 ix51: 10.51.0.101)
  ├─ inet0 (10.101.0.0/24): .71 BeaconSetup, .72 BootNode, .73 POS-3
  ├─ inet1 (10.101.1.0/24): .71 POS-4, .72 POS-5, .73 POS-6
  └─ inet2 (10.101.2.0/24): .71 POS-7, .72 POS-8, .73 POS-9
```

**注意**：12as_100nodes 的接口名为 `inet0/inet1/inet2`（非 `net0`），这影响混沌测试的接口参数配置。

---

## 4. 以太坊层设计

### 4.1 整体架构（Geth + Lighthouse PoS）

```
执行层 Geth                     共识层 Lighthouse
────────────────                 ─────────────────────────
处理交易、合约、状态   ←Engine API→   决定哪个区块有效
JSON-RPC :8545                   Beacon Node :8000
AuthRPC :8551 (JWT)              Validator Client (本地)
P2P devp2p :30303                P2P libp2p :9000
```

### 4.2 以太坊链参数

| 参数 | 2as_6nodes | 12as_100nodes |
|------|-----------|---------------|
| Chain Name | posRefinedNet | posCurrentEnhancedNet |
| Chain ID | 1337 | 1337 |
| 共识机制 | PoS (Lighthouse) | PoS (Lighthouse) |
| 执行层 | Geth | Geth |
| Terminal Total Difficulty | 20 | 20 |
| 验证者数量 | 4 | 107 (106个POS节点) |

### 4.3 启动流程（严格时序）

**节点类型说明：**
- `BeaconSetup`（hnode_X_host0）：创世初始化节点，运行一次后保持 HTTP 服务
- `BootNode`（hnode_X_host1）：P2P 发现引导节点，Geth bootnode + Lighthouse bootnode
- `POS-N`（hnode_X_host2~8）：PoS 验证者节点

**五步启动时序：**

```
Step 1: BeaconSetup (10.X.0.71)
  等待 POS-3 (10.X.0.73:8545) 的 Geth 就绪
  等待区块高度 > 5 (PoW 挖矿阶段)
  lcli deploy-deposit-contract → 部署验证者注册合约
  lcli insecure-validators --count 4/106 → 生成验证者密钥
  lcli interop-genesis → 生成 genesis.ssz 创世状态
  python3 beacon_bootnode_http_server.py → 在 :8090 提供文件下载服务

Step 2: 所有节点下载配置
  eth-bootstrapper 从 BootNode:8088 获取 Geth enode URL
  beacon-bootstrapper 从 BeaconSetup:8090 下载 testnet 配置、验证者密钥

Step 3: 各节点 Geth 启动
  geth init /tmp/eth-genesis.json  → 初始化创世块
  geth ... --bootnodes <enode> ... --mine --miner.threads=1
  → PoW 挖矿至 TTD=20，然后自动切换为 PoS 模式

Step 4: 各节点 Lighthouse 启动
  lighthouse bn ... --execution-endpoint http://localhost:8551  → Beacon Node
  lighthouse vc ... --beacon-nodes http://<self>:8000           → Validator Client

Step 5: P2P 网络自组织
  Geth devp2p: 通过 enode URL 发现 BootNode，再扩散到全网
  Lighthouse libp2p: 通过 ENR (Ethereum Node Record) 发现全网 Beacon 节点
  最终: 每个节点连接 50+ Geth peers，75-86 Lighthouse peers (12as_100nodes)
```

### 4.4 PoW → PoS 转换机制

```
启动时: Geth 以 PoW 模式挖矿（--mine --miner.threads=1）
  → 挖到 terminaltotaldifficulty = 20（通常只需 1-2 块）
  → Geth 停止 PoW，等待 Lighthouse 接管

Lighthouse 接管后：
  → 每 12 秒一个 slot 提议新区块
  → Validator Client 签名 Attestation
  → 超过 2/3 验证者签名后区块被 Finalized
```

### 4.5 以太坊账户管理

所有验证者节点启动时通过 `--unlock <address> --password <file>` 解锁账户。这意味着：
- **无需私钥**即可通过 `eth_sendTransaction` 发送交易
- 账户在本节点的 Geth RPC 上有效，但在其他节点 Geth 上无效
- 合约部署者必须使用对应节点的 RPC 端点

**2as_6nodes 已知账户：**

| 节点 | IP | 账户地址 | 角色 |
|------|-----|---------|------|
| BootNode | 10.151.0.72 | `0x1081c645CC8c21EfbB0114eAc5fcDBE01a1a4b19` | 引导节点 |
| POS-3 | 10.151.0.73 | `0x8c400205fDb103431F6aC7409655ad3cf8f6d007` | **主用账户**（合约部署者） |
| POS-4 | 10.152.0.71 | `0xD4CC43e3f2830f9082495Dba904B57fc2Ca95CBd` | 验证者 |
| POS-5 | 10.152.0.72 | `0x72943017A1fa5f255fC0f06625Aec22319FCd5b3` | 验证者 |
| POS-6 | 10.152.0.73 | `0xC5247277519ca71C488e7D093350aa659aCaDF7e` | 验证者 |

**关键配置**：eth_simulation 的 `ETH_RPC_URL` 必须指向持有解锁账户的节点（不是 BootNode，因为 BootNode 只有自己的账户）。

---

## 5. 监控层设计

### 5.1 eth_node_cleaner（中央协调器，:8888）

**内部两个并行进程：**

```python
main.py
├── ProcessPoolExecutor → EthNetworkTopologyManager (eth_node_cleaner.py)
│     # 独立进程，同步循环，每6秒：
│     # 1. 查 Neo4j 中所有 ExecNode/ConsNode 的 IP
│     # 2. 对每个 IP 执行 ping -c 2 -W 3
│     # 3. ping 失败 → MATCH (n {ip:$ip}) DETACH DELETE n
│     # 4. 向自身 8888 端口 POST network_topology_change 事件
│
└── asyncio → CentralDataCollector (central_collector/)
      # 异步事件驱动，常驻HTTP服务：
      # 1. HTTPServer (aiohttp) 监听 8888 端口
      # 2. asyncio.Queue (max=1000) 缓冲数据
      # 3. DataProcessor 从队列取数据，路由到 11 种处理器
      # 4. _heartbeat_checker 每 30s 检查心跳超时（60s 无心跳判定离线）
```

**11种数据类型处理路由：**

| data_type | 处理路径 | 存储目标 |
|-----------|---------|---------|
| `p2p_topology` | DataProcessor + TopologyChangeDetector | Neo4j 图 + Redis 状态缓存 + PG 变化记录 |
| `execution_links` | DataProcessor | Neo4j EXEC_PEERS_WITH 关系 |
| `transactions` | DataProcessor | PG transactions 表 + Neo4j Address 图 |
| `contracts` | DataProcessor | PG contracts/contract_events + Neo4j Contract 图 |
| `metrics` | DataProcessor | Redis Sorted Set（时序指标） |
| `beacon_state` | DataProcessor | Redis Beacon 状态缓存 |
| `beacon_blocks` | BlockchainProcessor | PG beacon_blocks + Redis 缓存 + 分叉检测 |
| `attestations` | DataProcessor | PG attestations 表 |
| `fork_event` | BlockchainProcessor | PG fork_events + Redis Pub/Sub 告警 |
| `node_snapshots` | DataProcessor | PG node_snapshots 表 |
| `network_topology_change` | DataProcessor + ChangeEventSender | PG 拓扑变化 + Redis 事件流 |

### 5.2 P2P 拓扑变化检测算法

```
每次收到节点 A 的 p2p_topology 数据：
  1. 从 Redis 获取历史状态: key = topology:execution_state:{node_id}
  2. 从当前数据提取状态（节点属性 + Peer 列表）
  3. 对比生成变化事件：
     - 首次上报 → node_added
     - Peer 新增 → link_added
     - Peer 减少 → link_removed
     - 节点属性变化 → node_updated（IP、版本等）
     - 验证者状态变化 → validator_status_changed
  4. 将变化事件通过 ChangeEventSender 写入：
     - PostgreSQL: eth_*_topology_changes 表（持久化历史）
     - Redis XADD: topology:changes Stream（可回放）
     - Redis PUBLISH: topology:changes:{layer}（实时通知）
  5. 更新 Redis 历史状态（TTL 1小时）

重要修复：validator_index=0 的问题
  原代码: if v.get('validator_index')  → 0 是假值，被过滤！
  修复后: if v.get('validator_index') is not None  → 正确保留索引0
```

### 5.3 eth_node_monitoring_agent.py（节点内置 Agent）

**部署方式**：热部署（docker cp + docker exec），不修改镜像。

```bash
# 部署命令（一键部署所有节点）
cd 2as_6nodes/   # 或 12as_100nodes/
./deploy_monitoring.sh

# 内部实现：对每个节点执行
docker cp eth_node_monitoring/eth_node_monitoring_agent.py ${container}:/usr/local/bin/
docker exec -d ${container} bash -c "
  CONTAINER_NAME='${container}' NODE_IP='${ip}' HAS_VALIDATOR='true'
  CENTRAL_COLLECTOR_URL='http://eth_node_cleaner:8888'
  nohup python3 /usr/local/bin/eth_node_monitoring_agent.py >> /var/log/eth_monitoring_agent.log 2>&1
"
```

**Agent 内部逻辑（纯 Python stdlib，无额外依赖）：**

```python
main():
  1. detect_node_ip()  # 从 CONTAINER_NAME 解析 IP，或读取接口（inet0/net0/eth0）
  2. wait_for_geth(timeout=300)   # 轮询 localhost:8545 直到响应
  3. wait_for_lighthouse(timeout=300)  # 轮询 <node_ip>:8000 直到响应
  4. 主采集循环（每 30 秒）:
     a. collect_geth(node_ip):    # admin_peers + admin_nodeInfo + eth_blockNumber
     b. collect_lighthouse(node_ip):  # /node/peers + /node/identity + /node/syncing + validators
     c. report_topology(...)      # POST p2p_topology 到 eth_node_cleaner:8888
     d. send_heartbeat(node_ip)   # POST heartbeat（保活信号）
```

**接口名自动检测**（支持两种拓扑）：
- 2as_6nodes：接口名为 `net0`
- 12as_100nodes：接口名为 `inet0`
- Agent 自动尝试：`inet0` → `net0` → `eth0`

### 5.4 eth_node_monitoring（只读仪表盘，:9999）

**9个 HTTP API 端点：**

| 端点 | 返回内容 | 数据来源 |
|------|---------|---------|
| `GET /health` | 服务状态 + 数据库连接 | 内存 |
| `GET /api/v1/monitoring/topology` | 完整拓扑快照 | Neo4j（每10s轮询） |
| `GET /api/v1/monitoring/events` | 最近200条变化事件 | 内存（Pub/Sub+Stream合并） |
| `GET /api/v1/monitoring/statistics` | 运行统计摘要 | 内存 |
| `GET /api/v1/monitoring/nodes` | 节点列表（可按layer过滤）| Neo4j缓存 |
| `GET /api/v1/monitoring/changes/execution` | 执行层变化记录 | PostgreSQL |
| `GET /api/v1/monitoring/changes/consensus` | 共识层变化记录 | PostgreSQL |
| `GET /api/v1/monitoring/validators` | 验证者信息 | PostgreSQL / Neo4j |
| `GET /api/v1/monitoring/stream/latest` | Redis Stream最新事件 | Redis |

**四个后台任务：**

```python
_topology_poll_loop():  每10秒 → Neo4j 查询完整拓扑 → 内存缓存
_stream_reader_loop():  持续 → XREAD topology:changes → 内存events列表
_pubsub_listener_loop(): 订阅 4 个 Redis 频道 → 实时接收变化通知
_log_summary_loop():    每60秒 → 打印统计摘要
```

---

## 6. 仿真层设计

### 6.1 eth_simulation 三大功能

#### 功能1：随机交易发送器 (tx_generator.py)

**设计原则：**
- 连接持有解锁账户的验证者节点 RPC（非 BootNode）
- 账户已通过 `--unlock` 解锁，直接 `eth_sendTransaction` 无需私钥
- 异步等待收据，确保交易上链后再统计

**关键参数：**

```yaml
ETH_RPC_URL: http://10.151.0.73:8545  # POS-3 节点（账户已解锁）
TX_MIN_INTERVAL: 15                    # 最小发送间隔（秒）
TX_MAX_INTERVAL: 45                    # 最大发送间隔（秒）
UNLOCKED_ACCOUNTS: 0x8c400...          # 发送方账户（仅本节点解锁的账户）
```

**数据流：**
```
web3.eth.send_transaction() → Geth mempool → 打包进区块（12s/slot）
    → 获取 receipt → POST p2p_topology to eth_node_cleaner:8888
    → PostgreSQL transactions 表 + Neo4j Address-TRANSACTED_WITH-Address 图
```

#### 功能2：节点混沌代理 (chaos_agent.py)

**核心安全约束：**

```python
# 1. 最短下线时间 >= eth_node_cleaner 检测时间（6s * 2次 = 12s）
CHAOS_DOWN_MIN = 60   # ≫ 12s，确保拓扑变化被记录

# 2. 同时下线数 ≤ max_concurrent_down（保证 >2/3 验证者在线）
# 2as_6nodes:   4个验证者，最多下线1个（75% > 66.7%）
# 12as_100nodes: 107个验证者，最多下线30个（72% > 66.7%）

# 3. 绝不操作基础设施
chaos_exclude_keywords = ["BeaconSetup", "BootNode"]
```

**完整执行流程：**

```python
async def bring_down(container):
    # 步骤1: 保存网络配置
    addr_output = container.exec_run("ip addr show <iface>")
    ip_with_prefix = parse(addr_output)   # e.g. "10.151.0.73/24"
    gateway = parse(route_output)          # e.g. "10.151.0.254"
    neighbors = parse(neigh_output)        # e.g. ["10.151.0.254", "10.151.0.72"]

    # 步骤2: 执行下线（保留IP，仅断开L2链路）
    container.exec_run("ip link set <iface> down")
    # 效果: 接口DOWN，IP保留，路由表删除默认路由，BIRD撤销BGP/OSPF广播

    # 等待60-120秒（期间 eth_node_cleaner ping失败→删除 Neo4j 节点）

    # 步骤3: 执行上线恢复
    container.exec_run("ip link set <iface> up")
    container.exec_run("ip route add default via <gateway> dev <iface>")
    # 验证恢复
    container.exec_run("ping -c 1 -W 2 <gateway>")
    # BIRD 自动检测接口UP → 重建BGP/OSPF邻居 → 以太坊P2P自动重连
```

**接口名差异（重要）：**
- 2as_6nodes：`net0`（由 interface_setup 将 eth0 重命名）
- 12as_100nodes：`inet0`（命名为 inet + 子网编号）

#### 功能3：智能合约代理 (contract_agent.py)

**部署的两个合约：**

**SimpleCounter** (Solidity 0.8.20, EVM Paris)：
```solidity
contract SimpleCounter {
    uint256 public count;
    event CountChanged(address indexed by, uint256 newCount, string action, uint256 ts);
    
    function increment() public { count++; emit CountChanged(msg.sender, count, "increment", block.timestamp); }
    function incrementBy(uint256 amount) public { ... }  // 1~100
    function decrement() public { require(count > 0); count--; ... }
    function reset() public onlyOwner { count = 0; ... }
    function getStats() public view returns (count, totalIncrements, totalDecrements, owner);
}
```

**SimpleToken** (ERC20-like)：
```solidity
contract SimpleToken {
    string public name = "SimTestToken";  // 符号: STT
    mapping(address => uint256) public balanceOf;
    
    function transfer(address to, uint256 amount) public returns (bool);
    function mint(address to, uint256 amount) public onlyOwner;
    function burn(uint256 amount) public;
    function approve/transferFrom...
}
```

**关键编译参数（必须）：**
```python
compiled = compile_source(
    source,
    solc_version="0.8.20",
    evm_version="paris",    # ← 必须！否则 PUSH0 操作码导致部署失败
    optimize=True,
)
```

**自动交互循环（每30-60秒随机选1种操作）：**

```
counter.increment()          → 调用计数器递增
counter.incrementBy(1-10)    → 批量递增
counter.decrement()          → 递减（count>0时）
token.transfer(to, amount)   → 代币转账（接收方从已知地址列表选取）
token.mint(to, amount)       → 铸造代币（owner only）
token.burn(amount)           → 销毁代币
```

---

## 7. 数据层设计

### 7.1 Neo4j 图数据模型

```cypher
// 节点类型
(:ExecNode {
    node_id: "7a4035fae408...",    // Geth enode ID (64 hex)
    ip: "10.151.0.73",
    client_type: "geth",
    client_version: "Geth/v1.13...",
    container_id: "as151h-Ethereum-POS-3-...",
    last_seen: datetime()
})

(:ConsNode {
    node_id: "16Uiu2HAmKLC...",    // Lighthouse peer_id (libp2p)
    ip: "10.151.0.73",
    client_type: "lighthouse",
    enr: "enr:-xxx",
    p2p_addresses: ["/ip4/10.151.0.73/tcp/9000/p2p/..."],
    sync_status: '{"is_syncing": false, "head_slot": "800"}'
    last_seen: datetime()
})

(:Validator {
    validator_index: 0,
    public_key: "0xaaa...",
    status: "active_ongoing",
    balance: 32000000000,
    effective_balance: 32000000000
})

(:Address { address: "0x8c400..." })         // 以太坊地址
(:Transaction { hash: "0x...", block_number: 100, value: 5000... })
(:Contract { address: "0xcFAB..." })

// 关系类型
(ExecNode)-[:EXEC_PEERS_WITH {direction: "outbound"}]->(ExecNode)
(ConsNode)-[:CONS_PEERS_WITH {direction: "inbound"}]->(ConsNode)
(ExecNode)-[:PAIRED_WITH]->(ConsNode)
(ConsNode)-[:MANAGES_VALIDATOR]->(Validator)
(Address)-[:SENT]->(Transaction)-[:RECEIVED_BY]->(Address)
(Address)-[:TRANSACTED_WITH {count: 3, total_value: 15000}]->(Address)
(Address)-[:CALLED_CONTRACT {call_count: 5, methods: ["increment"]}]->(Contract)
```

### 7.2 Redis Key 设计

```
# 拓扑变化事件流（可回放历史）
topology:changes              → Stream，ChangeEventSender 写入

# 实时通知频道
topology:changes:execution    → Pub/Sub，执行层P2P变化
topology:changes:consensus    → Pub/Sub，共识层P2P变化
fork_alerts                   → Pub/Sub，分叉检测告警
topology:detector:status      → Pub/Sub，检测器心跳

# 节点状态缓存（供 TopologyChangeDetector 对比）
topology:execution_state:{node_id}   → JSON，执行层节点状态（TTL 1h）
topology:consensus_state:{node_id}   → JSON，共识层节点状态（TTL 1h）
topology:active_nodes:execution      → Set，活跃执行层节点ID集合
topology:active_nodes:consensus      → Set，活跃共识层节点ID集合
topology:validator_to_node:{index}   → String，验证者→节点映射（TTL 1h）

# 检测器心跳
topology:detector:heartbeat          → String，TTL 5分钟

# 区块缓存
beacon:block:{hash}                  → Hash，区块信息（TTL 1h）
beacon:state:{container_id}          → Hash，Beacon链状态

# 性能指标时序（24h保留）
metrics:{container_id}:{type}:{key}  → Sorted Set（score=timestamp）
```

### 7.3 PostgreSQL 核心表结构（32张表）

**以太坊拓扑追踪（核心数据）：**

```sql
-- 执行层拓扑快照（每次重大变化时保存）
eth_execution_topology_snapshots (
    id, timestamp, snapshot_hash UNIQUE,
    node_count, link_count, topology_data JSONB
)

-- 执行层拓扑变化事件（主表，外键约束到快照）
eth_execution_topology_changes (
    id, event_id UUID UNIQUE, timestamp,
    change_type,                -- node_added/node_removed/link_added/link_removed
    after_snapshot_id → snapshots(id),
    diff_data JSONB,            -- 变化详情
    source, metadata JSONB
)

-- 执行层节点变化详情（每个节点变化一行）
eth_execution_node_changes (
    id, change_event_id → changes(id),
    node_id, change_type, old_data JSONB, new_data JSONB
)

-- 共识层（结构相同，表名前缀 eth_consensus_*）
```

**监控代理数据：**

```sql
-- 代理心跳记录（用于离线检测）
agent_heartbeats (
    id, container_id, node_id, heartbeat_time,
    status, agent_type, agent_version,
    monitoring_capabilities JSONB, local_ip
)

-- 活跃代理视图（最近5分钟）
CREATE VIEW active_agents AS
    SELECT ... FROM agent_heartbeats
    WHERE heartbeat_time >= NOW() - INTERVAL '5 minutes'

-- 节点故障记录
node_failures (
    id, container_id, node_id UNIQUE(container_id,node_id),
    failure_time, failure_type, status, details JSONB
)
```

---

## 8. 两个拓扑方案对比

### 8.1 规模与资源

| 维度 | 2as_6nodes | 12as_100nodes |
|------|-----------|---------------|
| 自治域(AS) | 2 | 12 |
| IXP | 1 | 4 |
| 以太坊节点 | 6 | 108 |
| 验证者 | 4 | 107 |
| Docker容器总数 | ~19 | ~140 |
| 最低内存需求 | 8GB | 32GB（推荐62GB） |
| 最低CPU | 4核 | 16核（推荐24核） |
| 存储 | 20GB | 100GB+ |

### 8.2 网络接口名称差异（重要）

| 拓扑 | 接口名 | 原因 |
|------|--------|------|
| 2as_6nodes | `net0` | interface_setup 将 eth0 重命名为 net0 |
| 12as_100nodes | `inet0/inet1/inet2` | 多子网，按 inet+编号命名 |

**影响范围：**
- `CHAOS_INTERFACE` 环境变量
- Agent IP检测逻辑
- 混沌测试的 `ip link set <iface> down/up` 命令

### 8.3 链上活动规模

| 指标 | 2as_6nodes（~30分钟）| 12as_100nodes（~64分钟）|
|------|--------------------|-----------------------|
| 区块高度 | #88 | **#289** |
| 区块时间 | ~10秒 | ~2-3秒 |
| Geth P2P连接 | ~0（同子网ARP）| **50个/节点** |
| Lighthouse P2P连接 | 4个/节点 | **75-86个/节点** |
| 监控事件总数 | 135 | **50,313** |
| 执行层拓扑变化 | 35 | **790** |
| 共识层拓扑变化 | 0 | **3,073** |
| P2P连接（当前） | exec=1, cons=10 | exec=**1,778**, cons=**6,574** |

### 8.4 配置差异汇总

```yaml
# 2as_6nodes eth_simulation 关键配置
ETH_RPC_URL: http://10.151.0.73:8545   # POS-3 节点
CHAOS_INTERFACE: net0                    # 接口名
CHAOS_MAX_CONCURRENT: 1                  # 最多同时下线1个

# 12as_100nodes eth_simulation 关键配置
ETH_RPC_URL: http://10.101.0.73:8545   # AS101 POS-3 节点
CHAOS_INTERFACE: inet0                   # ← 不同!
CHAOS_MAX_CONCURRENT: 30                 # 107个验证者，最多30个下线
CONTRACT_DEPLOY_TIMEOUT: 180s           # ← 需要更长超时（107节点共识慢）
```

---

## 9. 部署指南

### 9.1 系统要求

```bash
# 软件依赖
- Docker Engine 24.0+
- Docker Compose v2.0+
- sshpass（用于远程部署脚本）

# 验证
docker --version           # Docker version 28.x+
docker compose version     # Docker Compose version v2.x+
```

### 9.2 一键启动（推荐）— 已在 161.97.133.14 实测验证

两个拓扑各提供一个 `start.sh` 脚本，自动完成所有步骤：

```bash
# ── 2as_6nodes（6节点，约5分钟启动）────────────────────────────────
cd 2as_6nodes/
./start.sh            # 一键启动：构建→数据库→网络→等待出块→部署Agent
./start.sh status     # 查看运行状态（区块高度、监控统计、Agent状态）
./start.sh logs       # 实时查看关键服务日志
./start.sh stop       # 停止所有服务
./start.sh restart    # 重启（stop + start）

# ── 12as_100nodes（108节点，约10分钟启动，需要 ≥32GB 内存）────────
cd 12as_100nodes/
./start.sh            # 一键启动（自动分批启动，避免内存峰值）
./start.sh status     # 查看状态（含监控事件统计）
./start.sh stop       # 停止所有容器
./start.sh build-only # 仅重建监控镜像（节点镜像已存在时使用）
```

`start.sh` 自动处理：
- 构建 Docker 镜像（基础镜像 + 监控镜像）
- 启动数据库并修复 PostgreSQL 认证兼容性
- 分批启动路由器、IXP 和以太坊节点
- 等待以太坊链初始化（区块高度 ≥ 5）
- 热部署节点内置监控 Agent

### 9.3 手动分步启动（高级用法）

若需要单独控制各阶段：

```bash
cd 2as_6nodes/   # 或 12as_100nodes/

# 1. 构建镜像
docker compose build eth_node_cleaner eth_node_monitoring eth_simulation

# 2. 启动数据库（并修复 PostgreSQL 认证）
docker compose up -d postgresql redis neo4j
docker exec eth_postgresql bash -c "
  sed -i 's/scram-sha-256/md5/' /var/lib/postgresql/data/pg_hba.conf
  psql -U postgres -c \"SELECT pg_reload_conf()\"
  psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'password'\"
" 2>/dev/null || true

# 3. 启动全部服务
docker compose up -d

# 4. 等待链初始化（约5分钟）并验证
curl -s -X POST http://localhost:8545 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# 5. 热部署监控 Agent
./deploy_monitoring.sh
./deploy_monitoring.sh --status   # 验证
```

### 9.4 关键环境变量说明

```yaml
# ── eth_simulation 关键配置 ─────────────────────────────────────
ETH_RPC_URL: http://10.151.0.73:8545
  # 必须指向持有解锁账户的验证者节点，不能用 BootNode
  # 2as_6nodes: 10.151.0.73 (POS-3)
  # 12as_100nodes: 10.101.0.73 (AS101 POS-3)

UNLOCKED_ACCOUNTS: 0x8c400205fDb103431F6aC7409655ad3cf8f6d007
  # 仅列出在 ETH_RPC_URL 指向节点上有效的账户
  # 多账户用逗号分隔

CONTRACT_DEPLOYER: 0x8c400205fDb103431F6aC7409655ad3cf8f6d007
  # 与 UNLOCKED_ACCOUNTS 中的主账户一致

CHAOS_INTERFACE: net0        # 2as_6nodes
CHAOS_INTERFACE: inet0       # 12as_100nodes（重要！）

CHAOS_DOWN_MIN: 60           # 节点最短下线时间（秒）
CHAOS_UP_MIN: 180            # 下次混沌事件最短等待时间（秒）

# ── eth_node_cleaner 关键配置 ────────────────────────────────────
NEO4J_URI: bolt://eth_neo4j:7687    # 2as_6nodes
NEO4J_URI: bolt://eth_neo4j:7688    # 12as_100nodes（端口不同！）
NEO4J_PASSWORD: 1qaz@WSX

REDIS_HOST: eth_redis
POSTGRES_DSN: postgresql://postgres:password@eth_postgresql:5432/ethereum_monitor

# ── deploy_monitoring.sh 关键配置 ────────────────────────────────
CENTRAL_COLLECTOR_URL: http://eth_node_cleaner:8888
NODE_COLLECT_INTERVAL: 30           # Agent 采集间隔（秒）
HEARTBEAT_INTERVAL: 30              # 心跳发送间隔（秒）
```

### 9.5 运维管理命令

```bash
# 查看所有服务状态
docker compose ps

# 热更新监控 Agent（无需重启节点）
./deploy_monitoring.sh              # 重新部署，自动热更新

# 查看 Agent 运行状态
./deploy_monitoring.sh --status

# 实时查看 Agent 日志
./deploy_monitoring.sh --logs       # 轮询所有节点

# 停止 Agent
./deploy_monitoring.sh --stop

# 查看某节点 Agent 日志
docker exec as151h-Ethereum-POS-3-10.151.0.73 tail -f /var/log/eth_monitoring_agent.log

# 查看拓扑监控实时数据
curl http://localhost:9999/api/v1/monitoring/statistics
curl http://localhost:9999/api/v1/monitoring/topology
curl "http://localhost:9999/api/v1/monitoring/events?limit=10"

# 查询 PostgreSQL 数据
psql postgresql://postgres:password@localhost:5433/ethereum_monitor -c \
  "SELECT COUNT(*) FROM transactions; SELECT COUNT(*) FROM eth_consensus_topology_changes;"

# 完全重置环境
docker compose down -v --remove-orphans  # 删除容器和数据卷
docker compose up -d                      # 重新启动
```

---

## 10. 真实环境测试结论

**测试服务器**：Contabo VPS，24核 Intel Xeon，62GB RAM，928GB NVMe SSD，Ubuntu 20.04，Docker 28.1.1

### 10.1 2as_6nodes 测试结论

**运行时长**：约45分钟

| 测试项目 | 结果 | 关键数据 |
|---------|------|---------|
| 区块链出块 | ✅ 正常 | 区块 #88，约10秒/块 |
| Geth P2P 连接 | ✅ 正常 | Docker 同网段直接通信 |
| Lighthouse 共识 | ✅ 正常 | slot 7+，4-5个节点参与共识 |
| 随机交易发送 | ✅ 通过 | 15笔确认，100%成功率 |
| 合约部署 | ✅ 通过 | SimpleCounter + SimpleToken 10秒内完成 |
| 合约自动调用 | ✅ 通过 | Counter=7，Token转账1次，Token burn 1次 |
| 节点混沌测试 | ✅ 通过 | ip link set net0 down/up，网关验证恢复 |
| Agent 热部署 | ✅ 通过 | 5/5节点，30秒内完成部署 |
| 拓扑监控事件 | ✅ 通过 | 135个事件（89 Pub/Sub + 46 Stream） |
| PostgreSQL数据 | ✅ 通过 | 15交易/4合约/12事件/35拓扑变化 |
| Neo4j图数据 | ✅ 通过 | 5 ExecNode + 5 ConsNode + 关系 |
| eth_node_monitoring API | ✅ 通过 | 9个端点全部正常响应 |

**发现并修复的关键Bug：**

1. **`PUSH0` 操作码不兼容**：Solidity 0.8.20 默认编译目标为 Shanghai EVM（含 `PUSH0` 操作码），但私链 genesis 为 Paris EVM 不支持。修复：添加 `evm_version="paris"` 编译参数。

2. **账户解锁范围问题**：eth_simulation 连接 BootNode RPC，但验证者账户仅在各自节点上解锁，导致 `eth_sendTransaction` 返回 "unknown account"。修复：ETH_RPC_URL 改为 POS-3 节点（10.151.0.73:8545）。

3. **PostgreSQL scram-sha-256 兼容性**：asyncpg 0.29.0 与 scram-sha-256 认证方式不兼容。修复：pg_hba.conf 改为 md5 认证，ALTER USER 重置密码。

4. **单账户 TxGenerator 初始化失败**：代码要求 `>=2` 个有余额账户，但 POS-3 RPC 只有1个解锁账户。修复：条件改为 `>=1`，to地址从已知地址列表选取。

### 10.2 12as_100nodes 测试结论

**运行时长**：约64分钟（测试结束时仍在运行）

| 测试项目 | 结果 | 关键数据 |
|---------|------|---------|
| 区块链出块 | ✅ 正常 | 区块 #289，约2-3秒/块 |
| Geth P2P 连接 | ✅ 正常 | **50个连接/节点** |
| Lighthouse 共识 | ✅ 正常 | slot 137+，epoch 34，finalized epoch 31，36+ peers |
| 验证者参与 | ✅ 正常 | **107/107个验证者全部注册和参与** |
| 随机交易发送 | ✅ 通过 | 17笔确认，77.8%成功率 |
| 合约部署 | ✅ 通过 | 180s超时内成功（107节点共识约40-60秒） |
| 合约自动调用 | ✅ 通过 | Counter=11，Token转账5次，mint 1次 |
| 节点混沌测试 | ✅ 通过 | ip link set inet0 down/up，路由恢复验证 |
| Agent 热部署 | ✅ 通过 | 抽样5/5节点运行正常，采集50-86 P2P连接 |
| 拓扑监控事件 | ✅ 通过 | **50,313个事件**（27,006 Pub/Sub + 23,307 Stream）|
| 节点覆盖 | ✅ 通过 | **107/107个共识节点，107/108个执行节点** |
| P2P连接监控 | ✅ 通过 | **1,778条执行层 + 6,574条共识层**实时追踪 |
| PostgreSQL数据 | ✅ 通过 | 17交易/6合约/3,073共识拓扑变化/790执行拓扑变化 |

**发现并修复的额外Bug（12as_100nodes特有）：**

1. **合约部署超时**：107个验证者共识耗时约40-60秒，默认60s超时不足。修复：超时改为180秒。

2. **网络接口名称不同**：12as_100nodes 使用 `inet0`（非 `net0`），导致混沌测试失败。修复：`CHAOS_INTERFACE=inet0`，Agent 自动检测接口名。

3. **Token转账接收方为空**：`self.accounts` 仅含1个账户，过滤后为空导致异常。修复：添加已知地址列表作为后备接收方。

### 10.3 宿主机网络注意事项

**Docker `--iptables=false` 环境**（嵌套虚拟化/某些云服务器）：
- 容器间可以通过**容器名（Docker DNS）**通信（如 `eth_postgresql`、`eth_redis`）
- 容器间**直接IP通信**（如 10.151.0.73）依赖 iptables，可能受限
- **解决方案**：使用容器名作为主机名，确保所有服务在同一 Docker 网络

**标准物理服务器**（如测试服务器 161.97.133.14）：
- 所有容器间通信正常（iptables 支持完整）
- 以太坊节点之间通过 BGP/OSPF 路由正常通信
- eth_simulation 可直接访问节点 IP（10.101.0.73:8545）

---

## 11. 已知问题与解决方案

### 11.1 以太坊链相关

| 问题 | 症状 | 根因 | 解决方案 |
|------|------|------|---------|
| 链启动后区块不增长 | eth_blockNumber 持续为 0x0 或 0x1 | 验证者未获取到 BootNode enode URL，孤岛挖矿 | 手动 admin_addPeer 连接节点，或重启容器 |
| Lighthouse 无 peers | "Low peer count: 0" | ENR 配置问题或网络不通 | 检查 Lighthouse 日志，确认 beacon_bootnode HTTP 在 8090 端口服务 |
| 合约部署超时 | "Transaction not in chain after Xs" | 链上共识慢（特别是 12as_100nodes） | 增加 wait_for_transaction_receipt timeout 到 180s |
| PUSH0 操作码错误 | 合约部署报 `invalid opcode` | Solidity 0.8.20 编译为 Shanghai EVM | compile_source 添加 `evm_version="paris"` |

### 11.2 监控服务相关

| 问题 | 症状 | 根因 | 解决方案 |
|------|------|------|---------|
| PostgreSQL 认证失败 | `password authentication failed` | 旧卷中密码与新配置不一致，或 start.sh 时序竞争 | pg_hba.conf 改为 md5，`ALTER USER postgres WITH PASSWORD 'password'` |
| validator_index=0 未检测 | 第一个验证者变化不触发事件 | `if v.get('validator_index')` 0是假值 | 改为 `if v.get('validator_index') is not None` |
| validators 表为空/写入失败 | `Integer 18446744073709551615 out of range` | Ethereum FAR_FUTURE_EPOCH (uint64 max) 超出 PostgreSQL int64 | 代码层将 `>= 18446744073709551615` 的 epoch 转为 None，SQL 列改为 BIGINT |
| Neo4j 拓扑为空 | eth_node_monitoring /topology 返回空 | 无 Agent 推送数据 | 执行 `./deploy_monitoring.sh` 部署 Agent |
| Agent 找不到接口 | Agent 日志报 "Device not found" | 接口名差异（net0 vs inet0） | Agent 自动尝试 inet0/net0/eth0 |
| 交易报 `replacement transaction underpriced` | 发送频率高时 nonce 冲突 | 使用已确认 nonce，pending 交易导致重用 | 改为 `get_transaction_count(addr, 'pending')` + gas_price * 1.1 |

### 11.3 混沌测试相关

| 问题 | 症状 | 根因 | 解决方案 |
|------|------|------|---------|
| 节点下线后无法恢复 | ping 网关失败，BIRD 未重建路由 | 默认路由未恢复 | `ip route add default via <gateway> dev <iface>` |
| 链停止出块 | Lighthouse finalized_epoch 不增长 | 同时下线节点过多（<2/3在线）| 降低 CHAOS_MAX_CONCURRENT，确保 >2/3 在线 |
| ping-based 删除未触发 | Neo4j 节点未被删除 | Docker 桥接网络绕过了接口DOWN的影响 | 心跳超时（60s）作为备份机制，或使用 `docker stop` |

---

## 12. 扩展与二次开发

### 12.1 添加新的监控数据类型

在 `eth_node_cleaner/central_collector/data_processor.py` 中添加：

```python
# 1. 在 data_type_handlers 字典中注册
data_type_handlers = {
    ...
    "my_new_type": self._process_my_new_type,
}

# 2. 实现处理函数
async def _process_my_new_type(self, data: CollectedData):
    payload = data.data
    # 处理逻辑：写 Neo4j / Redis / PostgreSQL
    async with self.neo4j_driver.session() as session:
        await session.run("MERGE (:MyNode {id: $id})", id=payload.get("id"))
```

### 12.2 添加新的混沌场景

在 `chaos_agent.py` 中扩展：

```python
# 延迟注入
async def inject_latency(self, container, iface, delay_ms=200):
    container.exec_run(f"tc qdisc change dev {iface} parent 1:0 handle 10: netem delay {delay_ms}ms")

# 丢包模拟
async def inject_packet_loss(self, container, iface, loss_pct=20):
    container.exec_run(f"tc qdisc change dev {iface} parent 1:0 handle 10: netem loss {loss_pct}%")

# 带宽限速
async def throttle_bandwidth(self, container, iface, rate_kbps=100):
    container.exec_run(f"tc qdisc change dev {iface} root handle 1:0 tbf rate {rate_kbps}kbit buffer 1000000 limit 1000")
```

### 12.3 为 12as_100nodes 添加更多验证者账户

```bash
# 1. 从各节点提取账户信息
for as in $(seq 101 112); do
  for host in $(seq 2 8); do
    docker exec as${as}h-Ethereum-... geth attach /root/.ethereum/geth.ipc \
      --exec "eth.accounts[0]"
  done
done

# 2. 更新 docker-compose.yml
UNLOCKED_ACCOUNTS: 0xacc1,0xacc2,...

# 3. 为 eth_simulation 配置多个 ETH_RPC_URL（轮询或随机选择）
```

### 12.4 数据分析查询示例

```sql
-- 按小时统计共识层拓扑变化趋势
SELECT DATE_TRUNC('hour', timestamp) as hour,
       change_type, COUNT(*) as changes
FROM eth_consensus_topology_changes
GROUP BY 1, 2 ORDER BY 1 DESC LIMIT 20;

-- 节点连接稳定性分析（连接断开次数）
SELECT source_node_id, COUNT(*) as disconnections
FROM eth_consensus_link_changes
WHERE change_type = 'link_removed'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- 验证者活动分析
SELECT status, COUNT(*) FROM validators GROUP BY 1;

-- 交易活动时序
SELECT DATE_TRUNC('minute', timestamp) as ts, COUNT(*), SUM(value)/1e18 as eth_moved
FROM transactions GROUP BY 1 ORDER BY 1;
```

```cypher
// Neo4j: 查询连接最多的节点（网络中心节点）
MATCH (n:ConsNode)-[r:CONS_PEERS_WITH]->(m:ConsNode)
RETURN n.ip, COUNT(r) as degree ORDER BY degree DESC LIMIT 10;

// 查询验证者分布
MATCH (c:ConsNode)-[:MANAGES_VALIDATOR]->(v:Validator)
RETURN c.ip, COUNT(v) as validators ORDER BY validators DESC;

// 发现交易网络中的活跃账户
MATCH (a:Address)-[r:TRANSACTED_WITH]->(b:Address)
RETURN a.address, SUM(r.count) as tx_count ORDER BY tx_count DESC LIMIT 10;
```

---

*本文档版本：v3.0 | 基于远程服务器（161.97.133.14）真实测试结论*  
*最后更新：2026-03-17*
