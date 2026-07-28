## Why

`g1-data-minimum-contract` design child（已归档，`openspec/specs/data-minimum-contract/spec.md` canonical）已冻结 G1 数据契约语义：字段六维属性、缺失四态状态机、结果优先级表、pledge 三态、可用率五拆。但契约只定义了「应如何处理缺失」，**runtime 仍未按契约落地**——归档 design D9 明确把六项 runtime 修复拆到本 repair child。G1-4「300 样本规模预检」之所以 5533→18 崩塌，根因正是 runtime 缺失行为违反契约：`industry_mapper` 静默返空 dict（5533→18 直接成因）、`risk.pledge_ratio` 单源无 fallback 且 `None` 成因不分、`valuation` fallback 把 pe_ttm 静默塞全市场均值当真值、H2 缺失即误杀、heat_filter 缺失即放行、F-Score 缺失即 0。本 child 只承接 canonical spec 实现这六项 runtime 修复，不改契约语义（契约已冻结，重开需另开 change）。

## What Changes

- **修 `industry_mapper.build_industry_map()` 静默空 dict**（`industry_mapper.py:104-107`）：东财行业接口失败时不再静默返 `{}`，加 fallback（同花顺或等价）+ 失败显式化（返带 `status`/`attempted_sources` 的结构或抛具体异常，下游 `generate_g1_4_sample._fetch_industry_map` 不再吞异常返 `{}`）。解 5533→18 根因。
- **修 `risk.pledge_ratio` 单源 + None 成因不分**（`risk.py:30-42,99`）：加 fallback provider（或等价多源），expose `pledge_status`（`record_not_found`/`source_failed`/`invalid_value`）区分三态；`record_not_found`=known-zero 满分，`source_failed` 才 safety=0 + manual_action_required。`risk.py:38` 注释「视为 0」与代码返 None 不符——统一返 None + `pledge_status`。
- **修 `valuation` fallback 静默塞全市场均值**（`valuation.py:89-95`）：`_fallback_cninfo` 不再把全表均值当 `pe_ttm` 真值，标 `present_but_degraded` + provenance `source=fallback_cninfo_full_market_mean`，下游 factor PE 子项退出排名只保留诊断，禁当真值参与 ranking。
- **修 H2 缺失即误杀**（`hard_gates.py:46-48`）：`financials` 维度缺失或 `years` 空 list 时 H2 输出 `not_evaluable`（不 FAIL），与「宁可漏过不误杀」一致；不再 `len([])<3` 判 FAIL 排除。
- **修 heat_filter 缺失即放行**（`heat_filter.py:29-37`）：`kline` 维度缺失或 `close`/`turnover_rate` 不足 60 日时 heat_filter 输出 `not_evaluable`（禁静默 `pass`），阻断 heat 放行但不自动造成 L2 error（kline 不在 L2 critical_fields）。
- **修 F-Score 缺失即 0**（`stock_features.py:16` `_f(default=0.0)` + `factor_scores.py:297` `f_score=0 if not financials`）：financials 缺失时 F-Score 子项 `not_evaluable`（不参与该子项，权重不重分配），结果标 degraded，禁空值转 0 拉低 quality/value。
- **不改契约语义**：本 child 只落 runtime 行为，不修改 canonical `data-minimum-contract` spec 的 requirement；不改 G1-1/G1-2/G1-3 已冻结 contract（L1 stats 结构、L2 三元组、canonical identity）。
- **不跑 G1-4 真实样本 Gate**：本 child 只修 runtime；修复验证后回 G1-4 重跑真实样本 Gate 属后续（G1-4 child 自身，按 AD-10 不解冻）。

## Capabilities

### New Capabilities

- `data-source-resilience`: G1 数据源韧性——provider fallback、缺失成因显式区分（`pledge_status` 三态、industry 失败显式化）、fallback 派生值标 `present_but_degraded` 不当真值、缺失即 `not_evaluable`（禁误杀/禁放行/禁转 0）。承接 canonical `data-minimum-contract`，实现其 §4 禁止清单的六项 runtime 修复。

### Modified Capabilities

- `quantitative-screener`: MODIFIED H2 行为——`financials` 维度缺失或 `years` 空时 H2 输出 `not_evaluable` 而非 FAIL（`hard_gates.py:46-48`）；MODIFIED safety_margin——`pledge_ratio` 缺失按 `pledge_status` 三态处理，仅 `source_failed` 才 safety=0 + manual（`factor_scores.py:220-232`）。
- `scout-agent`: MODIFIED assemble_snapshot 缺失处理——`valuation.pe_ttm` 经 fallback 返全市场均值时标 `present_but_degraded`，下游子项退出排名保诊断（如触及 `input_assembly.py`，需符合 f3a 防污染：不改 21 key 结构）。

## Impact

**受影响 runtime 代码**：
- `value-screener/data/lib/industry_mapper.py` — `build_industry_map` 失败显式化 + fallback
- `value-screener/data/fetchers/risk.py` — `pledge_ratio` 加 fallback provider + expose `pledge_status`
- `value-screener/data/fetchers/valuation.py` — `_fallback_cninfo` 不塞全市场均值，标 `present_but_degraded`
- `value-screener/screener/hard_gates.py` — H2 `not_evaluable`
- `value-screener/screener/heat_filter.py` — heat `not_evaluable`
- `value-screener/data/lib/stock_features.py` + `screener/factor_scores.py` — F-Score 缺失 `not_evaluable`
- `value-screener/scripts/generate_g1_4_sample.py` — `_fetch_industry_map` 不吞异常返 `{}`（若修复 industry_mapper 后下游仍吞，一并修）

**AD / canonical 引用**（不重复搬运）：
- canonical `data-minimum-contract` spec（§4 禁止清单 + D9 六项修复）：本 child 承接实现，不改其 requirement。
- AD-10（串行 Gate）：本 child 解 G1-4 数据能力根因；G1-4 真实样本 Gate 重跑属后续，不勾 umbrella 4.1/4.2。
- AD-02（不择时）：修复不改 H1-H8/factor/anti-trap/heat filter 阈值，只改缺失行为。
- AD-03（成本闸门）：`pledge_status` 三态 + fallback 不引入新 LLM 调用，零成本影响。

**依赖关系**：承接 `g1-data-minimum-contract`（已归档 + canonical sync）。本 child 通过后，回 G1-4 重跑真实样本 Gate（G1-4 child 自身推进）。不接触 L3 council、G2/G3 runtime、前端、部署。

**风险**：修复触及 runtime，需 TDD 守护（写测试验证缺失行为→最小修复→回归）。industry_mapper fallback 与 risk fallback 若涉及新数据源接入，需验证接口可用率，避免用新源掩盖旧失败。
