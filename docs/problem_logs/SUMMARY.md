# 问题日志压缩摘要

## 核心结论（截至第23次）

- ETH 真实网络：Ours 稳定提升，主结果约 `R 0.5528 -> 0.7981`（`+44.38%`）。
- DOT 真实网络：主流程 Ours 常见 `+0%`，但 failure mode 显示在更宽松 `k_max` 下可达约 `+4.94%~+4.98%`。
- 基线“全 0%”问题已定位并修复：从“中间态强制连通”改为“可配置的软惩罚”，ETH 基线恢复正增益。
- 公平性口径已增强：新增 fair-time 对比；下一步建议补 `edge + time` 联合公平预算。

## 已落地改动

- `src/models/baselines.py`
  - 增加 `allow_disconnected_intermediate`
  - 增加 `disconnect_penalty`
- `experiments/run_eth_real_experiments.py`
  - 增加 `5b. Fair-Time Baseline Comparison`
  - 结果写入 `comparison_fair_time`
- `experiments/run_real_dual_network_experiments.py`
  - 增加 `*_comparison_fair_time` 结果块
- `experiments/run_repro_tifs.py`
  - 提供一键入口：`--eth / --dual / --all`

## 最近一次全量实跑（第23次）

- 命令：`python experiments/run_repro_tifs.py --all`
- 总耗时：约 `79.4min`
- 结果：
  - ETH：Ours `+44.38%`
  - DOT：Ours `+0.00%`
  - DOT failure mode：`21` 组有增益，`6` 组无增益

## 后续最小必做

1. 在 ETH 或双网补一版 `edge + time` 联合公平预算结果；
2. 在正文明确“优化目标 R”与“攻击指标验证”的口径区别；
3. 保持每次更新单文件记录，不再扩展超长总日志。

