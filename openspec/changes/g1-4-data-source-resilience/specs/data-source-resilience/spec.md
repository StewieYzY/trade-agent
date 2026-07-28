## ADDED Requirements

### Requirement: industry_mapper 失败显式化与 fallback

`industry_mapper.build_industry_map()` SHALL NOT 在东财行业接口失败时静默返回空 dict。主选东财失败时 SHALL 尝试 fallback（`ak.stock_individual_info_em` 逐只查行业，或等价可用源；MUST NOT 用同花顺 `cons_ths`——akshare 无此接口）。fallback 也失败时 SHALL 返回带 `status="source_failed"` + `attempted_sources` 的结构（或抛具体异常让下游显式处理），MUST NOT 返回空 dict `{}` 掩盖失败。下游 `generate_g1_4_sample._fetch_industry_map` SHALL NOT 吞异常返 `{}`，SHALL 把 `source_failed` 透传给 G1-4 样本 Gate（validation_gate 判不通过或换源）。承接 canonical `data-minimum-contract` §4「industry_mapper 静默空 dict」禁止项。

#### Scenario: 东财失败 fallback 到逐只查询

- **WHEN** `ak.stock_board_industry_name_em()` 或 `stock_board_industry_cons_em` 失败（反爬/接口变更）
- **THEN** `build_industry_map` SHALL 尝试 `ak.stock_individual_info_em` 逐只查行业作 fallback，MUST NOT 直接返空 dict

#### Scenario: fallback 也失败显式标 source_failed

- **WHEN** 东财主选与逐只 fallback 都失败
- **THEN** `build_industry_map` SHALL 返回带 `status="source_failed"` + `attempted_sources=["eastmoney","individual_info"]` 的结构，MUST NOT 返空 dict `{}` 让下游误判「全市场无行业」

#### Scenario: 下游不吞 source_failed

- **WHEN** `generate_g1_4_sample._fetch_industry_map` 收到 `status=source_failed`
- **THEN** SHALL 把失败透传给 G1-4 样本 Gate（validation_gate 判不通过或换源），MUST NOT 吞异常返 `{}` 导致全市场塌进「未分类」（5533→18 根因）

### Requirement: risk.pledge_ratio fallback 与 pledge_status 三态暴露

`RiskFetcher` SHALL 为 `pledge_ratio` 加 fallback provider（主选 `stock_gpzy_pledge_ratio_em` 全市场表，fallback 单只接口——具体源由 implementer 验证 akshare 可用性后定）。`_fetch_pledge_ratio` SHALL 返回结构区分三态：`source_failed`（表空/`__error__`，provider 全失败）、`record_not_found`（`rows.empty`，查无该 ticker 记录即 known-zero）、`invalid_value`（值解析失败）。`fetch()` 返回值 SHALL 含 `pledge_status` 字段。下游 safety_margin SHALL 按三态处理：`record_not_found`→满分（known-zero 最安全）、`source_failed`→safety=0 + manual_action_required（`ranking_blocked=false`）。`risk.py:38` 注释「视为 0」与代码返 None 不符——统一返 None + `pledge_status`。承接 canonical `data-minimum-contract`「risk.pledge_ratio 缺失三态区分」requirement。

#### Scenario: record_not_found 满分

- **WHEN** `pledge_ratio` 返回 `None` 且 `pledge_status=record_not_found`（provider 成功，查无该 ticker 质押记录）
- **THEN** safety_margin SHALL 按已知零质押给满分，H6/A5 SHALL pass/不扣分，MUST NOT 当 `source_failed` 标 manual_action_required

#### Scenario: source_failed 标 manual_action_required

- **WHEN** `pledge_ratio` 的主选与 fallback 都失败，`pledge_status=source_failed`
- **THEN** safety_margin SHALL 返回 0（惩罚性降级），H6/A5 SHALL 跳过（缺失≠质押高），SHALL 标 `manual_action_required`（`ranking_blocked=false`），MUST NOT 自动填 0 当安全值

#### Scenario: fallback provider 保留不删

- **WHEN** `RiskFetcher` 加 fallback provider
- **THEN** 主选 `stock_gpzy_pledge_ratio_em` 的 intra-batch 复用（`_LazyTable`）与 `fallback_providers` 链 SHALL 保留，MUST NOT 删主选只留 fallback（provider 保留原则）

### Requirement: valuation fallback 标 present_but_degraded 不当真值

`ValuationFetcher._fallback_cninfo` SHALL NOT 把全表 PE 均值（全市场均值，非按 ticker 行业匹配）赋给 `pe_ttm` 当真值。fallback 路径 SHALL 返 `pe_ttm=None` 或保留均值但加 `pe_ttm_status="present_but_degraded"` + provenance `source=fallback_cninfo_full_market_mean`。下游 factor PE 行业折价/PE×PB 子项 SHALL 退出排名只保留诊断，MUST NOT 用全市场均值当该公司自己的 PE 参与排名打分。不删 fallback 能力（provider 保留原则）。承接 canonical `data-minimum-contract` §4「CNINFO fallback 把 pe_ttm 静默改写为全市场均值」禁止项。

