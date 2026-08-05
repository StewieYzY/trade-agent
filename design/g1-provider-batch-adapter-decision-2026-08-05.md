# G1 Provider Batch Adapter Decision — 2026-08-05

## Decision

`g1-provider-batch-adapter` 的工程边界已完成：provider 必须显式注册，按 provider/method/ticker set 批量调用，先生成字段级 evidence，再交给 canonical snapshot 做 fail-closed merge。

本 change 不接入 LongPort/Longbridge SDK，不执行真实网络调用，也不改变现有 `BatchFetcher`、legacy cache、ranking 或 staged screening。LongPort/Longbridge 仍只能作为后续具备授权后的 shadow candidate；当前 unavailable provider 只产生 `not_evaluated` evidence，不静默切换来源。

## Implemented boundary

- canonical ticker set、request identity、provider family、shadow/eligibility 和 batch call statistics 均显式记录。
- 多 ticker response 拆成独立 field evidence，保留 response hash、retrieved time、unit/currency/time basis 和 provenance。
- omitted ticker、provider exception、field failure、permission/rate-limit/unsupported 等状态隔离并保留 sidecar。
- eligible provider agreement 可进入 canonical record；value/unit/currency/time/freshness 冲突 fail closed。
- shadow/not-qualified evidence 保留但不能写入 production canonical value。
- snapshot writer 继续使用 run-scoped output，不触碰 legacy cache。

## Verification

在 `/Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter`：

- `python3 -m pytest -q value-screener/tests/test_provider_batch_adapter.py`：12 passed
- 既有 provider qualification、provenance、canonical snapshot 边界套件合计：39 passed
- `python3 -m compileall -q value-screener`：通过
- `git diff --check`：通过
- `openspec validate g1-provider-batch-adapter --strict`：通过

## Capability boundary

这是 provider adapter/snapshot 工程 checkpoint，不是 A 股 provider qualification 结果，也不是 G1 capability pass。真实 provider coverage、字段口径、权限、限流、成本和 network evidence 仍需后续独立 child 与明确授权后验证；G1/G2/G3 capability Gate 不因本 change 自动放行。

后续 staged screening、全市场性能/成本、LongPort/Longbridge runtime probe 和 canonical consumer migration 均保持为独立工作，不在本 change 内扩 scope。

## Post-review corrections — 2026-08-05

针对独立 review 的 6 个 P1 问题，当前 worktree 已补充修复：

- snapshot 落盘 manifest 现在保留 batch method、requested ticker set、invalid ticker、provider/method call count、provider summaries 和 freshness window。
- 混合非法 ticker 会写入 `invalid_tickers`，合法 A 股仍继续执行；非 A 股不会生成伪造的 A-share provenance。
- mapping key 与 embedded ticker 不一致、重复 canonical ticker、malformed response envelope 均 fail closed 为 `invalid_value`，不能进入 canonical value。
- stale evidence 保留 `production_eligible` 作为冲突证据，但标记 `freshness_status=stale`；fresh/stale disagreement 产生 freshness conflict，canonical value 为 null，单独 stale 也不能消费。

修复后验证：adapter focused 18 passed；provider qualification、provenance、canonical snapshot 边界套件合计 45 passed；compileall 与 `git diff --check` 通过。该修复仍不代表真实 provider qualification 或 G1 capability pass。
