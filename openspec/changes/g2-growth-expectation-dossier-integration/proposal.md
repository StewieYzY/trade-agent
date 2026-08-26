## Why

G2 umbrella 3.1 and 3.2 已冻结并实现了可验证的 `growth_expectation_diagnostic`，但 dossier 与 `InvestmentThesis` 尚未消费同一份不可变 artifact。现在需要闭合 3.3，确保成长预期诊断的 identity/digest、用户假设快照、provenance、计算状态和失败语义在研究档案与最终 thesis 之间不丢失或被重新计算。

## What Changes

- 在 `research_dossier` 组装结果中接收并验证已计算的 growth-expectation diagnostic artifact，保留完整 artifact 与绑定 identity。
- 在 `InvestmentThesis` 结构化输出中发布 `valuation_expectation`，只引用经过 dossier identity 绑定的 diagnostic artifact，不自行生成或修改数值结论。
- 传递 `assumption_snapshot`、`provenance`、`input_digest`、`diagnostic_digest`、`calculation_status`、`quality_status`、warnings/reasons 和 failure metadata。
- 对 ticker、dossier snapshot、profile/formula version、输入字段或 digest 不一致，以及 `not_evaluable`/`failed` artifact 携带数值结论的情况 fail closed；不得发布失败结果的数值结论。
- 新增 RED→GREEN focused tests，覆盖 clean/degraded/not_evaluable/failed 四种状态、identity/digest 绑定、假设与来源传递及失败发布边界。
- 仅更新 G2 3.3 对应 OpenSpec child artifacts；不修改 growth expectation engine 计算逻辑。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `research-dossier`: dossier SHALL 接收、绑定并原样保留 growth-expectation diagnostic artifact。
- `investment-thesis`: InvestmentThesis SHALL 暴露 dossier 已绑定的 `valuation_expectation`，并保持诊断状态与失败语义。

## Impact

- 修改 `value-screener/council/research_dossier.py` 及其相关 dossier 组装接口。
- 修改现有 `InvestmentThesis` 定义/构造与发布路径。
- 新增或修改 `value-screener/tests/` 下的 dossier、thesis 和 integration focused tests。
- 新增本 child 的 OpenSpec proposal/design/spec/tasks；不新增依赖、不调用外部 provider/LLM、不修改 G1 ranking/hard gate、Council A/B、G2 3.4 或 G3。
