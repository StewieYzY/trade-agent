## Context

`g1-fast-personal-value-screening` umbrella 将 canonical snapshot 放在 G1
生产路径的 provider qualification 与 staged screening runtime 之间。现有
`data.lib.canonical_snapshot.read_snapshot()` 能读取三个文件，但未验证
schema、运行身份、ticker 集合或 records/provenance 的 field identity，也没有
给下游提供明确的 available/unavailable 语义。

本 child 是 Track A 的单一能力建设。输入是已经生成的 run-scoped canonical
snapshot 目录；输出是内存中的只读 consumer 对象。它不负责生成、提升或修改
snapshot，也不负责调用任何 provider、LLM 或生产路径。

## Goals / Non-Goals

**Goals:**

- 原子读取并 fail closed 校验 manifest、records、provenance。
- 绑定 `schema_version`、`run_id`、`plan_version`、canonical ticker 和
  `ticker_set_hash`。
- 为每个字段返回稳定的 value/status/reason/provenance/as_of/freshness 契约。
- 将 rejected、not_evaluated、source_failed、invalid_value、stale 和
  degraded 明确保持为不可用，不以默认值或 fallback 参与下游排序。
- 通过测试证明输入文件保持不变，且 consumer 不触发 provider/LLM 或生产写入。

**Non-Goals:**

- 不实现 `g1-staged-screening-runtime`、Stage A/B/C 或 provider call narrowing。
- 不实现 provider qualification、canonical promotion、300+ 样本、全市场
  性能/成本 Gate 或 Top 20 用户验收。
- 不修改 G1 ranking、cache、watchlist、debate、decision 或 production snapshot。
- 不新增 Repair ID，不修改已归档 Change。

## Decisions

### 1. 独立 consumer API

新增独立模块提供 `consume_snapshot(...)` 和 field-level 读取能力，而不扩展
`read_snapshot()` 的返回语义。这样底层读取器仍可作为兼容的原始 round-trip
工具，G1 consumer 则拥有明确且可演进的下游契约。

备选方案是直接修改 `read_snapshot()` 返回消费对象；这会把文件读取、兼容性和
产品消费语义耦合在一起，且可能影响现有 writer/reader 测试，因此不采用。

### 2. 显式期望身份

consumer 的调用者必须提供 expected `run_id`、`plan_version`、ticker 集合及
snapshot `ticker_set_hash`（或由 canonical ticker 集合通过
`identity.compute_snapshot_ticker_set_hash` 计算），consumer 对 manifest、records
和 provenance 三者做一致性校验。该 hash 与
`identity.compute_input_ticker_set_hash` 是两个不同契约，不能混用。缺失或不匹配
立即抛出明确的 `SnapshotConsumerError`。

备选方案是信任 manifest 内的 identity；这会让下游无法发现误接 run 或 ticker
集合漂移，因此不采用。

### 3. provenance 驱动字段状态

records 只提供 value；field status、reason、provenance、as_of 和 freshness
从 provenance sidecar 中绑定。qualified available 字段返回 value；所有其他
状态返回 `value=None`，即使 records 中意外存在非空值也不可用。

consumer 支持现有 provenance 状态集合，并要求 freshness 明确为 `fresh` 才能
暴露 available value；缺失、`stale`、`unknown`、`degraded` 都保持不可用。

### 4. 纯内存、只读实现

读取阶段只使用 `Path.read_text()` 和 JSON 解析；不会调用 BatchFetcher、
provider adapter、LLM、CacheManager 或任何写入函数。consumer 对象及其嵌套
metadata 使用深层只读结构，测试通过 hash/字节快照和边界 spy 验证输入目录及
生产调用边界没有变化。

## Risks / Trade-offs

- [Risk] 旧 snapshot 可能缺少 consumer 所需字段 → 直接 fail closed，并返回可定位
  的 schema/contract 错误，不用默认值补齐。
- [Risk] provenance 中同一 ticker/field 出现重复记录 → 拒绝 snapshot，避免
  first-non-empty 或隐式覆盖改变 ranking。
- [Risk] input identity 与 snapshot identity 的历史实现不同 → 由
  `identity.compute_snapshot_ticker_set_hash` 作为 snapshot writer/consumer 的
  共同 SoT，并在契约测试中固定两者不可混用。
- [Risk] consumer 被误接入生产路径 → API 不接受 provider/cache/LLM 依赖，测试
  显式 patch 这些边界并断言未调用。

## Migration Plan

1. 在 child 内新增 consumer contract 和 RED tests。
2. 以最小实现让 focused tests 通过，再运行 canonical snapshot、provenance、
   identity、screener 相关测试。
3. 通过 strict OpenSpec validation、compileall、diff 检查和只读边界 review。
4. 本 child 不 archive；待 independent review 完成后再由后续流程决定归档。

## Open Questions

无。staged screening runtime 如何消费该 API 由后续独立 child 决定。
