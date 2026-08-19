## MODIFIED Requirements

### Requirement: 辩论缓存命中
同股同日内重跑时，系统 SHALL 仅在存在绑定同一 canonical ticker 与 `run_id` 的 G2
run-quality record，且该记录为 `status="complete"`、`final_quality_gate="passed"`
时命中 Council 成功缓存并跳过 LLM。仅有
`debate/{ticker}/{date}.md`、Round 1、方向性 verdict 或 legacy artifact 不构成
clean cache hit。

`warning`、`failed`、`incomplete`、`runtime_degraded` 与 `da_skipped` 结果 SHALL
保留为可读诊断证据，但 MUST NOT 命中成功缓存。缓存读取 MUST NOT 根据可解析
markdown、watchlist 文件存在或部分 round 自动升级状态。
缓存请求 SHALL 按本次 execution mode 过滤；`single_agent` 的 complete record
不得命中 `council` 请求，反之亦然。record payload、record path、debate artifact
必须绑定同一 canonical ticker 与 run_id。
成功缓存仅限当前日期的 run-scoped debate artifact；跨日记录 SHALL miss 并触发新 run。

#### Scenario: 合格完整运行命中成功缓存
- **WHEN** 同 ticker 的可复用结果有 `complete` quality record 且 final quality gate passed
- **THEN** `run_debate` SHALL 返回该完整结果而不调用 LLM

#### Scenario: R1-only markdown 不命中
- **WHEN** 当日 debate markdown 只含 Round 1 或没有合格 complete quality record
- **THEN** `run_debate` SHALL 视为 cache miss，MUST NOT 将其作为成功结果返回

#### Scenario: 非 complete 记录不命中
- **WHEN** 最近一次同 ticker 运行的 quality record 是 warning、failed、incomplete、runtime_degraded 或 da_skipped
- **THEN** `run_debate` SHALL 视为 cache miss，并保留该记录供诊断读取

#### Scenario: Execution mode 隔离
- **WHEN** 最近一次 complete record 的 execution mode 与本次请求不同
- **THEN** Council SHALL 视为 cache miss，并继续本次请求所需的编排模式
