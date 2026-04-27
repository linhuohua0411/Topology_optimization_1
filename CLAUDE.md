# 全局拓扑优化论文与实验总领计划书（Topology Optimization × IEEE TIFS）

## 项目目标

将本仓库《基于网络演化动力学的区块链网络拓扑结构全局优化》从当前“实验持续迭代”状态推进到可稳定支撑 TIFS 投稿的“主张-证据闭环”状态，形成：

- 中文主稿（`docs/论文初稿/` + `paper_cn/`）
- 英文稿与范围同步（`paper_en/`）
- 可复现实验证据链（`results/raw` → `results/processed` → `results/statistics`）

方法主线聚焦于图优化方法（M-OUR）与多基线（M-RESI / M-STAT / M-ASIM / M-FPS）在 Eth-Docker 场景下的鲁棒性与效率对比，并通过协议冻结参数（`experiments/experiment_protocol.py`）保证版本可追溯与统计口径一致。

> 录用现实性说明：TIFS 是否录用取决于理论完整性、实验严谨性、统计可信度与叙事一致性。本计划书用于将这些高风险点前置为可执行交付项，不代表绕过评审标准的保证。

---

## 关联资产与初稿

| 资产 | 路径 / 说明 |
|------|-------------|
| 项目总览 | `README.md`（目录说明、Eth-Docker 闭环口径） |
| 实验主说明 | `experiments/README.md`（指标、脚本、run_id 语义） |
| 协议冻结 | `experiments/experiment_protocol.py`（`PROTOCOL_VERSION=tifs-freeze-v3`） |
| 图优化主脚本 | `experiments/scripts/run_eth_docker_experiments.py` |
| 采集与聚合链 | `experiments/scripts/collect_eth_docker_scenarios.py`、`experiments/scripts/compute_eth_docker_metrics_fast.py`、`experiments/scripts/aggregate_eth_docker_collected_stats.py` |
| 论文中文资产 | `docs/论文初稿/`、`paper_cn/README.md` |
| 论文英文资产 | `paper_en/README.md`、`paper_en/MANUSCRIPT_SCOPE_en.md` |
| 协议矩阵与执行清单 | `protocol/03_experiment_matrix.md`、`protocol/04_experiment_execution_checklist.md` |
| Claim 追溯 | `docs/论文初稿/claim_traceability.md`（重点 C007/C009） |

---

## 实验证据分层（论文叙事硬性约定，IEEE TIFS）

为避免“观测数据”和“模型统计”混写，正文统一采用分层口径：

| 层级 | 内容与来源 | 在本项目中的作用 |
|------|------------|------------------|
| **Layer A** | Eth-Docker 采集样本（`sample_*.json`）与场景定义（BASE/LINK/NETEM） | 提供优化输入图与攻击场景上下文 |
| **Layer B** | 图优化与鲁棒性模型状态（R、Rs、Rc、Rr、`lcc_ratio`、`avg_path_len` 等） | 形成方法比较的核心数值输出 |
| **Layer C** | 统计汇总与显著性检验（`stats_summary_graph_optimizer.{csv,json}`） | 支撑主文“方法优于基线”的定量证据 |
| **Layer D** | 工程运行与可复现实验流程（manifest、run logs、脚本版本） | 支撑可追溯性与复现实证 |

硬性要求：不得将 Layer C 的统计结论描述为链上真实直接观测，也不得将 Layer A 的采样拓扑描述为“理论真值”。

---

## 当前状态评估

| 模块 | 状态 | 说明 |
|------|------|------|
| 实验协议冻结 | ✅ 已具备 | `tifs-freeze-v3`、固定权重与预算策略已代码化 |
| ED 主线脚本 | ✅ 可执行 | 主脚本已覆盖 `gradient_mode`、`budget_variant`、分场景与并行运行 |
| 统计导出 | ✅ 已接通 | 生成 `stats_summary_graph_optimizer`，含 Holm 口径 |
| 消融体系 | ⚠️ 持续完善 | 已有组件消融、梯度模式消融、MLE 注入对照；需与正文绑定稳定版本 |
| 跨平台主线（EC/BTC） | ⚠️ 待完全闭环 | 当前论文主闭环应明确为 ED，其他平台保持扩展语气 |
| 中英文稿一致性 | ⚠️ 待强化 | 需持续同步 claim 状态、表号与统计口径 |

---

## 总体流程（六大阶段）

```
阶段1: 实验设计精化（ED 主线、预算口径、统计族定义）
  → 阶段2: 图优化与基线实现固化（M-OUR + M-RESI/M-STAT/M-ASIM/M-FPS）
  → 阶段3: 数据与执行资产规范化（raw/processed/statistics + manifest）
  → 阶段4: 全部实验执行与统计闭环（主结果 + 消融 + 预算敏感性）
  → 阶段5: 中文论文撰写与主张对齐
  → 阶段6: 英文稿同步与投稿包整理
```

---

## 阶段1：实验设计精化

### 目标

