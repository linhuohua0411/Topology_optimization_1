# 以太坊虚拟网络仿真平台

基于 BIRD BGP/OSPF 广域网 + Geth + Lighthouse PoS 的多 AS 以太坊公有链测试网仿真平台，  
支持实时 P2P 拓扑监控、链上活动仿真（随机交易/智能合约/节点混沌）。

## 两个拓扑规模

| 拓扑 | AS数 | 节点数 | IXP | 验证者 | 适用场景 |
|------|------|--------|-----|--------|---------|
| [`2as_6nodes/`](2as_6nodes/) | 2 | 6 | 1 | 4 | 开发调试、快速验证 |
| [`12as_100nodes/`](12as_100nodes/) | 12 | 108 | 4 | 107 | 规模测试、鲁棒性研究 |

## 核心功能

| 服务 | 端口 | 功能 |
|------|------|------|
| `eth_node_cleaner` | **8888** | 中央数据收集器 + 节点下线检测（ping 12s / 心跳 60s 双重机制） |
| `eth_node_monitoring` | **9999** | 实时拓扑仪表盘（9个 API 端点，Redis Pub/Sub + Neo4j 轮询） |
| `eth_simulation` | **8890** | 随机交易发送 + 节点混沌（ip link down/up）+ 持续随机部署/触发合约 + BIRD WAN 随机整形 + 手工控制 API |
| `eth_node_monitoring_agent` | 内置 | 每30秒采集 Geth/Lighthouse P2P 数据，**热部署**到节点容器 |

## 快速启动（一键）

```bash
# 2as_6nodes（小规模，推荐先用）
cd 2as_6nodes/
./start.sh           # 一键启动（约5分钟完成）
./start.sh status    # 查看运行状态
./start.sh stop      # 停止所有服务

# 12as_100nodes（大规模，需要 ≥32GB 内存）
cd 12as_100nodes/
./start.sh           # 一键启动（约10分钟完成）
./start.sh status    # 查看运行状态
```

## 文档

| 文档 | 用途 |
|------|------|
| **[MASTER_REFERENCE.md](MASTER_REFERENCE.md)** ⭐ | 完整技术参考手册（架构原理/方案设计/功能说明/部署指南/测试结论/扩展开发） |
| **[TEST_REPORT.md](TEST_REPORT.md)** | Bug 修复代码对比 + 60个测试用例详细结果 |

## 控制接口（eth_simulation，默认 `127.0.0.1:8890`）

```bash
# 查看当前节点状态
curl http://127.0.0.1:8890/api/v1/chaos/nodes

# 指定某个节点下线 120 秒
curl -X POST http://127.0.0.1:8890/api/v1/chaos/nodes/down \
  -H 'Content-Type: application/json' \
  -d '{"container_name":"as151h-Ethereum-POS-3-10.151.0.73","duration_seconds":120}'

# 指定某个节点立即上线
curl -X POST http://127.0.0.1:8890/api/v1/chaos/nodes/up \
  -H 'Content-Type: application/json' \
  -d '{"container_name":"as151h-Ethereum-POS-3-10.151.0.73"}'

# 查看可扰动的 WAN 链路
curl http://127.0.0.1:8890/api/v1/wan/targets
```

## 真实测试数据（服务器 161.97.133.14，24核/62GB）

| 指标 | 2as_6nodes | 12as_100nodes |
|------|-----------|---------------|
| 区块高度 | #88 | **#289** |
| 监控事件 | 135 | **50,313** |
| P2P 连接（共识层） | 4/节点 | **75-86/节点** |
| 实时追踪连接数 | 10 | **6,574** |
| 拓扑变化记录 | 35 | **3,073+** |
