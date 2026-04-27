# Unified Full Protocol（主文唯一口径）

> 本文档为 **unified_full_protocol** 的权威定义。主文结论、主图表与 `claim_traceability.md` 仅允许引用本协议下产生的统计与实验标识。

## 1. 研究问题与成功判据

- 问题陈述：在真实异构区块链网络（Ethereum PoS + Bitcoin 多 AS 广域拓扑）中，验证本文拓扑结构全局优化方法在攻击与网络扰动下是否可稳定提升鲁棒性与传播性能。
- 主指标：鲁棒性综合指标 `R`（及其分项 `Rs/Rc/Rr`）。
- 次要指标：`LCC`、`avg_path_length`、`components`、`peer_stability`、`fork_events`、`block_progress`、`reachable_ratio`（BTC）。
- 成功判据：在 `fair-budget` 条件下，相比主流基线在主指标上达到统计显著（p < 0.05）且效应量达到中等及以上（Cohen's d >= 0.5 或 Cliff's delta >= 0.33）。

## 2. 平台与规模

| 平台 | 是否纳入主文 | 节点规模 / 角色 | 备注 |
|------|----------------|------------------|------|
| Eth-Cloud | 是 | 100 节点（执行层+共识层，全员验证者） | 主实验平台 |
| BTC-Docker | 是 | 108 节点，12 AS，多矿工 | 主实验平台 |
| Eth-Docker | 是 | 108 节点（评估 107） | 受控复现实验 |
| Fabric-Docker | 否（附录） | 108 节点虚拟化广域网 | 外推验证 |
| Pol-Docker | 否（暂缓） | 100 节点规划 | 运行态未确认，不纳入主文定量结论 |

## 3. 软件与配置快照策略

- 版本锁定方式：镜像 digest + 仓库 commit hash + 关键配置快照。
- 配置快照存放路径约定：`results/traceability/config/`。
- 每次运行记录字段：`experiment_id`、`run_id`、`platform`、`git_commit`、`random_seed`、`protocol_variant`、`budget_variant`。

## 4. 实验阶段与时间轴

- 阶段定义：`pre_attack` -> `attack_ramp` -> `under_attack` -> `recovery` -> `post_recovery`。
- 每阶段时长：每阶段至少覆盖 3 个采样周期；攻击与恢复阶段至少覆盖 5 个采样周期。
- 采样周期（按平台）：
  - Eth-Cloud / Eth-Docker：30 s
  - BTC-Docker：10 s
  - Fabric-Docker（附录）：按 Prometheus 采样周期登记

## 5. 攻击与恢复（与 Threat Model 对齐）

- 纳入主文的 `attack_label`：
  - Eth：`none`、`random_remove`、`targeted_remove`、`adaptive_remove`、`link_down`、`tc_netem`
  - BTC：`none`、`eclipse(net_down/bird_peer_down)`、`partition(stop_transit)`、`tc_netem_delay_loss`
- 附录可选 `attack_label`：`bird_hijack`（BTC 路由扰动）、`tc_netem_profile`（Fabric）。
- 注入与恢复要求：注入前记录基线；注入后记录完整参数；恢复后验证网络恢复至可比较稳定状态；全过程写入 `attack_params`。

## 6. 重复与随机性

- 每条件重复次数 `n`：
  - 主文：`n = 20`
  - MLE 注入消融：`n = 30`
  - 附录探索：`n = 10`（仅辅助讨论）
- `random_seed` 策略：预生成种子池并固定映射；同一 `comparison_id` 下各方法使用一致种子序列；缺失运行必须补齐或整组剔除。

## 7. 统计与检验（主文层）

- 95%CI 方法：当前主线统一采用 t-interval（与 `experiments/tifs_stats.py::mean_std_ci95_t` 一致）；若切换为 bootstrap 版本，需在同一 `PROTOCOL_VERSION` 下同步更新协议并整体重算统计结果。
- 显著性检验流程：先做正态性检查（Shapiro-Wilk，alpha=0.05）；满足正态则 paired t，否则 Wilcoxon signed-rank。
- 效应量：paired t 报 Cohen's d（或 dz）；Wilcoxon 报 Cliff's delta（或 rank-biserial）。
- 多重比较策略：主文方法多组对比采用 Holm 校正；消融多项对比采用 FDR（Benjamini-Hochberg）。
- 关键对比列表：以 `protocol/03_experiment_matrix.md` 的 `comparison_id` 为唯一登记表。

## 8. 预算口径

- `raw-budget` 定义：按平台默认资源/连接/攻击注入能力直接运行，不做人为对齐。
- `fair-budget` 定义：在跨方法或跨平台对比时，对齐可操作预算（可改连边数、攻击强度区间、可达比例约束、运行时间窗）。
- 主文结论规则：主排序与主结论以 `fair-budget` 为准；`raw-budget` 仅用于敏感性与差异解释。

## 9. 结果纳入与追溯

- 仅 `protocol_variant=unified_full_protocol` 可进入 `07-主结果.md`、`01-摘要.md`、`11-结论.md`。
- `ablation_*` 仅进入 `09-消融与敏感性.md`。
- `exploratory` 仅进入 `12-附录.md`。
- 主文每条量化结论必须在 `docs/论文初稿/claim_traceability.md` 登记 `claim_id`、`evidence_paths`、`stat_key`，状态为 `done` 后方可写入摘要与结论。

## 10. 变更记录

| 版本 | 日期 | 变更摘要 |
|------|------|----------|
| v0.1 | 2026-04-17 | 建立协议模板 |
| v0.2 | 2026-04-17 | 实填主文平台、统计流程、预算口径与追溯规则 |
