## Context

M0 已把 G2 fallback foundation 合入 main，但 G1 仍缺少真实 provider/sample Gate。当前项目的主要 A 股数据链路来自 AkShare 封装的东财、同花顺和新浪接口；LongPort/Longbridge 仅有文档级字段映射，尚未完成 A 股 runtime qualification。

本 change 是 M1 的只读 qualification child。它需要在不影响现有 fetcher、cache、ranking、canonical snapshot 和 diagnostic 的前提下，对固定代表性 A 股执行可复现 probe，并保存足以支持后续字段合同和 adapter 决策的 evidence。

## Goals / Non-Goals

**Goals:**

- 固定至少 5 只覆盖不同市场和类型的 A 股样本，并绑定 canonical ticker。
- 对基线 provider 与候选 LongPort/Longbridge provider 做字段级、方法级 probe。
- 保存 raw response 的 run-scoped 副本或受控摘要、字段映射、单位、报告期、as-of、provider metadata 和失败状态。
- 让没有 SDK、凭据、权限或 A 股支持的 provider 以 `not_evaluated`/`permission_denied`/`not_supported_for_market` 等状态结束，而不是伪造空成功。
- 生成逐字段 comparison report，区分“文档声明”“代码可调用”“A 股 runtime 返回”“可进入正式链路”。
- 为后续 `provider-contract-and-provenance` 和 `g1-canonical-snapshot-sync` 提供输入，但不接入生产消费路径。

**Non-Goals:**

- 不新增 LongPort/Longbridge 依赖或修改 lockfile/requirements。
- 不实现 provider adapter、canonical snapshot、批量同步、字段 merge、ranking 或 G1 Gate。
- 不把候选 provider 的 probe 结果作为 G1/G2/G3 的已通过证据。
- 不使用未经核验的 fallback source；单个 provider 失败必须保留失败 provenance。
- 不执行写入、下单、订阅或其他有外部副作用的 provider 操作。

## Decisions

### D1. Probe 以 provider/method/field 三元组为最小证据单位

每个 probe case 固定 `provider_family`、`provider`、`method`、`market`、`ticker`、字段集合和请求时间。结果必须逐字段记录 `status`、raw field、normalized value（若可安全解析）、unit、currency、as-of/report period 和错误分类。

选择字段级证据而不是仅记录接口成功，是为了避免“接口返回非空”被误认为字段可消费；备选方案是只保存接口级 pass/fail，无法处理部分字段、单位冲突和报告期错位，因此不采用。

### D2. baseline 与 candidate 并列，不做隐式 fallback

AkShare/东财/同花顺/新浪作为现有基线按实际 fetcher 方法记录；LongPort/Longbridge 作为 candidate 单独记录。probe runner 不自动把 candidate 返回值写入现有 cache，也不以 first-non-empty 规则合并。

选择并列 evidence 而不是 probe 时直接 fallback，是为了保持 provider 差异可审计，并防止未 qualification 的字段污染 ranking。

### D3. 失败状态使用封闭枚举并保留原始原因

至少支持 `available`、`partial`、`record_not_found`、`source_failed`、`permission_denied`、`rate_limited`、`not_supported_for_market`、`invalid_value`、`not_evaluated`。原始异常只做敏感信息脱敏后保存，不能用空 dict、零值或 `None` 的静默结果代表成功。

### D4. run-scoped evidence 与可重放 manifest

每次 probe 生成唯一 `run_id`，manifest 记录 code version、样本集 hash、probe plan hash、provider configuration 的非敏感摘要和输出路径。raw response 采用 JSON-safe 序列化，必要时按字段截断，但必须记录截断状态和 raw hash。

选择 run-scoped 目录而不是按 ticker 覆盖文件，是为了避免同日、多 provider 或不同 probe plan 互相覆盖，并支持后续复核。

### D5. qualification 结果不进入正式消费链

probe 输出只写 qualification evidence/report 目录；现有 `data/cache`、`debate`、`watchlist`、ranking 和 diagnostic 路径不得读取它作为业务输入。只有后续独立 contract/adapter child 明确通过后，字段才可进入 canonical snapshot。

## Risks / Trade-offs

- [Risk] 外部 provider 无凭据或权限 → 记录 `not_evaluated`/`permission_denied`，不将未运行误判为失败，也不解锁正式接入。
- [Risk] provider 返回动态 schema → 保存 raw keys、响应 hash 和字段级解析错误，comparison report 标记 schema drift。
- [Risk] 真实 probe 触发限流 → 固定小样本、只读、串行/低并发执行，遇到 rate limit 立即停止该 provider 并保留 evidence。
- [Risk] 不同 provider 的报告期/单位不可比 → comparison report 只比较经明确 normalization 的字段，未能对齐时标记 `not_evaluated`。
- [Trade-off] 本 change 只产出 evidence，不立即提高生产覆盖率 → 换取不会把未经验证的数据源带入 G1/G2 的安全边界。

## Migration Plan

1. 先冻结 probe plan、样本、字段矩阵和状态枚举。
2. 实现只读 runner、provider invocation boundary、raw/evidence writer 和 comparison report。
3. 先运行基线 provider，再按凭据情况运行 LongPort/Longbridge candidate。
4. 对所有结果执行 manifest/schema/diff 校验，生成 dated qualification report。
5. 若通过，创建后续 `provider-contract-and-provenance`；若不通过，保留 evidence 并阻止 adapter 接入。

不涉及生产数据迁移或回滚；如 runner 产生错误，只删除对应 run-scoped evidence，不修改现有 cache。

## Open Questions

- LongPort 与 Longbridge 的最终 probe adapter 是否能在不新增依赖的情况下复用现有运行环境，需在实现前检查实际 SDK/凭据。
- 5 只样本的最终 ticker 与类型标签需要在 probe plan 中冻结，并保留选择理由。
- raw response 的最大保存大小和敏感字段脱敏规则需按实际 provider response 最终确认。
