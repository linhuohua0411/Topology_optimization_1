# Experiment Matrix（论文全量实验总表 v3 · TIFS 强化）

> 面向 TIFS 审稿的一页式执行表：不仅列实验，还给出“数据可获取性、主文纳入资格、证据追溯状态、下一步动作”。**v3** 在 v2 基础上收口 **主文最小充分证据集（MVS）**、**主/次统计终点**、**方法对比封闭规格**、**物理实验床 ↔ 矩阵**映射及 **Pol 附录实验**定义（仍不含任何主机账号口令；凭据仅放脱敏配置，不入库）。  
> **快速理解「平台–实验–数据」**：优先读 **§0.0（MVS）** 与 **§0.1**；需要逐条勾选执行时再打开 **`04_experiment_execution_checklist.md`**（其开头「导读表」指向本节）。

## 0) 平台–实验–数据 一览（推荐先读本节）

> **读法**：先读 **§0.0** 明确「主文最少要做哪几条实验」；再对照 **§0.1** 弄清「平台是谁、数据落哪」；用 **§0.2** 逐行核对「要做什么实验、必须采什么、最后产出什么」；需要审稿级细字段时再下钻 **§1**（含 **§1 宽表「闭环与主文约束」列**：每行可写/不可写边界）与 **§2.4**。若 **`04_experiment_execution_checklist.md`** 与本文件冲突，以 **本文件 §0 + §2.4 + §6** 为准，并 **升高 `PROTOCOL_VERSION`** 在 `run_manifest` 中留痕。

### 0.0 主文最小充分证据集（MVS，TIFS 收口）

> 目的：回答审稿人「最少哪些实验支撑主贡献」。**主文强结论句**仅允许绑定下表行；其余 `experiment_id` 为扩展、消融或附录。若某行数据未齐，对应结论 **整句删除或降级为附录/观察性表述**，不得换检验或换对比事后补叙事。

| 主文主张（论文中可写成的句子类型） | 必须完成的 `experiment_id`（最小集合） | 必须预注册的 `comparison_id`（见 §4） | 主终点 `metric`（§4 同步） | 缺失时的处理 |
|:---|:---|:---|:---|:---|
| 云上 PoS 拓扑鲁棒/重连方法优于强基线 | `EC-MAIN-BASE` +（若写攻击）`EC-MAIN-RAND` 或 `TGT` 或 `ADP` 之一族 | `CMP-EC-OUR-RESI`、`CMP-EC-OUR-STAT`（+ 可选 `M-ASIM` 行，Holm 族内） | **R**（primary）；LCC、`avg_path_len` 为 secondary | 缺基线或缺 **EL+CL 时序边表** → 不写「优于 SOTA」类句 |
| 受控栈上链路与广域劣化下仍有效（可用性/韧性，非拜占庭主结论） | `ED-MAIN-BASE`、`ED-MAIN-LINK`、`ED-MAIN-NETEM`（至少各完成 **mid** 档满样本；见 §2.3） | `CMP-ED-MAIN-R-UNDER-minus-PRE` / `CMP-ED-MAIN-LCC-UNDER-minus-PRE` / `CMP-ED-MAIN-PATH-UNDER-minus-PRE`（**Holm 族一次预注册**：三指标最多报 **1 个 primary**，其余 secondary） | **R**（默认 primary）；另两行为 secondary | 缺 `network_condition` 与 phase 对齐 → 不写攻击主结论 |
| 云实验与 Docker 受控实验方向一致（互证，非数值复制） | 上两行 **均** Done | `CMP-ED-EC-DIRECTION` | 预注册标量（默认：**run 聚合后的 ΔR = mean(R_under−R_pre)** 的符号） | EC 或 ED 缺一 → **禁止**写「跨环境一致」类主文句 |
| 公平预算 vs 原始预算口径不翻转主结论 | 绑定主对比的同一批 runs | `CMP-BUDGET-FAIR-RAW` | 与主文主终点一致 | 仅一侧齐 → 只报告可用侧，摘要不写「对任意预算均成立」 |
| （可选）第二条链上 P2P 证据 | `BTC-MAIN-BASE` + 至少一种攻击线（`ECL`/`PART`/`NETEM` 之一） | `CMP-BTC-OUR-RESI`（若主文写 BTC 方法对比） | **lcc_ratio**（primary）；path secondary | 缺 **`reachable_ratio`** 或拓扑边表 → **整表不入主文**（矩阵硬门槛） |
| （可选）跨平台方法排序 | `MTH-CMP-FAIR`、`MTH-CMP-RAW` | 聚合层生成 `CMP-MTH-*` 行（脚本落地后写入 §4） | 与 EC 主终点对齐的 `metric` | **EC+ED+BTC 任一平台缺方法行** → 不写跨平台排名句 |

**n_runs 收口规则（TIFS）**：主文 MVS 内方法对比与 EC/ED 主场景默认 **`n_runs=20`**；若主文仅报告效应量与 CI 而声称「小效应也可检测」，须在 `run_manifest` 中引用 **pilot 方差**或 **事后功效说明**（同一 `PROTOCOL_VERSION` 增补段落）。`ABL-MLE-INJ` 维持 **`n_runs=30`** 成对设计。

### 0.1 平台代号、含义与落盘根路径

| 代号 | 平台 | 物理/逻辑实验床（与本文矩阵对齐的一句话） | `results/raw/...` 下平台目录名 | 本仓库已接线入口（采集/加工） |
|:---:|:---|:---|:---|:---|
| **EC** | Eth-Cloud | 多区域云上 **PoS（EL+CL）**；受控对等（如手动 addPeer）；**广域延迟异质性**主证据 | `eth_cloud` | 当前仓库未维护 EC 远端采集入口（已下线，主线改为 ED 本地） |
| **ED** | Eth-Docker | 单宿主或多容器 **多 AS + BIRD（BGP/OSPF）+ IXP mesh**；**链路 down + tc netem** 双层注入；**30 s** 拓扑采样 | `eth_docker` | `collect_eth_docker_scenarios.py` **或** `eth_docker_collect/ed_main_{base,link,netem}/collect.py` → `compute_eth_docker_metrics_fast.py` → `aggregate_eth_docker_collected_stats.py` → **`run_eth_docker_experiments.py`（必做：方法对比）** |
| **BTC** | BTC-Docker | 多 AS **Bitcoin Core（如 regtest）**；日蚀/分区/BGP/传播劣化等；**10 s** 级拓扑轮询；**须单写 `reachable_ratio` 产出** | `btc_docker`（约定） | **外部位虚拟网可部署**；本仓库须补齐 **Neo4j→`results/raw/btc_docker/...` 契约导出 + `run_manifest`**（清单 §三） |
| **CMP** | — | **非单独采集**：在 EC+ED(+BTC) 各平台 **`stats_summary` 同构行**齐后做的**方法对比聚合** | 依赖各平台 `stats_summary` + `budget_log` | 清单 §四：聚合脚本 **待补**；规格见 **§2.0** |
| **ABL** | EC 为主（部分含 BTC） | 消融：MLE 注入、组件、权重等 | 依子实验 | 清单 §五 |
| **FAB** | Fabric-Docker | 联盟链 **Raft**；Prometheus/自研监控；**附录外推** | `fabric_docker`（约定） | 探索性，**主文不强定量** |
| **POL** | Pol-Docker | Substrate **BABE/GRANDPA**；多 AS + BGP + **tc**；**20 s** `system_peers` 拓扑 | `pol_docker`（约定） | **主文默认不入**；若跑通则仅 **`POL-EXT-*` 附录**（见 §0.2 新增行） |

### 0.2 主文/主线实验：要做什么 ↔ 必须采什么 ↔ 产出什么

