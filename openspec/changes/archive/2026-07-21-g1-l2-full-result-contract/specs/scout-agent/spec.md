## ADDED Requirements

### Requirement: L2 全量结果契约

`scout_batch` SHALL 返回三元组 `(full_results, usage_summary, failure_summary)`，为每只输入候选生成最终分类与可审计信息，shortlist SHALL 由 `full_results` 派生而非作为唯一返回。

- `full_results`：长度 SHALL 等于输入候选数 N（含 cache hit、degraded、缺 ticker / 非 dict 坏输入的 error result，**不丢任何输入**），每条含 `ticker`、`verdict`（`deep_dive`/`watch`/`skip`/`error`）及统一契约字段 `one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`；degraded 票额外含 `degraded`/`degraded_reason`；error 票额外含 `error`/`missing_fields`/`stage`/`input_index`（缺 ticker 时 `ticker` 为 `None`，不伪造，以 `input_index` 定位原始输入）。
- `usage_summary`：契约不变（`call_count`/`cache_hits`/`prompt_tokens`/`completion_tokens`/`total_tokens`），累加**所有** LLM 调用（含 watch/skip/error 路径，非仅 deep_dive），cache hit 不计 `call_count` 单独计 `cache_hits`。
- `failure_summary`：SHALL 把 `error`/`skip`/`watch`/`degraded` 分开计数，且 SHALL 可定位每个 `error` 的 ticker、原因与失败阶段：`{"errors":[{ticker,input_index,reason,stage}], "skips":n, "watches":n, "degraded":n, "unhandled_exceptions":0}`。
- `shortlist`：SHALL 由消费方从 `full_results` 派生为 `[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20（受既有 Top-20 Cap requirement 约束），MUST NOT 是 `scout_batch` 的唯一返回项。
- 整批运行 SHALL 无未处理异常：`failure_summary["unhandled_exceptions"] == 0`。单只采集/特征计算/LLM 调用失败、缺 ticker、非 dict 坏输入 SHALL 计入 `errors` 而非中断整批——输入校验 SHALL 在异常捕获范围内，坏输入 MUST NOT 逃逸 `asyncio.gather`。

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

#### Scenario: 缺 ticker 的输入不丢失

- **WHEN** `scout_batch` 收到含缺 ticker 候选（如 `{}`）的输入
- **THEN** 该候选 SHALL 在 `full_results` 中（长度 == 输入 N），`verdict` 为 `error`，`ticker` 为 `None`（不伪造），含 `input_index` 定位原始输入，并计入 `failure_summary["errors"]`

#### Scenario: 非 dict 坏输入不逃逸整批

- **WHEN** `scout_batch` 收到非 dict 输入（如 `None`）
- **THEN** 该输入 SHALL 不抛异常逃逸 `asyncio.gather`，返回 `verdict=error` 的 result（`stage=unexpected_exception`），整批继续，`unhandled_exceptions` SHALL 为 0

#### Scenario: error result 满足 full-result 字段契约

- **WHEN** 候选走 insufficient_data 或 LLM 调用失败路径生成 `verdict=error` 的 result
- **THEN** 该 error result SHALL 含与正常 result 相同的契约字段 `one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`（空数组/默认值），MUST NOT 只有 `ticker`/`verdict`/`error`

## MODIFIED Requirements

### Requirement: Top-20 Cap

Scout SHALL limit the deep_dive shortlist to at most 20 candidates, sorted by confidence descending, to maintain AD-03 cost constraint (200→20 for L3). `scout_batch` SHALL return `full_results`（每只输入一条，含全部 verdict 分类），NOT return the shortlist as its sole output; the shortlist SHALL be a derived view the consumer computes from `full_results` as `[r for r in full_results if verdict=="deep_dive"]` sorted by `confidence` descending, capped at 20.

> g1-l2-full-result-contract 修改：原 requirement 要求 Scout「return only the top 20」，与新「L2 全量结果契约」矛盾（scout_batch 现返回 full_results，shortlist 由消费方派生）。cap 语义不变（≤20、按 confidence 降序），仅改承载位置——从「scout_batch 直接返回」改为「消费方从 full_results 派生」。

#### Scenario: Deep dive cap

- **WHEN** more than 20 candidates have `verdict == "deep_dive"` in `full_results`
- **THEN** the shortlist derived from `full_results` SHALL contain only the top 20 by confidence descending

#### Scenario: scout_batch returns full_results not shortlist

- **WHEN** `scout_batch(candidates)` returns
- **THEN** the first return item SHALL be `full_results`（length == N, 含 deep_dive/watch/skip/error）, NOT the top-20 shortlist; shortlist is a consumer-derived view

---

### Requirement: CLI Integration

The CLI SHALL provide a `scout` subcommand that reads L1 output (S5 schema), assembles feature snapshots for each candidate, calls the LLM in batch, and outputs the full results bundle: `full_results`（每只输入一条 verdict 分类）, `shortlist`（deep_dive 按 confidence 降序 top-20 派生视图，供 L3 消费）, `usage_summary`, and `failure_summary`. The shortlist is a derived view, not the sole persisted output.

> g1-l2-full-result-contract 修改：原 requirement 要求 CLI「outputs the filtered shortlist（verdict="deep_dive", top-20 cap）」，与新契约矛盾。CLI 现输出四字段 payload，shortlist 仍是 top-20 派生视图供 L3 不变，但不再唯一持久化——full_results + failure_summary 一并写，使 watch/skip/error 分布可审计。

#### Scenario: Scout command invocation

- **WHEN** user runs `python cli.py scout --input l1_output.json --output l2_shortlist.json`
- **THEN** the system SHALL read L1 candidates, call Scout batch, and write a payload of `full_results`/`shortlist`/`usage_summary`/`failure_summary` to the output file

#### Scenario: Missing input file

- **WHEN** user runs `scout` without `--input` and no L1 output is available
- **THEN** the CLI SHALL raise an error with a clear message
