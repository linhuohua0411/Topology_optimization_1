# TIFS 共用参考（三条线共用，只维护本文件）

> 三个 Cursor 条目（总控 / 实验 / 写作）的 `SKILL.md` 仅写**触发场景与本角色动作**；**路径、闸门、分章、JSON 等全文以本文件为准**，避免多处改写漂移。

---

## 0. 三角色导读（该读哪一节）

| 角色 | 目录名 | 优先阅读 |
|------|--------|------------|
| **总控** | `tifs-chief-coordinator` | §1 路径、§2 术语、§3、§4、§7、§8、**§10、§11**、`qa/tifs_gate_report.md` |
| **实验** | `tifs-experiment` | §1（尤其 1.2）、§2、§3、§6、§8、**§10（R3/R6）、§11（G2/G3/G6）** |
| **写作** | `tifs-writing` | §1（尤其 1.3）、§2、§3、§5、§8、**§10（R1/R2/R4/R5/R7）、§5.5** |

**固定平台（本项目）**：Eth-Docker、Eth-Cloud、Pol-Docker、BTC-Docker、Fabric-Docker。

---

## 1. 仓库路径锚点

### 1.1 协议与清单

| 路径 | 说明 |
|------|------|
| `protocol/03_experiment_matrix.md` | 实验总表、MVS、方法对比封闭、`n_runs`、档位与 `experiment_id` |
| `protocol/04_experiment_execution_checklist.md` | 执行勾选、与审稿口径对齐 |
| `protocol/04_metrics_dictionary.md` | 指标与 **raw-budget / fair-budget** 术语 |
| `protocol/threat_model.md` | 威胁模型权威版（与正文一致） |
| `protocol/unified_full_protocol.md` | 若已落库：**主文唯一口径**（unified full protocol） |

### 1.2 代码与结果

| 路径 | 说明 |
|------|------|
| `experiments/tifs_stats.py` | 检验、Holm、效应量、导出列名；**论文表头须与此一致** |
| `experiments/experiment_protocol.py` | `PROTOCOL_VERSION`（当前 **`tifs-freeze-v2`**；变更须同步矩阵 §6.5 与采集/聚合 manifest） |
| `experiments/run_repro_tifs.py` | 一键复现入口（标志位以 README / 问题日志为准） |
| `experiments/collect_*`、`compute_*`、`aggregate_*` | 按任务选读 |
| **Eth-Docker 闭环（必做口径）** | **`collect_eth_docker_scenarios.py` → `compute_eth_docker_metrics_fast.py` → `aggregate_eth_docker_collected_stats.py` → `run_eth_docker_experiments.py`**；与 **`protocol/04` §二**、**`protocol/03` §0.1/§6.4**、**`claim_traceability.md` C007** 一致；缺图优化产出则 **ED 方法主张证据不齐** |
| `results/raw/`、`results/statistics/`、`results/traceability/` | 原始、汇总、追溯（若使用） |

### 1.3 论文资产

| 路径 | 说明 |
|------|------|
| `docs/论文初稿/` | 中文分章稿**唯一权威**；含 `claim_traceability.md`、`figures/`、`tables/` |
| `paper_en/` | 英文 TIFS 向稿与图表（与中文结构对应） |

### 1.4 状态与 QA（可选）

`state/*.json`、`qa/tifs_gate_report.md`、`plans/next_actions.md` — 进度与闸门留痕；`plans/next_actions.md` 中任务建议注明 **输入/输出路径** 与 **完成判据**。

---

## 2. 术语（与协议对齐）

- **unified full protocol**：主文结论**仅**允许引用该 `protocol_variant` 下的统计与图。
- **raw-budget / fair-budget**：定义见指标字典；**须分开展示**（分列或分文件），禁止混成单列含糊「开销」。
- **exploratory**：试跑口径，**不得**进入主文追溯链。

---

## 3. G1–G6 闸门（最低标准）

1. **G1**：主文只使用 **unified full protocol**；消融/探索在矩阵与命名上可区分。
2. **G2**：核心结果含 **mean / std / 95%CI**，且 **CI 方法**在统计目录或 README 中可追溯。
3. **G3**：关键对比含 **检验、p、效应量**；必要时非参数；多重比较与 **`tifs_stats.py` / 实验矩阵**一致。
4. **G4**：威胁模型 **五字段** + **非目标边界**（`protocol/threat_model.md`）。
5. **G5**：raw 与 fair **分报**（定义在协议层，数字在结果层分列）。
6. **G6**：图/表/句可映射到 **配置 + 日志 + 原始/统计**（manifest、trace 等），无断链。

未通过项视为 **P0**，不得宣称「仅润色即可投稿」。

| 编号 | 速查 |
|------|------|
| G1 | unified full protocol 主文口径 |
| G2 | mean / std / 95%CI |
| G3 | 显著性 + 效应量；必要时非参数 |
| G4 | Threat 五字段 |
| G5 | raw / fair 分报 |
| G6 | 配置 / 日志 / 数据可追溯 |

---

## 4. 项目阶段状态机（建议写入 `state/project_state.json`）

