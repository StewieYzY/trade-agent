# A 股 Provider Qualification Decision

日期：2026-08-04

## 结论

本轮没有任何 provider/field 被 qualification 放行。

```text
ranking:             不变
canonical snapshot:  不变
G1 Gate:             不解锁
G2 diagnostic:       不解锁
```

这是一次 evidence decision，不是 provider 能力否定；当前运行条件不足以证明
候选 provider 对 A 股字段可用。

## Probe 基线

```text
plan:       a-share-provider-qualification-v1
tickers:    600519.SH, 600009.SH, 000858.SZ, 300750.SZ, 601318.SH
methods:    10 类，只读
baseline:   akshare-existing-fetcher-chain
```

本轮使用现有 primary fetcher binding 做 consumer-level baseline probe。它不把
fetcher 内部 fallback 结果伪装成单一 provider 证据。

## Evidence

baseline run：

```text
run_id:       20260804-baseline-chain-v4
evidence:     /private/tmp/trade-agent-qualification/20260804-baseline-chain-v4
source_failed: 50
not_evaluated: 115
```

`source_failed` 主要来自现有主选接口返回空响应，例如
`stock_zh_a_spot_em empty`。该状态不等于 `record_not_found`：

- `source_failed`：provider/接口没有提供可验证响应；
- `record_not_found`：provider 请求成功，但响应中明确没有该 ticker 记录；
- `not_evaluated`：当前没有 ticker-aligned contract、单位/报告期不足，或方法未暴露。

LongPort/Longbridge 默认 blocked run：

```text
run_id:       20260804-default-blocked
evidence:     /private/tmp/trade-agent-qualification/20260804-default-blocked
status:       825 not_evaluated
reason:       no_runtime_provider_adapter_available
```

本轮没有调用 LongPort/Longbridge，也没有把文档映射当成 runtime evidence。

## Provider/field decision

| Provider | 当前决定 | 原因 |
|---|---|---|
| `akshare-existing-fetcher-chain` | 不放行 | 主选 runtime response 不足；且属于 consumer-level chain，不是单 provider 字段证据 |
| `longport` | `not_evaluated` | 没有显式 adapter、凭据和 A 股 runtime response |
| `longbridge` | `not_evaluated` | 没有显式 adapter、凭据和 A 股 runtime response |

以下字段类别全部保持未放行：

```text
static_info / quote / calc_indexes
historical_kline
income_statement / balance_sheet / cash_flow
historical_valuation
industry_valuation
consensus
```

特别是 `industry_valuation` 和 `consensus`，当前项目没有 ticker-aligned、
单位/报告期明确的基线 contract；不使用全市场均值或文档字段补齐。

## Verification

```text
provider qualification tests: 15 passed
compileall: passed
OpenSpec strict: passed
git diff --check: passed
```

## 下一步

1. 保持当前 provider qualification child 未 archive，直到真实 evidence 可审计；
2. 在具备完整项目依赖的环境中重跑基线 primary probe；
3. 若需要评估 LongPort/Longbridge，提供只读凭据/SDK 后再执行显式 adapter；
4. 真实字段证据通过后，再创建 `provider-contract-and-provenance`；
5. 在 provider contract 通过前，不创建生产 adapter，不修改 canonical snapshot。
