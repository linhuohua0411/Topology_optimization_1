# 实验矩阵（小白版）

> 这份文档是 `03_experiment_matrix.md` 的“人话版”。
> 目标：不改实验设计，只把内容讲清楚：**要做什么、要哪些数据、现在是否能做、下一步怎么做**。

---

## 1. 先看懂：我们到底在做哪几类实验？

可以把所有实验分成 4 大类：

1. **主结果实验（最重要）**  
   用于论文主文表格（7-1 到 7-5），必须数据完整、统计完整。
2. **攻击实验（验证抗攻击能力）**  
   看在随机攻击、定向攻击、链路扰动下，网络有没有更稳。
3. **方法对比实验（和别人比）**  
   把我们方法和 ResiNet / Static / AttackSim 等方法在同预算下对比。
4. **消融与附录实验（解释“为什么有效”）**  
   包括去掉模块、参数扰动、Fabric 外推等，主要用于补充说明。

---

## 2. 实验编号怎么读？

你看到的编号如 `ED-MAIN-BASE`，可以拆开读：

- `EC` = Eth-Cloud
- `ED` = Eth-Docker
- `BTC` = BTC-Docker
- `MTH` = 方法对比（method compare）
- `ABL` = 消融（ablation）
- `MAIN` = 主实验
- `BASE` = 基线场景（无攻击）
- `LINK / NETEM / RAND / TGT / ADP / ECL / PART` = 不同攻击或扰动类型

举例：

- `ED-MAIN-BASE`：以太坊 Docker 平台，主实验，无攻击基线
- `ED-MAIN-NETEM`：以太坊 Docker 平台，主实验，网络时延/丢包扰动

### 2.1 Eth-Docker 在本仓库怎么算「跑完」（与正式矩阵同一口径）

**顺序固定**：**采集**（`collect_eth_docker_scenarios.py`）→ **加工**（`compute_eth_docker_metrics_fast.py`）→ **观测统计聚合**（`aggregate_eth_docker_collected_stats.py`）→ **图优化 / 方法对比**（`run_eth_docker_experiments.py`，**必做**）。缺最后一步则 **ED 方法主张**在证据链上不齐。执行勾选与细节见 **`protocol/04` §二**；权威定义见 **`protocol/03` §0.1、§6.4**。

---

## 3. 每个实验最少要准备什么数据？

不想记太多字段时，只记下面 8 个“硬必需”：

1. `timestamp_utc`（时间）
2. `experiment_id`（实验编号）
3. `run_id`（第几次重复）
4. `phase`（阶段：pre/attack/recovery 等）
5. `attack_label + attack_params`（攻击类型和参数）
6. `R, Rs, Rc, Rr`（鲁棒性指标）
7. `lcc_ratio, avg_path_len, components`（拓扑稳定性指标）
8. `budget_variant + budget_cost`（预算口径与成本）

如果是 BTC 主实验，还要加：`reachable_ratio`（协变量，缺了不能进主文统计）。

---

## 4. 一条主文实验“合格”需要满足什么？

下面 4 条必须同时满足：

1. **字段齐全**：核心字段不能缺。
2. **样本够**：默认每实验 `n_runs >= 20`，且每个 run 至少 19 个时序点。
3. **周期固定**：同一个实验中途不能换采样周期。
4. **统计齐全**：至少要有 `mean/std/ci95/p/effect_size` 等统计结果。

做不到上面 4 条时，结论最多写“探索性结果”，不能写主文硬结论。

---

## 5. 一页看懂所有实验（按优先级）

### A. 主文必做（优先级最高）

1. `EC-MAIN-BASE`（Eth-Cloud 基线）
2. `ED-MAIN-BASE`（Eth-Docker 基线；须含 **§2.1** 全链，含 **`run_eth_docker_experiments.py`**）
3. `BTC-MAIN-BASE`（BTC-Docker 基线）
4. `EC/ED/BTC` 上的主要攻击实验（RAND/TGT/NETEM/ECL/PART）
5. `MTH-CMP-FAIR`、`MTH-CMP-RAW`（方法公平对比）

### B. 主文次要但建议做

1. `BTC-MAIN-BGP`（条件纳入，先附录验证）
2. 跨层一致性分析（Eth 的 EL+CL 双层）

### C. 仅消融/附录

1. `ABL-COMP`（组件消融）
2. `ABL-MLE-INJ`（MLE 注入对照）
3. `ABL-WEIGHT`（参数敏感性）
4. `FAB-EXT-NETEM`（Fabric 外推，附录）
5. `POL-HOLD`（暂缓）

---

## 6. 小白常见疑问（直接答案）

### Q1：为什么我有快照还不能写主文结论？

