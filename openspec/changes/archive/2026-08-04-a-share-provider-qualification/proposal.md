## Why

当前项目已有 AkShare、东财、同花顺等生产数据链路，也完成了 LongPort/Longbridge 的文档级字段映射，但尚未证明候选 provider 对 A 股实际返回、单位、报告期、权限和失败状态。现在需要用至少 5 只代表性 A 股做只读、字段级 runtime qualification，避免把文档能力或 mock 返回误当成可进入 G1/G2 的真实数据能力。

## What Changes

- 新增 A 股 provider qualification 能力，覆盖 LongPort/Longbridge 候选能力与现有基线 provider 的字段级对照。
- 对固定代表性 A 股执行只读 probe，覆盖静态信息、实时行情、计算指标、历史 K 线，以及 IS/BS/CF、历史估值、行业估值和 consensus 候选字段。
- 保存每次 probe 的 ticker、market、provider、method、raw response 摘要、字段映射、单位、报告期、as-of、权限/限流信息和失败状态。
- 区分 `record_not_found`、`source_failed`、`permission_denied`、`rate_limited`、`not_supported_for_market`、`invalid_value` 和 `not_evaluated`，禁止 silent fallback。
- 产出字段级差异报告和可供后续 `provider-contract-and-provenance` 使用的 evidence manifest。
- qualification 结果仅用于候选 provider 评估；未通过的字段不得进入 ranking、canonical snapshot、成长预期 diagnostic 或 capability Gate。

## Capabilities

### New Capabilities

- `a-share-provider-qualification`: 对候选和基线 provider 执行可复现、可追溯的 A 股字段级 runtime probe，并生成不影响生产链路的 qualification evidence。

### Modified Capabilities

无。本 change 只生成 qualification evidence，不修改现有 provider、ranking、canonical snapshot 或 G1/G2 runtime requirement。

## Impact

- 新增 qualification probe/manifest/report 工具及其测试或 fixture。
- 读取现有 provider adapter/fetcher 和字段映射文档，但不替换现有 provider chain。
- 可能需要使用已配置的 LongPort/Longbridge SDK 或只读 API 凭据；不新增依赖，缺少凭据或 provider 不可用时必须输出可审计的 blocked/未评估状态。
- 影响后续 `provider-contract-and-provenance`、`g1-canonical-snapshot-sync` 和 M4.5 输入资格判断，但不直接修改这些模块。
