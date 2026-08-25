## Context

G2 的 `growth_expectation_diagnostic` 是 dossier 与 Agent 推理之间的确定性分析产物。它必须被强单 Agent 与 Council A/B 共享，因此输入、输出、用户假设和失败语义必须在实现引擎之前冻结，否则两条路径会因口径或 provenance 不一致而失去可比性。

当前 `value-screener/data/lib/` 已有 identity、audit_chain、quality_status 等契约模块，但没有成长预期诊断的 schema。本 change 只建立契约与 golden cases，不实现 EPV proxy、成熟期估值交叉锚或 reverse 求解。

## Goals / Non-Goals

**Goals:**

- 冻结 `growth_expectation_diagnostic` 的输入字段、单位、报告期、来源与时间基准。
- 冻结输出结构与 `clean`、`degraded`、`not_evaluable`、`failed` 状态，禁止半成品。
- 冻结用户 assumption snapshot 的显式记录、必需键和版本化，禁止静默默认值。
- 冻结模型适用边界与失败语义，区分数据不足、模型不适用和计算失败。
- 用正反 golden cases 固化可计算、不可评估、失败和降级路径。

**Non-Goals:**

- 不实现任何估值计算（EPV proxy、成熟期交叉锚、reverse 求解、敏感性）。
- 不接入 dossier 与 `InvestmentThesis`。
- 不宣称 G2 capability passed，不启动 G3。
- 不新增第三方依赖，不修改既有 L0-L4 runtime。

## Decisions

### D1. 契约模块只做 schema 与校验，不持有计算

新增 `value-screener/data/lib/growth_expectation_contract.py`，提供冻结 dataclass、常量枚举和 `validate_*` / `evaluate_applicability` 函数。所有数值字段只校验类型、有限性、单位一致性和状态一致性，不产生任何计算结果。这样 engine 后续可独立实现并被本契约约束。

备选方案是把 schema 放在 engine 内。该方案会让契约随实现漂移，且 A/B 无法在 engine 完成前预注册口径，因此不采用。

### D2. `calculation_status` 统一为四值

`CALCULATION_STATUSES = ("clean", "degraded", "not_evaluable", "failed")`。

- `clean`：完整计算且无 warning，数值输出齐全。
- `degraded`：可计算但携带 warning 或区间不确定性，仍必须输出区间而非点估计。
- `not_evaluable`：数据不足或模型不适用，禁止返回数值结论。
- `failed`：计算失败，禁止返回数值结论。

umbrella spec 中的 `partial` 归并为 `degraded`，`not_evaluable/partial/failed` 与用户确认的 `clean/degraded/not_evaluable/failed` 一一对应。这样契约单一、可枚举。

### D3. 输入契约与 fail-closed 校验

`DiagnosticInput` 冻结 `ticker`、`valuation_date`、`report_period`、`as_of`、`currency`、`value_scale`、`current_market_value`、`normalized_operating_cashflow`、`normalized_earnings`、`total_capex`、`normalized_net_profit`、可选 `industry` 和 `sources`。报告期不得晚于 `as_of`，`as_of` 不得晚于 `valuation_date`；来源的 `report_period` 期末不得晚于 `published_at`，`fresh` 声明必须满足发布时间年龄上限。所有货币字段必须声明同一 `currency` 与 `value_scale`；每个货币输入字段（包括 `normalized_earnings`）必须恰好一个字段级 source，source_id 必须唯一；来源必须携带字段级 ticker、provider、raw field、raw payload hash、report period、as_of、freshness，且与主输入一致。缺失、未知单位、非有限数值、来源不匹配一律抛出 `ContractError`。

`current_market_value` 必须为正数，禁止 `0`、负数、`NaN`、`inf`。这避免引擎在非法单位、零市值或负市值上继续运行。

### D4. 用户 assumption snapshot 显式化与版本化

`AssumptionSnapshot` 使用 `ASSUMPTION_SNAPSHOT_VERSION = "g2-assumption-snapshot-v1"`，包含 `created_at`、`version` 和 `assumptions`。每条 `Assumption` 必须含 `key`、`value`、`unit`、`source`、`confirmed_by_user` 和 `version`。

