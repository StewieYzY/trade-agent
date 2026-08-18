# Proposal: g2-identity-audit-chain

## Why

G2 umbrella 的 1.1 要求证明一次深研运行中的 dossier、prompt、debate、quality
report 与最终结果属于同一个 canonical ticker、同一个 run、同一个 profile 和同一个
dossier snapshot。当前代码已有零散的 ticker preflight、run_id 和 grounding 检查，但
没有统一的不可变 identity context、跨 artifact hash 链和 fail-closed 读取/写入边界，
因此仍可能把不同 run、不同 prompt 或不同 dossier 误当成同一份结果。

## What Changes

- 新增统一的 G2 identity context 与 audit artifact contract。
- 由入口一次生成 `run_id`，绑定 canonical ticker、profile version、input hash、
  dossier snapshot/version、prompt version 和 model configuration。
- 建立
  `dossier → prompt → debate → quality report → final result`
  的 hash/provenance chain，并保存可复核的 manifest。
- 任一 identity、parent hash、payload hash 或 artifact path mismatch 时 fail closed。
- 为 audited Council/fallback 路径提供同一 identity 语义；fallback 不得生成另一套
  run_id 或使用另一份 dossier identity。
- 同 ticker 同日多次 audited run 使用不同 run_id 和不同 artifact root，不覆盖旧证据。

## Scope Boundary

- 本 child 隶属 `g2-deep-investment-thesis`，只推进 G2 umbrella 1.1。
- 不实现 incomplete cache/quality status；G2 1.2 由后续独立 child 负责。
- 不修改 f3c child；G2 1.3 继续由 `f3c-r1-crosstalk-root-cause` 负责。
- 不实现 dossier data-quality、growth diagnostic、A/B harness、InvestmentThesis
  最终接口。
- 不宣称 G2 capability passed。
- 不放行 G3 runtime。
- 默认不运行真实 provider/LLM；本 child 的机制验证使用 fixture/mock。
  若用户在实施后明确授权，可执行受控、run-scoped 的真实 provider/LLM
  diagnostic run。该 run 必须保留 fixture/降级 provenance，产物不得进入提交，
  仅作为 pre-gate engineering evidence，不代表真实 provider qualification、
  G2 capability passed 或 G3 runtime 放行。

## Impact

- 新增 `value-screener/data/lib/audit_chain.py`。
- 修改 `value-screener/council/fallback.py`，使 audited fallback 复用统一 context。
- 修改/新增 Council audited adapter 与行为测试；legacy cache/output 保持兼容。
- 不引入新依赖，不触碰 `data/`、`debate/`、`watchlist/` 根目录现有用户 WIP。