因为主文要求的是“**完整时序 + 足够重复 + 统计显著性**”，不是单次快照或少量样本。

### Q2：`fair` 和 `raw` 有什么区别？

- `raw`：每个方法按自己默认资源跑。
- `fair`：把时间/边改动预算对齐后再比，避免“谁算得更久谁赢”。

### Q3：什么时候可以回填表 7-1 到 7-5？

当且仅当：

- 目标实验 `n_runs` 达标；
- 每 run 阶段完整；
- `stats_summary` 输出完整（含 p 值、效应量）；
- 证据追溯表状态是 done。

---

## 7. 推荐执行顺序（最稳妥）

1. 先跑 `ED-MAIN-BASE` / `EC-MAIN-BASE` / `BTC-MAIN-BASE`，确认主链路通。
2. 再跑攻击实验（每个平台 1~2 个代表攻击先跑通）。
3. 再做 `MTH-CMP-FAIR/RAW` 方法对比。
4. 最后做消融和附录（ABL、FAB、BGP 条件项）。

---

## 8. 你可以直接照抄的“日报模板”

```text
今天完成：
- 实验：ED-MAIN-BASE
- 运行：20/20 runs
- 时序：每 run 19 点，阶段完整
- 字段：核心字段齐全
- 统计：已产出 mean/std/ci95/p/effect_size
- 结论状态：可纳入主文（是/否）
- 问题与补救：xxx
```

---

## 9. 术语最小词典（只保留必要）

- **LCC**：最大连通子图占比，越高越稳。
- **avg_path_len**：平均路径长度，越短通常越好。
- **R / Rs / Rc / Rr**：综合鲁棒性及其分项。
- **run**：同一实验重复一次。
- **phase**：实验阶段（攻击前、攻击中、恢复期）。
- **effect_size**：效果强度，不只看“显著不显著”。

---

## 10. 给导师/审稿人一句话说明版本

“我们将实验分为主结果、攻击验证、方法对比和消融附录四类；主文结论仅来自满足字段完整、样本充分、统计齐全和证据可追溯的 `unified_full_protocol` 实验。”

---

## 11. 执行补充（统计与追溯）

为了和主表口径完全一致，执行时再补 8 条固定动作：

1. 固定随机种子池（`run_id -> seed`）。
2. 先做正态性检验（Shapiro-Wilk）。
3. 正态用 paired t，非正态用 Wilcoxon。
4. 主文多组比较做 Holm 校正，消融做 FDR(BH)。
5. paired t 报 Cohen's d(dz)，Wilcoxon 报 Cliff's delta/rank-biserial。
6. CI 统一用 bootstrap percentile（10,000 次）。
7. 缺失 run 先补采；补不了就整组剔除并写入 manifest。
8. 每条结论必须在追溯表登记：`claim_id + comparison_id + stat_key + evidence_paths + status`。

主文统计字段最小集合（必须全有）：

`mean,std,ci95_low,ci95_high,test_name,p_value,effect_size,n,comparison_id,stat_key`

---

## 12. 闭环与主文约束（对照正式矩阵 §1 新列）

> 与 `03_experiment_matrix.md` **§1 宽表**中「**闭环与主文约束（TIFS）**」列同一口径；此处为速查版。

| 对象 | 一句话约束 |
|:---|:---|
| **EC-MAIN-*** | 没有 **EL+CL 时序边表**，就不要写主文「云上拓扑/优于基线」类硬句；攻击行要有 **`network_condition`** 与档位预注册。 |
| **ED-MAIN-*** | 必须 **采集→加工→聚合→`run_eth_docker_experiments.py`** 四步全齐，才能写 **ED 上方法对比**；与 EC 是 **方向互证**（`CMP-ED-EC-DIRECTION`），不是数值复制；定位为 **链路/劣化韧性**，不要写成拜占庭主结论。 |
| **ED Holm 三指标** | 事先定 **1 个 primary**（见 `04` §0.11）；主文只报 mid 时，low/high **仍要跑满样本**才能写跨强度。 |
| **BTC-MAIN-*** | **`reachable_ratio` 定义冻结**且每 run 有值；契约/字段不齐则 **整段 BTC 主文定量**不写。 |
| **MTH-CMP-*** | 三平台 **`stats_summary` 同构** + §2.0 基线 **ready** + **聚合脚本**产出前，不要写 **跨平台排名**主文句。 |
| **探索性 / 消融** | `exploratory` 与未预注册对比：**单独文件或前缀**，不要混进主文表；`ABL-COMP` 变体不齐不写「组件显著贡献」。 |
| **缺失 run / skip** | 按 manifest **`missing_run_policy`**；脚本 **skip 已有 run** 时注明 **不覆盖**，勿与失败混淆（见 `04` §0.15）。 |

