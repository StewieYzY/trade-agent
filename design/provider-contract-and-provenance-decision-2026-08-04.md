# Provider Contract and Provenance Decision

日期：2026-08-04

## 决定

provider contract 已冻结为独立 sidecar metadata，不改变现有 fetcher
consumer payload，不解锁任何生产 provider。

```text
production eligibility: 只能由后续显式 qualification policy 产生
candidate provider:     not_qualified / shadow_only
conflict:               保留所有 evidence，默认 fail closed
canonical snapshot:     由独立 child 实现
```

## Contract 内容

每个字段 evidence 必须包含：

- provider family、provider、method、market、canonical ticker；
- raw field、normalized value、response hash、retrieved_at；
- status、unit/currency、as-of/report period；
- 非敏感 provenance 和独立 integration eligibility。

`status=available` 只表示本次 response 可解析，不表示生产可用。

以下状态保持不同语义：

```text
record_not_found       provider 成功，但没有该 ticker 记录
source_failed          provider/endpoint 请求失败或空响应
permission_denied      权限或凭据问题
rate_limited           provider 限流
not_supported_for_market  provider 不支持目标市场
invalid_value          返回值无法安全解析
not_evaluated          元数据不足或方法未暴露
conflict               多来源值/单位/报告期冲突
```

## Verification

```text
provider contract + qualification tests: 21 passed
compileall: passed
OpenSpec strict: passed
git diff --check: passed
```

## Boundary

本 change 不修改：

- `data/cache` JSON；
- G1 ranking；
- canonical snapshot；
- provider fallback chain；
- LongPort/Longbridge runtime；
- G2 growth diagnostic。

后续 `g1-canonical-snapshot-sync` 必须消费该 contract，并保留原始
provenance/status；不得以 first-non-empty、静默默认值或机械平均解决冲突。