V0 必需假设键冻结为：`normalized_earnings_basis`、`maintenance_capex_ratio`、`cost_of_equity`、`maintenance_growth`、`credible_growth_rate`、`mature_pe`、`reverse_mode`。缺失任一必需键、出现重复键或 `confirmed_by_user=False`，均 fail closed，不得静默使用系统建议值或行业默认值。

### D5. 输出契约与“不返回半成品”

`GrowthExpectationDiagnostic` 冻结 `schema_version`、`ticker`、`valuation_date`、`report_period`、`currency`、`value_scale`、`calculation_status`、`failure_kind`、`reasons`、`warnings`、`input_snapshot`、`assumption_snapshot`、`current_business_value`、`priced_growth_value_range`、`priced_growth_share_range`、命名三情景 `reverse_scenarios`、`credible_growth_range`、`expectation_gap`、非负有限 `value_pulled_forward_years`、`expectation_overdraft`、结构化 `evidence`、`counter_evidence`、`unknowns`、`what_would_change_my_mind`、`provenance`、`input_digest` 和完整输出 `diagnostic_digest`。四个 PRD context 字段必须显式存在，即使为空；`not_evaluable` 可以省略 assumption snapshot，省略时 canonical serialization 不输出 `assumptions`，并与显式 `assumptions=null` 使用同一 digest 口径以保持 round-trip 稳定。

- `clean`：必须包含全部数值区间、非空 reverse scenarios、`failure_kind=None` 且 `warnings` 为空。
- `degraded`：数值区间可存在但 `warnings` 非空，`failure_kind=None`。
- `not_evaluable`/`failed`：必须提供 `failure_kind` 与非空 `reasons`，数值区间、reverse scenarios、credible range 和 overdraft 必须为空。

### D6. 模型适用边界与失败语义

`evaluate_applicability` 只做确定性判定：它必须接收已验证的 input 和 `AssumptionSnapshot`，从 snapshot 读取 `normalized_earnings_basis`，再校验 input 中对应的正常化盈利字段；同时保留 `normalized_earnings` 本身为正的基础门槛。金融行业、非正正常化盈利、负经营现金流、单位/报告期不对齐、来源失败时返回 `not_evaluable` 与 `data_insufficient`/`model_not_applicable`；缺失或未验证的 assumption snapshot 返回 `data_insufficient/data_missing`，不得静默使用默认 basis。行业匹配使用词边界，`non-financial` 不得仅因包含 `financial` 被判为金融行业。冲突的旁路 industry 直接失败。计算过程本身的异常由 engine 以 `computation_failed` 表达。失败语义映射为 `data_insufficient → not_evaluable`、`model_not_applicable → not_evaluable`、`computation_failed → failed`，任何失败都不得伪装为成功。

### D7. Provenance 绑定

诊断 artifact 携带 `input_digest` 和 `diagnostic_digest`，分别绑定完整输入 identity 和完整序列化输出，使用 canonical JSON sha256 口径；对无 assumption snapshot 的失败结果，`assumptions` 缺失与显式 `null`在 digest 中 canonical 等价。provenance 记录 `dossier_snapshot`、`profile_version`、`assumption_snapshot_version`；evidence 通过字段级 ticker/source_id/field/raw payload hash 绑定 input snapshot，真实性证明仍由 audit chain 负责。

## Risks / Trade-offs

- [Risk] 契约字段过多会过度约束未来 engine → 只冻结 PRD 已确认的 V0 字段，V1 字段（NOPAT、ROIC、净债务等）不在本契约中。
- [Risk] `partial` 归并为 `degraded` 与历史措辞不一致 → 在 spec 中显式记录等价关系，避免下游误读。
- [Risk] 假设计数不足导致模型在真实数据上频繁 `not_evaluable` → 这是诚实降级的预期行为，先暴露缺口，后续 engine/数据 child 修复，不以静默默认值换取成功率。
- [Risk] 适用性判定与引擎最终判定可能重复 → `evaluate_applicability` 只输出契约级 verdict，engine 在计算前后复用同一判定，不引入第二套口径。