下列「必须采集」均默认满足 **§0 通用门槛**：`n_runs=20`（`ABL-MLE-INJ` 除外）、阶段 **3/5/3/5/3**（共 19 点/run）、每 run 可重建 \(G_t\) 的 **`topology_edges_timeseries.csv`**、每 run **`run_manifest.json`**（含 `PROTOCOL_VERSION`、**`attack_tier`**、软件/拓扑版本摘要）、**`network_condition.csv` 与 `phase` 对齐**（无注入实验须写 **baseline 行**：`inject_active=false` 或等效字段，不得缺文件）、全实验 **`budget_log.jsonl`**（公平/原始预算审计；观测链 `budget_cost=0` 规则见 §6.3）。鲁棒与图指标由 **processed** 链产出（如 `topology_metrics_timeseries.csv`）并汇总 **`results/statistics/<experiment_id>/stats_summary.csv`**。

**攻击强度与 `experiment_id`（TIFS 冻结）**：同一攻击族若 **low/mid/high** 三档各满 **`n_runs=20`**，推荐目录命名为 **`<experiment_id>-<tier>`**（如 `ED-MAIN-LINK-mid`），或在 `run_manifest.json` 内 **`attack_tier`** 字段区分；统计汇总时 **分 tier 分层**，多重比较族在 §4 备注栏声明。**主文只报 mid 时**，low/high 仍须满样本进附录，否则不得写「跨强度单调」类句。

| 平台 | `experiment_id` | **要做的实验**（动作级） | **必须采集 / 对齐的核心数据** | **主要产出与论文锚点** |
|:---:|:---|:---|:---|:---|
| EC | `EC-MAIN-BASE` | 无攻击；全阶段时序拓扑；**MVS**：本文方法 vs **M-RESI/M-STAT**（+可选 M-ASIM）**fair+raw** 成对可比 | **EL+CL 双层**时序边表（主文拓扑结论门槛）、`R/Rs/Rc/Rr`、LCC、路径、peer、`chain_kpi`、`budget_log` | 表 7-1；`stats_summary` + §4 预注册行；**主终点 R** |
| EC | `EC-MAIN-RAND` | **随机移除**韧性；三档参数 **执行前锁定**（§2.3） | 上列 + **`network_condition`** + `attack_params`（比例/种子） | 表 7-1/7-2；**Holm 族**；secondary：LCC、path |
| EC | `EC-MAIN-TGT` | **目标移除（hub/高度）**；三档同上 | 同上；**中心性定义**写入 `attack_params` 预注册 | 同上 |
| EC | `EC-MAIN-ADP` | **自适应序列移除**；三档同上 | 同上；**重算窗口长度**写入 `attack_params` | 表 8；**EC 为策略性攻击主证据** |
| ED | `ED-MAIN-BASE` | 无注入；**链路/路由拓扑正常**基线；与 EC **方向互证** | EL 时序拓扑（CL 可选）、`R/LCC/path`、`peer_count_el`、`budget_log` | 表 7-3；**CMP-ED-EC-DIRECTION** |
| ED | `ED-MAIN-LINK` | **`ip link`/容器 down** 类断连 + 恢复；**每 tier 满 20 runs** | 上列 + **`network_condition`**（链路状态时间线） | 攻击章节；**定位为可用性/韧性，非拜占庭** |
| ED | `ED-MAIN-NETEM` | **`tc netem`** 延迟/丢包/抖动/带宽；**每 tier 满 20 runs** | 上列 + **`network_condition`**（tc 参数 JSON） | 同上 |
| BTC | `BTC-MAIN-BASE` | 无攻击；拓扑 + 出块/分叉 | P2P 边表、`block_height`、`fork_events`、`peer_count_btc`、**`reachable_ratio`（定义见 §3 说明）**、`budget_log` | 表 7-2 |
| BTC | `BTC-MAIN-ECL` / `PART` / `NETEM` | 日蚀 / 分区 / **tc** 传播劣化（与物理床脚本名对齐即可） | 上列 + **`network_condition`** + 攻击参数（隔离时长、分区比等） | 表 7-2/8 |
| BTC | `BTC-MAIN-BGP` | **BIRD 路由劫持类** | 同上 + 可达/路由相关 | **默认附录**；入主文须单独论证威胁模型 |
| — | `MTH-CMP-FAIR` | **三平台**在 **公平预算** 下同一 `method_id` 列表（§2.0） | 各平台 **`method_id, metric, fair_or_raw_value, budget_cost, random_seed`** 对齐汇总 | 表 7-4；**缺一平台不写跨平台排名** |
| — | `MTH-CMP-RAW` | 同上 **raw** 口径 | 同上 | 表 7-5 |
| EC (+BTC) | `ABL-MLE-INJ` | inject vs no-inject，**`n_runs=30` 成对** | `inject_flag`、`delta_R` 等 | 表 9-2；**CMP-ABL-MLE** |
| EC (+BTC) | `ABL-COMP` | full vs **预注册**消融变体列表 | `variant`、`metric_value`、`budget_variant` | 表 9-1；**FDR 族** |
| EC | `ABL-WEIGHT` | 权重 **预注册区间** 扫描 | `param_name`、`perturbation`、`metric_value` | 敏感性图/表 |
| FAB | `FAB-EXT-NETEM` | 附录外推，`n_runs=10`；**LAN/MAN/REGION/GLOBAL profile** | `network_condition`、`prometheus_up`、`chain_kpi` 代理 | **仅附录趋势** |
| POL | `POL-EXT-BASE` | **附录**：无攻击全阶段；**20 s** 采样、`3/5/3/5/3` 与 Eth 同阶段语义 | `system_peers` 解析边、`network_condition`（若有 tc）、`budget_log` | **仅附录**；不写与 PoS 主结论直接推广句 |
| POL | `POL-EXT-NETEM` | **附录**：tc 劣化（参数锁定） | 上列 + `network_condition` | 附录图；**exploratory** |

**说明（EC 采集脚本与矩阵 `attack_label` 用语）**：矩阵正文常用 `targeted_remove` / `adaptive_remove`；当前仓库不再维护 EC 远端采集脚本，若后续恢复 EC 管线，请在新入口中保持与 **EC-MAIN-TGT / EC-MAIN-ADP** 的语义映射并登记 `experiment_id` 对应关系。

**说明（BTC `reachable_ratio`）**：须在采集规范中 **冻结定义**（例如：监控侧对已知节点集合成功 RPC/心跳的比例，或路由可达比例），并 **每 run 每时刻**与 `getpeerinfo` 同学周期写入；定义变更须 **`PROTOCOL_VERSION` 升级**。

### 0.3 与 §1 宽表的关系

- **§0.0**：面向 TIFS 审稿——「主文最少实验 + 主终点 + 缺失熔断」。  
- **§0.2**：面向执行与写方法章——「谁、干什么、采什么、出啥表」。  
- **§1 大表**：面向项目管理——增加 **章节、主文资格、证据状态、闭环与主文约束（TIFS）、下一步动作** 等列。  
- 两处 **experiment_id 与 n_runs 口径一致**；若冲突以 **§0.0 + §1 + §2.4** 为最终执行口径。

---

## 1) 全量实验矩阵（执行与审稿双视角）

> **§1 宽表列说明**：**「闭环与主文约束（TIFS）」**列汇总每行 **证据链 Done 判据**与**正文可写边界**（熔断句、互证口径、聚合/MTH/BTC 门槛）；与 **`protocol/04_experiment_execution_checklist.md` §0.11–0.15** 及 **`TIFS_REFERENCE.md` §3（G1–G6）** 交叉索引。详列仍以本表为准。