#### Scenario: fallback pe_ttm 标 present_but_degraded

- **WHEN** `ValuationFetcher` 走 `_fallback_cninfo` 路径，返回表全部 PE 值的均值
- **THEN** 该 `pe_ttm` SHALL 标 `present_but_degraded` + provenance `source=fallback_cninfo_full_market_mean`，MUST NOT 当真值参与 ranking

#### Scenario: 下游 PE 子项退出排名保诊断

- **WHEN** factor_scores PE 行业折价/PE×PB 子项收到 `present_but_degraded` 的 `pe_ttm`
- **THEN** 子项 SHALL 退出排名只保留诊断，MUST NOT 用全市场均值当该公司自己的 PE 参与打分

### Requirement: H2 缺失输出 not_evaluable 不误杀

`hard_gates.check_hard_gates` 的 H2（上市<3 年）SHALL 在 `financials` 维度缺失或 `years` 为空 list 时输出 `not_evaluable`（不 FAIL），MUST NOT 因 `len([])<3` 判定 H2 FAIL 而排除该股票。`years` 有值但 `len<3`（真·上市不足 3 年）SHALL 保留 FAIL 语义。返回结构 SHALL 加 `not_evaluable_gates` 列表（如 `["H2"]`），与既有 `pass`/`failed_gates` 字段向后兼容。承接 canonical `data-minimum-contract` §4「H2 len(years)<3 缺失误杀」禁止项。

#### Scenario: financials 缺失 H2 not_evaluable 不 FAIL

- **WHEN** `financials` 维度缺失或 `years` 为空 list
- **THEN** H2 SHALL 输出 `not_evaluable`（加入 `not_evaluable_gates`），MUST NOT 加入 `failed_gates` 排除该股票

#### Scenario: years 不足 3 年仍 FAIL

- **WHEN** `years` 有值但 `len(years) < 3`（真·上市不足 3 年）
- **THEN** H2 SHALL FAIL（加入 `failed_gates`），保留原语义，与「数据缺失 not_evaluable」区分

### Requirement: heat_filter 缺失输出 not_evaluable 不静默放行

`heat_filter.check_heat_filter` SHALL 在 `kline` 维度缺失或 `close`/`turnover_rate` 不足 60 日时输出 `not_evaluable`，MUST NOT `return {"pass": True}` 静默放行。返回结构 SHALL 加 `not_evaluable` bool 字段 + `reason`（如 `kline_missing`/`insufficient_data`），与既有 `pass`/`failed_filters` 向后兼容。`not_evaluable` 的 ticker 不计入 `after_heat_filter` 放行。承接 canonical `data-minimum-contract` §4「heat_filter kline 缺失即放行」禁止项。

#### Scenario: kline 维度缺失 not_evaluable 不放行

- **WHEN** `kline` 维度缺失（`not kline`）
- **THEN** heat_filter SHALL 返 `{"pass": False, "not_evaluable": True, "reason": "kline_missing"}`，MUST NOT `return {"pass": True}` 静默放行

#### Scenario: 数据不足 60 日 not_evaluable

- **WHEN** `close`/`turnover_rate` 长度 < 60
- **THEN** heat_filter SHALL 返 `not_evaluable`（不放行），MUST NOT 静默 `pass=True`

### Requirement: F-Score 缺失输出 not_evaluable 不转 0

`compute_f_score` SHALL 在 `financials` 维度缺失时返回 `None`（非 0），标 `not_evaluable`。`factor_scores.compute_factor_scores` 的 `f_score = compute_f_score(financials) if financials else 0` SHALL 改为返 `None`。quality/value 子项的 `if not scores: return 0.0` SHALL 改返 `None` + 标 degraded（子项 not_evaluable，不参与 composite，权重不重分配）。`_score_linear_decay` 的 `if value is None: return 0.0` SHALL 改返 `None`（子项 not_evaluable），composite 聚合时跳过 None 子项。`stock_features._f` 的 `default=0.0` 用于 F-Score 9 项内部比率分母处理可保留，但不影响整体 `compute_f_score` 返 None。承接 canonical `data-minimum-contract` §4「financials 维度缺失→F-Score=0」禁止项。

#### Scenario: financials 缺失 F-Score 返 None 不 0

- **WHEN** `financials` 维度缺失或为空
- **THEN** `compute_f_score` SHALL 返 `None`（非 0），F-Score 子项标 `not_evaluable`，MUST NOT 返 0 拉低 quality 子项

#### Scenario: composite 聚合跳过 None 子项不重分配权重

- **WHEN** quality/value 子项有 None（not_evaluable）
- **THEN** composite 聚合 SHALL 跳过 None 子项（权重不重分配，标 degraded），MUST NOT 把 None 当 0 拉低 composite
