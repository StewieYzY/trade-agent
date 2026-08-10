## Why

`g1-fast-personal-value-screening` 已定义 failure-visible canonical snapshot 作为 G1
下游输入，但当前 `read_snapshot()` 只返回未经身份和 schema 校验的原始 JSON。
Track A 需要一个稳定、只读、保留 provenance 的 consumer，避免下游通过猜测
`decision.json` 或默认值改变字段可用性与排序语义。

## What Changes

- 新增 `canonical-snapshot-consumer` capability，读取并校验
  `manifest.json`、`records.json`、`provenance.json`。
- 校验 `schema_version`、`run_id`、`plan_version`、canonical ticker identity
  和 `ticker_set_hash`。
- 提供稳定的 field-level consumer API，保留 value、status、reason、provenance、
  as_of 和 freshness。
- 对 rejected、not evaluated、source failed、invalid 或 stale 字段 fail closed，
  返回显式 `null` 和明确状态。
- 保证 consumer 只读，不调用 provider/LLM，不写入 cache、watchlist、debate、
  ranking 或 production snapshot。
- 本 child 只实现 canonical snapshot consumer；不实现 staged screening runtime、
  300+ 样本验证、全市场性能/成本 Gate、Top 20 验收或新的 Repair ID。

## Capabilities

### New Capabilities

- `canonical-snapshot-consumer`: 将已生成的 canonical snapshot 转换为稳定、
  可验证、保留 provenance 的 G1 下游输入契约。

### Modified Capabilities

无。`g1-fast-personal-value-screening` 作为 umbrella 被引用，不修改其既有
requirement。

## Impact

- 影响 `value-screener/data/lib/`，新增独立 consumer 模块及行为测试；并在
  `identity.py`/`canonical_snapshot.py` 共享明确的 snapshot ticker hash helper，
  不改变既有 manifest hash 的输出语义。
- 复用现有 `canonical_snapshot`、`identity` 和 `provenance` contract，不新增依赖。
- 不修改已归档 Change，不修改现有 G1 ranking 逻辑，不改变 canonical snapshot
  writer 的输出。