| experiment_id | 章节 | 平台 | attack_label | protocol_variant | budget_variant | n_runs | 关键指标 | 主要数据表 | 数据可获取性 | 主文纳入资格 | 证据追溯状态 | 闭环与主文约束（TIFS） | 下一步动作 |
|---|---|---|---|---|---|---:|---|---|---|---|---|---|---|
| EC-MAIN-BASE | 07 | Eth-Cloud | none | unified_full_protocol | fair+raw | 20 | R/Rs/Rc/Rr,LCC,path | topology_snapshot,robustness_metrics,chain_kpi,budget_log | 高 | 是 | pending | 无 EL+CL 时序 `topology_edges_timeseries` 则熔断主文拓扑类句；fair/raw **分报**；「优于强基线」仅绑 §4 已登记 `CMP-EC-*` + 齐套 `stats_summary` | 跑基线并回填表7-1 |
| EC-MAIN-RAND | 07/08 | Eth-Cloud | random_remove | unified_full_protocol | fair+raw | 20 | LCC,path,peer_stability | topology_snapshot,network_condition,robustness_metrics | 高 | 是 | pending | 须 `network_condition`+**执行前锁定**档位参数；缺档/缺对齐 → 不写攻击主结论与跨强度单调；Holm 族内探索性输出**不得**共用主文 `comparison_id` | 回填表7-1/7-2 |
| EC-MAIN-TGT | 07/08 | Eth-Cloud | targeted_remove | unified_full_protocol | fair+raw | 20 | LCC,path,Rc | topology_snapshot,network_condition,robustness_metrics | 高 | 是 | pending | 同 RAND；**中心性定义**写入 `attack_params` 预注册 | 回填表7-1/7-2 |
| EC-MAIN-ADP | 08 | Eth-Cloud | adaptive_remove | unified_full_protocol | fair+raw | 20 | LCC,path,R | topology_snapshot,network_condition,robustness_metrics | 高 | 是 | pending | 同 RAND；**重算窗口/自适应规则**写入 `attack_params` 预注册 | 回填攻击章节表 |
| ED-MAIN-BASE | 07 | Eth-Docker | none | unified_full_protocol | fair+raw | 20 | R,LCC,path,peer_count_el | topology_snapshot,robustness_metrics,budget_log | 中-高 | 是 | pending | **必** `collect→compute→aggregate→run_eth_docker_experiments.py`（§6.4/C007）；缺优化链则熔断 ED **方法**主张；与 EC 「互证」= **方向一致**（`CMP-ED-EC-DIRECTION`），**非**数值复制；定位为**链路/劣化韧性**非拜占庭主结论 | 回填表7-3 |
| ED-MAIN-LINK | 08 | Eth-Docker | link_down | unified_full_protocol | fair+raw | 20 | LCC,components,path | topology_snapshot,network_condition,robustness_metrics | 中-高 | 是 | pending | 同 BASE 闭环；§4 ED Holm 三指标 **事先书面 1 个 primary**；主文仅 mid 时 low/high **仍须各满 n** 方可写跨强度；`missing_run_policy` 写入 manifest | 回填攻击章节表 |
| ED-MAIN-NETEM | 08 | Eth-Docker | tc_netem | unified_full_protocol | fair+raw | 20 | path,Rc,LCC | topology_snapshot,network_condition,robustness_metrics | 中-高 | 是 | pending | 同 LINK | 回填攻击章节表 |
| BTC-MAIN-BASE | 07 | BTC-Docker | none | unified_full_protocol | fair+raw | 20 | R,LCC,path,block_height,fork_events | topology_snapshot,chain_kpi,robustness_metrics,budget_log | 高 | 是 | pending | `reachable_ratio` **定义冻结**（`run_manifest.reachable_ratio_definition_id`）；缺字段 run **不入**主文统计；Neo4j→raw **契约未齐**则 MVS 不写 BTC 句、`MTH-CMP` 不含 BTC | 回填表7-2 |
| BTC-MAIN-ECL | 07/08 | BTC-Docker | eclipse | unified_full_protocol | fair+raw | 20 | LCC,path,peer_count_btc,fork_events | topology_snapshot,network_condition,chain_kpi | 高 | 是 | pending | 同 BASE；分攻击分层 + 正文讨论 **reachable_ratio** 协变量 | 回填表7-2/8章 |
| BTC-MAIN-PART | 07/08 | BTC-Docker | partition | unified_full_protocol | fair+raw | 20 | components,LCC,fork_events | topology_snapshot,network_condition,chain_kpi | 高 | 是 | pending | 同 ECL | 回填表7-2/8章 |
| BTC-MAIN-NETEM | 07/08 | BTC-Docker | tc_netem_delay_loss | unified_full_protocol | fair+raw | 20 | path,block_progress,fork_events | network_condition,chain_kpi,robustness_metrics | 高 | 是 | pending | 同 ECL | 回填表7-2/8章 |
| BTC-MAIN-BGP | 08/12 | BTC-Docker | bird_hijack | unified_full_protocol | fair+raw | 20 | reachable_ratio,LCC,path | network_condition,robustness_metrics,chain_kpi | 中 | 条件 | pending | 默认附录；入主文须 **威胁模型五字段** + reachable 定义与数据齐 | 附录优先；入主文须威胁模型+reachable 定义齐全 |
| MTH-CMP-FAIR | 07.5/7.6 | EC+BTC+ED | matched | unified_full_protocol | fair | 20 | delta,CI,p,effect_size | stats_summary,budget_log | 条件 | 是 | pending | 三平台 **`stats_summary` 同构** + §2.0 各 `method_id` **ready**；**聚合脚本落地前**禁写主文跨平台排名；输出与 §4 `CMP-MTH-*` 对齐 | §2.0 封闭后聚合；表7-4 |
| MTH-CMP-RAW | 07.6 | EC+BTC+ED | matched | unified_full_protocol | raw | 20 | rank_change,sensitivity | stats_summary,budget_log | 条件 | 是 | pending | 同 FAIR（raw 口径） | 同上；表7-5 |
| ABL-MLE-INJ | 09 | Eth-Cloud | none | ablation_mle | fair | 30 | delta_R,p,effect_size | robustness_metrics,stats_summary | 条件 | 否（消融） | pending | 成对设计；**仅 §09**；统计输出命名与主文 Holm 族**物理隔离**（文件名/表号） | 成对 30；表9-2 |
| ABL-COMP | 09 | Eth-Cloud+BTC | matched | ablation_components | fair | 20 | drop,p,effect_size | robustness_metrics,stats_summary | 条件 | 否（消融） | pending | 变体**预注册列表**齐全方可写「组件显著贡献」；**FDR** 与主文攻击族校正区分 | 变体列表预注册；表9-1 |
| ABL-WEIGHT | 09 | Eth-Cloud | none | ablation_weights | fair | 20 | stability,sensitivity | robustness_metrics,stats_summary | 条件 | 否（消融） | pending | 扰动区间**执行前锁定**；探索性扫描进附录或 `exploratory_*` 文件 | 扰动区间预注册 |
| FAB-EXT-NETEM | 12 | Fabric-Docker | tc_netem_profile | exploratory | fair+raw | 10 | prometheus_proxy | chain_kpi,network_condition,budget_log | 中 | 否（附录） | pending | **`exploratory`**：不入主文追溯链/摘要量化句；仅附录趋势+局限 | 仅附录趋势；不写 PoS 推广 |
| POL-EXT-BASE | 12 | Pol-Docker | none | exploratory | fair+raw | 10 | system_peers,R,lcc_ratio | topology_snapshot,network_condition,budget_log | 中 | 否（附录） | pending | 同 FAB；与 PoS 主结论**禁止**直接推广句 | 20s 周期；主文不写 |
| POL-EXT-NETEM | 12 | Pol-Docker | tc_netem | exploratory | fair+raw | 10 | system_peers,path | topology_snapshot,network_condition,budget_log | 中 | 否（附录） | pending | 同 BASE（POL） | 附录外推；与 FAB 并列叙述局限 |

