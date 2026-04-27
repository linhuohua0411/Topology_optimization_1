# 实验执行清单（文字版 · 对齐 TIFS）

> **用途**：按平台说明「采什么 → 做什么 → 预期得到什么 → TIFS 审稿对应什么」，并拆成 **可逐项勾选** 的执行条。  
> **详细矩阵与字段表**：仍以 `protocol/03_experiment_matrix.md` 为权威；本文件是其 **执行向文字版**，不另改口径。  
> **Eth-Docker 全库统一口径**：**观测链（§二 2.1–2.3）与图优化 / 方法对比（2.4，`run_eth_docker_experiments.py`）均为必做**；与 `protocol/03` §0.1、§6.4 及 `docs/论文初稿/claim_traceability.md` 之 **C007** 一致。

### 范围说明（当前阶段：只谈实验，不谈结果与证据）

- **纳入范围**：采什么字段、阶段与采样率、`n_runs`、落盘文件结构、统计**方案**应包含哪些列、预注册 `comparison_id`、协议版本与 manifest——即 **实验怎么做才算「按协议跑完」**。  
- **暂不纳入**：指标数值好坏、是否显著、能否画进某张表、**`claim_traceability.md` 是否 done**、证据是否足以支撑正文某句——属 **撰稿/审稿轮** 再与结果绑定。  
- **与 TIFS 的关系**：满足下面条目 ≈ 实验设计/执行在 **可复现性与统计规范** 上对齐 TIFS 常见审稿标准；**不预设**跑出来的效应方向或显著性。

---

## 导读：平台 × 实验 × 数据（扫读表）

> **权威宽表与字段细则**：始终以 **`03_experiment_matrix.md`** 为准；其中 **`§0`「平台–实验–数据一览」** 把「要做的事 / 要采的数据 / 对应平台」拆成最易扫读的三列表，**建议先读 §0 再读本清单各节**。

| 你关心的 | 去哪里看 |
|:---|:---|
| 我是哪个平台、raw 落盘路径、仓库里用哪个脚本 | `03` **§0.1** |
| 每个 `experiment_id` 要**做什么实验**、**必须采哪些数据**、**论文里对接哪张表** | `03` **§0.2** |
| 每行 **闭环与主文约束**（熔断句、互证口径、MTH/BTC 门槛） | `03` **§1 宽表**「闭环与主文约束」列 |
| 勾选怎么打、Eth/BTC 分节执行步骤 | **本文件 §0–§七** |
| 采样点数、周期、拓扑张数硬门槛 | `03` **§2.4** |
| 跨平台方法对比（MTH-CMP）何时能写进主文 | **本文件 §四** + `03` **§1** 中 MTH-CMP 行 |

---

## 0. 全平台通用：TIFS 向实验执行硬门槛（建议最先逐项落实）

完成下列条目后，在**实验定义**上可认为该 `experiment_id` 已按矩阵完成「可复现执行」（与是否产生理想统计结果、是否已写论文无关）。

