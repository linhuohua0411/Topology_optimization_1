# 论文初稿（分章总控）

本目录是中文论文分章稿的唯一权威路径。所有主文量化结论必须能回溯到 `results/statistics/` 与 `claim_traceability.md`。

## 目录与顺序

- `00-全文标题.md`
- `01-摘要.md`
- `02-引言.md`
- `03-相关工作.md`
- `04-问题定义与威胁模型.md`
- `05-方法.md`
- `06-实验设置.md`
- `07-主结果.md`
- `08-攻击类型分析.md`
- `09-消融与敏感性.md`
- `10-局限性.md`
- `11-结论.md`
- `12-附录.md`
- `claim_traceability.md`

## 当前证据口径（2026-04）

- 主文已闭环平台：**Eth-Docker**
- 当前主线实验：`1 + 2x3`（`ED-MAIN-BASE` + `ED-MAIN-LINK/NETEM-{low,mid,high}`）
- 主文统计口径：`unified_full_protocol` + `fair-budget` + `gradient_mode=full`
- 当前回填批次样本量：`n=10`（若补跑 `n=20`，需整章重算并统一替换）

## 章节状态速览

- **已回填主文核心**：`01-摘要.md`、`06-实验设置.md`、`07-主结果.md`、`08-攻击类型分析.md`、`11-结论.md`
- **追溯已更新**：`claim_traceability.md`（C007 等 `done` 条目可回溯到 ED 统计文件）
- **待继续打磨**：`09-消融与敏感性.md`、`12-附录.md`（仍有待补跑项与定稿前同步项）
- **待平台补跑后回填**：EC/BTC 相关主文结论（C001/C002/C008 仍 `pending`）

## 关键数据路径（写作必引）

- 场景统计：`results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.{csv,json}`
- 运行清单：`results/statistics/ED-MAIN-*/run_manifest_graph_optimizer.json`
- 行级记录：`results/raw/ED-MAIN-*/results_rows_graph_optimizer.json`

## 当前待办清单（高优先级）

- 在 `claim_traceability.md` 中完成 C001/C002/C008 的证据回填（需 EC/BTC 统计产物）
- 清理以下待补跑/待定稿项：
  - `08-攻击类型分析.md`（表格模板行与结论模板）
  - `09-消融与敏感性.md`（跨平台模板空表）
  - `12-附录.md`（Fabric 扩展结果与定稿版参考文献同步）
  - `06-实验设置.md` 中 EC/BTC 的补跑样本量与统计路径回填

## 使用规则（简版）

- 摘要与结论只允许写 `claim_traceability.md` 中 `status=done` 的定量主张
- 主文第 7 章只写 `unified_full_protocol`，消融数字不得混入
- 所有数字优先来自 `stats_summary_graph_optimizer.*`，禁止手写与 CSV 冲突的 p 值/效应量
