# 仿真系统测试报告

**测试日期**: 2026-03-19  
**测试拓扑**: 2as_6nodes  
**测试服务器**: 111.230.44.107（腾讯云 32核 61GB 内存）  
**代码分支**: `cursor/-bc-68fb2362-250f-44c0-bcdc-731f6e0ab922-0076`

---

## 1. 测试环境

### 1.1 基础设施

| 组件 | 版本 | 状态 |
|------|------|------|
| Docker Engine | 29.3.0 | ✅ |
| Docker Compose | v5.1.0 | ✅ |
| PostgreSQL | 15-alpine | ✅ healthy |
| Redis | 7-alpine | ✅ healthy |
| Neo4j | latest | ✅ |

### 1.2 网络拓扑

| 组件 | 数量 | 说明 |
|------|------|------|
| AS | 2 | AS151, AS152 |
| IXP | 1 | IX100 |
| BIRD 路由器 | 3 | 2 边界路由 + 1 IXP 路由服务器 |
| Transit 路由器 | 2 | AS2/AS21 |
| 以太坊 BootNode | 1 | AS151 |
| 以太坊 POS 验证者 | 4 | POS-3~POS-6 |
| 容器总数 | 19 | 全部正常运行 |

---

## 2. 功能测试结果

### 2.1 功能1：随机交易发送

| 指标 | 结果 |
|------|------|
| 状态 | ✅ **通过** |
| 发送交易数 | 15 笔 |
| 确认交易数 | 15 笔 |
| 成功率 | **100%** |
| 发送间隔 | 15~45 秒（随机） |
| 交易金额 | 0.001~0.01 ETH |
| 区块确认范围 | block #6 ~ #38 |

**数据库验证**:
```
 tx_count 
----------
       15
```

**交易网络拓扑视图**:
```
              from_address              |               to_address               | tx_count | success_count
----------------------------------------+----------------------------------------+----------+---------------
 0x8c400205fDb...                       | 0x72943017A1fa...                      |        4 |             4
 0x8c400205fDb...                       | 0x1081c645CC8c...                      |        4 |             4
 0x8c400205fDb...                       | 0xC5247277519c...                      |        1 |             1
 0x8c400205fDb...                       | 0xD4CC43e3f283...                      |        1 |             1
```

### 2.2 功能2：节点随机上下线

| 指标 | 结果 |
|------|------|
| 状态 | ✅ **通过** |
| 总下线次数 | 1 |
| 总上线次数 | 1 |
| 恢复失败 | 0 |
| 使用接口 | `net0`（自动发现） |
| 操作方式 | `ip link set net0 down/up` |
| 网关 ping 恢复 | ✅ 成功 |
| Geth RPC 恢复 | ✅ 成功 |
| Peer 重连 | ✅ 通过 admin_addPeer |

**混沌事件详细日志**:
```
01:34:47 ⬇️  下线节点 as152h-Ethereum-POS-6-10.152.0.73，接口 net0
01:34:48    ✅ 已下线，将在 78s 后自动尝试恢复
01:36:06 ⬆️  恢复节点 as152h-Ethereum-POS-6-10.152.0.73，接口 net0
01:36:08    ✅ Geth RPC 可达，当前 peer 数: 0
01:36:08    ➕ 已添加 peer 10.152.0.71 的 enode
01:36:08 ⬆️  已恢复上线
```

**数据库验证 (node_chaos_events)**:
```
   event_type   |          container_name           | interface |    trigger    | gateway_ping_ok
----------------+-----------------------------------+-----------+---------------+-----------------
 node_link_down | as152h-Ethereum-POS-6-10.152.0.73 | net0      | random        |                
 node_link_up   | as152h-Ethereum-POS-6-10.152.0.73 | net0      | auto_recovery | t              
```

**时间线视图 (node_updown_timeline)**:
```
 container_name | event_type | trigger | seconds_since_prev_event | event_time
 POS-6          | link_down  | random  |                          | 01:34:48
 POS-6          | link_up    | auto_recovery | 80.17                | 01:36:08
```

### 2.3 功能3：合约部署与自动调用

| 指标 | 结果 |
|------|------|
| 状态 | ✅ **通过** |
| 合约部署成功数 | 4（2 × SimpleCounter + 2 × SimpleToken） |
| 合约调用事件数 | 13 |
| 调用方法覆盖 | increment, incrementBy, decrement, transfer, mint, burn |
| Counter 当前值 | 6 |

**数据库验证 (contracts)**:
```
 contract_name |              contract_address              | block_number
---------------+--------------------------------------------+--------------
 SimpleCounter | 0x26e87D2c873b...                          |            2
 SimpleToken   | 0xDe4cd5d4bd26...                          |            4
 SimpleCounter | 0xA9784D3B2c35...                          |           14
 SimpleToken   | 0xceBa56a26dF4...                          |           16
```

**合约交互拓扑视图 (contract_interaction_topology)**:
```
 contract_address | contract_name | method_name | call_count
------------------+---------------+-------------+------------
 0xDe4c...        | SimpleToken   | transfer    |          2
 0xA978...        | SimpleCounter | increment   |          2
 0xA978...        | SimpleCounter | incrementBy |          2
 0xceBa...        | SimpleToken   | mint        |          2
 0xA978...        | SimpleCounter | decrement   |          1
 0xDe4c...        | SimpleToken   | burn        |          1
```

