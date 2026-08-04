## Context

M1 已将 provider qualification 和 provenance contract 分开，当前生产仍有 legacy
`data/cache/{ticker}/{dim}.json`，但它不保证一次运行内字段集合、source set、as-of
和失败状态一致。canonical snapshot 需要成为后续 G1 batch/screening 的可复现输入，
同时保留 legacy consumer 的兼容窗口。

## Goals / Non-Goals

**Goals:**

- 定义 run-scoped snapshot root、manifest、ticker record 和 field sidecar。
- 从已存在的 field evidence 生成 canonical values，并保留原始 evidence hash。
- 记录 source-set hash、ticker-set hash、schema version、as-of 和 status summary。
- source failure、conflict、stale、not qualified 字段不被静默删除或转成默认值。
- 用 atomic write 和 immutable run directory 避免同 run/跨 run 覆盖。

**Non-Goals:**

- 不实现 provider batch adapter、staged screening、ranking 或 full-market run。
- 不修改现有 cache manager 的目录格式和 TTL。
- 不把 shadow/candidate provider 值合并到 canonical production value。
- 不声明 G1 capability passed。

## Decisions

### D1. Snapshot 是 append-only run artifact

每次 sync 写入 `snapshots/<run_id>/manifest.json`、`plan.json`、`records.json` 和
`provenance.json`，同一 run_id 重复使用时拒绝覆盖。选择 immutable run directory
而不是按 ticker 覆盖，保证同日多 run 可比较。

### D2. Raw、canonical、sidecar 三层分离

raw/evidence 保留 provider response hash 和 status；canonical 只保存通过基本 contract
校验的 normalized value；sidecar 保留每字段来源和失败原因。没有资格的字段可以存在于
sidecar，但 canonical value 必须为 `null` 并带状态，不得用零值替代。

### D3. source set hash 由真实 provenance 计算

source-set hash 对参与本次 snapshot 的 provider/method/response hash/status 集合做稳定
哈希。只要 provider、方法、response 或字段状态变化，hash 就变化；不能只对最终 values
哈希。

### D4. canonical eligibility fail closed

只有 `status=available` 且 `eligibility` 不是 `not_qualified` 的 evidence 才能生成
canonical value；当前 M1 产生的 `not_qualified`/`shadow_only` evidence 只进入 sidecar，
不进入正式 canonical values。生产 eligibility 仍由后续 policy 决定。

### D5. Legacy consumer 通过读取兼容层

先提供 snapshot reader 返回 legacy-like field dict 加 metadata，不改现有 ranking
模块；真正切换消费方由后续 staged runtime child 决定。

## Risks / Trade-offs

- [Risk] 当前大部分字段未 qualification → snapshot 可能稀疏；保留 status/sidecar，禁止静默补值。
- [Risk] snapshot 与 legacy cache 不一致 → manifest 记录输入 hash 和 schema version，迁移前只读比较。
- [Risk] 大批量 raw response 造成产物过大 → raw 只保存 hash/引用，canonical run 保留字段级证据。
- [Trade-off] 先做 artifact boundary 而不是马上提速 → 牺牲短期吞吐，换取 G1 输入可复现。

## Migration Plan

1. 实现 snapshot model、manifest、source-set hash 和 immutable writer。
2. 实现从 provenance sidecar/evidence 到 canonical record 的转换。
3. 添加 legacy-like reader，不接入 ranking。
4. 用 fixture 覆盖 available、not_qualified、source_failed、conflict、stale 和 duplicate run。
5. 后续由 provider batch adapter 写入真实 run；失败时删除/隔离当前 run，不影响 legacy cache。

## Open Questions

- production eligibility policy 的最终字段矩阵由后续 G1 Gate/adapter child 冻结。
- snapshot 是否需要压缩和分片由全市场性能 child 根据真实数据量决定。
