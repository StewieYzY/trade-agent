# G1 Field Qualification and Canonical Promotion Decision — 2026-08-05

## Decision

新增独立的 field-level qualification policy 与 promotion entrypoint：

```text
qualification evidence -> explicit field policy -> decision.json
                                           -> canonical snapshot (qualified groups only)
```

本 child 只消费已完成的 run-scoped `manifest.json`/`evidence.json`，不调用真实
provider，不扩展已冻结的 provider health runner，不修改 legacy cache、ranking、
watchlist、debate、G2/G3 runtime，也不把 promotion artifact 视为 G1 capability
pass。

## Implemented boundary

- `FieldQualificationPolicy` 冻结 policy version、A 股 ticker set、method/field
  matrix、允许 provider 和 freshness window，并生成稳定 policy hash。
- source run 必须是 `completion_status=completed`，evidence artifact 存在且计数
  与 manifest/status counts 一致；不完整或 malformed source fail closed。
- 最小 promotion 单位是
  `(provider_family, provider, method, field)`，要求全部 policy ticker 恰好一条
  `available` evidence。
- 缺少 provenance/time basis、失败 status、duplicate ticker、stale/unknown
  freshness、过期 evidence、单位/币种/时间基准冲突和 provider 不在 allowlist
  时，整个 field group rejected。
- 仅对 qualified group 生成 deep-copied `production_eligible` evidence；原始
  qualification evidence 不被修改，rejected/failure evidence 保留在 decision
  sidecar 中。
- promotion 输出使用独立 run ID；qualified run 写入 `decision.json`、canonical
  `manifest.json`、`records.json`、`provenance.json`，blocked run 只写 decision
  artifact，不写 canonical records。
- protected production roots、duplicate run ID 和 unsafe path 在写入前拒绝。

## Verification

使用仓库已有 venv：

```text
field qualification + canonical + provenance + provider adapter + qualification:
  84 passed

full pytest:
  651 passed in 49.70s

compileall:
  passed

openspec validate g1-field-qualification-canonical-promotion --strict:
  passed

git diff --check:
  passed

CLI:
  python -m scripts.promote_provider_snapshot --help
  passed
```

项目根目录和 `value-screener/` 均没有 `package.json`，所以没有可运行的
`npm run lint` 脚本。

## Capability boundary and remaining risk

本次没有执行 live provider runtime，也没有用历史 live evidence 生成新的
promotion artifact；LongPort/Longbridge 继续保持 candidate/blocked。当前 policy
验证的是字段合同、覆盖、时间和一致性，不证明全市场覆盖、下游 ranking 适配或
G1 capability Gate。后续若要放行生产消费者，仍需独立的 snapshot consumer/staged
screening child 和新的真实 A 股 evidence。
