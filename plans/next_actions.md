# 下一步整改清单（P0 / P1 / P2）

> 目标：先补齐 TIFS 审稿高风险项（P0），再提升方法-评估一致性（P1），最后完善展示与可读性（P2）。

## P0（必须先完成）

### P0-4 ED 攻击分档（1 + 2×3）对齐与重跑（进行中）
- 优先级：P0
- 负责人：实验 + 写作
- 状态：**in_progress**（2026-04-22）
- 输入路径：
  - `experiments/experiment_protocol.py`
  - `experiments/run_eth_docker_experiments.py`
  - `results/raw/eth_docker/*/run-*/sample_*.json`
- 输出路径：
  - `results/statistics/ED-MAIN-BASE/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-LINK-low|mid|high/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-NETEM-low|mid|high/stats_summary_graph_optimizer.csv`
  - 回填 `docs/论文初稿/06-实验设置.md`、`07-主结果.md`、`08-攻击类型分析.md`、`claim_traceability.md`
- 完成判据：
  - [x] 代码支持 `--attack-tier {low,mid,high,all}`，并按 tier 输出独立 `experiment_id`
  - [ ] `n=20` 全档位统计与 manifest 产物落盘
  - [ ] 主文以 `mid` 为主排序、`low/high` 作为强度敏感性补充完成回填
  - [ ] `claim_traceability` 与 `qa/tifs_gate_report` 证据路径更新完成

### P0-3 v3 协议重跑与主文回填（固定参数主线）
- 优先级：P0
- 负责人：实验 + 写作
- 状态：**done**（2026-04-22）
- 输入路径：
  - `experiments/experiment_protocol.py`（`tifs-freeze-v3`）
  - `src/models/global_optimizer.py`（默认 `w=(0.25,0.55,0.20)`）
  - `results/raw/eth_docker/*/run-*/sample_*.json`
- 输出路径：
  - `results/statistics/ED-MAIN-BASE/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-LINK/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-NETEM/stats_summary_graph_optimizer.csv`
  - 回填 `docs/论文初稿/07-主结果.md`、`12-附录.md`、`qa/tifs_gate_report.md`
- 完成判据：
  - [x] 三场景按 v3 权重重跑完成并生成新 manifest
  - [x] 主文表 7-3/7-5 与附录 A.1 更新为 v3 数值
  - [x] `claim_traceability` 中 C007 明确绑定 v3 证据路径
  - [x] `adaptive_vs_fixed`（ED, n=20）完成决策：固定权重保留为主线，在线自适应降级为消融

### P0-1 目标函数与梯度口径对齐（实验）— **已完成（2026-04-20）**
- 优先级：P0
- 负责人：实验
- 状态：**done**（判据已满足；主文 `results/statistics` 已 restore 为 `gradient_mode=full`）
- 输入路径：
  - `experiments/run_eth_docker_experiments.py`
  - `src/models/robustness.py`
  - `results/raw/eth_docker/*/results_rows_graph_optimizer.json`
- 输出路径：
  - `results/statistics/ED-MAIN-BASE/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-LINK/stats_summary_graph_optimizer.csv`
  - `results/statistics/ED-MAIN-NETEM/stats_summary_graph_optimizer.csv`
  - `results/statistics/*/run_manifest_graph_optimizer.json`
- 消融归档（勿与主文默认路径混写）：
  - `results/ablation_snapshots/gradient_R_s_only/ED-MAIN-*/`
  - `results/ablation_snapshots/gradient_R_s_R_r/ED-MAIN-*/`
  - `results/ablation_snapshots/full_baseline/ED-MAIN-*/`
  - 日志：`results/ablation_snapshots/logs/ed_gradient_ablation_20260420_214052.log`
- 写作回填：
  - `docs/论文初稿/claim_traceability.md`：**C009**（`ablation_gradient`）
  - `docs/论文初稿/09-消融与敏感性.md`：**§9.2**、**表 9-A**
  - `docs/论文初稿/07-主结果.md`：**§7.4** 交叉引用 §9.2 / C009
- 完成判据：
  - [x] 主文至少提供 `gradient_mode` 对照（`R_s_only`、`R_s_R_r`、`full` 中至少两组）
  - [x] 主结果与表注明确当前采用的 `gradient_mode`
  - [x] `claim_traceability.md` 中对应证据路径可回溯到含 `gradient_mode` 的 manifest

### P0-2 统计协议一致化（实验+写作）— **文档口径已对齐（2026-04-21）**
- 优先级：P0
- 负责人：实验 + 写作
- 输入路径：
  - `docs/论文初稿/06-实验设置.md`
  - `experiments/tifs_stats.py`
- 输出路径：
  - `docs/论文初稿/06-实验设置.md`
  - `results/statistics/*/stats_summary*.csv`（如重算）
- 完成判据：
  - CI 方案“文档与代码完全一致”（bootstrap 或 t-interval 二选一并统一）
  - 方法节/实验设置中写明 CI 计算方式与检验切换规则
  - 主文表格注释不再出现协议漂移
  - [x] 文档侧（`docs/论文初稿/` + `paper_en/MANUSCRIPT_SCOPE_en.md`）已统一写明本版平台范围与补跑策略
  - [ ] 若后续切换 CI 算法或检验实现，需升级 `PROTOCOL_VERSION` 并重算 `results/statistics/*`

