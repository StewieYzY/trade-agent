## ADDED Requirements

### Requirement: L2 数据降级模式（优雅降级）
`scout-agent` SHALL 在 features 不充分但非完全缺失时，从 fail-fast 改为优雅降级模式继续运行，不中断整批：

- 当 `critical_fields`（name/industry/market_cap）齐全但 `financials_floor`（pe_ttm/roe_3y/net_margin）任一缺失时，触发降级（区别于完全 insufficient 的 fail-fast）
- 降级行为：`confidence` 上限 50（`confidence_cap=50`）、`verdict` 强制 `"watch"`、标注 `degraded: true` + `degraded_reason: "incomplete_financials"`
- 降级模式 SHALL 继续调用 LLM（用不完整 features），不跳过整只，避免 200 只批处理因个别数据不全而中断

> 背景：Kimi 校准要点 4（优雅降级，数据不可得时切简化模型继续运行）。区别于 L3 的 fail-fast——L2 是 200 只批处理，单只 fail 中断整批不可接受；L3 是单只深研，数据不足硬出结论是 600900 复读茅台悲剧（[[design]] D5）。

#### Scenario: financials 不齐但 basic 齐触发降级
- **WHEN** `assemble_snapshot` 返回 name/industry/market_cap 齐全，但 pe_ttm/roe_3y/net_margin 任一为 None
- **THEN** scout SHALL 进入降级模式：confidence 上限 50、verdict 强制 "watch"、标注 `degraded: true`

#### Scenario: 降级模式继续调用 LLM
- **WHEN** 某只票触发降级模式
- **THEN** scout SHALL 仍调用 LLM（用不完整 features），不跳过该只，结果含 `degraded: true` 标记

#### Scenario: critical_fields 完全缺失仍 fail-fast
- **WHEN** `assemble_snapshot` 返回 name 或 market_cap 缺失
- **THEN** scout SHALL 保持现有 fail-fast（返回 `{"verdict": "error", "reason": "insufficient_data"}`），不进入降级模式

#### Scenario: 降级结果不进 deep_dive 短名单
- **WHEN** 降级模式的票 LLM 原本返回 `{"verdict": "deep_dive", "confidence": 70}`
- **THEN** 经降级处理后 `confidence` 上限为 50、`verdict` 强制 "watch"，不进入 deep_dive 短名单（避免数据不全的票占 L3 深研资源）