- [ ] **0.1 时序与阶段**：每个 `run_id` 覆盖 `pre_attack → attack_ramp → under_attack → recovery → post_recovery`；每阶段采样点数不少于矩阵 **3/5/3/5/3**（共 19 点/run）。
- [ ] **0.2 采样周期锁定**：Eth-Cloud / Eth-Docker **30 s**；BTC-Docker **10 s**（或矩阵允许的分阶段 30/10/…）；同一 `experiment_id` 运行中 **不得改周期**。
- [ ] **0.3 拓扑证据（实验完备性）**：每 run 须能重建 \(G_t\)，并落盘 **`topology_edges_timeseries.csv`**；若仅有标量无边表，在矩阵语义下 **该拓扑实验未按协议完成**（与后续是否写进主文无关）。
- [ ] **0.4 攻击与网络状态**：凡攻击类实验，落盘 **`network_condition.csv`**（与 `phase`、`attack_params`、注入是否生效可对齐）。
- [ ] **0.5 加工与统计**：每 run 有 **`topology_metrics_timeseries.csv`**（processed）；每 `experiment_id` 有 **`results/statistics/<experiment_id>/stats_summary.csv`** + **`run_manifest.json`**。
- [ ] **0.6 样本量**：默认 **`n_runs = 20`**，故每实验至少 **19×20 = 380** 条时间样本；拓扑快照数按矩阵 **2.4.1-bis**（如 ED：19×20=380 张 EL 层）。
- [ ] **0.7 统计字段**：`stats_summary` 至少含 `mean, std, ci95_low, ci95_high, test_name, p_value, effect_size, n, comparison_id, stat_key`；建议含 **`p_value_holm`**（与 `experiments/tifs_stats.py` 一致）。
- [ ] **0.8 预注册对比（方案层）**：统计脚本只针对 **`03_experiment_matrix.md` §4** 已登记的 `comparison_id` 产出主对比行；探索性对比若做，须在输出中 **单独命名/分文件**，与预注册族区分（避免事后挑检验）。
- [ ] **0.9（撰稿阶段；纯实验阶段可跳过）**：若已进入写结论/投稿，再在 **`docs/论文初稿/claim_traceability.md`** 为每条量化结论登记 `claim_id + comparison_id + stat_key + evidence_paths`。
- [ ] **0.10 协议版本**：`run_manifest.json` 写入 **`PROTOCOL_VERSION`**（见 `experiments/experiment_protocol.py`；当前冻结 **`tifs-freeze-v2`**）。**`budget_log.jsonl`** 每行建议含同字段（采集脚本已写入 `protocol_version`）。
- [ ] **0.11 预注册主终点（ED 攻击族）**：对 §4 中 **ED Holm 族**（R / LCC / path 三行）在跑统计前 **书面冻结 1 个 primary**（写入 `run_manifest` 自定义字段或 `stats_summary` 侧元数据 README）；摘要/主文 **仅 1 个 primary**，其余一律 secondary。
- [ ] **0.12 探索性输出隔离**：凡 **非** `03_experiment_matrix.md` §4 已登记之 `comparison_id`，统计产物须 **`exploratory_` 前缀或单独子目录**，禁止与主文 `stats_summary` 同文件混排或事后挑行入表。
- [ ] **0.13 小效应与功效叙事**：若主文/摘要声称「仍能检测小效应」等，须在 **`run_manifest` 或同版本协议增补段** 引用 **pilot 方差**或**事后功效**（与 `03` §0.0 `n_runs=20` 规则一致）。
- [ ] **0.14 `CMP-ED-EC-DIRECTION` 启用条件**：仅当 **EC-MAIN-BASE 与 ED-MAIN-BASE**（及可比 `attack_tier`）均满足 §2.2 Done 后执行；**EC 数据未齐前**正文禁写「云与 Docker 数值/趋势一致」类句，最多预备「待互证」表述。
- [ ] **0.15 缺失 run 与 skip 语义**：`invalid` run **不**换种子重算（§2.0）；补采或整组剔除规则写入 **`missing_run_policy`**。采集因已有 `run_manifest` **skip** 时，在 **`eth_docker_collection_summary.json` / manifest** 注明 **skip=不覆盖**，与失败 run 区分。

---

## 一、Eth-Cloud（EC-MAIN-*）

**平台含义**：云上/远程可控以太坊拓扑（执行层 + 共识层为主）。当前仓库已切换为**本地 Eth-Docker 主线**，远端 EC 采集脚本已移除（不再维护 `collect_eth_cloud_scenarios.py` / `collect_eth_full_dataset.py` / `collect_eth_topology_remote.py` / `collect_both_networks.py`）。

**要采集的数据（共性）**  
- 时序拓扑边（可重建 \(G_t\)），建议 **EL + CL 双层**（主文互证更强）。  
- 每样本：`timestamp_utc, platform, experiment_id, run_id, phase, attack_label, attack_params, protocol_variant, budget_variant, layer`。  
- 鲁棒性与图统计：`R, Rs, Rc, Rr, lcc_ratio, avg_path_len`；`peer_count_el`（必）、`peer_count_cl`（强烈建议）。  
- 链侧 KPI（若主文写链行为）：`chain_kpi` 类字段按矩阵 1.1。  
- **`budget_log`**：公平预算 / 原始预算对齐证据。

