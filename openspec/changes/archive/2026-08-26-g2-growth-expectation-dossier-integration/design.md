## Context

G2 3.1 已冻结 `growth_expectation_diagnostic` contract，3.2 已提供纯确定性 engine。当前 `build_research_dossier` 只组装事实维度，`CouncilResult` 也没有一条稳定的估值预期载荷；如果上层重新拼接 diagnostic 字段，会丢失 digest、用户假设、provenance 或失败状态。

本 change 只闭合 umbrella 3.3：在 dossier 中保存经过 contract binding 验证的不可变 artifact，并提供一个面向 `InvestmentThesis` mapping 的最小 adapter。完整 InvestmentThesis 字段集合、A/B 选择和 publication Gate 仍属于后续 interface/A-B child。

## Goals / Non-Goals

**Goals:**

- 让 dossier 接收可选的已计算 diagnostic，并通过归档 contract 的 `validate_diagnostic_binding` 校验 ticker、输入、假设、formula/profile/dossier provenance 和两个 digest。
- 将 artifact 原样序列化为 dossier 的 `growth_expectation_diagnostic`，并提供 `valuation_expectation` 视图；不重新计算、不修改、不降级其数值。
- 让 `InvestmentThesis` adapter 只从 dossier 消费 `valuation_expectation`，原样保留 assumption snapshot、provenance、calculation/quality status、warnings/reasons、failure metadata 与 identity digest。
- 对 `clean`、`degraded`、`not_evaluable`、`failed` 均有可测试语义；失败状态的 thesis 视图不得携带数值结论。
- 保持未传入 diagnostic 的旧 dossier 调用兼容，且不污染 G1/L2、engine、Council A/B 或 G3。

**Non-Goals:**

- 不修改 `growth_expectation_contract.py` 或 `growth_expectation_engine.py`。
- 不实现完整 InvestmentThesis v1、publication Gate、A/B 选择、Council/A-B 运行或 watchlist writer。
- 不把 `quality_status=warning`、`not_evaluable` 或 `failed` 结果宣称为 passed Thesis 或 G2 capability passed。
- 不新增依赖，不调用外部 provider/LLM，不修改根目录用户 WIP。

## Decisions

### 1. Artifact-first binding

新增 `council/growth_expectation_integration.py` 作为唯一适配边界。它只接受 contract 的 dict/dataclass，先由 `validate_diagnostic_binding` 重新解析和校验，再生成深拷贝后的 JSON-compatible mapping。dossier 不保存可被调用方继续修改的 dataclass 引用，也不从数值字段重建 artifact。

备选方案是让 dossier 直接复制几个数值字段；该方案会破坏完整 digest/assumption/provenance 绑定，因此不采用。

### 2. Dossier 作为身份载体

`build_research_dossier` 增加 keyword-only `growth_expectation_diagnostic` 参数。传入时要求 diagnostic ticker 与 symbol 的 canonical ticker 一致，并要求其 provenance 的 `dossier_snapshot`、`profile_version` 与 dossier 顶层同名 identity（若显式提供）一致；缺失或冲突直接抛出 `ContractError`。未传入时保持现有行为，不自动调用 engine。

### 3. Thesis 只消费视图

`build_investment_thesis` 以 mapping 方式返回一个最小、稳定的 integration envelope：保留调用方已有字段，并新增 `valuation_expectation`、`growth_expectation_diagnostic`、`assumptions` 和 quality/status 元数据。数值内容来自已绑定 artifact 的 `to_dict()`，不单独计算。后续完整 InvestmentThesis interface 可在不改变该 envelope 的情况下扩展其他字段。

### 4. Fail-closed failure projection

contract 已保证 `not_evaluable`/`failed` 无数值结论；adapter 再执行一次显式检查，禁止失败状态的 `valuation_expectation` 出现市值、经营价值、增长区间、reverse scenarios、sensitivity 等 numeric conclusion。失败结果仍保留原因、provenance、input/diagnostic digest 和可用的 assumption snapshot。

## Risks / Trade-offs

- [Risk] 传入的 diagnostic 与 dossier 事实输入不是同一 snapshot → 要求 provenance identity 对齐，并由 contract binding 重新校验完整 input/assumption payload；缺少 dossier identity 时不推测、不伪造。
- [Risk] `degraded` 被下游误当作 clean → 视图同时保留 `calculation_status`、`quality_status`、warnings/reasons，且不改变状态。
- [Risk] 完整 thesis interface 尚未实现 → 本 child 只提供 valuation expectation integration envelope，不勾选 umbrella 8.1/8.2。
- [Risk] 历史 dossier fixture 没有 diagnostic → 参数为 optional，保留现有返回结构与旧测试。

## Migration Plan

1. 先新增 integration focused RED tests，覆盖 artifact 注入、binding、四种状态和失败数值禁止发布。
2. 以最小改动接入 `research_dossier.py`，新增 thesis mapping adapter 与测试。
3. 运行 focused/full pytest、compileall、OpenSpec strict 和 diff check。
4. 独立 child-only review 通过后 archive；再合入 main、push 并清理本 change worktree/分支。

## Open Questions

- 完整 InvestmentThesis 的 publication status、evidence/inferences 和 A/B pipeline selection 仍由后续 child 决定，本 change 不预设其 Gate 语义。
