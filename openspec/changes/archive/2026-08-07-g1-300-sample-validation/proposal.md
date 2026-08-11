## Why

G1 的 300+ 样本预检当前依赖东财全市场 spot 和行业映射，外部取数阻塞使可控的抽样契约无法离线开发和验证。需要建立与真实 consumer 一致、可注入且确定性的 contract-fixture foundation，先验证样本选择边界与失败可见性，但不把 fixture 结果当作 G1 Capability Gate 证据。

## What Changes

- 新增 `g1-300-sample-validation` 离线能力，接收 spot 形状数据与行业映射，输出确定性的 ticker 列表、逐票 strata 元数据和汇总设计信息。
- 固定随机种子、输入排序、行业覆盖/配额/上限、ST/小市值/负 PE/过热风险层、去重和 unmapped industry 行为。
- 明确缺失值与 `invalid_value` 的处理，保留 `complete`、`degraded`、`source_failed`、`record_not_found` 等状态，不静默伪造成功。
- 固定“样本数至少 300 才具有 full-market 语义”的输出契约；不足 300 时显式标记 insufficient/development 状态。
- 输出复用 canonical ticker、run identity、input hash、`as_of` 和 provenance 约束，并明确标记 `fixture/reference` 或 `simulated/development`。
- 仅建立可测试的离线 selector/contract foundation；不调用 AkShare、东财、其他 provider 或 LLM，不修改 L1 规则、provider、G2/G3 或 Capability Gate 状态。

## Capabilities

### New Capabilities

- `g1-300-sample-validation`: 为 G1 规模预检提供可注入、确定性的离线验证样本选择与 contract-fixture 输出能力。

### Modified Capabilities

无。现有 `g1-fast-personal-value-screening` umbrella、`data-minimum-contract` 和 canonical identity contract 只作为约束与引用，不修改其 requirement。

## Impact

- 新增离线 selector/contract 实现及其行为测试，预计位于 `value-screener/` 的 G1 validation/sample 相关模块。
- 新增 OpenSpec capability spec、design 与 tasks。
- 不新增依赖，不改用户未跟踪的 `value-screener/scripts/build_validation_sample.py`，不生成 live sample、provider qualification、canonical promotion 或 G1 evidence bundle。
