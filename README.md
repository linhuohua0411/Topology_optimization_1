# 全局拓扑优化

本目录为「基于网络演化动力学的区块链网络拓扑结构全局优化」专题根目录，与 TIFS 论文计划对应。

## 子目录说明

| 目录 | 用途 |
|------|------|
| `docs/` | 参考文档、整体流程与公式、计划与实验设计等 |
| `src/` | 源码：鲁棒性模块、全局优化器、数据加载与预处理 |
| `data/` | 拓扑与指标数据（如 private_dot、sepolia）；Eth 云/快照导出默认在 **`results/derived/`** |
| `experiments/` | 实验配置与产出（configs、metrics） |
| `paper_cn/` | 中文论文**合并稿** `论文初稿.md`；分章稿在 `docs/论文初稿/` |
| `paper_en/` | 英文 TIFS 稿及图表 |

详见各子目录中的 README。

## Eth-Docker（TIFS）闭环口径

**观测链**：`experiments/collect_eth_docker_scenarios.py`（或分场景 `experiments/eth_docker_collect/ed_main_{base,link,netem}/collect.py`）→ `compute_eth_docker_metrics_fast.py` → `aggregate_eth_docker_collected_stats.py`。**方法对比（必做）**：`experiments/run_eth_docker_experiments.py`。权威说明见 **`protocol/04_experiment_execution_checklist.md` §二**、**`protocol/03_experiment_matrix.md` §0.1 / §6.4**，追溯见 **`docs/论文初稿/claim_traceability.md`**（**C007**）。
