# CLAUDE.md — 传播动力学关键链路实验规范（IKL-2）

> 本文件是 `Identification_Key_Links_2/experiments/` 的唯一实验执行规范。  
> 所有实验运行、结果引用、论文回填必须遵循本文件。  
> 若与项目根目录规则冲突，以项目根目录 `CLAUDE.md` 为准。

---

## 一、目录结构与职责

```text
experiments/
├── CLAUDE.md                 # 本文件
├── README.md                 # 实验入口说明
├── run_all.py                # 一键全流程（导出 + 批量 + checklist）
├── run_batch.py              # 核心批量实验与统计检验
├── src/
│   ├── algorithms/           # 本文方法 + 基线
│   ├── dynamics/             # 传播动力学求解
│   ├── experiment/           # GT、指标、统计、写入
│   ├── io/                   # stage3/virtualized 数据加载
│   └── graph/                # 图构建与评分
├── data/                     # stage3_assets / virtualized / synthetic
├── results/                  # 实验输出（论文数字唯一来源）
└── tests/                    # 单测
```

**职责边界**：
- 论文主结果必须来自 `run_batch.py` 或 `run_all.py` 的正式输出。
- 临时脚本/手工分析不可直接作为论文数字来源。

---

## 二、实验执行协议

### 2.1 标准执行顺序

1. 运行一键入口（推荐）：

```bash
python3 experiments/run_all.py --repeats 30 --top-k 10
```

2. 或分步执行：
- 先运行虚拟化数据导出（由 `run_all.py` 自动触发）
- 再运行 `run_batch.py`
- 最后检查 `EXPERIMENT_CHECKLIST.md`

### 2.2 固定关键参数（默认投稿口径）

- `n_repeats = 30`
- `top_k = 10`
- GT 协议：impact-based（`build_impact_ground_truth`）
- 统计：配对检验 + Holm-Bonferroni 校正

若参数变更，必须在结果目录和论文中显式披露，不得与默认口径混写。

### 2.3 方法集合（当前权威）

以 `run_batch.py` 中 methods 列表为准：
- `dynamics`
- `dynamics_qw`
- `betweenness`
- `edgeload`
- `pagerank`
- `spectral`
- `mc_cascade`
- `random`

禁止在论文中声明“已对比”但代码未实际运行的方法。

---

## 三、结果文件规范与可引用边界

### 3.1 正式结果最小集合

每次正式实验至少应产出：
- `results/batch_results.csv`
- `results/stat_tests.csv`（若有统计比较）
- `results/SUMMARY.md`
- `results/EXPERIMENT_CHECKLIST.md`
- `results/run_meta.json`

### 3.2 可引用规则

**可引用**：
- `batch_results.csv` 的均值/置信区间字段
- `stat_tests.csv` 的检验类型、p 值、Holm 校正结果、效应量
- `run_meta.json` 中的参数与方法配置

**不可直接引用**：
- 控制台打印临时结果
- 未落盘的中间变量
- 历史目录中无法对应当前代码版本的孤立 JSON/CSV

### 3.3 结果命名与版本化

- 新实验结果不得覆盖历史关键文件；建议复制到带时间戳子目录备份。
- 若复跑得到不同数值，保留新旧结果并在 `SUMMARY.md` 解释差异来源（参数/数据/代码变更）。

---

## 四、数据与真值协议

### 4.1 数据源优先级

1. `stage3_assets`（Sepolia/pos100）
2. `manifest_virtualized.json`（eth_virtual/polkadot_virtual）
3. 合成图（BA 规模扩展）

论文必须注明“真实网络/虚拟化网络/合成网络”来源，不得混称。

### 4.2 Ground Truth 红线

- 使用 `build_impact_ground_truth` 时，不得在得到模型结果后反向调整 GT 参数。
- GT 的 MC 重复数（`n_mc_truth`）必须记录在 `run_meta.json`。
- 若对不同数据集使用不同 GT 策略，必须分表或分段汇报。

---

## 五、质量门控（提交前必过）

1. `batch_results.csv` 存在且字段完整（dataset/family/scenario/method 等）。
2. `stat_tests.csv` 中显著性结论使用 Holm 校正结果，而非原始 p 值。
3. `SUMMARY.md` 与 CSV 数字一致。
4. `EXPERIMENT_CHECKLIST.md` 存在且聚合结果可读。
5. 论文中的“提升幅度”可追溯到具体 dataset/scenario/method 行。

---

## 六、论文回填约束

- 表格与正文仅引用 `batch_results.csv` 和 `stat_tests.csv` 的数字。
- “显著提升”必须满足 Holm 校正后显著，否则写“趋势提升/未达显著”。
- 时间复杂度或运行时结论必须注明测试规模（n_nodes、top-k、方法）。

---

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| ❌ 改论文数字而不重跑实验 | 破坏可复现性 |
| ❌ 用单次 seed 结果替代 30 次统计结果 | 统计不稳健 |
| ❌ 只报告准确率不报告时间与统计显著性 | 证据不完整 |
| ❌ 删除历史结果文件掩盖差异 | 不可审计 |
| ❌ 把 synthetic 结果写成真实网络结论 | 结论失真 |

---

## 八、推荐命令模板

```bash
# 全流程（推荐）
python3 experiments/run_all.py --repeats 30 --top-k 10

# 仅批量实验
python3 experiments/run_batch.py --repeats 30 --top-k 10 --n-mc-truth 5

# 大图快速模式（跳过慢方法）
python3 experiments/run_batch.py --repeats 30 --top-k 10 --skip-slow
```

> 任何新增实验场景（新攻击策略、新GT、新方法）应先更新本文件，再执行与回填论文。