---
name: tifs-experiment
description: Runs and validates TIFS-style experiments in Topology_optimization_1: manifests, staged JSON records, collectors, tifs_stats.py outputs, PROTOCOL_VERSION, results under results/raw and results/statistics, ablation_snapshots discipline, and traceability. Use when executing or debugging collectors, aggregating runs, graph optimizer runs, or aligning stats CSV columns with the experiment matrix.
---

# 实验（TIFS 向）

## 何时使用

- 执行或核对 **`results/raw/`**、**`results/statistics/`**、**`run_manifest*.json`**、**`results/ablation_snapshots/`**。
- 使用或修改 **`experiments/tifs_stats.py`**、**`experiments/experiment_protocol.py`**（`PROTOCOL_VERSION`）、**`experiments/run_eth_docker_experiments.py`** 及 **`collect_*` / `compute_*` / `aggregate_*`**。
- 为论文侧提供 **可引用** 的统计行：mean/std/CI、检验、p、效应量；**列名与 `tifs_stats.py` 导出完全一致**。

## 必读

[`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — **§1.2、§2、§3、§6、§8、§10（R3/R6）、§11（G2/G3/G6）**；Eth-Docker 闭环句以 **§1.2** 为准。

## Eth-Docker 主线闭环（必做证据链）

与 **`protocol/04` §二**、**C007** 一致，顺序为：

1. **`experiments/collect_eth_docker_scenarios.py`**（或当前仓库等价采集入口）→ `results/raw/eth_docker/...`  
2. **`experiments/compute_eth_docker_metrics_fast.py`**  
3. **`experiments/aggregate_eth_docker_collected_stats.py`**  
4. **`experiments/run_eth_docker_experiments.py`**（默认 **`--gradient-mode full`**；读 `sample_*.json`，**非必要不用** `--from-snapshots`）

**产出（主文）**：`results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.{csv,json}`、`run_manifest_graph_optimizer.json`、`results_rows_graph_optimizer.json`；每行/manifest 含 **`gradient_mode`**、**`protocol_version`**。

## 预检清单（跑前）

- [ ] **`experiment_id`、`protocol_variant`、`budget_variant`** 与 **`protocol/03`** 行一致；**试跑**标 **`exploratory`**，**不得**写入主文汇总路径。  
- [ ] **`PROTOCOL_VERSION`**（`experiments/experiment_protocol.py`）：若改 CI 算法、检验门控或主指标定义，**必须**升版本并在矩阵 **§6.5** 留痕，**重算**受影响统计。  
- [ ] **多重比较**：主文方法对比 **Holm**；消融探索性多假设 **FDR（BH）** — 与矩阵、`tifs_stats` 调用一致，**禁止**混族解释。  
- [ ] **manifest**：`git_commit` 或镜像 digest、`random_seed`、`raw_root`、`n_runs`、`parallel_runs`、`gradient_mode`、输入图路径等可填尽填（**G6**）。

## 统计与 G2/G3（与 `tifs_stats.py` 对齐）

- **95%CI**：当前主线对 delta 使用 **`mean_std_ci95_t`**（见 `experiments/tifs_stats.py`）。论文 **`06-实验设置.md`** 必须能复述该事实；若改用 bootstrap，属 **协议升级**，不是「改个字」。  
- **正态性门控**：使用 **`test_one_sample_deltas_with_normality_gate`**（或当前等价 API）时，记录 **Shapiro** 等门控结果；日志警告须在实验 README 或 `qa/tifs_gate_report.md` 备注中解释（近常数 delta 等）。  
- **效应量**：写入 `effect_size` + `effect_size_name`；**禁止**手算与导出列冲突的 Cohen d。  
- **Holm**：输出列 **`p_value_holm`**；族内比较集合须与 **附录 / 06** 声明一致（通常：同场景同指标下 OUR vs 多基线）。

## 消融与归档（防污染主文路径）

| 类型 | `protocol_variant` | 路径约定 |
|------|---------------------|----------|
| 主文图优化 | `unified_full_protocol` | **`results/statistics/ED-MAIN-*/`**（跑前备份、跑后 **restore `full`**） |
| 梯度组成消融 | `ablation_gradient` | **`results/ablation_snapshots/gradient_*`、`full_baseline/`** + 日志；**禁止**长期把 `R_s_only` 结果留在 `results/statistics` 冒充主文 |
| 组件 / MLE 等 | `ablation_components` / `ablation_mle` | 以矩阵为准；文件名、表族与主文 **物理隔离** |

**增强（审稿友好）**：对同 **`run_id`** 跨 `gradient_mode` 的 run 级配对差分，单独产出 CSV + FDR，供 **`09-消融`** 引用（见 **TIFS_REFERENCE §10 R6**）。

## 预算与 G5

- **raw** 与 **fair** 分列或分文件；列名或路径中可辨；**禁止**混成单列「预算未标注」。  
- 聚合脚本须能复现 **`claim_traceability`** 中 C003 类 fair/raw 敏感性。

## 追溯（G6）

- 原始 JSON / 日志路径 → manifest → `stats_summary` 行 **`comparison_id` + `stat_key`** 可互链。  
- 大流水线附 **单一总日志**（如 `results/ablation_snapshots/logs/*.log`）便于总控勾选。

## 反模式（禁止）

- 为「好看」删除失败 run、改 `n`、换基线后不重算 Holm。  
- 把 **`exploratory_*`** 目录结果抄进主文表。  
- 矩阵未登记的 `experiment_id` 却产出「主文表」。

## 共用条文（唯一维护处）

[`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — 重点：**§0、§1.2、§2、§3、§6、§8、§10、§11**。
