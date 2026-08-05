# M0：G2 前置可信基础 Rolling Handoff（2026-08-05 r2）

本文件是 2026-08-05 handoff 的更新快照，保留旧版
`design/m0-g2-trust-foundation-rolling-handoff-2026-08-05.md` 不覆盖。

## 当前真实工作区

```text
main checkout:
  path:   /Users/admin/Documents/trade-agent
  branch: main
  HEAD:   d5fc1af docs: add 2026-08-05 rolling handoff
  status: clean

clean integration checkpoint:
  path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter-mainline
  branch: codex/g1-provider-batch-adapter-mainline
  HEAD:   1297639 fix(g1): keep qualification evidence timestamps consistent
  status: clean before this handoff update
```

`main` 目前仍未合入 G1 provider adapter；integration checkpoint 也不是 G1
capability pass。

## 已集成的工程变更

clean integration checkpoint 从 `main@d5fc1af` 选择性合入：

```text
172c365 feat(g1): add explicit provider batch adapter
ba0458f fix(g1): close provider batch review findings
5c79baa fix(g1): close second provider review findings
8c6ccbf fix(g1): isolate malformed provider responses
59462c2 docs(g1): record baseline provider runtime probe
9a4730a docs(g1): record corrected provider runtime probe
4eda8f8 fix(g1): close final provider boundary review findings
1297639 fix(g1): keep qualification evidence timestamps consistent
```

adapter contract 当前覆盖：

- 显式 provider registration、A 股 ticker/field/method 输入边界和批量 request identity；
- field-level evidence、status、eligibility、unit/currency/time basis 和 provenance；
- provider/ticker/field failure isolation、malformed response fail-closed；
- `record_not_found` 只表示成功响应明确遗漏 ticker；
- provider exception/空响应保持 `source_failed`；
- 顶层与 nested `retrieved_at` 一致性、freshness status 枚举和 freshness conflict；
- shadow/not-qualified evidence 不进入 production canonical；
- 不修改 legacy cache、ranking、watchlist、debate 或 staged screening。

## 最新验证

在 integration checkpoint 使用：

```text
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python
```

结果：

```text
main baseline full pytest:       554 passed
integrated full pytest:          597 passed
provider/canonical focused:      55 passed
compileall:                      passed
git diff --check:                passed
```

全量 pytest 生成的 `debate/`、`watchlist/` 临时产物已清理，没有进入
integration checkpoint。

## 真实 provider evidence

有效历史 run 仍是：

```text
run_id:       baseline-20260805-b
code_version: 23c791d977c7455a6adb1c09dac885fc45e5ed7f
evidence:
/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805/baseline-20260805-b
```

历史统计：

```text
available:       75
record_not_found: 50
invalid_value:   10
not_evaluated:   30
```

对该历史 evidence 重新应用当前 contract 时，原始 `available=75` 因旧版
qualification runner 顶层/nested `retrieved_at` 微秒级不一致，全部降为
`not_evaluated`。因此它不能直接 promotion；原始 evidence 仍保留，未被改写。

已修复证据生成器：`1297639` 让每条新 evidence 复用同一个
`retrieved_at`，并加入回归测试。该修复需要新的真实 probe 才能产生新的
qualification evidence。

## 当前阻塞

使用修复后代码和正确 venv 尝试运行：

```text
run_id: baseline-20260805-c
```

该次 probe 运行约 5 分钟后仍处在 AkShare fetcher 等待中，没有写出任何
run artifact，随后被中止；空 run directory 已清理。它不是成功 evidence，
也不计入 capability 结论。

因此当前硬阻塞是：

```text
baseline provider fetcher chain lacks bounded request timeout/health isolation
```

不能通过无限等待、mock、旧 partial evidence 或默认值绕过。

## 下一阶段顺序

1. 单独建立 provider health/timeout/failure-visibility child，给真实 probe
   加 bounded timeout、阶段级进度和中止后的可审计 failure artifact；
2. 在相同正确 venv 下重跑新的 baseline qualification；
3. 对新 evidence 做 field-level qualification decision：只 promotion
   明确满足 provenance、时间基准、跨样本覆盖和下游消费契约的字段；
4. 生成 run-scoped canonical snapshot；其余
   `record_not_found`、`source_failed`、`invalid_value`、
   `not_evaluated` 保留在 sidecar，不转默认值；
5. snapshot 冻结后，才准备 Council-vs-fallback A/B；
6. M4.5 仍按 contract → V0 engine → dossier integration，完成前不运行
   最终 Council A/B。

## 明确不做

- 不将 `baseline-20260805-b` 描述为 full provider qualification；
- 不将 `baseline-20260805-c` 描述为成功或 partial success；
- 不接入 LongPort/Longbridge production；二者仍 candidate/blocked；
- 不修改 G1 ranking、legacy cache 或 G3 runtime；
- 不把 adapter archive、clean integration、597 tests 或 partial evidence
  描述为 G1/G2 capability pass。
