## ADDED Requirements

### Requirement: Top 20 必须派生自固定 run 且身份可追溯

系统 SHALL 只从通过工程 Gate 的 pinned run 派生 Top 20。派生过程 MUST 记录 pinned run identity（run_id、profile_version、input_ticker_set_hash）与 derivation run identity，并满足绑定校验：derivation 的 `profile_version` 与 `input_ticker_set_hash` MUST 与 pinned run 相同，derivation 漏斗统计 MUST 与 pinned bundle 一致。Top 20 MUST 来自同一次 derivation 的候选排序，MUST NOT 混入其他 run、其他 profile 或其他输入集合的结果。

#### Scenario: 正常派生绑定固定 run

- **WHEN** 以 pinned bundle（run_id、profile_version、input_ticker_set_hash、input_tickers）执行 Top 20 派生，且 derivation 的 profile_version、input_ticker_set_hash 与漏斗统计均与 pinned 一致
- **THEN** Top 20 记录 SHALL 全部携带同一 pinned run_id、profile_version 与 input_ticker_set_hash，并 SHALL 记录 derivation run_id 与 `derivation_kind`

#### Scenario: 规则版本或输入集合不一致时阻断

- **WHEN** derivation 的 profile_version 或 input_ticker_set_hash 与 pinned run 不一致
- **THEN** 系统 SHALL 标记结果为 `not_evaluable` 并记录原因，MUST NOT 输出 Top 20 Gate 通过结论

#### Scenario: 漏斗统计漂移时阻断

- **WHEN** derivation 的漏斗统计（after_hard_gates / after_factors / after_heat_filter）与 pinned bundle 的 funnel 不一致
- **THEN** 系统 SHALL 标记结果为 `not_evaluable` 并记录漂移项，MUST NOT 继续派生 Top 20 Gate

### Requirement: Top 20 数量与排序确定

Top 20 SHALL 取 derivation 候选列表的前 20 只，排序 MUST 为 derivation 的 canonical 候选顺序（adjusted_composite 降序，heat filter 之后）。候选不足 20 只时 SHALL 只保留实际数量，MUST NOT 通过降低门槛补足。

#### Scenario: 候选充足取前 20

- **WHEN** derivation 产生不少于 20 只候选
- **THEN** Top 20 SHALL 恰好为 20 只，rank 从 1 到 20 连续，且顺序与 derivation 候选顺序一致

#### Scenario: 候选不足不凑数

- **WHEN** derivation 候选少于 20 只
- **THEN** Top 20 SHALL 等于实际候选数量，Gate 阈值 SHALL 按实际数量的 ≥70% 计算，MUST NOT 补足到 20

### Requirement: 逐只复核记录完整且合法

每只 Top 20 SHALL 拥有一条用户复核记录，包含 ticker、rank、pinned run identity、用户判断标签与逐只非空理由。判断标签 MUST 属于枚举：`worth_further_research`、`not_worth_further_research`、`unable_to_judge_insufficient_data`。记录缺失、重复、rank/ticker 不匹配、标签非法或理由为空 MUST 阻断 Gate 计算，MUST NOT 静默接受。

#### Scenario: 记录不完整阻断 Gate

- **WHEN** Top 20 中任一只缺少复核记录、存在重复记录，或 rank/ticker 与 derivation 不匹配
- **THEN** 系统 SHALL 拒绝计算 Gate 并标记 `not_evaluable` 或报错，MUST NOT 仅凭汇总比例出结论

#### Scenario: 非法标签报错

- **WHEN** 任一复核记录的 label 不属于枚举值
- **THEN** 系统 SHALL 报错并指明非法 label 与对应 ticker，MUST NOT 将其归类到任何合法标签

#### Scenario: 空理由阻断

- **WHEN** 任一复核记录的 reason 为空或仅空白字符
- **THEN** 系统 SHALL 阻断 Gate 计算并指明对应 ticker

### Requirement: 70% Gate 判定严格三态

Gate SHALL 仅在全部 Top 20 复核记录合法后计算。`worth_further_research` 数量占比 ≥70%（`worth_count * 10 >= n * 7`）时 verdict 为 `passed`；占比不足时为 `failed`；身份不一致或记录非法时为 `not_evaluable`。`failed` 与 `not_evaluable` MUST NOT 被写成 `passed` 或 G1 capability passed。

#### Scenario: 达到阈值通过

- **WHEN** 20 只记录全部合法且 worth_research_count 为 14 或以上
- **THEN** gate_verdict SHALL 为 `passed`，evidence SHALL 记录逐只记录、计数与比例

#### Scenario: 未达阈值失败

- **WHEN** 20 只记录全部合法且 worth_research_count 少于 14
- **THEN** gate_verdict SHALL 为 `failed`，evidence SHALL 保留全部逐只记录与失败统计，且 MUST NOT 出现 capability passed 表述

#### Scenario: 不可判定不冒充通过

- **WHEN** 派生身份绑定失败或复核记录非法
- **THEN** gate_verdict SHALL 为 `not_evaluable` 并记录原因，MUST NOT 输出 `passed`

### Requirement: Evidence 可审计并保留原始记录

Gate evidence SHALL 保留 pinned/derivation identity、完整 Top 20 逐只记录、用户逐只标签与理由、统计汇总和 gate_verdict。Evidence MUST NOT 用 mock、fixture、历史 debate/watchlist 结果或模型输出冒充用户复核。运行产物 SHALL 写入 gitignore 的 evidence 目录，最终复核副本 SHALL 归档到本 change 的 evidence 目录并登记 SHA-256。

#### Scenario: evidence 保留逐只审计链

- **WHEN** Gate 计算完成（无论 passed/failed/not_evaluable）
- **THEN** evidence SHALL 包含每只 Top 20 的 rank、ticker、run identity、用户 label 与 reason，以及 worth/not_worth/unable 计数、比例与 verdict

#### Scenario: 缺少逐只记录的输入被拒绝

- **WHEN** finalize 输入只包含汇总比例而没有逐只复核记录
- **THEN** 系统 SHALL 拒绝生成 Gate evidence 并报错

### Requirement: 本 child 不改变 umbrella closure 与 G2 边界

本 child SHALL 只服务于 G1 umbrella 6.1/6.2 的证据链。它 MUST NOT 修改 umbrella tasks 的 7.1/7.2/7.3，MUST NOT 在用户完成逐只复核前勾选 6.1/6.2，MUST NOT 宣称 G1 capability passed，且 MUST NOT 触发 G2/G3 能力或采集。

#### Scenario: 用户未完成复核不勾选 Gate

- **WHEN** 实现与测试完成但用户尚未提交逐只复核记录
- **THEN** umbrella tasks 6.1/6.2 SHALL 保持未勾选，本 child SHALL 将真实用户复核列为待执行步骤