## 1.1) 每类实验的数据需求说明（必需/可选/统计产物）

| 实验类别 | 对应 experiment_id | 必需原始字段（缺一不可） | 可选字段（缺失不阻塞） | 最小统计产物（入文门槛） |
|---|---|---|---|---|
| Eth 主场景 | EC-MAIN-BASE | `timestamp_utc,platform,experiment_id,run_id,phase,attack_label,budget_variant,R,Rs,Rc,Rr,lcc_ratio,avg_path_len,peer_count_el,peer_count_cl,attack_params` | `consensus_delay_proxy` | `mean,std,ci95_low,ci95_high,test_name,p_value,effect_size,n,comparison_id,stat_key` |
| Eth 攻击分析 | EC-MAIN-RAND/TGT/ADP, ED-MAIN-LINK/NETEM | `timestamp_utc,platform,experiment_id,run_id,phase,attack_label,attack_params,budget_variant,lcc_ratio,avg_path_len,components_or_peer_stability` | `peer_count_cl`（ED 可不稳定） | `按攻击类型分层统计 + Holm/FDR 校正 + effect_size` |
| Eth 复现实验 | ED-MAIN-BASE | `timestamp_utc,platform,experiment_id,run_id,R,lcc_ratio,avg_path_len,peer_count_el,budget_cost` | `peer_count_cl` | `与 EC 主结论方向一致性检验 + ci95 + p + effect_size` |
| BTC 主场景/攻击 | BTC-MAIN-BASE/ECL/PART/NETEM/BGP | `timestamp_utc,platform,experiment_id,run_id,phase,attack_label,attack_params,budget_variant,R,lcc_ratio,avg_path_len,peer_count_btc,block_height,fork_events,reachable_ratio` | `tx_confirm_latency_proxy` | `分攻击统计 + 协变量 reachable_ratio 控制说明 + p/effect_size` |
| 方法对比 | MTH-CMP-FAIR/RAW | `method_id,platform,experiment_id,run_id,metric,fair_or_raw_value,budget_cost,random_seed` | `time_to_converge` | `方法排名 + 配对检验 + 多重比较校正 + 效应量` |
| 组件消融 | ABL-COMP | `variant,platform,experiment_id,run_id,metric_value,budget_variant` | `component_internal_state` | `delta_vs_full + p + effect_size + n` |
| MLE 对照 | ABL-MLE-INJ | `inject_flag,platform,experiment_id,run_id,metric_value` | `fit_residual_proxy` | `inject vs no_inject 的 ci95 + p + effect_size` |
| 参数敏感性 | ABL-WEIGHT | `param_name,perturbation,platform,run_id,metric_value` | `gradient_norm_proxy` | `稳定区间/斜率 + 显著性` |
| Fabric 外推 | FAB-EXT-NETEM | `timestamp_utc,platform,experiment_id,run_id,attack_label,network_condition,prometheus_up` | `endorsement_latency_proxy,gossip_peer_state` | `趋势统计（附录）+ 不写主文定量主张` |
| Pol 附录 | POL-EXT-BASE / POL-EXT-NETEM | `timestamp_utc,platform,experiment_id,run_id,phase,attack_label,attack_params,system_peers,budget_variant` | `chain_kpi`（若可采） | `附录趋势/局限段；不生成主文 stats 主张` |

## 1.2) 拓扑与时序拓扑刚性需求（TIFS 主文必需）

> 以下要求用于回答“你到底采了什么拓扑、是否是时序拓扑、能否复现实验阶段变化”。

| 维度 | 必需内容 | 最小字段/结构 | 适用平台 | 入文要求 |
|---|---|---|---|---|
| 静态拓扑快照 | 每个阶段至少可重建一次图结构 | `node_id,peer_id,edge_type,directed,weight(optional),timestamp_utc` | Eth-Cloud/Eth-Docker/BTC-Docker | 必需 |
| 时序拓扑序列 | 连续采样形成 `G_t` 序列（非单点） | `run_id,phase,timestamp_utc,topology_edges` | Eth-Cloud/Eth-Docker/BTC-Docker | 必需 |
| 跨层拓扑映射 | 执行层/共识层或网络层/链层关联 | `layer,node_id,peer_count_*,block_height/fork_events` | Eth-Cloud/BTC-Docker（ED 可部分） | 主文建议 |
| 攻击阶段切片 | pre/attack/recovery 的拓扑可分段比较 | `phase` + 攻击参数 `attack_params` + `network_condition` | 全部主文平台 | 必需 |
| 连通性拓扑统计 | 连通分量与路径统计按时序输出 | `lcc_ratio,components,avg_path_len`（按 t） | 全部主文平台 | 必需 |
| 鲁棒性拓扑统计 | 结构指标与鲁棒分项同步输出 | `R,Rs,Rc,Rr`（按 t 或阶段聚合） | 全部主文平台 | 必需 |
| 路由/可达性协变量 | 区分拓扑退化与可达性波动 | `reachable_ratio`（BTC） | BTC-Docker | 必需 |
| 外推拓扑代理 | 无完整 P2P 图时使用代理并标注局限 | `prometheus_up` 等代理指标 | Fabric-Docker | 仅附录 |

### 时序采样与窗口约束（执行门槛）

1. 采样周期按平台固定：Eth-Cloud/Eth-Docker 为 30 s，BTC-Docker 为 10 s。  
2. 每个 `run_id` 必须覆盖完整阶段：`pre_attack -> attack_ramp -> under_attack -> recovery -> post_recovery`。  
3. 每阶段至少 3 个采样点；攻击与恢复阶段至少 5 个采样点。  
4. 任一主文对比若缺失完整时序拓扑（仅有汇总值），不得进入表 7-1 至 7-5。  

### 拓扑采集数量硬指标（必须满足）

| 平台 | 拓扑层 | 采样间隔 | 每 run 最少时刻数 | 每 run 最少拓扑快照数 | 每 experiment 最少拓扑快照数 |
|---|---|---|---:|---:|---:|
| Eth-Cloud | EL + CL 双层 | 30s | 19 | 38（19x2 层） | 760（38x20 runs） |
| Eth-Docker | EL 主层（CL 可选） | 30s | 19 | 19（仅 EL 计主文） | 380（19x20 runs） |
| BTC-Docker | P2P 单层拓扑 | 10s（或分阶段 30/10/10/10/30） | 19 | 19 | 380（19x20 runs） |
| Fabric-Docker（附录） | 拓扑代理层 | 30/15/15/15/30 | 12 | 12 | 120（12x10 runs） |
| Pol-Docker（附录） | P2P 单层（`system_peers`） | **20s**（全阶段统一） | 19 | 19 | 190（19×10 runs） |

说明：  
- “拓扑快照”指可重建图的 `G_t`（包含节点与边），不是单纯指标行。  
- Eth-Cloud 主文建议同时保留 EL 与 CL，两层拓扑快照用于跨层一致性分析。  
- Eth-Docker 若 CL 不稳定，主文最小要求按 EL 层计算，不影响主文达标。

### 拓扑产物文件约定（建议）

- 时序边表：`results/raw/<platform>/<experiment_id>/<run_id>/topology_edges_timeseries.csv`  
- 阶段聚合图：`results/processed/<platform>/<experiment_id>/<run_id>/phase_graph_*.json`  
- 拓扑统计：`results/processed/<platform>/<experiment_id>/<run_id>/topology_metrics_timeseries.csv`  
- 统计汇总：`results/statistics/<experiment_id>/stats_summary.csv`  