## P1（强烈建议，提升说服力）

### P1-1 评估口径补齐加权指标（实验）
- 优先级：P1
- 负责人：实验
- 输入路径：
  - `experiments/graph_metrics.py`
  - `results/raw/eth_docker/*/results_rows_graph_optimizer.json`
- 输出路径：
  - `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv`（新增加权指标列或新增统计文件）
  - `docs/论文初稿/07-主结果.md`（引用新增指标）
- 完成判据：
  - 至少补充一组“非二值化”指标用于与现有二值指标对照
  - 主文明确说明“优化变量为加权图，评估包含加权口径”
  - 结论方向在二值/加权两套口径下不自相矛盾

### P1-2 连通性约束偏置控制（实验）
- 优先级：P1
- 负责人：实验
- 输入路径：
  - `src/models/global_optimizer.py`
- 输出路径：
  - `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv`（约束策略更新后重算）
  - `docs/论文初稿/05-方法.md`（约束策略说明）
- 完成判据：
  - 替换“固定 0.1 人工桥接”或在预算/惩罚中显式计入其代价
  - 方法章节可解释“为何该约束不引入工程修补偏置”
  - 关键结论在新约束下仍可复现

## P2（展示与审稿防御）

### P2-1 主流基线全量展示（写作）
- 优先级：P2
- 负责人：写作
- 输入路径：
  - `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv`
  - `docs/论文初稿/07-主结果.md`
- 输出路径：
  - `docs/论文初稿/07-主结果.md`
  - `docs/论文初稿/12-附录.md`（如正文放不下则全量移附录）
- 完成判据：
  - 每个场景×每个指标都展示 OUR vs RESI/STAT/ASIM/FPS，不再仅单行代表
  - 正文与附录之间有明确交叉引用（防 cherry-picking 质疑）

### P2-2 Claim 与摘要/结论同步（写作）
- 优先级：P2
- 负责人：写作
- 输入路径：
  - `docs/论文初稿/claim_traceability.md`
  - `docs/论文初稿/01-摘要.md`
  - `docs/论文初稿/11-结论.md`
- 输出路径：
  - 同上
- 完成判据：
  - 摘要与结论中的量化句均可映射到 `status=done` claim
  - 未完成 claim（pending）不进入主文“确定性结论”表述

### P2-3 非跑数项口径收口（写作+总控）— **已完成（2026-04-21）**
- 优先级：P2
- 负责人：写作 + 总控
- 状态：**done**
- 输入路径：
  - `docs/论文初稿/02-引言.md`
  - `docs/论文初稿/04-问题定义与威胁模型.md`
  - `docs/论文初稿/06-实验设置.md`
  - `docs/论文初稿/07-主结果.md`
  - `docs/论文初稿/08-攻击类型分析.md`
  - `docs/论文初稿/10-局限性.md`
  - `docs/论文初稿/11-结论.md`
  - `paper_en/README.md`
  - `paper_en/MANUSCRIPT_SCOPE_en.md`
  - `qa/tifs_gate_report.md`
- 输出路径：
  - 同上
- 完成判据：
  - [x] 中文主文统一为“本版 ED 闭环，EC/BTC 待本地部署补跑”
  - [x] 英文稿口径文件同步同一表述（`MANUSCRIPT_SCOPE_en.md`）
  - [x] `08-攻击类型分析.md` 表头与状态字段不再误导为“全部已是主文已完成结果”

### P1-3 机制消融补齐（组件 + MLE）— **已完成（2026-04-21）**
- 优先级：P1
- 负责人：实验 + 写作
- 状态：**done**（脚本、样本量与回填均完成）
- 输入路径：
  - `experiments/run_component_ablation_ed.py`
  - `experiments/run_mle_injection_comparison.py`
  - `docs/论文初稿/09-消融与敏感性.md`
  - `docs/论文初稿/claim_traceability.md`
- 输出路径：
  - `results/ablation_snapshots/component_ablation_ed_base/results_rows_component_ablation.json`
  - `results/ablation_snapshots/component_ablation_ed_base/stats_summary_component_ablation.csv`
  - `experiments/metrics/mle_injection_comparison.json`
  - 同步回填 `09-消融与敏感性.md`（表 9-1 / 表 9-2）与 C004/C005
- 当前进展：
  - [x] 组件消融脚本落地并在 `ED-MAIN-BASE` 上完成正常样本量跑数（`n=20`）
  - [x] MLE 注入对照脚本落地（可直接输出 paired 结构化 JSON）
  - [x] MLE 注入对照已完成 `n=30`（`experiments/metrics/mle_injection_comparison.json`），并回填表 9-2 / C005
  - [x] C004/C005 已补充证据路径与验收判据（C004 已按“机制分工+trade-off”口径置 done，C005 已 done）
  - [x] 将组件消融扩展到预注册样本量（`n=20`）
  - [x] 运行 MLE 注入对照到目标样本量（建议 `n=30`）并回填统计值

## 执行顺序与闸门

1. 先完成 P0-1、P0-2，再更新主文结果。  
2. P1 完成后再固化方法叙述，避免“先写死后改数”。  
3. P2 作为投稿前统一收口，确保 G1–G6 口径闭环。  