将当前“脚本可运行”状态提升为“审稿可复核”状态：每个主张均可定位到具体 `comparison_id`、统计文件与运行清单。

### 任务清单

#### 1.1 协议与口径冻结（硬性）

- 固定主协议：`unified_full_protocol` + `PROTOCOL_VERSION=tifs-freeze-v3`。
- 固定主文梯度模式：`gradient_mode=full`；`R_s_only/R_s_R_r` 仅用于消融。
- 固定预算口径：`fair` 与 `raw` 分离报告，避免混排结论。

#### 1.2 实验矩阵（ED-MAIN）

主场景按 BASE + LINK + NETEM 执行，其中 LINK/NETEM 包含 low/mid/high tier；主文可固定 tier 并在附录给出全 tier 扩展。

#### 1.3 基线方法与公平性

- 统一比较方法：M-OUR、M-RESI、M-STAT、M-ASIM、M-FPS。
- 同输入图、同随机种子映射、同预算约束（尤其 fair-time/fair-edge）。
- 禁止在正文仅展示“有利基线子集”而不声明全集。

#### 1.4 统计检验策略

- 主比较采用配对差分统计 + Holm 多重比较修正。
- 关键字段需可在统计文件中直接溯源：`p_value_holm`、`effect_size`、`comparison_id`、`stat_key`。

#### 1.5 消融与敏感性计划

- 梯度组成消融（`full`/`R_s_R_r`/`R_s_only`）。
- 组件消融（`wo_evolution`、`wo_self_organization`、`wo_Rc`、`wo_Rr`）。
- MLE 注入对照（paired）。

#### 1.6 主张与证据对齐规则

- C007（ED 主结果）只能引用 `stats_summary_graph_optimizer.*` 及对应 manifest。
- C009（梯度组成消融）仅引用 `results/ablation_snapshots/` 证据，不得并入 C007 主表结论。

---

## 阶段2：代码实现（`src/` + `experiments/`）

### 目标

确保优化器、基线、攻击评估、统计导出在同一协议下稳定运行，并且所有关键参数有显式来源。

### 建议目录结构（以当前仓库为准）

```
src/
├── models/                 # global_optimizer、robustness、baselines
experiments/
├── scripts/
│   ├── run_eth_docker_experiments.py
│   ├── collect_eth_docker_scenarios.py
│   ├── compute_eth_docker_metrics_fast.py
│   ├── aggregate_eth_docker_collected_stats.py
│   ├── run_component_ablation_ed.py
│   └── run_mle_injection_comparison.py
└── tifs_stats.py
results/
├── raw/
├── processed/
├── statistics/
└── ablation_snapshots/
```

### 任务清单

#### 2.1 优化器与基线接口统一

- 保证 M-OUR 与四类基线输出字段一致，便于统一统计聚合。
- 保证预算约束注入方式一致（time/edge）。

#### 2.2 运行记录与 manifest 完整化

- 每个实验输出 run 级 manifest，记录 seed、weights、gradient_mode、input_path、预算等。
- 禁止“无 manifest 的统计文件”进入主文证据链。

#### 2.3 异常场景处理

- 图规模过小、样本缺失、运行跳过需保留 skip reason。
- 汇总脚本保留可诊断日志，支持复盘。

---

## 阶段3：数据资产与真实栈环境说明

### 任务清单

- 规范化 `results/raw/eth_docker/*/run-*/sample_*.json` 结构与命名。
- 明确 `results/processed/eth_docker/` 与 `results/statistics/` 的上游关系。
- 在文档中固定数据来源说明：`collected_samples` 与 `legacy_snapshots` 区别仅作兼容，不作主文推荐路径。

---

## 阶段4：实验执行与结果分析

### 目标

按主线协议产出可直接写入论文表格的统计结果，并保持 fair/raw 与主结果/消融边界清晰。

### 实验映射（本项目）

| 实验 | 内容 |
|------|------|
| **Exp1** | ED-MAIN-BASE：无攻击场景下方法对比 |
| **Exp2** | ED-MAIN-LINK：链路降级攻击下对比（tier 化） |
| **Exp3** | ED-MAIN-NETEM：时延扰动攻击下对比（tier 化） |
| **Exp4** | 预算口径分析：fair vs raw 稳定性与排序变化 |
| **Exp5** | 梯度与组件消融：机制贡献拆分 |
| **Exp6** | MLE 注入对照：注入策略有效性与显著性 |
| **Exp7** | 扩展平台/外部场景验证（若当期未闭环，正文仅写计划） |

### 阶段4 输出

- `results/raw/*/results_rows_graph_optimizer.json`
- `results/statistics/*/stats_summary_graph_optimizer.{csv,json}`
- `results/statistics/*/run_manifest_graph_optimizer.json`
- 消融快照与日志：`results/ablation_snapshots/`

---

## 阶段5：中文论文撰写

### 任务清单

#### 5.1 方法与协议表述

- 明确主协议、攻击分层、预算定义、统计检验流程。
- 给出 “主结果 vs 消融” 的证据边界说明，防止审稿人质疑 cherry-picking。