## 2) 主流对比方法清单（用于 MTH-CMP-*）

### 2.0 方法对比「封闭规格」（TIFS：公平性可审计）

> 目的：把「待公平预算对齐」落实为**可检查**条目；**主文表 7-4/7-5** 仅允许引用满足下列全部条件的 runs。探索性超参可在附录单独文件产出，**不得共用**同一 `comparison_id`。

| 条款 | 规则 |
|:---|:---|
| **输入图** | 同一 `experiment_id` + `attack_tier` + `run_id` 下，各 `method_id` 使用 **同一拓扑输入**（同一时间窗的 `topology_edges_timeseries` 或冻结 `phase_graph`/快照 JSON；以 `run_manifest.input_artifact_sha256` 记录） |
| **随机性** | `random_seed`：**同一 run_id 映射到同一种子序列**（§6 `seed_policy`）；各方法仅允许消耗各自子流 |
| **预算 fair** | `budget_cost` 单位：**一次合法重连/一次 RPC 轮询/一次优化迭代**等须在 `experiment_protocol.py` 或附录「预算字典」**冻结**；达到 `B_fair` 上限即停，超预算结果 **弃用** |
| **预算 raw** | `budget_cost`：**墙钟时间或总 RPC 次数**等原始口径，同样在 manifest 登记 `raw_budget_definition_id` |
| **停止条件** | 各方法共享 **最大 wall-clock** 与 **最大迭代步** 两上限；先触发者停；平局规则预注册 |
| **失败 run** | 崩溃/超时/指标全缺 → 该 `method_id`×`run_id` 记 **invalid**，**不替换种子重算**；优先补采；补采规则写入 `missing_run_policy` |
| **观测 vs 优化** | **Eth 观测采集链** `budget_cost=0`（§6.3）；**方法优化对比**仅在与 **`run_eth_docker_experiments.py` 或云上等价优化入口**绑定的产出中读取 `budget_cost>0` 行 |

| method_id | 方法名称 | 类型 | 主文必选 | 状态 |
|---|---|---|---|---|
| M-OUR | 本文方法 | 两阶段动力学 | 是 | ready（须按上表封闭） |
| M-RESI | ResiNet | 学习式重连 | 是 | **须满足 §2.0 后标 ready** |
| M-STAT | Static | 静态图启发式 | 是 | **须满足 §2.0 后标 ready** |
| M-ASIM | AttackSim | 攻击仿真驱动 | 是 | **须满足 §2.0 后标 ready** |
| M-FPS | FPSblo-EP | 区块链P2P优化 | 可选 | 附录候选；同 §2.0 |

## 2.1) 字段-接口白名单（执行侧）

> 目的：把“字段名”绑定到“采集接口/来源”，避免跑完后字段口径不一致。  
> 稳定性分级：A=稳定可采；B=可采但偶发缺失；C=当前不可稳定依赖（仅观察）。

| field_name | 来源接口/命令 | 平台 | 稳定性 | 主文必需 | 备注 |
|---|---|---|---|---|---|
| peer_count_el | Geth `admin_peers` JSON-RPC | Eth-Cloud/Eth-Docker | A | 是 | 执行层核心连接度 |
| peer_count_cl | Lighthouse `/eth/v1/node/peers` | Eth-Cloud/Eth-Docker | A(Cloud)/B(Docker) | 条件 | ED 中仅补充观察 |
| topology_edges | 监控代理汇聚到 Neo4j（边表） | Eth/BTC/Pol | A(BTC/EC)/B(ED) | 是 | 用于重建图 `G_t` |
| network_condition | `tc netem` / 链路状态注入日志 | Eth/BTC/Fabric | A | 是 | 需与 `phase` 对齐 |
| block_height | Bitcoin RPC `getblockcount` 或 monitor | BTC-Docker | A | 是 | 链进展指标 |
| fork_events | monitor 分叉检测或链状态差异统计 | BTC-Docker | A | 是 | 攻击影响关键证据 |
| peer_count_btc | Bitcoin RPC `getpeerinfo` | BTC-Docker | A | 是 | P2P 邻居规模 |
| reachable_ratio | 监控端可达节点比率聚合 | BTC-Docker | A | 是 | 主文协变量 |
| prometheus_up | Prometheus `up` 指标 | Fabric-Docker | A | 否（附录） | 运行态代理 |
| endorsement_latency_proxy | Fabric 监控指标/日志聚合 | Fabric-Docker | B | 否（附录） | 外推解释用 |
| system_peers | Substrate `system_peers` RPC | Pol-Docker | C（当前） | 否 | 运行态恢复后启用 |
| R,Rs,Rc,Rr | `robustness_metrics` 计算产物 | EC/ED/BTC | A | 是 | 需固定计算脚本版本 |
| lcc_ratio,components,avg_path_len | 拓扑统计脚本产物 | EC/ED/BTC | A | 是 | 按时序/阶段输出 |
| budget_cost | `budget_log` 聚合 | EC/ED/BTC | A | 是 | fair/raw 对齐证据 |

## 2.2) 实验完成判据（Done Criteria）

> 目的：避免“跑了一半就写结论”。必须同时满足字段、时序、统计、追溯四类条件。

| experiment_id | 完成判据（全部满足） | 失败处理 |
|---|---|---|
| EC-MAIN-BASE | `n_runs>=20`；完整阶段时序；主字段齐全；产出 `stats_summary` 含 CI/p/effect；登记 `comparison_id/stat_key` | 缺字段补跑；阶段缺失整 run 标记无效并补齐 |
| EC-MAIN-RAND/TGT/ADP | 各攻击强度至少一组有效结果；攻击参数可追溯；多重比较已校正 | 强度档位缺失则不允许写攻击章节主结论 |
| ED-MAIN-BASE/LINK/NETEM | 执行层拓扑完整；若 `peer_count_cl` 缺失不阻塞主文；统计项完整 | 仅保留可用字段；CL 字段降级为观察项 |
| BTC-MAIN-BASE/ECL/PART/NETEM/BGP | 主字段 + `reachable_ratio` 必须齐；分攻击统计完成；异常窗口有说明 | 未记录 `reachable_ratio` 的 run 不入主文统计 |
| MTH-CMP-FAIR/RAW | 三基线 + 本文方法均有同种子/同预算对齐结果；排名与检验完整 | 任一基线缺失则只可附录，不可写主文对比结论 |
| ABL-COMP | full 与关键消融变体齐全；`delta_vs_full + p + effect` 完整 | 变体缺失不得写“组件显著贡献”结论 |
| ABL-MLE-INJ | inject/no-inject 成对样本齐；统计检验完整 | 样本不成对时改用附录探索描述 |
| ABL-WEIGHT | 参数扰动覆盖预设区间；稳定性统计可复算 | 区间覆盖不足不写参数鲁棒结论 |
| FAB-EXT-NETEM | 指标可稳定采集并有趋势统计 | 仅附录使用，不上主文主张 |
| POL-EXT-BASE / POL-EXT-NETEM | `n_runs>=10`；**20s** 周期；阶段完整；`system_peers` 可解析为边 | 不入主文统计；仅附录 |

## 2.3) 攻击强度参数登记（低/中/高）

> 目的：把“低/中/高”变成可复现实数区间。执行前锁定，不得事后调整。