**要做的实验（共性）**  
- 在统一协议 `unified_full_protocol` 下，对每个 `experiment_id` 完成 **20 次独立 run**（种子与 manifest 可追溯）。  
- **BASE**：无攻击，全阶段时序采集 + 优化/对比（若主文含方法对比）。  
- **RAND / TGT / ADP**：在攻击强度 **low / mid / high** 至少各有一组可分析结果（矩阵 2.2）；攻击参数 **执行前锁定**（2.3）。

**预期产生的效果（审稿可验收）**  
- 可画 **时序拓扑 + 阶段切片** 图；可报 **跨 run 的 CI / p / 效应量**，且 **Holm/FDR** 与攻击族一致。  
- EC 作为主文 **「规模 + 攻击多样性」** 锚点，支撑「方法在云环境有效」类主张。

**TIFS 对应**  
- 满足 **§1.2 时序拓扑刚性**、**§2.4.2 入表硬门槛**、**§2.2 Done** 中 EC 各行。

### 1.1 EC-MAIN-BASE

| 维度 | 内容 |
|------|------|
| **采集** | 无攻击；双层拓扑时序；`R/Rs/Rc/Rr`、LCC、路径、peer；`budget_log`。 |
| **实验** | 基线 +（若论文含）本文方法与基线方法在 **fair + raw** 下对比；`n_runs=20`。 |
| **预期效果** | 主表 7-1 类：本文在 **R 与路径/LCC** 等指标上相对强基线有 **可复现优势**；`stats_summary` 含 **comparison_id**（如 CMP-EC-OUR-RESI）。 |
| **TIFS** | 完整时序 + 统计追溯；无拓扑边表则该条目不写主文拓扑主张。 |

**执行项**

- [ ] 1.1.1 配置远程/批量采集，保证 **30 s** 间隔与 **19 点/run**。  
- [ ] 1.1.2 每 run 输出 **`topology_edges_timeseries.csv`**（EL+CL 各一份或合并列明 layer）。  
- [ ] 1.1.3 聚合 **`topology_metrics_timeseries.csv`** 与 **`stats_summary.csv`**。  
- [ ] 1.1.4 在 `claim_traceability.md` 登记 **C001** 类证据路径并标 `done`（仅当数据齐）。

### 1.2 EC-MAIN-RAND / EC-MAIN-TGT / EC-MAIN-ADP

| 维度 | 内容 |
|------|------|
| **采集** | 同上 + **`network_condition.csv`**；`attack_params` 含强度与随机种子。 |
| **实验** | 各攻击类型下 **low/mid/high** 至少一组有效结果；各 **20 runs**（若主文写跨强度，需每档满样本，见矩阵 2.2/6.3）。 |
| **预期效果** | 攻击章节表：攻击前后 **LCC/路径/Rc** 等变化 **可检验**；多重比较已校正。 |
| **TIFS** | 缺强度档位 → **不写攻击主结论**；缺 `network_condition` → 攻击证据弱，易被拒。 |

**执行项（每种攻击各一套）**

- [ ] 1.2.1 预注册 **random_remove / targeted_remove / adaptive_remove** 参数模板（2.3）。  
- [ ] 1.2.2 完成采集 + 加工 + **`stats_summary`**（分层 + Holm/FDR + effect_size）。  
- [ ] 1.2.3 异常窗口（掉线、采集中断）在 manifest 或附录 **文字说明**。

---

## 二、Eth-Docker（ED-MAIN-*）

**平台含义**：真实以太坊客户端容器 + 可控故障/广域劣化（`eth_simulation` 等）；**不等价**于「拜占庭共识对抗」，正文应定位为 **链路故障与网络劣化韧性**。

