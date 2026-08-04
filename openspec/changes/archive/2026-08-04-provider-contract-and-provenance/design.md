## Context

当前 `data/fetchers` 返回的是面向消费者的 dict，部分字段带有失败标记，部分字段仍缺少 provider、单位、报告期和原始字段信息。M1 qualification runner 已能生成字段级 evidence，但后续 canonical snapshot 需要一个独立、不可被 provider adapter 随意解释的 contract。

本 change 只定义和校验 contract。它位于 provider raw response 与 canonical snapshot 之间，不要求现有消费者立即迁移，也不负责把任何候选 provider 标记为 qualified。

## Goals / Non-Goals

**Goals:**

- 冻结字段 provenance、status、unit/currency、as-of/report period、raw field 和 qualification eligibility。
- 提供可序列化、可校验、可作为 sidecar 的 metadata 结构。
- 定义同字段多 provider 冲突、freshness、单位和报告期不一致的 fail-closed 规则。
- 保留现有消费者字段，允许后续 adapter 逐步补充 metadata。

**Non-Goals:**

- 不实现 canonical snapshot storage、batch sync 或 ranking merge。
- 不新增 provider，不执行网络 probe，不接入 LongPort/Longbridge。
- 不把 `available` 自动等同于 `qualified_for_production`。
- 不用 `None`、零值或 first-non-empty 规则掩盖失败和冲突。

## Decisions

### D1. FieldEvidence 与 ConsumerValue 分离

`FieldEvidence` 保存 provider/raw/normalized/provenance/status；现有消费者值继续作为独立 payload。选择 sidecar 而不是立即重写所有字段，是为了降低迁移风险并避免把审计 metadata 混入计算逻辑。

### D2. status 与 eligibility 分离

`status=available` 只表示该次 provider 响应经过基本解析；`eligibility` 单独表达 `not_qualified`、`shadow_only` 或 `production_eligible`。本 change 只能产生前两者，不能产生 production eligibility。

### D3. 冲突默认 fail closed

同一 canonical ticker、field、as-of/report period 出现不同单位、币种、报告期或数值时，保留所有 evidence 并输出 `conflict`；不得自动平均、覆盖或选择 first-non-empty。只有显式 contract policy 才能选择一个来源。

### D4. 时间与单位是字段级必需判断

财务、估值和历史序列字段必须记录 `report_period` 或 `as_of`；金额和比率字段必须记录 unit/currency，无法确认时 status 降为 `not_evaluated`。文本字段可以没有 currency，但仍需 raw field 和 provider method。

### D5. provenance 只允许非敏感信息

保存 provider family/provider/method/market、raw field、response hash、retrieved_at、code version 和 source status；不得写 API key、Authorization、URL userinfo 或完整 secret。

## Risks / Trade-offs

- [Risk] 旧 fetcher 缺少 metadata → 通过 sidecar 标记 `metadata_incomplete/not_evaluated`，不静默补默认值。
- [Risk] 严格冲突规则降低可用率 → 先保留冲突 evidence，后续独立 policy child 决定是否可合并。
- [Risk] 单位标准不覆盖所有字段 → 对未定义单位保持未评估，不扩张当前 G1 critical path。
- [Trade-off] contract 先于 snapshot runtime → 短期不能自动提高覆盖率，但避免未审计字段污染下游。

## Migration Plan

1. 实现 `FieldEvidence`、`Provenance`、status/eligibility 枚举和 validator。
2. 为 qualification evidence 写 sidecar contract adapter。
3. 添加冲突、时间、单位、脱敏和序列化测试。
4. 只对测试 fixture 和 qualification artifacts 生成 metadata，不改现有 cache。
5. 后续由 `g1-canonical-snapshot-sync` 决定 storage 和消费者迁移。

回滚只需停止 sidecar 生成；现有 consumer payload 和 cache 文件不变。

## Open Questions

- 生产可用 eligibility 的最终 policy 需要结合 provider qualification evidence 冻结。
- 部分历史字段的 unit normalization 需要在 snapshot child 中按字段矩阵落实。
