## Context

当前 `BatchFetcher` 是按维度逐 ticker 调用 `fetch_with_fallback`，它适合 legacy cache/resume，
但不提供 provider-level batch identity、字段级 provenance 或多 provider 冲突证据。canonical
snapshot 已能接收 contract evidence，因此本 child 只补齐 provider batch boundary。

## Goals / Non-Goals

**Goals:**

- provider adapter 以 ticker 集合和 method/dimension 为输入，返回字段级 evidence。
- 批量调用按 provider/method 计数，支持 provider 内部批量接口。
- 单个 ticker/field failure isolation。
- merge 保留所有 evidence；只有显式 production eligibility 才可进入 canonical values。
- candidate/shadow provider 的 evidence 与 baseline 隔离。

**Non-Goals:**

- 不改现有 fetcher fallback chain、CacheManager TTL 或 ranking。
- 不新增 LongPort/Longbridge SDK，不执行未经授权的网络调用。
- 不实现 staged screening、全市场性能/成本或 G1 capability Gate。
- 不在 adapter 层推断单位、报告期或 provider qualification。

## Decisions

### D1. Adapter 是显式依赖注入接口

adapter 接受一个 provider implementation 和 batch request，不在模块内部 import 或发现 SDK。
这样没有凭据时可以使用 deterministic fixture；真实 provider 只在调用方显式配置后运行。

### D2. Batch response 先转 evidence，再 merge

每个 provider/method/ticker/field 先生成独立 evidence，记录 response hash/status，
再按 canonical ticker/field/time basis 聚合。选择先 evidence 后 merge，是为了保留冲突
和失败来源，而不是在 provider 层丢失信息。

### D3. Merge 默认 fail closed

多个 available 值若 value/unit/currency/report period 冲突，输出 conflict sidecar，
canonical value 为 null。shadow/not_qualified/source_failed 不得覆盖 production evidence，
也不能被 first-non-empty 规则选中。

### D4. Failure isolation

provider batch exception 按请求粒度转为 source_failed；provider 返回的 partial mapping
逐 field 处理。单个 provider 失败不取消其他 provider，单 ticker 失败不取消同批其他 ticker。

### D5. Snapshot 只接收显式 production eligibility

adapter 可以产出 shadow evidence，但只把 contract 已明确标记为 production_eligible 的字段
交给 canonical snapshot 作为可消费值；当前 qualification 未放行的 provider 默认保持 shadow。

## Risks / Trade-offs

- [Risk] provider batch API 部分失败 → 保存成功/失败 ticker 列表和 response hash，继续其他请求。
- [Risk] provider 返回全市场表导致重复 merge → adapter contract 要求声明 batch scope 和 ticker binding。
- [Risk] shadow provider 污染 production → eligibility 与 provider family 双重隔离，并测试 canonical value 为 null。
- [Trade-off] 需要显式 adapter registration → 少了自动发现，但避免隐藏网络调用和不可审计 provider stack。

## Migration Plan

1. 先用 fixture adapter 写 RED tests，冻结 call count、merge 和 isolation 语义。
2. 实现 adapter protocol、batch invocation、evidence normalization 和 merge。
3. 接入 canonical snapshot writer 的 evidence 输入，不改 legacy cache。
4. 运行 focused tests；真实 provider 只有在凭据和授权存在时执行。
5. 后续 staged screening child 再决定是否将 G1 消费从 legacy cache 切到 snapshot。

## Open Questions

- provider-specific batch size/rate limit 由后续 health/ops child 根据真实 provider 配额冻结。
- production eligibility policy 仍由 qualification/contract policy 决定，本 child 不自行放行字段。