**要采集的数据**  
- 每样本 JSON + **`topology_edges_timeseries.csv`**；**`network_condition.csv`**（LINK/NETEM 必需）。  
- **`budget_log.jsonl`**（观测链：`budget_cost=0` + `notes`，与优化管线的 fair/raw **分立叙述**）。  
- `peer_count_el`（必）；`peer_count_cl` 可选。  
- 字段：`protocol_variant, budget_variant, layer, attack_params`（含 **`strength`** 若分档）；**`run_manifest.json`** 另含 **`attack_tier_applied`**、**`target_selection_rule`**（与矩阵 §2.3 目标选取规则对齐）；BASE 的 `attack_params` 含 **`injection_semantics`**（无混沌注入语义）。

**要做的实验**  
- **ED-MAIN-BASE**：无注入，全阶段时序。  
- **ED-MAIN-LINK**：节点 down/up 类故障；建议 **`--attack-tier` low/mid/high 各跑满 20 runs**（或主文只报 mid，low/high 附录仍须满样本）。  
- **ED-MAIN-NETEM**：WAN tc/netem；同上三档策略与矩阵 2.3 对齐。  
- **（必做）图优化 / 方法对比**：`run_eth_docker_experiments.py` **默认**读 **`results/raw/eth_docker/<experiment>/run-*/sample_*.json`**（`--raw-root` / `--sample-pick`）；**`--from-snapshots`** 时读 **`results/derived/eth_snapshots/snapshot_*.json`**（仅迁移/回放旧数据时用）。产出 **`results_rows_graph_optimizer.json`**（每行含 **`protocol_version`**、**`gradient_mode`**）、**`stats_summary_graph_optimizer.csv`**，避免覆盖观测 **`results_rows.json`**。**M-OUR** 默认 **`--gradient-mode full`**（与 `DEFAULT_PARAMS` 一致）；全文梯度消融或附录再显式传 **`R_s_only`** / **`R_s_R_r`**。

**预期产生的效果**  
- **采集链**：阶段对比（under vs pre）在 **R / LCC / path** 上可报 **p、p_holm、效应量**（`aggregate_eth_docker_collected_stats.py`）；差分检验与矩阵 **§6.1** 一致：**Shapiro-Wilk（n≥3）→ 单样本 t vs 0 或 Wilcoxon signed-rank**，`stats_summary.test_name` / `effect_size_name` 与 `experiments/tifs_stats.py` 输出一致。CI 仍用 **t 分布 95%**（描述性）；需 **`n_runs` 满盘** 时可用 **`--strict-n-runs`** 令聚合非零退出。  
- **（必做）优化链**：在自拓扑快照上跑 **M-OUR vs 基线**（与实链采集 **并列叙述**，非替代关系；缺此步则 ED **方法主张**证据不齐）。  
- **与 EC 互证**：仅当 EC 数据齐后，做 **CMP-ED-EC-DIRECTION** 类方向一致性（`claim_traceability` **C008**）。

**TIFS 对应**  
- ED Done 判据 **§2.2**；路径 **`results/raw/eth_docker`** 等价矩阵 `<platform>=eth_docker`（§6.3/6.4）。

**执行项**