| attack_label | 强度档位 | 参数模板（示例） | 适用平台 | 说明 |
|---|---|---|---|---|
| random_remove | low/mid/high | 失效节点比例 `{0.05,0.10,0.20}` | EC/ED | 节点选择固定随机种子 |
| targeted_remove | low/mid/high | Top-k 中心节点比例 `{0.03,0.06,0.10}` | EC/ED | 中心性定义需预注册 |
| adaptive_remove | low/mid/high | 每窗口重算并移除 `{1,2,4}` 个关键点 | EC | 记录重算窗口长度 |
| link_down | low/mid/high | 断链比例 `{0.05,0.10,0.20}` 或关键链路数 | ED | 与拓扑层级一同记录 |
| tc_netem | low/mid/high | delay `{50,150,300}ms`, loss `{1,5,10}%` | ED | jitter/bw 需同步登记 |
| eclipse | low/mid/high | 受害节点比例 `{0.05,0.10,0.20}` + 邻居隔离策略 | BTC | 必须记录隔离时长 |
| partition | low/mid/high | 分区规模比 `{7:3,6:4,5:5}` | BTC | 记录跨分区连边数 |
| tc_netem_delay_loss | low/mid/high | delay `{100,300,500}ms`, loss `{5,15,30}%` | BTC | 与区块进展同步采样 |
| bird_hijack | low/mid/high | 劫持前缀比例 `{0.05,0.10,0.20}` | BTC | 当前建议先附录验证 |
| tc_netem_profile | LAN/MAN/REGION/GLOBAL | 预置配置文件 ID | Fabric | 仅附录，写明 profile |

## 2.4) 采集执行总表（采什么/采多少/隔多久）

> 本表为执行侧唯一口径。所有主文实验必须满足“字段完整 + 最小样本量 + 固定采样周期”三条件。  
> 阶段定义：`pre_attack`, `attack_ramp`, `under_attack`, `recovery`, `post_recovery`。

| 平台 | 实验范围 | 必采字段（核心） | 每阶段最少采样点 | 采样周期（分阶段） | 单次 run 最少样本点 | 每实验最少样本点（按 n_runs） |
|---|---|---|---|---|---:|---:|
| Eth-Cloud | EC-MAIN-* | `timestamp_utc,experiment_id,run_id,phase,attack_label,attack_params,R,Rs,Rc,Rr,lcc_ratio,avg_path_len,peer_count_el,peer_count_cl,budget_variant` | `3/5/3/5/3` | 30s / 30s / 30s / 30s / 30s | 19 | 380（n=20） |
| Eth-Docker | ED-MAIN-* | `timestamp_utc,experiment_id,run_id,phase,attack_label,attack_params,R,lcc_ratio,avg_path_len,peer_count_el,budget_variant` | `3/5/3/5/3` | 30s / 30s / 30s / 30s / 30s | 19 | 380（n=20） |
| BTC-Docker（统一10s） | BTC-MAIN-*（默认） | `timestamp_utc,experiment_id,run_id,phase,attack_label,attack_params,R,lcc_ratio,avg_path_len,peer_count_btc,block_height,fork_events,reachable_ratio,budget_variant` | `3/5/3/5/3` | 10s / 10s / 10s / 10s / 10s | 19 | 380（n=20） |
| BTC-Docker（分阶段推荐） | BTC-MAIN-*（推荐） | 同上（与统一10s字段完全一致） | `3/5/3/5/3` | 30s / 10s / 10s / 10s / 30s | 19 | 380（n=20） |
| Fabric-Docker（附录） | FAB-EXT-* | `timestamp_utc,experiment_id,run_id,phase,attack_label,network_condition,prometheus_up,budget_variant` | `2/3/2/3/2` | 30s / 15s / 15s / 15s / 30s | 12 | 120（n=10） |
| Pol-Docker（附录） | POL-EXT-* | `timestamp_utc,experiment_id,run_id,phase,attack_label,network_condition,system_peers,budget_variant` | `3/5/3/5/3` | **20s** 全阶段 | 19 | 190（n=10） |

### 2.4.1 样本量计算规则

1. 单次 `run` 最少样本点：  
   `N_run = N_pre + N_ramp + N_under + N_recovery + N_post`  
   主文当前最小配置为 `3+5+3+5+3=19`。  
2. 单个实验最少样本点：  
   `N_exp = N_run * n_runs`。主文默认 `n_runs=20`，因此 `N_exp>=380`。  
3. 若任一阶段样本点不足，则该 `run_id` 记为不合格样本，不得进入主文统计。

### 2.4.1-bis 拓扑数量计算规则（主文）

1. 单次 `run` 的拓扑快照数：  
   `Topo_run = N_run * L`，其中 `L` 为纳入主文的拓扑层数。  
2. 单个实验的拓扑快照数：  
   `Topo_exp = Topo_run * n_runs`。  
3. 主文最小阈值（当前配置）：
   - Eth-Cloud：`Topo_exp >= 760`（EL+CL）
   - Eth-Docker：`Topo_exp >= 380`（EL）
   - BTC-Docker：`Topo_exp >= 380`
4. 若仅有指标聚合而无 `topology_edges_timeseries.csv`，视为“无拓扑证据”，该实验不得支撑主文拓扑结论。

### 2.4.2 主文入表硬门槛（表7-1到7-5）

- 字段门槛：必采字段齐全（缺失值允许 `null`，但关键字段不得缺失）。  
- 样本门槛：`N_exp>=380`（或按协议定义的等效更高阈值）。  
- 周期门槛：同一 `experiment_id` 不得中途变更采样周期配置。  
- 统计门槛：必须产出 `mean,std,ci95_low,ci95_high,p_value,effect_size,test_name,comparison_id,stat_key`。  

### 2.4.3 输出文件最小集合（每个 experiment_id）

- `results/raw/<platform>/<experiment_id>/*/topology_edges_timeseries.csv`
- `results/raw/<platform>/<experiment_id>/*/network_condition.csv`（无注入时须含 **baseline** 行，见 §0.2）
- `results/processed/<platform>/<experiment_id>/*/topology_metrics_timeseries.csv`
- `results/statistics/<experiment_id>/stats_summary.csv`
- `results/statistics/<experiment_id>/run_manifest.json`

## 3) 字段级最小采集规范（每条样本）

| 字段 | 必需性 | 说明 |
|---|---|---|
| timestamp_utc | 必需 | UTC 时间戳 |
| platform | 必需 | 平台枚举 |
| experiment_id | 必需 | 与本矩阵一致 |
| run_id | 必需 | 重复运行编号 |
| phase | 必需 | pre_attack/attack_ramp/under_attack/recovery/post_recovery |
| layer | 必需 | execution/consensus/network/routing/app |
| attack_label | 必需 | 攻击标签 |
| attack_params | 必需 | JSON 参数对象 |
| protocol_variant | 必需 | unified_full_protocol/ablation_*/exploratory |
| budget_variant | 必需 | fair/raw |
| reachable_ratio | 条件必需 | **仅 BTC**：须在 `run_manifest.reachable_ratio_definition_id` 指向冻结定义（如「已知节点集合 K 上 RPC 成功比例」）；**定义变更 ⇒ `PROTOCOL_VERSION` 升级** |

## 4) 关键对比登记（统计预注册）

> **primary / secondary**：主文摘要与「优于基线」类句 **仅绑定 primary**；secondary 仅支持机制解释与附图，**不进 Holm 主族**（除非在备注中显式升格并预注册第二族）。

