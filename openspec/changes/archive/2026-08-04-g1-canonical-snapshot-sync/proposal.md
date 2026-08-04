## Why

当前 G1 仍依赖逐股在线 fetcher 和分维度 cache，raw response、normalized value、field status 和 provider provenance 没有统一的 snapshot 边界。M1 已冻结 provider contract，因此现在需要把可信数据保存为可复现的 canonical snapshot，但不改变现有筛选消费者或接入未经 qualification 的 provider。

## What Changes

- 新增 canonical snapshot sync 能力，明确 raw response 与 canonical value 的分层。
- 为每次 snapshot 生成 run_id、ticker set hash、source-set hash、as-of、schema version 和 manifest。
- 保存字段级 provenance/status/eligibility sidecar，显式保留 source failure、degraded、conflict 和 stale 状态。
- 支持从现有 cache/fetcher 结果生成兼容 snapshot，不覆盖原始 cache，不把 LongPort/Longbridge shadow 数据混入正式值。
- 为现有 G1 消费者提供 sidecar-compatible 读取边界；本 change 不改 staged screening 或 provider batch adapter。

## Capabilities

### New Capabilities

- `g1-canonical-snapshot-sync`: 将已验证的 raw/provider evidence 转换为可复现、可审计、带 manifest 的 canonical snapshot。

### Modified Capabilities

无。本 change 先新增 snapshot 边界，不直接修改现有 ranking 或筛选 requirement。

## Impact

- 新增 snapshot manifest、canonical record、sidecar reader/writer 和 deterministic tests。
- 复用 `provider-contract-and-provenance` 的 FieldEvidence/status/eligibility 语义。
- 不新增依赖，不改变现有 `data/cache` JSON 格式，不接入 LongPort/Longbridge。
- 为后续 `g1-provider-batch-adapter`、staged screening 和 G1 real Gate 提供输入。
