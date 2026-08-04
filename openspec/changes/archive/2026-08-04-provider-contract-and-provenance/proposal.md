## Why

M1 qualification 已证明当前候选 provider 不能因文档存在或接口非空就直接进入生产链路，但项目还缺少统一的字段来源、单位、报告期、失败状态和冲突处理合同。没有这个合同，后续 canonical snapshot 仍可能把不同 provider 的不可比值合并成看似完整的数据。

## What Changes

- 定义统一的 provider metadata、field provenance、as-of/report period、unit/currency 和 qualification eligibility 合同。
- 定义字段状态：`available`、`partial`、`record_not_found`、`source_failed`、`permission_denied`、`rate_limited`、`not_supported_for_market`、`invalid_value`、`not_evaluated`。
- 定义多 provider 同字段冲突、单位不一致、报告期不一致和 stale 数据的处理规则。
- 定义 canonical snapshot 之前的 provenance-preserving normalized raw boundary。
- 规定未 qualification 字段不得作为隐式 fallback、ranking 输入、diagnostic 输入或 Gate 证据。
- 为现有 fetcher/cache 输出提供兼容的 sidecar metadata 形状，但不在本 change 实现 canonical snapshot sync。

## Capabilities

### New Capabilities

- `provider-contract-and-provenance`: 为数据字段定义来源、状态、时间、单位、冲突和后续消费资格的可审计合同。

### Modified Capabilities

无。本 change 先冻结跨 provider 合同，不直接改变现有 ranking 或 snapshot runtime requirement。

## Impact

- 新增 provider contract/provenance schema、校验工具和 deterministic tests。
- 影响后续 `g1-canonical-snapshot-sync`、provider batch adapter、G1 validation 和 M4 dossier 输入边界。
- 不新增外部依赖，不调用 LongPort/Longbridge，不替换现有 provider chain。
- 现有数据消费者继续读取原字段；兼容 metadata 通过 sidecar 或明确包装层提供，避免无计划 breaking migration。