| comparison_id | 对比目的 | primary_metric | secondary_metrics | group A | group B | 预设检验 | 效应量 | 多重比较 | 归属 |
|---|---|---|---|---|---|---|---|---|---|
| CMP-EC-OUR-RESI | Eth-Cloud 主场景对比 | **R** | LCC, avg_path_len, Rs/Rc/Rr | M-OUR | M-RESI | paired t / Wilcoxon | Cohen's d / Cliff's delta | Holm（与 STAT/ASIM 同族） | 主文 |
| CMP-EC-OUR-STAT | Eth-Cloud 主场景对比 | **R** | 同上 | M-OUR | M-STAT | paired t / Wilcoxon | Cohen's d / Cliff's delta | Holm | 主文 |
| CMP-EC-OUR-ASIM | Eth-Cloud 主场景对比（若 M-ASIM 入主文表） | **R** | 同上 | M-OUR | M-ASIM | paired t / Wilcoxon | Cohen's d / Cliff's delta | Holm（与 RESI/STAT **同族**） | 主文 |
| CMP-BTC-OUR-RESI | BTC 方法对比（若启用） | **lcc_ratio** | avg_path_len, fork_rate | M-OUR | M-RESI | paired t / Wilcoxon | Cohen's d / Cliff's delta | Holm | 主文/附录 |
| CMP-ED-MAIN-R-UNDER-minus-PRE | ED 采集链：R 的阶段差 | **R**（under−pre 每 run 聚合） | lcc_ratio, avg_path_len | pre_attack | under_attack | paired t / Wilcoxon | Cohen's d_z | Holm（与下列两行合并为「ED 指标族」时须整体设计） | 主文/附录 ED |
| CMP-ED-MAIN-LCC-UNDER-minus-PRE | ED：LCC 阶段差 | **lcc_ratio** | R, avg_path_len | pre_attack | under_attack | 同上 | 同上 | Holm | 主文/附录 ED |
| CMP-ED-MAIN-PATH-UNDER-minus-PRE | ED：路径阶段差 | **avg_path_len** | R, lcc_ratio | pre_attack | under_attack | 同上 | 同上 | Holm | 主文/附录 ED |
| CMP-ED-EC-DIRECTION | ED 与 EC **方向互证**（非数值复制） | **sign(ΔR_EC)·sign(ΔR_ED)>0** 的一致率（见 §6.3.1） | 可选 lcc_ratio 符号 | EC 侧 ΔR | ED 侧 ΔR | **单侧二项检验** \(H_0:p=0.5\) | 一致率 **+ Wilson 95%CI** | 单独族，不与 Holm 混 | 主文（仅 EC+ED 齐） |
| CMP-BUDGET-FAIR-RAW | 预算口径敏感性 | 与主文 primary 一致 | — | fair | raw | paired t / Wilcoxon | Cohen's d | N/A | 主文 |
| CMP-ABL-MLE | MLE 注入消融 | **delta_R** | — | no_inject | inject | paired t | Cohen's dz | N/A | 消融 |
| CMP-ABL-COMP | 组件消融 | **R**（或预注册替代主指标） | LCC, path | full | ablated | paired t / Wilcoxon | Cohen's d | FDR | 消融 |
| CMP-FAB-EXT | 联盟链外推 | **prometheus_up** 或预注册代理 | — | M-OUR | baseline | Mann-Whitney | Cliff's delta | N/A | 附录 |

## 5) 主文纳入规则（TIFS 审稿口径）

1. 仅 `protocol_variant=unified_full_protocol` 可进入 `07-主结果.md`、`01-摘要.md`、`11-结论.md`。  
2. `ablation_*` 仅进入 `09-消融与敏感性.md`。  
3. `exploratory` 仅进入 `12-附录.md`。  
4. 每条主文量化结论必须在 `docs/论文初稿/claim_traceability.md` 存在 `claim_id + comparison_id + stat_key + evidence_paths` 且 `status=done`（与 §6 `traceability_required` 一致）。  
5. 若存在 `paper_cn/` 等平行撰稿目录，**不得**另起一套 claim 口径：或 **单向引用** 上述 `claim_traceability.md`，或将同结构块 **同步复制** 并注明 canonical 路径，避免审稿材料双稿漂移。  

## 6) 统计与追溯执行规范（落地版）

> 目的：把矩阵中的统计要求变成统一执行动作，避免“同一实验不同口径”。

| 项 | 执行规则 | 适用范围 |
|---|---|---|
| seed_policy | 固定种子池并建立 `run_id -> seed` 映射；同一 `comparison_id` 各方法使用同序列 | 主文全部对比 |
| normality_test | 先做 `Shapiro-Wilk(alpha=0.05)` | 主文与消融 |
| test_selection | 正态用 paired t；非正态用 Wilcoxon signed-rank | 主文与消融 |
| multiple_correction | 主文方法多组对比用 Holm；消融多项对比用 FDR(BH) | 主文与消融 |
| effect_size_rule | paired t 报 Cohen's d(dz)；Wilcoxon 报 Cliff's delta / rank-biserial | 主文与消融 |
| ci_method | 95%CI 当前主线统一为 t-interval（`mean_std_ci95_t`）；若切换 bootstrap，需升级 `PROTOCOL_VERSION` 并整体重算 | 主文与消融 |
| missing_run_policy | 缺失 run 优先补采；无法补采则整组剔除并在 manifest 标注 | 全部实验 |
| traceability_required | 每条结论登记 `claim_id + comparison_id + stat_key + evidence_paths + status` | 主文结论 |

### 6.1 输出契约（与 2.4.3 配套）

每个 `experiment_id` 至少包含：

- `results/raw/<platform>/<experiment_id>/*/topology_edges_timeseries.csv`
- `results/raw/<platform>/<experiment_id>/*/network_condition.csv`（攻击实验必需；无攻击见 §0.2 baseline）
- `results/processed/<platform>/<experiment_id>/*/topology_metrics_timeseries.csv`
- `results/statistics/<experiment_id>/stats_summary.csv`
- `results/statistics/<experiment_id>/run_manifest.json`

### 6.2 主文统计最小字段（再次锁定）

`mean,std,ci95_low,ci95_high,test_name,p_value,effect_size,n,comparison_id,stat_key`

（建议与实现一致时补充 **`p_value_holm`**、**`effect_size_name`** 列，便于与 `experiments/tifs_stats.py` 输出对齐。）

### 6.3 审稿人常见意见 ↔ 本文对策（在**现有平台可完成**前提下尽量做到最好）

> 把易被质疑的点写成可执行对策；**不承诺**仓库尚未接线的 BTC 全链路。主文若收缩跨链主张，下列条目仍显著提高可辩护性。

