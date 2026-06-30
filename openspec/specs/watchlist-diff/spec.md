## ADDED Requirements

### Requirement: 增量 diff 检测
系统 SHALL 对比当前 `watchlist/{date}.json` 与上一快照，检测变化。

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

### Requirement: 历史轨迹查询
系统 SHALL 提供某只股票的 N 日历史轨迹查询能力（通过 `monitor history` CLI 子命令暴露，内部由 `diff.py` 的 `history()` 函数实现）。

#### Scenario: 查询单只股票轨迹
- **WHEN** 查询某 ticker 的历史轨迹
- **THEN** 输出该 ticker 在所有快照中的 `l1_score` 走势、`stage` 变化、`l3_verdict` 变化、`pe_percentile_5y` 走势

#### Scenario: ticker 无历史记录
- **WHEN** 查询的 ticker 在所有快照中均不存在
- **THEN** 输出"无历史记录"

### Requirement: 触发 L2 重评估阈值
系统 SHALL 在 diff 检测到显著变化时触发 L2 重评估。

#### Scenario: candidate 新增触发 L2
- **WHEN** diff 检测到 candidate 新增（`added`）
- **THEN** 调用 `scout_batch` 对该 ticker 重新评估（绕过 24h 缓存）

#### Scenario: l1_score 变化 > 15 触发 L2
- **WHEN** diff 检测到 `l1_score` 变化 > 15
- **THEN** 调用 `scout_batch` 对该 ticker 重新评估

#### Scenario: l1_score 变化 <= 15 不触发 L2
- **WHEN** diff 检测到 `l1_score` 变化 <= 15
- **THEN** 不触发 L2 重评估，等待下次 weekly 周期

### Requirement: 触发 L3 深研阈值
系统 SHALL 在 L2 verdict 翻转时触发 L3 深研。

#### Scenario: L2 verdict 翻转为 deep_dive
- **WHEN** diff 检测到 `l2_verdict` 从 `pass`/`reject`/null 变为 `deep_dive`
- **THEN** 调用 `council` 对该 ticker 跑深研

#### Scenario: L2 verdict 未翻转
- **WHEN** `l2_verdict` 保持 `deep_dive` 或保持 `pass`/`reject`
- **THEN** 不触发 L3 深研，即使已有 L3 结果也不重跑