- [ ] 2.1 运行采集（默认 `n_runs=20`、**`--interval 30`**；按需 **`--attack-tier`**）：**三场景拆分**（推荐、减轻单次写盘峰值）→ `experiments/eth_docker_collect/ed_main_base/collect.py`、`…/ed_main_link/collect.py`、`…/ed_main_netem/collect.py`（各写 `results/raw/eth_docker_collection_summary_<EXP>.json`）；或一次性 **`collect_eth_docker_scenarios.py`**（汇总 `eth_docker_collection_summary.json`）。补采 mid 示例：**`bash experiments/pipeline/resume_ed_docker_collection_mid.sh`**（先 prune，再 LINK→NETEM）。**仿真先停再起再补采**（默认 12as 拓扑目录）：**`bash experiments/pipeline/stop_sim_restart_and_resume_ed_collect.sh`**；2as 或其它路径设 **`ED_SIM_ROOT=.../2as_6nodes`**；停仿真后需多腾盘可加 **`PRUNE_DOCKER=1`**。某一 run 失败时默认 **记录错误并继续**；需严格停则 **`--no-continue-on-error`**。**采满后再**跑 2.2→2.3，并**必须**完成 **2.4 图优化**。  
- [ ] 2.2 运行 **`compute_eth_docker_metrics_fast.py --input-root results/raw/eth_docker`**，生成 **processed** 与 **`topology_metrics_timeseries.csv`**。  
- [ ] 2.3 运行 **`aggregate_eth_docker_collected_stats.py`**，生成 **`results/statistics/ED-MAIN-*/stats_summary.csv`**（可选 **`--strict-n-runs`** 与 **`--n-runs`** 对齐矩阵默认 20）。  
- [ ] 2.4 **（必做）** 图优化 / 方法对比：观测链 2.1–2.3 完成后 **`python experiments/run_eth_docker_experiments.py`**（默认 **`--raw-root results/raw/eth_docker`**、**`--gradient-mode full`**）；仅在使用旧平面快照时加 **`--from-snapshots --snapshot-dir ...`**；并行可加 **`--parallel-runs N`**。
- [ ] 2.5（撰稿阶段）在 **`claim_traceability.md`** 补 **`evidence_paths`**；**C007**（图优化证据）在 **完成 2.4** 后登记并标 `done`。

---

## 三、BTC-Docker（BTC-MAIN-*）

**平台含义**：比特币测试/私有部署；矩阵要求 **P2P 拓扑 + 链 KPI + 协变量**。

**要采集的数据**  
- 时序拓扑边、**`block_height`、`fork_events`、`peer_count_btc`**。  
- **`reachable_ratio`（主文必需）**；**`network_condition.csv`**（攻击场景）。  
- `R, lcc_ratio, avg_path_len, components`；`budget_log`。

**要做的实验**  
- **BASE / ECL / PART / NETEM / BGP**：均在 **unified_full_protocol** 下 **20 runs**；阶段与采样 **10 s** 或矩阵推荐分阶段。  
- **BGP**：矩阵标为 **条件入主文**，默认可先 **附录 only**。

**预期产生的效果**  
- 主文可写：**分叉/出块进度与拓扑扰动的时间对齐**；`reachable_ratio` 作为协变量在统计或正文中 **明确控制/讨论**。  
- 缺 **`reachable_ratio`** 的 run → **不得纳入主文统计**（矩阵 2.2）。

**TIFS 对应**  
- BTC 主场景 Done **§2.2**；拓扑快照数 **380+**（2.4.1-bis）。

**执行项（当前仓库若未接线，则标为阻塞项）**

- [ ] 3.1 实现或接入 **统一 BTC 采集 runner**（与 EC/ED 同字段语义）。  
- [ ] 3.2 验证 **`reachable_ratio`** 每 run 可采。  
- [ ] 3.3 按 **0.x** 全门槛生成 raw / processed / statistics。  
- [ ] 3.4 在 `claim_traceability.md` 为 BTC 相关 claim（如 **C002**）补证据；未齐前 **主文不写 BTC 定量对比句**。

---

## 四、跨平台方法对比（MTH-CMP-FAIR / MTH-CMP-RAW）

**要采集/对齐的数据**  
- 三平台（EC + BTC + ED）同一 **`method_id` 列表**（§2）：M-OUR、M-RESI、M-STAT、M-ASIM（M-FPS 可选）。  
- 每平台：`metric`、**`fair_or_raw_value`**、**`budget_cost`**、**`random_seed`**（同种子可比）。

**要做的实验**  
- **FAIR**：时间/边预算对齐下的 **排名 + 配对检验 + Holm + 效应量**。  
- **RAW**：原始预算下 **敏感性 / 排名变化**。

