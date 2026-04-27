# 数据目录说明

本目录存放拓扑与指标数据，与 TIFS 计划 4.4 / 6.2 一致。

## 子目录

| 目录 | 用途 |
|------|------|
| `private_eth/` | **已废弃**（本仓库 TIFS Eth-Docker 主线使用 **`results/raw/eth_docker`**；历史脚本若仍存在，勿再依赖此路径） |
| `private_dot/` | 波卡 100 节点私有链：拓扑快照、时序、结构指标与鲁棒性 R 相关数据 |
| `sepolia/` | Sepolia 测试网爬虫数据：节点、边列表、多时刻拓扑 |

**Eth 相关导出（推荐）**：`results/raw/eth_docker/`（**主线**：观测采集 `sample_*.json` → **`run_eth_docker_experiments.py` 默认输入**）；`results/derived/eth_snapshots/`（**仅迁移/回放**：`run_eth_docker_experiments.py --from-snapshots` 用 `snapshot_*.json`）；`results/derived/eth_cloud_snapshots/`（远程/全量采集脚本默认输出）。口径与 **`protocol/04` §二**、**`claim_traceability.md` C007** 一致。

## 文件命名约定

- **节点表**：`nodes.csv`（节点ID、角色、客户端等）
- **边列表**：`edges_tk.csv` 或 `edges_tXXXX.csv`（时间戳 tk 时的边列表；列如 src, dst, timestamp）
- **结构/性能指标**：`structure_<run_id>.csv`、`perf_timeseries_<run_id>.csv`、`tx_block_latency_<run_id>.csv` 等，与实验 run_id 对应

空目录已用 `.gitkeep` 保留，便于版本管理。
