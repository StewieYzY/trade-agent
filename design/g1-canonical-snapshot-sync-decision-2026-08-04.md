# G1 Canonical Snapshot Sync Decision

日期：2026-08-04

## 决定

canonical snapshot boundary 已实现并验证，但当前没有任何字段因本 change 自动获得
production eligibility。snapshot 只消费显式 contract evidence；未 qualification、
shadow、失败、冲突和 stale 字段保持可见 null/status。

## 已实现边界

- raw/evidence、canonical values、provenance sidecar 分层；
- immutable run directory，重复 run_id 拒绝覆盖；
- manifest 保存 plan/ticker/source-set hash、schema version、as-of 和 status summary；
- source-set hash 由 provider、method、response hash、status、eligibility 组成；
- conflict 保留所有来源，canonical value 置 null；
- 不修改 `data/cache`、ranking、debate、watchlist 或 diagnostic；
- LongPort/Longbridge shadow evidence 不会进入 canonical production values。

## Verification

```text
canonical snapshot + provenance + qualification tests: 27 passed
compileall: passed
OpenSpec strict: passed
git diff --check: passed
```

## Capability 边界

```text
G1: 未通过
provider qualification: 未通过/未评估
batch adapter: 未实现
staged screening: 未实现
full-market performance/cost: 未验证
```

后续由 `g1-provider-batch-adapter` 负责把真实 provider evidence 写入 snapshot；
由 staged screening child 负责让 G1 消费 snapshot。两者不得用 mock 或
first-non-empty 规则绕过 provider contract。
