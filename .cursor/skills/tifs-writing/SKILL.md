---
name: tifs-writing
description: Drafts or revises TIFS-oriented Chinese and English manuscript assets in Topology_optimization_1: docs/论文初稿 chapters, claim_traceability.md, figure and table captions, narrative–evidence alignment, and paper_en sync. Use when editing sections 01–12, checking abstract and conclusions against evidence, enforcing unified_full_protocol in main results, or closing TIFS reviewer risks R1–R7.
---

# 写作（TIFS 向）

## 何时使用

- 撰写或修订 **`docs/论文初稿/`** 分章（**§5.1 顺序**）、**`claim_traceability.md`**、图注表注。
- 将 **`results/statistics/`**（及允许的 **`results/ablation_snapshots/`**）的数字写入正文，并做 **摘要/结论 vs `claim_traceability`** 机械核对。
- 对齐 **`paper_en/`** 与中文稿：**claim、表号、`comparison_id`、口径** 一致；若尚无分章英文稿，至少维护 **`paper_en/MANUSCRIPT_SCOPE_en.md`** 中与摘要/引言/局限一致的英文口径段（随 `docs/论文初稿/` 更新）。
- **投稿前**：配合总控勾选 **`qa/tifs_gate_report.md`** 中与写作相关的项（§10 R1、R2、R4、R5、R7）。

## 必读

[`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — **§1.3、§2、§3、§5（含 5.5 主文/消融路径）、§8、§10、§11**。

## 章节顺序与依赖（再强调）

1. **`04-问题定义与威胁模型.md`**：五字段 + **非目标**；与 **`protocol/threat_model.md`** 一致。  
2. **`05-方法.md` → `06-实验设置.md`**：写清 **CI 方法**（与 `tifs_stats.py` 一致）、检验门控、Holm/FDR **分族**、样本量与 **`experiment_id`**。  
3. **`07-主结果.md`**：**仅** `unified_full_protocol` + 主文绑定的 `budget_variant`（通常 fair）；**禁止**把 **`ablation_*`** 数字写入 §07 主表。  
4. **`08`、`09`**：攻击与消融；须有 **`comparison_id`** 或可核验路径，**禁止**只有空矩阵无统计行（见 **§10 R5**）。  
5. **`01-摘要.md`、`11-结论.md`**：**仅**允许 **`claim_traceability.md` 中 `status=done`** 的量化确定性表述；`pending` 只能用「计划/待闭环」语气。  
6. **`10-局限性.md`**：与当前证据范围一致（如 ED 已闭环、EC/BTC 未齐）。

## 统计呈现（与 CSV 合同）

- 表头列名与 **`experiments/tifs_stats.py` 导出**一致：`mean`、`std`、`ci95_low`、`ci95_high`、`test_name`、`n`、`p_value` 或 `p_value_holm`、`effect_size`、`comparison_id`、`stat_key`、`budget_variant`。  
- **禁止**：手写与 CSV 冲突的 Holm p 或效应量符号。  
- **每个关键数字**旁（表注或正文）能回到 **`comparison_id` + 证据路径**。

## 预算与 raw/fair（G5）

- **分小节** 报告 raw 与 fair；主排序固定 fair 须在 **§06 / §07** 各写一次。  
- 出现 **fair/raw 符号翻转**（如 ED-LINK）时：**必须**有预算映射解释 + 表（你们已有表 7-5 范式），**禁止**跨口径混排「谁更好」。

## Claim 与消融边界

- **C007**：Eth-Docker 图优化主文；证据 **`results/statistics/.../stats_summary_graph_optimizer.*`** + **`gradient_mode=full`**。  
- **C009**：梯度组成消融；证据仅 **`results/ablation_snapshots/...`**；**不得**写进 C004。  
- **C004 / C005**：组件、MLE；**表 9-1 / 9-2** 与 **`protocol/03` ABL** 行绑定；**未 done 不得**写「组件显著贡献」「注入无效」等确定性句。

## 防 cherry-picking（§10 R4）

- §07 若每场景只展示单行基线，**必须**交叉引用 **附录全基线表**（如 **`12-附录.md` A.1**），并声明 **Holm 族内比较全集**。  
- 正文禁止暗示「仅列出的基线存在」。

## 叙事—证据（§10 R1）

- 若 **`results/statistics/`** 中尚无 EC/BTC 汇总文件，则 **`04`/`06`/`02`** 不得写「Eth-Cloud 主实验已完成」类表述；应写 **「本版主文定量闭环为 ED」** 或等价限定语。  
- **`08-攻击类型分析.md`**：矩阵中每一行若声称主文统计，须对应 **`stats_summary`** 行；否则改为 **「计划扩展」** 或删除该行。

## `paper_en/` 同步

- 任何 **`done` claim** 或表号变更，**同步**英文稿相关段与表注。  
- 英文 **不得** 比中文多写未 `done` 的量化结论。

## 反模式（写作禁止）

- 摘要列举具体 p 值但 **claim 仍为 pending**。  
- 将 **`gradient_mode` 消融** 写进摘要当主贡献（应 §09 + C009）。  
- 单文件混写全文（违反 **§5.1**）。  
- 图注不写 **n**、不区分误差条含义（SD/SE/CI）。

## Eth-Docker 写作硬规则

主文若写 **ED 上本文相对基线** 的定量优势：**必须**同时满足：绑定 **C007**；路径 **`stats_summary_graph_optimizer.*`**；与 **`protocol/04` §二** 一致。**C007 为必做 claim**，不得标为可选。

## 共用条文（唯一维护处）

[`../TIFS_REFERENCE.md`](../TIFS_REFERENCE.md) — 重点：**§0、§1.3、§2、§3、§5、§7、§8、§10、§11**。