| 阶段 ID | 含义 | 常见阻塞 |
|---------|------|----------|
| `P0_protocol` | 统一协议与威胁模型未定稿 | 缺 unified_full_protocol / Threat 五字段 |
| `P1_experiment` | 主实验与统计未齐 | 缺 CI、缺检验、重复不足 |
| `P2_ablation` | 消融/敏感性未完成 | 与主文口径混写 |
| `P3_writing` | 章节化写作 | 单文件混写、摘要超证据 |
| `P4_submission_ready` | 投稿就绪 | 六项闸门全过 |

阶段建议**顺序前进**；若闸门失败，回退到最早失败阶段对应的 P 编号。

---

## 5. 分章、Threat 五字段与 Claim（写作主用）

### 5.1 分章（`docs/论文初稿/`，禁止单文件混写正文）

| 顺序 | 文件名 |
|------|--------|
| 1 | `01-摘要.md` |
| 2 | `02-引言.md` |
| 3 | `03-相关工作.md` |
| 4 | `04-问题定义与威胁模型.md` |
| 5 | `05-方法.md` |
| 6 | `06-实验设置.md` |
| 7 | `07-主结果.md` |
| 8 | `08-攻击类型分析.md` |
| 9 | `09-消融与敏感性.md` |
| 10 | `10-局限性.md` |
| 11 | `11-结论.md` |
| 12 | `12-附录.md` |

另：`00-全文标题.md`（若使用）、`claim_traceability.md`、`figures/`、`tables/`。

### 5.2 Threat Model 建议小节标题（`04-问题定义与威胁模型.md`）

`attacker objective` · `attacker knowledge` · `attacker budget` · `attack modes` · `evaluation protocol` — 章末增加 **「非目标与边界」**。

### 5.3 `claim_traceability.md` 行模板（须与仓库表头一致）

| 列 | 含义 |
|----|------|
| `claim_id` | 稳定编号，如 C007 |
| `statement` | 一句可检验主张（避免「显著提升」而无指标） |
| `section` / `figure_or_table` | 正文锚点 |
| `comparison_id` | 与 `stats_summary*.csv` 中列一致；多对比用 `/` 分隔 |
| `evidence_paths` | 可机读路径；**禁止**在单元格内使用未转义的竖线字符（避免 Markdown 表断裂） |
| `protocol_variant` | `unified_full_protocol` 或 `ablation_*` / `exploratory` |
| `stat_key` | 如 `R.paired_delta` |
| `acceptance_criteria` | 通过判据（p、效应量、n 等） |
| `status` | `done` / `pending`；**仅 `done` 可进摘要/结论的确定性量化句** |

### 5.4 建议填写顺序

1. `06-实验设置.md` → 2. `07-主结果.md` → 3. `08`、`09` → 4. 回填 `01`、`11` → 5. 更新 `claim_traceability.md` 为 `done`。

### 5.5 主文 vs 消融 vs 归档路径（防混写）