| 审稿关切 | 风险 | 本文对策（可落地） |
|---|---|---|
| 威胁模型与实验是否匹配 | Major：引言偏「对抗/安全」但 ED 多为断链与 netem | **正文分层**：ED-MAIN-LINK/NETEM 明示为 **链路故障与广域劣化（可用性/韧性）**；策略性移除/自适应以 **EC-MAIN-\*** 为主证据。ED 行不写「拜占庭共识攻击已在实链验证」。 |
| 多平台可推广性 | Major：仅 Docker 易被指外部效度不足 | **贡献与矩阵对齐**：EC 为规模与攻击多样性锚；ED 为 **真实栈时序拓扑 + 阶段可复现** 互证；BTC 在 `reachable_ratio` 与链 KPI 未齐前 **不入主文定量表**，或仅附录并写局限。 |
| 统计「挑检验」 | Major | 执行 **§6 `normality_test` → `test_selection`**；主文表仅列 **§4 已登记 `comparison_id`**；探索性分析标 **exploratory**，不进摘要结论句。 |
| 多重比较与效应量 | Major | 方法族 **Holm**；消融族 **FDR-BH**；必报 **效应量**（t：**Cohen's d_z**；秩：**Cliff's delta / rank-biserial**）。以 `experiments/tifs_stats.py` 为口径锚。 |
| Run 独立性与状态泄漏 | Minor→Major | 同 `experiment_id`+`attack_tier` 下 `run_id` 递增；`run_manifest.json` 记录种子/阶段/注入登记；run 间 **recovery/reset** 与采集脚本语义一致。 |
| 拓扑证据不足 | Major | 遵守 **2.4.1-bis**：无 `topology_edges_timeseries.csv` 不写主文拓扑结论；`topology_metrics_timeseries.csv` 须由同批样本可复算。 |
| `network_condition` 与 phase | Major | 每样本/每时刻落 **`network_condition.csv`**，与 `phase`、`attack_params`、注入是否生效对齐；追问内核 tc 时 **声明**当前为控制 API + 观测代理，附录可预置抽检方案（平台允许时）。 |
| fair/raw 与观测采集混淆 | Minor | **两链分立**：观测采集 `budget_log.jsonl` 中 **`budget_cost=0` + `notes=topology_observation_only_*`**（raw 观测）；**fair/raw 方法对比** 仅 **`run_eth_docker_experiments.py`**。不得混在同一结论句。 |
| ED 与 EC 方向一致性（表 1.1） | Major | **EC 数据齐后**：按 **§6.3.1** 做 **ΔR 符号一致率**检验；**EC 缺失时不写**「与云实验一致」类结论。 |
| 攻击强度 low/mid/high | Minor | ED：用 **`--attack-tier`** 分档采集，**每档 `n_runs=20`** 方可写跨强度趋势；主文篇幅不足时主报 **mid**，low/high 放附录但仍须满样本。 |
| 路径与 artifact | Minor | **`results/raw/eth_docker`**、**`results/processed/eth_docker`** 与矩阵 **`<platform>=eth_docker`** 等价；审稿包附一行路径对照表。 |
| `phase_graph_*.json`（§81–85） | Minor | **不阻塞主文**；若有则附录；硬门槛以 **时序边表 + 指标时序** 为准。 |

### 6.3.1 `CMP-ED-EC-DIRECTION` 统计规格（冻结，防「事后叙事」）

> 仅当 **`EC-MAIN-BASE` 与 `ED-MAIN-BASE`** 均满足 §2.2 Done，且两平台 **`attack_tier=mid` 或未攻击** 的基线可比时启用（若 tier 不一致须在 manifest 标注并 **不写主文该对比**）。

1. **逐 run 标量**  
   - **EC**：对每个 `run_id`，计算 \(\Delta R_{\mathrm{EC}} = \overline{R}_{\mathrm{under}} - \overline{R}_{\mathrm{pre}}\)（阶段均值定义与 `stats_summary` 中 `stat_key` 一致并预注册）。  
   - **ED**：对每个 `run_id`，同式得 \(\Delta R_{\mathrm{ED}}\)。  
   - **配对规则**：按 **`run_id` 序号对齐**（同一序号使用同一随机种子策略）；若 EC run 数 ≠ ED run 数，取 **`n=min(n_{EC},n_{ED})`** 前序对齐，丢弃多余 run 并在 manifest 记录 **`direction_pairing_truncated=true`**。

2. **方向一致指示量**  
   - \(Z_i = \mathbf{1}\big[ \mathrm{sign}(\Delta R_{\mathrm{EC},i}) = \mathrm{sign}(\Delta R_{\mathrm{ED},i}) \big]\)，其中 **\(\Delta=0\)** 的 run **剔除**（计入 `manifest.zero_delta_excluded`），不参与主检验。

3. **检验与报告**  
   - **主要检验**：\(H_0: p = 0.5\)（无方向一致倾向），**单侧** \(H_1: p > 0.5\)；使用 **精确二项检验**（\(n\) 为有效 \(Z_i\) 数）。  
   - **报告量**：一致率 \(\hat{p}=\frac{1}{n}\sum Z_i\)、**Wilson 95% CI**、**p-value**；**不报 Holm**（与主方法族独立）。  
   - **效应量**：报告 **一致率与 CI** 即可；可选附录报告 **Cliff's delta** 于配对差分 \(\Delta R_{\mathrm{EC}}-\Delta R_{\mathrm{ED}}\)（探索性，**非主文摘要绑定**）。

4. **禁止事项**  
   - 不得更换为「相关系数最大化」未预注册目标；不得在剔除规则上 **按结果调参**。

### 6.4 当前仓库「可执行闭环」映射（尽量做到最好；≠ 全矩阵已 Done）

| 矩阵对象 | 平台 | 脚本链 / 关键产物 | 入主文前提 |
|---|---|---|---|
| ED-MAIN-BASE/LINK/NETEM（观测链） | Eth-Docker | `collect_eth_docker_scenarios.py` → `compute_eth_docker_metrics_fast.py` → `aggregate_eth_docker_collected_stats.py`；`topology_edges_timeseries.csv`、`network_condition.csv`、`budget_log.jsonl`（含 **`protocol_version`**）；每 run **`run_manifest.json`** 含 **`attack_tier_applied`**、**`target_selection_rule`**；`topology_metrics_timeseries.csv`；`results/statistics/<experiment_id>/stats_summary.csv` | 每实验 `n_runs=20`；攻击多强度见 §6.3；聚合对 under−pre **run 级差分** 使用 **`tifs_stats.test_one_sample_deltas_with_normality_gate`**（§6.1） |
| ED 方法对比（图优化，**必做**） | 本地优化 | **`run_eth_docker_experiments.py`**：默认读 **`results/raw/eth_docker/.../sample_*.json`**；**`--from-snapshots`** 时读 **`results/derived/eth_snapshots/`**；**`--gradient-mode`**（默认 **`full`**）写入结果行与 manifest → **`stats_summary_graph_optimizer.csv/json`** | 与观测链 **并列**：无主文方法表/无 **`stats_summary_graph_optimizer`** 则 ED **方法主张**不齐；产出文件名带 **`_graph_optimizer`** 以免覆盖观测 `results_rows.json` |
| EC-MAIN-\* | Eth-Cloud / 远程 | 当前仓库未维护（远端采集脚本已下线） | 若恢复 EC，按 §1.2 字段与时序验收 |
| BTC-MAIN-\* | BTC-Docker（外部位虚拟网） | **须**：Neo4j/监控 → **`results/raw/btc_docker/...` 契约导出** + `compute_*`/`aggregate_*` 与 EC/ED **同字段**；**`reachable_ratio` 定义冻结** | 契约未齐 → MVS 不写 BTC 句；`MTH-CMP` 不含 BTC |
| MTH-CMP-FAIR/RAW | EC+ED(+BTC) | 三平台 **`stats_summary` 同构** + §**2.0** 预算字典 + 聚合脚本（待补） | 缺一平台或基线未 **§2.0 ready** → 不写跨平台排名 |
| POL-EXT-\* | Pol-Docker | 附录采集；产出落 `results/raw/pol_docker/`；**不入** `unified_full_protocol` 主文统计 | 仅附录趋势 |

### 6.5 追溯与脚本版本（审稿友好）

- **Claim 登记**：canonical 为 `docs/论文初稿/claim_traceability.md`（见 §5）。  
- **协议冻结版本**：`experiments/experiment_protocol.py` 中 `PROTOCOL_VERSION`；各 `run_manifest.json` 应写入该字段。  
- **统计实现锚点**：`experiments/tifs_stats.py`（Holm、正态性门控后的单样本检验、效应量、CSV 列）；**ED 采集链聚合**见 `aggregate_eth_docker_collected_stats.py`（调用 **`test_one_sample_deltas_with_normality_gate`**）；**ED 图优化方法对比**见 `run_eth_docker_experiments.py` + **`build_method_comparison_rows`**（同一门控）。扩展 Wilcoxon/bootstrap 时在本节表格 **test_selection / ci_method** 下追加一行「实现脚本名」以免口径漂移。