#### 5.2 主结果章节

- 仅使用主线协议结果（C007）作为核心定量结论。
- fair 与 raw 分小节陈述，避免跨口径比较。

#### 5.3 消融与讨论章节

- 梯度组成与组件消融独立成节（C009/C004/C005 口径）。
- 对不显著结果保持中性描述，避免过度确定性语言。

#### 5.4 风险与局限

- 明确当前闭环平台范围（ED 主闭环，其他平台按实际状态谨慎表述）。
- 说明实验环境与真实主网行为之间的语义差异。

#### 5.5 定稿文件建议

- `paper_cn/论文初稿.md`（主合并稿）
- `docs/论文初稿/`（分章稿与 claim 追溯）

---

## 阶段6：英文论文撰写

### 建议标题（可微调）

- *Global Topology Optimization for Blockchain Networks via Evolution Dynamics under Fair Budgeting*
- *A Reproducible Eth-Docker Benchmark for Graph Optimization under Adversarial Degradation*

### 结构（IEEE TIFS）

- Abstract, Keywords
- I. Introduction
- II. Related Work
- III. Problem Setup and Threat Model
- IV. Method and Protocol Freeze
- V. Experimental Evaluation (ED Mainline + Ablations)
- VI. Discussion and Limitations
- VII. Conclusion
- References / Appendix

### 输出文件建议

- `paper_en/MANUSCRIPT_SCOPE_en.md`（范围与口径）
- `paper_en/README.md` 对应英文稿入口说明

### 术语表（节选）

| 中文 | 英文 |
|------|------|
| 全局拓扑优化 | global topology optimization |
| 预算公平对比 | fair-budget comparison |
| 观测链 | observation pipeline |
| 图优化主结果 | graph-optimizer main results |
| 梯度组成消融 | gradient-composition ablation |
| 组件消融 | component ablation |

---

## Cursor Cloud Agents 任务分解与提示词（摘要）

### Agent 任务 1：协议与矩阵核查

- 核查 `protocol/03`、`protocol/04` 与主脚本参数一致性，输出差异清单。

### Agent 任务 2：主线实验执行

- 按 ED-MAIN-BASE/LINK/NETEM 产出统计文件与 run manifest。

### Agent 任务 3：消融实验执行

- 跑梯度/组件/MLE 消融并输出独立路径结果。

### Agent 任务 4：统计与图表

- 基于 `tifs_stats.py` 导出可入稿 CSV/JSON 与图表素材。

### Agent 任务 5：中文稿对齐

- 把主结果与 claim_traceability 对齐，修复“结论先于证据”语句。

### Agent 任务 6：英文稿同步

- 同步 done claim、表号与定量口径，避免英文稿超写。

---

## 时间线估计

| 阶段 | 预计耗时 | 依赖 |
|------|---------|------|
| 阶段1：实验设计精化 | 0.5–1 session | 无 |
| 阶段2：实现与接口固化 | 1–2 sessions | 阶段1 |
| 阶段3：数据资产规范 | 0.5–1 session | 阶段2 |
| 阶段4：主实验与消融执行 | 2–4 sessions | 阶段2–3 |
| 阶段5：中文稿定稿 | 1–2 sessions | 阶段4 |
| 阶段6：英文稿同步 | 1–2 sessions | 阶段5 |

---

## 质量检查清单（IEEE TIFS 投稿标准）

### 理论与方法

- [ ] 主方法、预算定义、攻击层级、协议版本表述一致
- [ ] 主结果与消融结果边界清晰，不互相替代
- [ ] 所有关键参数可追溯到脚本或协议文件

### 实验严谨性

- [ ] 主线实验均有 run manifest 与统计汇总文件
- [ ] fair/raw 分开汇报，不混合排名结论
- [ ] 多重比较修正与效应量字段完整
- [ ] 失败/跳过 run 有记录，不隐性删除

### 写作质量

- [ ] 中文稿与英文稿 claim 状态一致
- [ ] 摘要与结论仅使用 `status=done` 的确定性主张
- [ ] 局限性与当前证据覆盖范围一致

### 复现与交付

- [ ] 脚本入口、输入路径、输出产物可一键追踪
- [ ] 提交包包含协议版本、结果索引、关键日志

---

## 注意事项

1. 主文定量结论优先绑定 ED 主闭环；扩展平台未闭环时使用“计划/扩展”语气。  
2. 不将消融路径结果写入主结果章节作为主结论。  
3. 不以单次运行替代统计结论，不以截图替代结构化结果。  
4. 任何“显著优于”措辞必须可追溯到修正后 p 值与效应量。  
5. 保持中英文稿证据一致，避免英文稿先行夸大。  

---

## 文档修订记录

| 日期 | 修订说明 |
|------|----------|
| 2026-04-27 | 初版：按 `Claude-ref.md` 章节结构生成本项目实验总领 `CLAUDE.md`，内容切换为 Topology_optimization_1 的 ED 主线与 TIFS 证据链口径 |
