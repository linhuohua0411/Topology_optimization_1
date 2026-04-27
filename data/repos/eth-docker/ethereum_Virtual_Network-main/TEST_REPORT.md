# 以太坊虚拟网络仿真平台 — Bug 修复与测试报告

> 本文档聚焦于两部分独有内容：**代码审查 Bug 修复明细**（含修复前后代码对比）和 **60 个单元/集成测试用例**的详细结果。  
> 架构说明、部署指南、测试结论等内容请查阅 → **[MASTER_REFERENCE.md](MASTER_REFERENCE.md)**

---

## 目录

1. [代码审查发现的 Bug 列表](#1-代码审查发现的-bug-列表)
2. [Bug 修复代码对比](#2-bug-修复代码对比)
3. [单元与集成测试结果（60项）](#3-单元与集成测试结果)
4. [远程服务器实测数据（161.97.133.14）](#4-远程服务器实测数据)

---

## 1. 代码审查发现的 Bug 列表

审查范围：两个拓扑目录下的全部 Python 文件（共约 3,000 行代码）

| ID | 严重级别 | 文件 | Bug 描述 | 影响范围 |
|----|----------|------|---------|---------|
| B-01 | 🔴 严重 | `http_server.py` | `node_id` 被列为必填字段，而 `eth_node_cleaner.py` 发送拓扑清理事件时不携带此字段 | 所有网络不可达节点的清理事件被 HTTP 400 拒绝，节点下线通知完全失效 |
| B-02 | 🔴 严重 | `data_processor.py` | `_process_p2p_topology()` 未检查 `neo4j_driver` 是否为 None | Neo4j 未连接时收到 p2p 数据 → AttributeError → 收集器进程崩溃 |
| B-03 | 🔴 严重 | `topology_change_detector.py` | `if v.get('validator_index')` 布尔过滤，`validator_index=0` 为假值被过滤 | 第一个验证者（索引0）的所有变化永远无法被检测到 |
| B-04 | 🟠 中等 | `models.py` | `DataCache` 未定义 `total_collected_data` 属性 | `get_cache_info()` 调用时 AttributeError |
| B-05 | 🟠 中等 | `change_event_sender.py` | `change_event.get('change_type').startswith()` 在 `change_type=None` 时崩溃 | 特定共识层事件处理时 AttributeError |
| B-06 | 🟡 低 | `data_utils.py` | `validate_node_id('')` 返回 `''` 而非 `False` | 节点 ID 验证逻辑不准确 |
| B-07 | 🔴 严重 | `12as_100nodes/data_processor.py` | `close()` 方法缩进错误，定义在类外部 | 关闭连接时 TypeError，资源泄漏 |
| B-08 | 🔴 严重 | `12as_100nodes/central_collector/` | 缺少 `node_manager.py` 和 `data_utils.py` | `data_processor.py` 导入失败，服务无法启动 |
| B-09 | 🟠 中等 | `12as_100nodes/collector.py` | 缺少 `_handle_inactive_containers()` 方法 | 心跳超时的节点不会触发 Neo4j / Redis 清理 |
| B-10 | 🔴 严重 | `contract_agent.py` | Solidity 0.8.20 默认 Shanghai EVM，私链为 Paris EVM（不含 PUSH0） | 合约部署报 `invalid opcode: PUSH0`，完全无法部署合约 |
| B-11 | 🔴 严重 | `docker-compose.yml` | ETH_RPC_URL 指向 BootNode，但验证者账户仅在各自节点解锁 | 所有交易发送报 `unknown account`，仿真功能失效 |
| B-12 | 🟠 中等 | `contract_agent.py`（12as_100nodes） | `wait_for_transaction_receipt` 超时 60s，107个验证者共识需40-60s | 合约部署超时失败 |
| B-13 | 🟡 低 | `chaos_agent.py`（12as_100nodes） | CHAOS_INTERFACE 默认 `net0`，12as_100nodes 接口名为 `inet0` | 混沌测试操作错误接口，down/up 命令失败 |

---

## 2. Bug 修复代码对比

### B-01：http_server.py — node_id 必填改为可选

```python
# 修复前：
required_fields = ['container_id', 'node_id', 'timestamp', 'data_type', 'data']
node_id = data['node_id']   # KeyError!

# 修复后：
required_fields = ['container_id', 'timestamp', 'data_type', 'data']
node_id = data.get('node_id', '')   # 可选，默认空字符串
```

**根因**：`eth_node_cleaner.py` 发送 `network_topology_change` 事件时不含 `node_id`（节点 ID 在 `data.node_id` 内），HTTP 层严格校验导致所有清理事件被 400 拒绝。

---

### B-02：data_processor.py — Neo4j 空值检查

```python
# 修复前：（Neo4j 未连接时直接崩溃）
async def _process_p2p_topology(self, data: CollectedData):
    topology = data.data
    async with self.neo4j_driver.session() as session:   # AttributeError: NoneType

# 修复后：
async def _process_p2p_topology(self, data: CollectedData):
    if not self.neo4j_driver:
        self.logger.error("Neo4j驱动未初始化，无法处理P2P拓扑数据")
        return
    topology = data.data
    async with self.neo4j_driver.session() as session:
```

---

### B-03：topology_change_detector.py — validator_index=0 过滤 Bug（最隐蔽）

```python
# 修复前：（0 在 Python 中是假值，validator_index=0 被过滤！）
previous_vals = {v.get('validator_index'): v for v in previous_validators
                 if v.get('validator_index')}          # ← 0 被排除

# 修复后：
previous_vals = {v.get('validator_index'): v for v in previous_validators
                 if v.get('validator_index') is not None}   # ← 0 被正确保留
```

**影响**：以太坊 PoS 验证者索引从 0 开始。第一个验证者（`validator_index=0`）的所有状态变化（`active_ongoing` → `active_slashed` 等）永远不会触发 `validator_status_changed` 事件。

---

### B-04：models.py — DataCache 补充属性

```python
# 修复前：属性不存在，调用时 AttributeError
@dataclass
class DataCache:
    beacon_blocks: List[Dict[str, Any]] = field(default_factory=list)
    # ... total_collected_data 未定义

# 修复后：
@dataclass
class DataCache:
    beacon_blocks: List[Dict[str, Any]] = field(default_factory=list)
    # ...
    total_collected_data: int = 0   # ← 新增
```

---

### B-05：change_event_sender.py — change_type 空值安全

```python
# 修复前：（change_type=None 时 AttributeError: NoneType.startswith）
if change_event.get('change_type').startswith('validator_'):

# 修复后：
change_type = change_event.get('change_type') or ''
if change_type.startswith('validator_'):
```

---

### B-06：data_utils.py — 明确返回 bool

```python
# 修复前：
def validate_node_id(node_id: Any) -> bool:
    return node_id and isinstance(node_id, str) and node_id.strip() != ""
    # validate_node_id('') 返回 '' 而非 False，'' == False 为 False

# 修复后：
def validate_node_id(node_id: Any) -> bool:
    return bool(node_id and isinstance(node_id, str) and node_id.strip() != "")
    # 明确返回 bool 类型
```

---

### B-07/B-08/B-09：12as_100nodes 同步修复

```bash
# B-08: 补充缺失文件
cp 2as_6nodes/eth_node_cleaner/central_collector/node_manager.py  \
   12as_100nodes/eth_node_cleaner/central_collector/
cp 2as_6nodes/eth_node_cleaner/central_collector/data_utils.py    \
   12as_100nodes/eth_node_cleaner/central_collector/
```

```python
# B-07: close() 方法缩进修复（从模块级移入类内）
class DataProcessor:
    # ... 所有方法
    async def close(self):    # ← 正确缩进，是类方法
        if self.neo4j_driver: await self.neo4j_driver.close()
        if self.pg_pool: await self.pg_pool.close()
        if self.redis_client: await self.redis_client.close()
```

B-09：`collector.py` 补充 `_handle_inactive_containers()` 方法，完成心跳超时节点的完整清理链：delete_nodes_by_container → mark_node_inactive_in_neo4j → delete_nodes_by_ip → record_node_failure_in_postgres → cleanup_node_state_in_redis → send_node_removed_event

---

### B-10：contract_agent.py — EVM 版本修复

```python
# 修复前：（Solidity 0.8.20 默认 Shanghai EVM，私链使用 Paris EVM）
compiled = compile_source(source, solc_version=version, optimize=True)
# 部署报错: invalid opcode: PUSH0

# 修复后：
compiled = compile_source(
    source,
    solc_version=version,
    optimize=True,
    evm_version="paris",    # ← 明确指定 Paris EVM（不含 PUSH0 操作码）
)
```

---

### B-11：docker-compose.yml — ETH_RPC_URL 指向正确节点

```yaml
# 修复前：（BootNode 只有自己的账户，无法用验证者账户发交易）
ETH_RPC_URL: http://10.151.0.72:8545   # BootNode

# 修复后：（POS-3 节点的账户已通过 --unlock 解锁，可直接 eth_sendTransaction）
ETH_RPC_URL: http://10.151.0.73:8545   # POS-3
UNLOCKED_ACCOUNTS: 0x8c400205fDb103431F6aC7409655ad3cf8f6d007
CONTRACT_DEPLOYER: 0x8c400205fDb103431F6aC7409655ad3cf8f6d007
```

---

### B-12：12as_100nodes — 合约超时修复

```python
# 修复前：（60秒对于107节点网络的共识不够）
receipt = self.w3.eth.wait_for_transaction_receipt(tx, timeout=60)

# 修复后：
receipt = self.w3.eth.wait_for_transaction_receipt(tx, timeout=180)
```

---

### B-13：12as_100nodes — 网络接口名修复

```yaml
# 修复前：（12as_100nodes 接口名为 inet0，非 net0）
CHAOS_INTERFACE: net0

# 修复后：
CHAOS_INTERFACE: inet0
```

Agent 的接口自动检测也同步更新（支持 `inet0/net0/eth0` 自动探测）。

---

## 3. 单元与集成测试结果

**执行时间**：2026-03-16（开发环境，Ubuntu 22.04，Python 3.12）

| 测试套件 | 测试项 | 结果 |
|---------|--------|------|
| T-01 模块导入（两拓扑） | 2 | ✅ |
| T-02 data_utils 工具函数（13项边界值） | 13 | ✅ |
| T-03 DataCache 属性 | 4 | ✅ |
| T-04 拓扑变化检测（4场景含 validator_index=0 修复验证） | 4 | ✅ |
| T-05 HTTP 请求验证（含无 node_id 请求） | 4 | ✅ |
| T-06 ChangeEventSender 空值安全 | 4 | ✅ |
| T-07 ping 网络检测逻辑 | 2 | ✅ |
| T-08 PostgreSQL 数据库结构（32张表） | 5 | ✅ |
| T-09 Redis 数据流（Stream/KV/TTL） | 3 | ✅ |
| T-10 端到端集成（9场景） | 9 | ✅ |
| T-11 eth_node_monitoring API（9端点） | 9 | ✅ |

**总计：60 项测试，60 项通过，通过率 100%**

### T-02 详细结果（data_utils 13项）

```
✅ hex_to_int("0x1a")      → 26
✅ hex_to_int("0x0")       → 0
✅ hex_to_int("invalid")   → 0
✅ hex_to_int(0)           → 0
✅ status_to_int("success")→ 1
✅ status_to_int("failure") → 0
✅ status_to_int(1)        → 1
✅ validate_node_id("abc") → True
✅ validate_node_id("")    → False
✅ validate_node_id(None)  → False
✅ validate_node_id("  ")  → False
✅ extract_ip(["/ip4/10.1.1.1/tcp/..."]) → "10.1.1.1"
✅ extract_ip([])          → ""
```

### T-04 关键场景（validator_index=0 修复验证）

```
场景A 执行层新节点:    ✅ 检测到 node_added
场景B 连接新增:        ✅ 检测到 link_added
场景C 连接断开:        ✅ 检测到 link_removed
场景D validator_index=0 状态变化:
  第1次: validator_index=0, status=active_ongoing → 建立基线
  第2次: validator_index=0, status=active_slashed → ✅ 检测到 validator_status_changed
  （修复前: 0被布尔过滤，此场景永远检测不到）
```

### T-05 HTTP 验证逻辑

```
✅ 含 node_id 完整请求  → HTTP 200（正常数据）
✅ 无 node_id 拓扑事件  → HTTP 200（修复 B-01：拓扑清理事件不需要 node_id）
✅ 缺 data 字段         → HTTP 400（必填字段缺失）
✅ 缺 container_id      → HTTP 400（必填字段缺失）
```

### T-10 端到端集成（9场景）

```
✅ GET  /health                       → 200
✅ GET  /api/v1/monitoring/status     → 200（queue_size=0）
✅ POST 拓扑清理事件（无 node_id）    → 200（修复 B-01 验证）
✅ POST p2p 拓扑数据（含 node_id）   → 200
✅ POST 缺少必填字段                  → 400（正确拒绝）
✅ POST 心跳数据                      → 200（PostgreSQL 写入）
✅ GET  /beacon/network_health        → 200
✅ GET  /beacon/blocks                → 200
✅ GET  /beacon/fork_events           → 200
```

---

## 4. 远程服务器实测数据

**测试服务器**：161.97.133.14（Contabo VPS，24核 Intel Xeon，62GB RAM，Ubuntu 20.04，Docker 28.1.1）

### 4.1 2as_6nodes（运行约45分钟）

| 测试项 | 数据 |
|--------|------|
| 最终区块高度 | **#88** |
| 交易确认数 | **15笔**，成功率 100% |
| 合约部署 | SimpleCounter + SimpleToken，均成功（<30s） |
| 合约调用 | Counter=7，Token转账1次，Token burn 1次 |
| 混沌事件 | 1次 ip link set net0 down/up，网关恢复验证通过 |
| Agent 部署 | 5/5 节点，30秒内完成 |
| 监控事件 | 135个（Pub/Sub=89，Stream=46） |
| PostgreSQL | tx=15，contracts=4，contract_events=12，node_failures=4，exec_topo_changes=35 |
| Neo4j | ExecNode=5，ConsNode=5，Address=5，Contract=2 |

### 4.2 12as_100nodes（运行约64分钟）

| 测试项 | 数据 |
|--------|------|
| 最终区块高度 | **#289** |
| 区块时间 | 约 2-3 秒/块 |
| Geth P2P 连接 | **50个/节点** |
| Lighthouse P2P 连接 | **75-86个/节点** |
| Lighthouse slot | 137+，epoch 34，finalized epoch 31 |
| 验证者全部注册 | **107/107个** |
| 交易确认数 | **17笔**，成功率 77.8% |
| 合约部署 | SimpleCounter + SimpleToken，均成功（<180s） |
| 合约调用 | Counter=11，Token转账5次，mint 1次 |
| 混沌事件 | ip link set inet0 down/up 执行成功，路由恢复验证通过 |
| Agent 抽样 | 5/5 节点正常运行，各采集 50-86 P2P 连接 |
| **监控事件** | **50,313个**（Pub/Sub=27,006，Stream=23,307） |
| 节点覆盖 | exec=107/108，cons=**107/107（全覆盖）** |
| 实时 P2P 连接 | exec_links=**1,778**，cons_links=**6,574** |
| PostgreSQL | tx=17，contracts=6，exec_topo_changes=790，**cons_topo_changes=3,073** |

### 4.3 远程实测新增修复（B-10~B-13）

| Bug | 症状 | 修复 |
|-----|------|------|
| B-10 PUSH0 操作码 | 合约部署报 `invalid opcode` | `evm_version="paris"` |
| B-11 账户未解锁 | 所有交易报 `unknown account` | ETH_RPC_URL → POS-3 节点 |
| B-12 合约超时 | 107节点共识需40-60s，60s不够 | timeout → 180s |
| B-13 接口名差异 | 12as_100nodes 用 `inet0` 而非 `net0` | CHAOS_INTERFACE=inet0 |

---

*测试报告版本：v2.0 | 详细架构与部署文档请查阅 [MASTER_REFERENCE.md](MASTER_REFERENCE.md)*

---

## 5. 云服务器 start.sh 一键启动验证（2026-03-17）

**服务器**：161.97.133.14（24核/62GB，Docker 28.1.1）

### 5.1 2as_6nodes 一键启动

```bash
cd 2as_6nodes/
./start.sh
```

**结果：**
- 启动耗时：约70秒（含数据库初始化 + 以太坊链出块 + Agent热部署）
- 19个容器全部正常运行
- 5/5节点 Agent 启动成功
- 区块高度达到 #5 后自动显示完成信息

**5分钟后验证数据：**

| 指标 | 数值 |
|------|------|
| 区块高度 | #25 |
| 交易数 | 37笔（100%成功率）|
| 合约调用 | Counter=14，Token转账=2 |
| 混沌事件 | 2次下线+1次恢复（1个正在down）|
| 监控事件 | 248个 |
| PostgreSQL | tx=37, contracts=6, events=36, failures=5, exec_topo=80 |
| Neo4j | Transaction=12, ConsNode=5, ExecNode=4, Contract=2 |
| Agent | exec_peers=3, cons_peers=4, validators=4 |
| 错误 | **0个** |

### 5.2 12as_100nodes 一键启动

```bash
cd 12as_100nodes/
./start.sh
```

**结果：**
- 启动耗时：约7分钟（含108个节点分批启动 + 以太坊链初始化）
- 138个容器全部正常运行
- 100/107节点 Agent 启动成功（7个跳过，已运行Agent）
- Lighthouse slot 115+，epoch 28，finalized_epoch 25

**验证数据：**

| 指标 | 数值 |
|------|------|
| 区块高度 | #42+ |
| 监控事件 | **151,852个** |
| exec节点 | 106/108 |
| cons节点 | 107/108 |
| cons_links | 6,448条 |
| PostgreSQL | tx=27, validators=**106个**, exec_topo=4,251, **cons_topo=54,093** |
| 错误 | **0个**（修复后） |

### 5.3 实测新增修复（B-14~B-16）

| Bug | 症状 | 根因 | 修复 |
|-----|------|------|------|
| B-14 | 验证者写入失败 | `exit_epoch=18446744073709551615`（FAR_FUTURE）超出 PostgreSQL/Neo4j 有符号 int64 范围 | 代码层转为 None，SQL 表改为 BIGINT |
| B-15 | `replacement transaction underpriced` | nonce 使用已确认状态，不包含 pending 交易 | 改为 `get_transaction_count(addr, 'pending')` + gas_price * 1.1 |
| B-16 | PostgreSQL 认证失败（时序问题）| start.sh 中 md5 修复与服务启动存在竞争条件 | 显式重启后重置密码 |
