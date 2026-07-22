## MODIFIED Requirements

### Requirement: 增量 diff 检测
系统 SHALL 对比当前 `watchlist` 快照与上一快照，检测变化。current 与 previous 快照的选定 SHALL 基于「真实生成时间」：聚合文件的 `generated_at` 字段（带时区 ISO 8601）按时间排序取最新为 current、次新为 previous。`generated_at` 缺失或非法的旧文件 SHALL fallback 到文件 mtime。MUST NOT 按文件名字典序排序选择（run_id 是 UUID4 无时间序，字典序最大者不一定是最后生成的 run）。

> g1-canonical-run-identity-repair 修改：G1-3 把聚合 watchlist 改为 run-scoped 命名 `{date}_{run_id[:8]}.json` 后，`get_latest_watchlist`/`get_previous_watchlist`（`monitor/diff.py`）原用 `sorted(..., reverse=True)` 按文件名字典序选「最新」——run_id 是 UUID4 无时间序，同日多个 run 时选到字典序最大的 hex 而非最后生成的 run。本修改要求按 `generated_at`（带时区 ISO 8601）排序选 latest/previous，mtime 仅 fallback。`generated_at` 字段已在 `watchlist-aggregation` canonical spec「watchlist JSON 结构」要求（ISO 8601 时间戳），本修改要求其带时区并用于 latest/previous 选定。两个函数 SHALL 共用同一选择逻辑。

#### Scenario: 首次运行无历史快照
- **WHEN** 不存在上一快照文件
- **THEN** diff 报告标注"首次运行，无历史对比"，产出当前快照供后续对比

#### Scenario: candidate 新增
- **WHEN** ticker 在 current 快照但不在 previous 快照
- **THEN** diff 报告标记为 `added`，严重度 `info`

#### Scenario: candidate 跌出
- **WHEN** ticker 在 previous 快照但不在 current 快照
- **THEN** diff 报告标记为 `removed`，严重度 `warning`

#### Scenario: l1_score 显著变化
- **WHEN** `abs(current.l1_score - previous.l1_score) > 10`
- **THEN** diff 报告标记为 `l1_score_changed`，严重度 `info`

#### Scenario: stage 升级
- **WHEN** candidate 的 `stage` 从 `l1` 变为 `l2` 或从 `l2` 变为 `l3`
- **THEN** diff 报告标记为 `stage_upgraded`，严重度 `significant`

#### Scenario: stage 降级
- **WHEN** candidate 的 `stage` 从 `l3` 变为 `l2` 或从 `l2` 变为 `l1`
- **THEN** diff 报告标记为 `stage_downgraded`，严重度 `significant`

#### Scenario: l3_verdict 变化
- **WHEN** `previous.l3_verdict != current.l3_verdict` 且均非 null
- **THEN** diff 报告标记为 `verdict_changed`，严重度 `significant`

#### Scenario: pe_percentile 触及低位阈值
- **WHEN** `previous.pe_percentile_5y >= 20%` 且 `current.pe_percentile_5y < 20%`
- **THEN** diff 报告标记为 `valuation_low`，严重度 `significant`

#### Scenario: latest/previous 按 generated_at 选定
- **WHEN** 同日存在多个 run-scoped 聚合文件 `{date}_{run_id_a[:8]}.json` 与 `{date}_{run_id_b[:8]}.json`，且 run_id_a 字典序大于 run_id_b 但 run_id_b 的 `generated_at` 时间更晚（后生成）
- **THEN** `get_latest_watchlist` SHALL 按 `generated_at` 返回 run_id_b 文件（真实最后生成），MUST NOT 返回字典序更大的 run_id_a 文件；`get_previous_watchlist` SHALL 返回次新的 run_id_a 文件

#### Scenario: generated_at 缺失 fallback mtime
- **WHEN** 某聚合文件无 `generated_at` 字段或字段非法（如 G1-3 前的旧 `{date}.json` 纯日期聚合文件）
- **THEN** 该文件 SHALL fallback 到文件 mtime 参与排序；新聚合文件 SHALL 写入带时区的 `generated_at`（ISO 8601，如 `2026-07-22T14:30:00+08:00`）
