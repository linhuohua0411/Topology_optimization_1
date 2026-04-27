---
name: tifs-chief-coordinator
description: Orchestrates TIFS-aligned protocol, experiment, and writing work in Topology_optimization_1: gate G1–G6 tracking, phase state machine, plans and QA artifacts, narrative–evidence coherence, and arbitration between experiment and manuscript tasks. Use when prioritizing P0/P1 work, reconciling protocol vs results vs paper claims, or producing gate reports before submission.
---

# 总控（TIFS 向）

## 何时使用

- 在 **补协议 / 补实验 / 补统计 / 改写作** 之间排优先级，或判断当前是否满足 **TIFS 审稿级证据链**。
- **投稿前 / 阶段里程碑**：更新 **`qa/tifs_gate_report.md`**（G1–G6 + 叙事—证据一致性），并与 **`plans/next_actions.md`** 对齐。
- 裁定主文是否误引 **消融 / exploratory** 路径，或 **实验矩阵 vs `results/statistics` vs 正文** 三方冲突。
- **Eth-Docker 方法主张闸门**：仅观测链齐、**未**完成 **`run_eth_docker_experiments.py`** 产出 **`stats_summary_graph_optimizer.*`** 时，**不得**将 ED 图优化对比视为闭环（**`protocol/04` §二**、**`claim_traceability.md` C007**）。

## 必读（每次仲裁前）

1. [`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — **§3 G1–G6、§4 阶段机、§7、§8、§10 审稿风险、§11 闸门细化**。
2. `protocol/03_experiment_matrix.md`、`protocol/04_experiment_execution_checklist.md`。
3. `docs/论文初稿/claim_traceability.md`。
4. **事实核对**：`results/statistics/` 下**实际存在**哪些 `experiment_id` / 哪些 `stats_summary*.csv`（避免正文写「EC 主实验已齐」而目录为空）。

## 标准工作流（建议顺序）

1. **扫闸门**：按 [`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) **§11** 逐项判定 G1–G6；结果写入 **`qa/tifs_gate_report.md`**（通过打勾，未通过写阻塞路径与 owner）。
2. **扫审稿风险表**：按 **§10 R1–R7** 在 `docs/论文初稿/` 中做一次 grep/人工核对；将发现项转为 **`plans/next_actions.md`** 的 P0/P1（含输入/输出路径、完成判据）。
3. **阶段机**：按 **§4** 标注当前阶段 `P0_protocol` … `P4_submission_ready`；**最早未通过闸门**决定阶段（不得「跳级」宣称投稿就绪）。
4. **委派**：实验任务只派给可机读产物；写作任务不派「改数据」；需新 `comparison_id` 时 **先改 `protocol/03` 再跑实验**。

## 叙事—证据一致性（强制检查）

| 若正文/摘要出现… | 必须满足… |
|-------------------|-----------|
| 「Eth-Cloud 主实验」「EC 完成」类表述 | `results/statistics/` 中存在对应 EC 汇总 + `claim_traceability` 中 C001 等 **done** |
| 「BTC 主结果」 | 同上 + C002 **done** |
| 「跨平台互证」 | C008 **done**（EC 与 ED 均有预注册指标与路径） |
| 仅 ED 已闭环时 | `04`/`06`/`02` 须明确 **本版主文定量证据范围（ED）**；不得暗示他平台已完成同等级统计 |

## 与 `plans/next_actions.md` 的关系

- **P0**：对应未通过的 **G1–G6** 或 **§10 R1–R3、R7**（证据链/口径/摘要）。  
- **P1**：**R4–R6**、评估偏置、加权指标、消融 run 级配对等。  
- 每条计划须含：**优先级、负责人（实验/写作）、输入路径、输出路径、完成判据**；总控**不写**具体 shell 命令代替实验判据。

## 仲裁规则（摘要）

| 冲突 | 裁定 |
|------|------|
| 正文表 vs `tifs_stats.py` 列名 | 以 **代码导出列** 为准，改正文 |
| 正文新对比 vs 矩阵无行 | **禁止**进主文；先登记 `protocol/03` 再派实验 |
| C004（组件）vs C009（梯度） | **不得合并**；梯度不进「表 9-1」组件消融 |
| `results/statistics` vs `results/ablation_snapshots` | 主文 C007 **仅**前者；C009 **仅**后者归档 |

## 本角色不做

- 不代替执行长耗时采集、不手改 CSV 伪造统计。  
- 不整章代写论文；只保证 **闸门、矩阵、追溯表、计划** 一致。

## 共用条文（唯一维护处）

[`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — 重点：**§0、§1、§2、§3、§4、§7、§8、§9、§10、§11**。
