# TIFS 闸门报告（G1–G6）

> 由 **tifs-chief-coordinator** 在阶段验收或投稿前更新。未通过项 = **P0**，须在 `plans/next_actions.md` 有对应条目与判据。  
> 共用定义见：`.cursor/skills/TIFS_REFERENCE.md`（§3、§10、§11）。

**日期**：2026-04-22  
**协议版本**：`experiments/experiment_protocol.py` → `PROTOCOL_VERSION` = `tifs-freeze-v3`  
**主文定量闭环平台**（本版本实际存在 `results/statistics/` 证据的）：Eth-Docker

---

## G1 主文口径（unified_full_protocol）


| 检查项                                                                                           | 通过  | 备注 / 路径 |
| --------------------------------------------------------------------------------------------- | --- | ------- |
| `01`/`07`/`11` 无 `exploratory` 或未登记 `ablation_`* 的确定性量化句                                      | ☑   | `claim_traceability` 中 done 项仅含 unified/ablation 已登记路径 |
| 图优化主文绑定 `gradient_mode=full` 与 `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.*` | ☑   | C007 与 `07-主结果` 对齐 |
| 消融数字仅出自 `ablation_*` 路径（如 `results/ablation_snapshots/…`）与 C009 等                             | ☑   | C004/C005/C009 仅引用消融路径 |


---

## G2 均值、方差、95%CI


| 检查项                                                                 | 通过  | 备注                     |
| ------------------------------------------------------------------- | --- | ---------------------- |
| 主表含 mean / std / ci95_low / ci95_high（或与 `tifs_stats.py` 导出列等价）     | ☑   | `07`、`09` 与 `stats_summary*` 对齐 |
| `06-实验设置.md`（或统计 README）写明 **delta 的 CI 算法**且与 `tifs_stats.py` 实现一致 | ☑   | 当前主线：`mean_std_ci95_t` |


---

## G3 检验、p、效应量、多重比较


| 检查项                                                       | 通过  | 备注  |
| --------------------------------------------------------- | --- | --- |
| 关键行含 `test_name`、`p_value` 或 `p_value_holm`、`effect_size` | ☑   | C003/C005/C007/C009 与表 9-1、9-2 已含 |
| Holm 族（主文方法对比）与 FDR 族（消融）**分族**且在正文或附录声明                  | ☑   | `09` 已声明 FDR(BH) 与主文 Holm 分族 |
| 与 `protocol/03_experiment_matrix.md` 中多重比较策略一致            | ☑   | 当前 ED 主线一致；EC/BTC 待补跑 |


---

## G4 威胁模型


| 检查项                             | 通过  | 备注  |
| ------------------------------- | --- | --- |
| `04-问题定义与威胁模型.md` 含五字段 + 非目标边界  | ☑   | 已完成 |
| 与 `protocol/threat_model.md` 一致 | ☑   | 已完成 |


---

## G5 raw / fair 分报


| 检查项                            | 通过  | 备注           |
| ------------------------------ | --- | ------------ |
| 主排序口径为 fair；raw 仅敏感性且有表或 claim | ☑   | C003、表 7-5 |


---

## G6 可追溯


| 检查项                                                                                    | 通过  | 备注                      |
| -------------------------------------------------------------------------------------- | --- | ----------------------- |
| `claim_traceability.md` 中每个 `done` 主张含 `evidence_paths` + `comparison_id` + `stat_key` | ☑   | C003/C005/C006/C007/C009 |
| Eth-Docker 图优化链：采集聚合 → `run_eth_docker_experiments.py` → manifest                      | ☑   | 见 `protocol/04` §二、C007 |


---

## 叙事—证据一致性（TIFS §10 R1）


| 检查项                                                                       | 通过  | 备注  |
| ------------------------------------------------------------------------- | --- | --- |
| `04`/`06` 的平台口径表述与 `results/statistics/` 实际文件一致（如“本版 ED 闭环，EC/BTC 待本地补跑”） | ☑   | 已对齐 |
| `08-攻击类型分析.md` 无「无统计行支撑」的伪主文表                                             | ☑   | 表头改为“本版本状态” |
| `paper_en/`（若用）与中文稿 claim / 表号对齐                                          | ☑   | `MANUSCRIPT_SCOPE_en.md` 已同步 |


---

## 签字 / 备注

- 本轮阻塞：EC/BTC 主文统计闭环尚未完成（C001/C002/C008 pending）；ED v3 回填链路已完成。  
- 已闭环项：C004/C005/C006/C007/C009/C011 已完成并与 `tifs-freeze-v3` 口径对齐；C010（自动调参试点）已完成 exploratory 证据。  
- 参数策略决策：`adaptive_vs_fixed`（ED, n=20）结果显示在线自适应未优于固定，主线继续采用固定权重 `w=(0.25,0.55,0.20)`；在线自适应仅保留为消融证据。  
- 新增进行中事项：ED 攻击场景已切换为 `1 + 2×3`（`ED-MAIN-BASE` + `LINK/NETEM-{low,mid,high}`）分档口径，主排序固定 `mid`。待 `n=20` 全档位统计落盘后，更新 C007 证据路径与第 7/8 章定量表。  
- 下一动作：见 `plans/next_actions.md` 中 P0-4（分档重跑）、P1-1 / P1-2（评估与约束完善）及 EC/BTC 本地补跑条目。 