### 2.4 功能4：WAN 链路随机整形

| 指标 | 结果 |
|------|------|
| 状态 | ✅ **通过** |
| 生效次数 | 3 |
| 恢复次数 | 0（测试窗口内未到恢复时间） |
| 失败次数 | 1（容器当时不可用） |
| 可用链路数 | 5 |

**WAN 事件详情 (wan_chaos_events)**:
```
     event_type      |        container_name         | interface | bandwidth_mbit | delay_ms | loss_pct
---------------------+-------------------------------+-----------+----------------+----------+----------
 wan_profile_changed | as100brd-ix100-10.100.0.100   | ix100     |            235 |       41 |    0.586
 wan_profile_changed | as152brd-router0-10.152.0.254 | ix100     |            124 |      106 |    2.136
 wan_profile_changed | as21brd-r100-10.100.0.21      | ix100     |             85 |      117 |        
```

### 2.5 以太坊共识验证

| 指标 | 结果 |
|------|------|
| 状态 | ✅ **共识未被破坏** |
| 当前区块 | 38 |
| POS-3 peer 数 | 3 |
| POS-3 区块 | 38 |
| POS-4 区块 | 38 |
| POS-5 区块 | 38 |
| 区块同步 | **3 个节点完全同步** |

### 2.6 控制 API 验证

| 端点 | 结果 |
|------|------|
| `GET /healthz` | ✅ `{"status": "ok"}` |
| `GET /api/v1/status` | ✅ 返回所有模块统计 |
| `GET /api/v1/chaos/nodes` | ✅ 返回 4 个节点状态 |
| `GET /api/v1/wan/targets` | ✅ 返回 5 条 WAN 链路 |
| `GET /api/v1/wan/active` | ✅ 返回 2 条活跃配置 |

---

## 3. 数据库完整性验证

| 表/视图 | 记录数 | 状态 |
|---------|--------|------|
| `transactions` | 15 | ✅ |
| `contracts` | 4 | ✅ |
| `contract_events` | 13 | ✅ |
| `node_chaos_events` | 2 | ✅ |
| `wan_chaos_events` | 3 | ✅ |
| `topology_changes` | 5 | ✅ |
| `transaction_network_topology` (视图) | 4 | ✅ |
| `contract_interaction_topology` (视图) | 9 | ✅ |
| `node_updown_timeline` (视图) | 2 | ✅ |
| `wan_bandwidth_timeline` (视图) | 3 | ✅ |

---

## 4. 代码一致性验证

两种拓扑的核心代码模块逐文件比对结果：

| 文件 | 结果 |
|------|------|
| `chaos_agent.py` | ✅ 完全一致 |
| `reporter.py` | ✅ 完全一致 |
| `tx_generator.py` | ✅ 完全一致 |
| `contract_agent.py` | ✅ 完全一致 |
| `wan_chaos_agent.py` | ✅ 完全一致 |
| `control_api.py` | ✅ 完全一致 |
| `main.py` | ✅ 完全一致 |
| `node_data_collector.py` | ✅ 完全一致 |
| `requirements.txt` | ✅ 完全一致 |
| `Dockerfile` | ✅ 完全一致 |
| `config.py` | ⚠️ 预期不同（不同拓扑参数） |
| `07-create-simulation-history-tables.sql` | ✅ 完全一致 |

**结论**: 两种拓扑共享完全相同的功能代码，仅 `config.py` 中的默认参数因拓扑规模不同而有差异（均可通过环境变量覆盖）。2as_6nodes 的完整测试覆盖了所有核心逻辑。

---

## 5. 拓扑可见性验证

验证仿真事件的间隔是否确保拓扑数据库能捕获变化：

| 功能 | 事件间隔 | 持续时间 | 监控采集(30s) | 数据库中可见变化 |
|------|----------|----------|---------------|-----------------|
| 交易 | 15~45s | 持续 | 每周期1-2笔 | ✅ `transactions` 持续增长 |
| 节点下线 | 180~480s | 60~120s | 下线期间2-4次采集 | ✅ `node_chaos_events` 记录间隔80s |
| 合约调用 | 30~60s | 持续 | 每周期1次 | ✅ `contract_events` 持续增长 |
| WAN 扰动 | 90~240s | 120~300s | 扰动期间4-10次采集 | ✅ `wan_chaos_events` 记录3条变化 |

**结论**: 所有仿真事件的间隔设计确保拓扑数据库中的时序数据能**持续产生变化**，不会出现长时间稳定的情况，适合作为科研使用的时序拓扑数据。

---

## 6. 发现并修复的问题

| 问题 | 严重程度 | 修复 |
|------|----------|------|
| `_save_network_config` 路由正则不匹配 `ip route show default dev X` 输出 | 严重 | 将 `dev` 匹配改为可选 |
| `node_failures` 表使用 UPSERT 覆盖历史 | 中等 | 新增 `node_chaos_events` 独立历史表 |
| 恢复后 Geth 无 peer 导致区块链孤立 | 中等 | 新增 `_verify_geth_recovery` + `admin_addPeer` |
| Dockerfile 缺少 `node_data_collector.py` COPY | 轻微 | 添加到 COPY 列表 |
| 12as_100nodes `agent_heartbeats` 表类型不一致 | 轻微 | 移除重复定义 |
| 12as_100nodes WAN 目标模式不匹配容器名 | 轻微 | `brd-` → `brd-router` |
