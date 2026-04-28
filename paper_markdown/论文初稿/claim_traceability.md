# Claim Traceability（论文初稿）

> 本文件用于维护 `paper_markdown/论文初稿/` 的主张-证据映射。  
> 仅 `status=done` 的主张可进入摘要与结论中的确定性表述。  
> **扩展实验（`extension`）**：可进入第 8 章、附录与扩展小节；**不得**冒充 C007 主文方法结论，亦不得写入摘要/结论的“方法优于基线”确定性句。

| claim_id | status | tier | claim_text | scope | evidence_type | comparison_id | stat_key | evidence_path | notes |
|---|---|---|---|---|---|---|---|---|---|
| C007-ED-R | done | main | 在 ED 主线场景下，`R.paired_delta` 相对四基线均为正，支持方法在综合鲁棒性上的稳定增益。 | `ED-MAIN-BASE/LINK/NETEM-{low,mid,high}` + fair + `gradient_mode=full` | Layer C + Layer D | `CMP-ED-MAIN-*-OUR-*` | `R.paired_delta` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.*` + `results/statistics/ED-MAIN-*/run_manifest_graph_optimizer.json` | 主文核心证据，仅在路径可见时保持 `done`。 |
| C007-ED-APL | done | main | 在 ED 主线场景下，`avg_path_len.paired_delta` 稳定为负且多数比较经 Holm 校正后显著。 | 同上 | Layer C + Layer D | `CMP-ED-MAIN-*-OUR-*` | `avg_path_len.paired_delta` | 同上 | 作为效率优势主证据。 |
| C007-ED-LCC | done | main | `lcc_ratio.paired_delta` 差分整体较小且部分场景饱和，不作为当前核心优势指标。 | 同上 | Layer C | `CMP-ED-MAIN-*-OUR-*` | `lcc_ratio.paired_delta` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.*` | 用于边界解释，避免过度宣称。 |
| C003-ED-BUDGET | done | main | `fair` 与 `raw` 口径下 ED 的排序方向总体一致，主文固定 `fair` 为排序口径。 | ED 主线 + `R.paired_delta` | Layer C | `CMP-ED-MAIN-*-OUR-*` | `R.paired_delta` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.*` | `raw` 用于稳健性解释，不参与主排序。 |
| C010-BTC-IMPACT | done | extension | BTC `mid` 档回填示出了攻击冲击量级画像，其中 `partition-mid` 连通冲击最强。 | `BTC-MAIN-{BASE,ECLIPSE-mid,PARTITION-mid,NETEM-mid}` | Layer A/B/C | `CMP-BTC-MAIN-*-UNDER-minus-PRE` | `peer_count_btc_avg.paired_delta_runs` 等 | `results/statistics/BTC/BTC-MAIN-*/stats_summary.*` + `results/statistics/BTC/BTC-MAIN-*/run_manifest.json` | **扩展实验**；不得写入摘要/结论的“方法优于基线”句。 |
| C010-BTC-DRIFT | done | extension | BTC `block_height_spread` 的攻击效应在扣除 `BASE` 背景漂移后仅 `partition-mid` 保持正净效应。 | `BTC-MAIN-{ECLIPSE-mid,PARTITION-mid,NETEM-mid}` | Layer C（extension） | `CMP-BTC-MAIN-*-UNDER-minus-PRE` | `block_height_spread.paired_delta_runs`（drift-adjusted） | `results/statistics/BTC/BTC-extension-drift-adjusted-summary.csv` | 扩展实验校正证据；仅用于第 8 章/附录机制解释。 |
| C010-BTC-SIG | pending | extension | （可选）BTC 方法比较显著性结论（含 Holm 校正）。 | BTC 全强度 + fair/raw + 多基线 | Layer C | 待补 | 待补 | 待补 | 仅当自愿将 BTC 升格为独立主证据链时置 `done`，且须与 C007 分表。 |
| C001-EC-MAIN | pending | main | Eth-Cloud 主场景结果可作为跨平台主文定量证据。 | `EC-MAIN` | Layer C + D | 待补 | 待补 | 待补 | 当前平台待本地部署补跑。 |

## 使用规则

1. 摘要与结论只能引用本表中 `status=done` 且 `tier=main` 的主张。  
2. 任何“显著”措辞必须对应 `p_value_holm` 或等价校正字段。  
3. 若证据路径变更，需先更新本表再改正文引用。  
4. 若统计文件缺失或不可复核，相关主张应降级为 `pending`。  
5. `tier=extension` 的主张仅可出现在第 8 章、附录及第 7 章明确标注的扩展小节。  
## 主文证据索引（用于 AE/Reviewer 快速核对）

> 本索引将主文核心表格行映射到 `comparison_id + stat_key + 证据路径`。  
> 若正文表格更新，需同步更新该索引与附录 A.1。

| main_table | claim_id | comparison_id | stat_key | evidence_path |
|---|---|---|---|---|
| 表 7-3（ED-LINK-mid） | C007-ED-R | `CMP-ED-MAIN-LINK-mid-OUR-M-RESI` | `R.paired_delta` | `results/statistics/ED-MAIN-LINK-mid/stats_summary_graph_optimizer.csv` |
| 表 7-3（ED-LINK-mid） | C007-ED-APL | `CMP-ED-MAIN-LINK-mid-OUR-M-RESI` | `avg_path_len.paired_delta` | `results/statistics/ED-MAIN-LINK-mid/stats_summary_graph_optimizer.csv` |
| 表 7-3（ED-NETEM-mid） | C007-ED-R | `CMP-ED-MAIN-NETEM-mid-OUR-M-RESI` | `R.paired_delta` | `results/statistics/ED-MAIN-NETEM-mid/stats_summary_graph_optimizer.csv` |
| 表 7-3（ED-NETEM-mid） | C007-ED-APL | `CMP-ED-MAIN-NETEM-mid-OUR-M-ASIM` | `avg_path_len.paired_delta` | `results/statistics/ED-MAIN-NETEM-mid/stats_summary_graph_optimizer.csv` |
| 表 7-4（全场景总览） | C007-ED-R | `CMP-ED-MAIN-*-OUR-M-RESI` | `R.paired_delta` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv` |
| 表 7-4（全场景总览） | C007-ED-LCC | `CMP-ED-MAIN-*-OUR-M-RESI` | `lcc_ratio.paired_delta` | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv` |
| 表 7-5（预算敏感性） | C003-ED-BUDGET | `CMP-ED-MAIN-*-OUR-*` | `R.paired_delta`（fair/raw 对照） | `results/statistics/ED-MAIN-*/stats_summary_graph_optimizer.csv` |
| 第 7.3 节（BTC 扩展） | C010-BTC-IMPACT | `CMP-BTC-MAIN-*-UNDER-minus-PRE` | `peer_count_btc_avg.paired_delta_runs` 等 | `results/statistics/BTC/BTC-MAIN-*/stats_summary.*` |

## 维护规则（审稿版）

1. 摘要与结论只能引用本表前半部分 `tier=main + status=done` 的结论。  
2. `tier=extension` 仅用于第 8 章与附录，不得作为主文方法排序依据。  
3. 任何“显著”措辞必须能回指 `p_value_holm` 的具体行。  
4. 若提交包中证据路径不可见，对应主张必须降级为 `pending`。  