| 叙事位置 | 允许绑定的 `protocol_variant` | 典型路径 |
|----------|------------------------------|----------|
| **§07 主结果、C007** | `unified_full_protocol` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.*`（**`gradient_mode=full`** 与 manifest 一致） |
| **§09 梯度组成、C009** | `ablation_gradient` | `results/ablation_snapshots/gradient_*`、`full_baseline/`、日志；**不得**把 `R_s_only` 产出混写入上表默认路径 |
| **§09 组件 / MLE、C004/C005** | `ablation_components` / `ablation_mle` | 以矩阵登记为准；与 **C009 分 claim** |

### 5.6 统计呈现与 `tifs_stats.py` 对齐（G2/G3）

- **delta 的 95%CI**：当前主线由 **`mean_std_ci95_t`** 生成列 `ci95_low` / `ci95_high`（见 `experiments/tifs_stats.py`）。**论文 `06` 须写明**「run 级差分均值的 CI 算法」；若改 bootstrap，须升 `PROTOCOL_VERSION` 并重算全量统计。  
- **检验**：正态性门控后 **t / Wilcoxon**；`p_value_holm` 为方法族 Holm；**消融多假设**用 **FDR（BH）** 须在 `09` 或附录声明，且与主文 Holm **分族**。  
- **效应量**：列 `effect_size` + `effect_size_name`；勿手写与 CSV 不一致的符号或名称。

---

## 6. 实验记录 JSON（实验主用）

每条阶段记录至少含：`timestamp_utc`、`platform`、`experiment_id`、`run_id`、`phase`、`layer`、`attack_label`、`attack_params`（无攻击：`none` / `{}`）。

推荐另含：`protocol_variant`、`budget_variant`（`raw` / `fair`）、`git_commit` 或镜像 digest、`random_seed`、`threat_model_ref`。

阶段标签：`pre_attack` → `attack_ramp` → `under_attack` → `recovery` → `post_recovery`。

**示例（片段）**：

```json
{
  "timestamp_utc": "2026-04-16T12:00:00Z",
  "platform": "Eth-Cloud",
  "experiment_id": "EC-LAT-001",
  "run_id": "EC-LAT-001-R03",
  "phase": "under_attack",
  "layer": "network",
  "attack_label": "netem_delay_loss",
  "attack_params": { "delay_ms": 200, "loss_pct": 2.0 },
  "protocol_variant": "unified_full_protocol",
  "budget_variant": "fair",
  "git_commit": "abcdef012345"
}
```

---

## 7. 交付前验收（总控汇总自检）

- [ ] `protocol/unified_full_protocol.md` 与 `protocol/threat_model.md` 已落库且版本可追溯  
- [ ] `docs/论文初稿/` 下 12 章分文件 + `claim_traceability.md`  
- [ ] 主文图表均指向 `protocol_variant=unified_full_protocol` 的统计产物  
- [ ] 关键对比附有检验名称、p、效应量；多样本对比说明多重比较处理  
- [ ] raw-budget 与 fair-budget 分文件或分表  
- [ ] 无密钥/口令写入仓库  
- [ ] **`qa/tifs_gate_report.md`**：G1–G6 逐项勾选 + 证据路径一句（见总控 skill）  
- [ ] **叙事—证据一致**：`04`/`06` 中「主实验平台」表述与 `results/statistics/` **实际闭环**一致；EC/BTC 无统计文件则不得写「已完成主实验」类措辞  
- [ ] **`08-攻击类型分析.md`**：每个主文攻击相关表/句可映射到 `comparison_id` + `stats_summary` 行，或显式声明「当前版本仅…」  
- [ ] **`paper_en/`**（若使用）：与中文稿 **claim、表号、口径** 同步，避免英文超前主张  
- [ ] **消融**：`protocol/03` 登记的 ABL 行（如 ABL-COMP、ABL-MLE）与 `09` 表号、C004/C005 状态一致；梯度消融不占用 C004  

---

## 8. 反模式与安全

**反模式**：矩阵未登记却写主文优势；缺已声明强度档位却写「跨强度单调」；主文混入 `exploratory`；摘要/结论无量化 Claim 追溯；图注不写 **n** 与误差条含义（SD/SE/CI）；论文列名与 `tifs_stats.py` 导出不一致；论文单文件混写全部章节；实验记录缺阶段标签。

**安全**：禁止在协议、论文、JSON、日志中写入 SSH 口令、私钥、JWT、API Token；脱敏规则写在 `12-附录.md` 等处说明。

---

## 9. 委派边界（总控仲裁）

- **实验**：只承诺可机读数据、统计与追溯；不因「叙事需要」改 `experiment_id` 或矩阵外对比。  
- **写作**：不擅自改实验参数；若正文需要新对比，须经总控在矩阵中登记后再派实验。  
- **总控**：裁定主文是否误引消融路径；未过 G1–G6 不得进入「终稿」表述。

---

## 10. TIFS 审稿高风险登记表（写作 / 实验交叉自检）

| 风险 | 典型表现 | 缓解动作 |
|------|----------|----------|
| **R1 scope–evidence** | §4/§6 写「EC 主实验」，但 `results/statistics` 无 EC 行 | 收紧叙事为「ED 已闭环 + EC/BTC 计划中」或补齐 EC 统计与 C001 |
| **R2 主文混入消融** | 摘要写梯度档对比却引用 `results/statistics` | 消融仅 §09 + `ablation_*` 路径 + C009；主文仅 C007 |
| **R3 CI / 检验解释** | Wilcoxon 检验仍写「t-CI」无说明 | `06` 写明 delta 的 CI 算法；非参数检验与 CI 的并列规则与代码一致 |
| **R4 cherry-picking** | §07 每场景只一行基线 | 附录全基线表（如 A-1）+ 正文声明 Holm **族内**全集 |
| **R5 攻击章空心化** | `08` 大矩阵无对应 `stats_summary` | 删未跑 attack 行或改为附录计划表，与 `claim_traceability` 对齐 |
| **R6 消融统计弱** | 仅描述两目录均值差、无 run 配对 | 对同 `run_id` 跨 `gradient_mode` 做配对差分 + FDR（BH）族，写入 §09 |
| **R7 摘要超证据** | `pending` claim 的数字进摘要 | 摘要每句映射 `done` claim；提交前跑一遍对照表 |

---

## 11. G1–G6 通过判据（细化，供 `qa/tifs_gate_report.md` 引用）

| 闸门 | 通过判据（摘要） |
|------|------------------|
| **G1** | `07`/`01`/`11` 无 `exploratory` / 未登记 `ablation_*` 数字；图优化主文绑定 **`gradient_mode=full`** |
| **G2** | 主表含 mean/std/ci95；`06` 或 `results/statistics/README` 写明 CI 方法且与 `tifs_stats.py` 一致 |
| **G3** | `test_name`、`p_value` 或 `p_value_holm`、`effect_size` 列齐全；Holm/FDR 族与矩阵 § 一致 |
| **G4** | `04` 含五字段 + 非目标；与 `protocol/threat_model.md` 无冲突 |
| **G5** | fair/raw 分列或分节；预算敏感性有表或 claim（如 C003） |
| **G6** | 每主文表行可指到 `comparison_id` + 文件路径 + manifest；ED 图优化含 **`run_eth_docker_experiments.py`** 链 |
