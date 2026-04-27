# CLAUDE.md — 实验执行与统计规范（Topology Optimization / TIFS）

> 本文件是 `experiments/` 目录的实验执行规范。  
> 所有实验运行、统计汇总、论文数字回填必须遵循本文件。  
> 若与项目根目录规则冲突，以项目根目录 `CLAUDE.md` 为准。

---

## 一、目录结构与职责

```text
experiments/
├── CLAUDE.md                                 # 本文件
├── README.md                                 # 实验目录说明
├── scripts/                                  # 统一执行入口（推荐）
├── experiment_protocol.py                    # PROTOCOL_VERSION 与固定参数
├── scripts/collect_eth_docker_scenarios.py           # 采集入口（ED 观测链）
├── scripts/compute_eth_docker_metrics_fast.py        # 指标计算
├── scripts/aggregate_eth_docker_collected_stats.py   # 聚合
├── scripts/run_eth_docker_experiments.py             # 图优化主实验（必做）
├── scripts/run_component_ablation_ed.py              # 组件消融
├── scripts/run_mle_injection_comparison.py           # MLE 注入对照
├── tifs_stats.py                             # 统计检验与导出
└── eth_docker_collect/                       # 分场景采集脚本
```

职责边界：
- 主文结果仅来自正式主线脚本产物（`results_rows_graph_optimizer` + `stats_summary_graph_optimizer`）；
- 临时脚本输出、控制台打印、手工拼表不可直接用于论文定量主张。
- 推荐从 `experiments/scripts/` 调用主线脚本，保留旧路径兼容性。

---

## 二、实验执行协议

### 2.1 标准执行顺序（ED 主线）

1. 采集：`scripts/collect_eth_docker_scenarios.py`（或 `eth_docker_collect/ed_main_*`）  
2. 计算：`scripts/compute_eth_docker_metrics_fast.py`  
3. 聚合：`scripts/aggregate_eth_docker_collected_stats.py`  
4. 对比：`scripts/run_eth_docker_experiments.py`（默认 `--gradient-mode full`）

与 `protocol/04_experiment_execution_checklist.md`、`claim_traceability.md` 的 C007 保持一致。

### 2.2 固定关键参数（投稿默认口径）

- `PROTOCOL_VERSION` 以 `experiment_protocol.py` 为准；
- 主文梯度模式：`gradient_mode=full`；
- 默认运行次数：`N_RUNS_DEFAULT`（可覆盖，但需留痕）；
- 攻击层级：BASE + LINK/NETEM 的 tier（low/mid/high）。

若变更关键参数，必须同步：
- `run_manifest_graph_optimizer.json`；
- 论文实验设置章节；
- `claim_traceability.md` 对应 claim 的证据说明。

### 2.3 方法集合（当前权威）

主线比较方法固定为：
- `M-OUR`
- `M-RESI`
- `M-STAT`
- `M-ASIM`
- `M-FPS`

禁止在论文中写“已对比”但脚本未真实运行的方法。

---

## 三、结果文件规范与可引用边界

### 3.1 主文最小证据集合

每次正式主线至少产出：
- `results/raw/eth_docker/<experiment_id>/results_rows_graph_optimizer.json`
- `results/statistics/<experiment_id>/stats_summary_graph_optimizer.csv`
- `results/statistics/<experiment_id>/stats_summary_graph_optimizer.json`
- `results/statistics/<experiment_id>/run_manifest_graph_optimizer.json`

### 3.2 可引用规则

可引用：
- `stats_summary_graph_optimizer.*` 中的均值、CI、检验、修正后 p 值、效应量；
- `run_manifest_graph_optimizer.json` 中的协议版本、参数、输入来源。

不可直接引用：
- 控制台临时输出；
- 未写入正式结果路径的中间 CSV；
- 无法对应当前代码版本的历史孤立文件。

### 3.3 结果命名与版本化

- 主文与消融结果必须物理隔离（`results/statistics` vs `results/ablation_snapshots`）；
- 复跑产生数值变化时保留变更记录，不覆盖证据链上下文；
- `exploratory_*` 结果不得写入主文证据路径。

---

## 四、数据与协议红线

### 4.1 数据来源优先级

1. `results/raw/eth_docker/.../sample_*.json`（推荐主路径）  
2. `--from-snapshots` 的 legacy 快照路径（仅兼容场景）  

主文不得把 legacy 模式当默认证据来源。

### 4.2 协议与统计红线

- `PROTOCOL_VERSION` 变更必须重算受影响统计；
- 主文方法比较采用 Holm，消融探索可用 FDR（BH），禁止混族解释；
- “显著”表述必须基于修正后 p 值与明确比较族。

---

## 五、质量门控（提交前必过）

1. 每个 `experiment_id` 有完整主线结果与 manifest；  
2. `stats_summary` 列字段与 `tifs_stats.py` 导出合同一致；  
3. 主文结论可追溯到 `comparison_id + stat_key`；  
4. fair/raw 口径分开汇报，无混排；  
5. 失败/跳过 run 有记录，不做静默删除。  

---

## 六、论文回填约束

- `07-主结果.md` 仅使用 `unified_full_protocol` 主线结果；  
- C007 绑定 ED 主线图优化结果，且 `gradient_mode=full`；  
- C009（梯度消融）只能来自 `results/ablation_snapshots/`；  
- 未 done 的 claim 只能写“计划/待闭环”，不得写确定性定量结论。  

---

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| ❌ 删除失败 run 后再统计 | 破坏统计真实性 |
| ❌ 不重算 Holm 直接复用旧 p 值 | 结论不可审计 |
| ❌ 混合 fair/raw 得出单一“最优”结论 | 口径错误 |
| ❌ 将消融结果写入主文主表 | 证据边界污染 |
| ❌ 未登记 experiment_id 输出主文表 | 违反矩阵可追溯性 |

---

## 八、推荐命令模板

```bash
# 1) 采集（示例）
python3 experiments/scripts/collect_eth_docker_scenarios.py

# 2) 指标计算
python3 experiments/scripts/compute_eth_docker_metrics_fast.py

# 3) 聚合
python3 experiments/scripts/aggregate_eth_docker_collected_stats.py

# 4) 主线图优化对比（主文口径）
python3 experiments/scripts/run_eth_docker_experiments.py --gradient-mode full

# 5) 梯度消融（示例）
python3 experiments/scripts/run_eth_docker_experiments.py --gradient-mode R_s_only

# 6) 组件消融 / MLE 对照
python3 experiments/scripts/run_component_ablation_ed.py
python3 experiments/scripts/run_mle_injection_comparison.py
```

> 任何新增场景、新统计口径或新方法集合，应先更新本文件与协议文档，再执行实验和论文回填。
