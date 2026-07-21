## ADDED Requirements

### Requirement: L2 全量结果契约

`scout_batch` SHALL 返回三元组 `(full_results, usage_summary, failure_summary)`，为每只输入候选生成最终分类与可审计信息，shortlist SHALL 由 `full_results` 派生而非作为唯一返回。

- `full_results`：长度 SHALL 等于输入候选数 N（含 cache hit 与 degraded 的票，不丢），每条含 `ticker`、`verdict`（`deep_dive`/`watch`/`skip`/`error`）、`one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`，degraded 票含 `degraded`/`degraded_reason`，error 票含 `error`/`missing_fields`。
- `usage_summary`：契约不变（`call_count`/`cache_hits`/`prompt_tokens`/`completion_tokens`/`total_tokens`），累加**所有** LLM 调用（含 watch/skip/error 路径，非仅 deep_dive），cache hit 不计 `call_count` 单独计 `cache_hits`。
- `failure_summary`：SHALL 把 `error`/`skip`/`watch`/`degraded` 分开计数，且 SHALL 可定位每个 `error` 的 ticker、原因与失败阶段：`{"errors":[{ticker,reason,stage}], "skips":n, "watches":n, "degraded":n, "unhandled_exceptions":0}`。
- `shortlist`：SHALL 由消费方从 `full_results` 派生为 `[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20（受既有 Top-20 Cap requirement 约束），MUST NOT 是 `scout_batch` 的唯一返回项。
- 整批运行 SHALL 无未处理异常：`failure_summary["unhandled_exceptions"] == 0`。单只采集/特征计算/LLM 调用失败 SHALL 计入 `errors` 而非中断整批。

> 背景：G1 umbrella `personal-value-screening` 的「完整漏斗与失败结果」requirement（D5）要求每只输入归属四类并保留阶段/理由/降级/失败信息，shortlist MUST 由全量结果派生。当前 `scout_batch` 返回点只留 `deep_dive`，watch/skip/error 被丢弃、无 failure_summary，shortlist 是唯一返回而非派生——本 requirement 闭合该缺口。AD-03：failure_summary 把 availability/error/degraded 分开计数，避免用 shortlist 掩盖失败分布。

#### Scenario: 全量结果含所有分类

- **WHEN** `scout_batch` 处理 3 只候选，LLM 分别返回 `deep_dive`/`watch`/`skip`
- **THEN** `full_results` SHALL 长度为 3，三条均含 `verdict` 字段（`deep_dive`/`watch`/`skip`），MUST NOT 只保留 deep_dive

#### Scenario: shortlist 由全量结果派生

- **WHEN** `full_results` 含 2 条 `verdict=="deep_dive"` 与若干 watch/skip
- **THEN** `shortlist` SHALL 等于 `[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20，MUST NOT 是 `scout_batch` 的独立返回项

#### Scenario: failure_summary 可定位失败 ticker 与原因

- **WHEN** 候选 `600002` 的 LLM 调用抛 `httpx.HTTPStatusError`
- **THEN** `failure_summary["errors"]` SHALL 含 `{"ticker":"600002","reason":<错误描述>,"stage":<失败阶段>}`，其他成功候选不受影响仍出现在 `full_results`

#### Scenario: error/skip/watch/degraded 分开计数

- **WHEN** 一批候选处理后含 1 只 error、2 只 skip、1 只 degraded（→watch）、1 只 deep_dive
- **THEN** `failure_summary` SHALL `{"errors":1, "skips":2, "watches":1, "degraded":1, "unhandled_exceptions":0}`（degraded 不计入 errors，单独计 degraded；watches 含 degraded 票的 watch 分类）

#### Scenario: 整批无未处理异常

- **WHEN** 处理过程中某只票触发非预期异常（脏数据/类型错位）
- **THEN** 该只 SHALL 计入 `failure_summary["errors"]`，`unhandled_exceptions` SHALL 为 0，整批 SHALL 继续不中断

#### Scenario: usage_summary 累加所有调用

- **WHEN** 一批候选含 deep_dive/watch/skip 三种 verdict 各调用 1 次 LLM
- **THEN** `usage_summary["call_count"]` SHALL 为 3（非仅 deep_dive 的 1），`cache_hits` SHALL 单独计 cache 命中数