**预期产生的效果**  
- 表 7-4 / 7-5：**跨环境方法排序**有统计支持；审稿人可检查 **公平性是否一致**。  
- **任一平台或基线缺失** → 矩阵规定：**不可写主文跨平台对比结论**，仅附录或改写贡献边界。

**TIFS 对应**  
- **§2.2 MTH-CMP** Done；**§4** 中 CMP-BUDGET-FAIR-RAW 等。

**执行项**

- [ ] 4.1 EC、ED（采集或快照链）、BTC **三套结果同口径字段表** 对齐。  
- [ ] 4.2 编写 **聚合脚本**（仓库当前为待补），输出统一 **`stats_summary`** 与 `comparison_id`。  
- [ ] 4.3 在正文明确：**主文跨平台句仅在三平台齐后启用**。

---

## 五、消融与其他（Eth-Cloud 为主 + 条件含 BTC）

### 5.1 ABL-MLE-INJ（Eth-Cloud，`n_runs=30`）

- **采集**：`inject_flag`、优化前后 **`delta_R`** 等。  
- **实验**：inject vs no-inject **成对**设计。  
- **预期**：表 9-2：**注入 ≠ 优化收益** 的统计证据。  
- **TIFS**：`stats_summary` 含 **ci95 + p + effect**；仅 **§09 消融**。  
- [ ] 5.1.1–5.1.3 设计脚本 → 跑满 30 → 统计 → 登记 claim。

### 5.2 ABL-COMP（Eth-Cloud + BTC，matched）

- **采集**：`variant`、主指标、`budget_variant`。  
- **实验**：full vs 关键消融变体。  
- **预期**：表 9-1：**组件贡献** 有 **delta_vs_full + p + effect**。  
- **TIFS**：多项对比用 **FDR**；缺变体不得写「组件显著贡献」。  
- [ ] 5.2.1–5.2.3 同上勾选链。

### 5.3 ABL-WEIGHT（Eth-Cloud）

- **采集**：权重扰动、`metric_value`。  
- **实验**：参数在 **预注册区间** 内扫描。  
- **预期**：参数敏感性图/表 + **显著性**。  
- [ ] 5.3.1–5.3.3 区间预注册 → 跑实验 → 统计。

### 5.4 FAB-EXT-NETEM（Fabric-Docker，附录）

- **采集**：`network_condition`、`prometheus_up`、`chain_kpi`（代理）。  
- **实验**：**10 runs**，exploratory。  
- **预期**：**趋势描述**，**主文不写强定量推广**（矩阵 1.1）。  
- [ ] 5.4.1–5.4.2 附录图表 + 局限段。

### 5.5 POL-EXT-*（Pol-Docker，附录；对齐 `03` v3）

- [ ] 5.5.1 仅附录：`POL-EXT-BASE`（无攻击）与可选 `POL-EXT-NETEM`；**20 s** 周期；阶段 **3/5/3/5/3**；`n_runs=10`；落盘 `results/raw/pol_docker/`。  
- [ ] 5.5.2 **不入主文**统计与摘要；与 PoS 结论之间只写「异构协议外推局限」。

---

## 六、建议执行顺序（一项一项做）

1. 先完成 **§0** 全平台勾选框架（目录结构、manifest、协议版本）。  
2. 并行或优先 **二、Eth-Docker**（仓库已布线最多，最快形成闭环图与统计）。  
3. **一、Eth-Cloud**（主文规模与攻击多样性锚点）。  
4. **三、BTC**（接线后再动主文 BTC 句）。  
5. **四、跨平台 MTH-CMP**（三平台数据齐后再写）。  
6. **五、消融与附录**（与主文结论隔离，先保证 **§5 规则**）。

---

## 七、本清单与矩阵的同步方式

- 新增或删减 `experiment_id` 时：**先改 `03_experiment_matrix.md`**，再在本文件对应节 **增删小节与勾选条**。  
- 审稿返修若补充检验（如 Wilcoxon/bootstrap）：在 **§6** 与 **`tifs_stats.py` 注释** 同步一行，避免「论文写 A、脚本做 B」。
