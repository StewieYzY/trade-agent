## Context

`g1-data-minimum-contract` design child（已归档，canonical `openspec/specs/data-minimum-contract/spec.md`）冻结了 G1 数据契约：字段六维属性、缺失四态状态机（`required_missing`/`degraded`/`manual_action_required`/`diagnostic_only`）、结果优先级表、pledge 三态（`record_not_found`/`source_failed`/`invalid_value`）、可用率五拆。但契约只定义「应如何处理缺失」，**runtime 仍违反契约**——归档 design D9 把六项 runtime 修复拆到本 repair child。

G1-4「300 样本规模预检」5533→18 崩塌的根因正是这些 runtime 违约：

- `industry_mapper.build_industry_map()`（`industry_mapper.py:104-107`）东财失败后**静默返空 dict**，下游 `generate_g1_4_sample._fetch_industry_map` 吞异常返 `{}`，抽样把全市场归单一「未分类」组每组封顶 10 只 → 5533→18。**这是直接根因。**
- `risk.pledge_ratio`（`risk.py:30-42,99`）单源东财 `fallback_providers=[]`，`None` 既可能是 `source_failed`（表空 raise）也可能是 `record_not_found`（`rows.empty→return None`），三漏斗（factor_scores safety=0 / anti_trap 不扣 / hard_gates 放行）各给相反语义。
- `valuation._fallback_cninfo`（`valuation.py:89-95`）对**整张返回表**求均值当 `pe_ttm` 真值（注释「全市场均值」，非按 ticker 行业匹配），下游 PE 子项基于「假 PE」打分。
- `hard_gates` H2（`hard_gates.py:46-48`）`years=financials.get("years",[])`→`len([])<3`→H2 FAIL，financials 维度缺失即误杀（与「宁可漏过不误杀」相反）。
- `heat_filter`（`heat_filter.py:29-30,36-37`）kline 缺失或不足 60 日 `return {"pass": True}` 静默放行。
- F-Score（`stock_features.py:16` `_f(default=0.0)` + `factor_scores.py:297` `f_score=0 if not financials`）financials 缺失即 0，拉低 quality 子项。

**约束**（不重复搬运，只引用）：

- canonical `data-minimum-contract` spec：本 child 承接实现其 §4 禁止清单六项，**不改其 requirement**（契约已冻结，重开需另开 change）。
- AD-10（串行 Gate）：本 child 解 G1-4 数据能力根因；G1-4 真实样本 Gate 重跑属 G1-4 child 自身，本 child 不勾 umbrella 4.1/4.2。
- AD-02（不择时）：修复不改 H1-H8/factor/anti-trap/heat filter 阈值，只改缺失行为。
- AD-03（成本闸门）：fallback + `pledge_status` 不引入新 LLM 调用，零成本影响。
- G1-1/G1-2/G1-3 已冻结 contract：L1 stats 结构（`total/after_hard_gates/after_factors/after_heat_filter/input_scale/industry_pe_degraded`）、L2 三元组、canonical identity 不改。

**本 child 性质**：implementation/repair child，改 runtime。每项修复走 TDD（写测试验证当前违约行为→最小修复→回归）。不跑 G1-4 真实样本 Gate（修复验证后回 G1-4 重跑）。

## Goals / Non-Goals

**Goals:**

- 实现六项 runtime 修复，使 runtime 行为符合 canonical `data-minimum-contract` 契约：
  1. industry_mapper 失败显式化 + fallback（解 5533→18 根因）
  2. risk.pledge_ratio 加 fallback + expose `pledge_status` 三态
  3. valuation fallback 不塞全市场均值，标 `present_but_degraded`
  4. H2 缺失 `not_evaluable`（禁误杀）
  5. heat_filter 缺失 `not_evaluable`（禁静默放行）
  6. F-Score 缺失 `not_evaluable`（禁转 0）
- 每项修复 TDD 守护：测试验证违约→修复→回归 G1-1/G1-2/G1-3 既有测试不破。
- 暴露 `pledge_status` / industry 失败 status / valuation fallback provenance，使可用率五拆可计算。

**Non-Goals:**

- 不改 canonical `data-minimum-contract` spec 的 requirement（契约已冻结）。
- 不改 H1-H8/factor/anti-trap/heat filter 阈值（AD-02）。
- 不改 L1 stats 结构、L2 三元组、canonical identity（G1-1/G1-2/G1-3 已冻结）。
- 不跑 G1-4 真实样本 Gate（属 G1-4 child，修复验证后回 G1-4 重跑）。
- 不动 L3 council、G2/G3 runtime、前端、部署。
- 不 archive G1-4、不勾 umbrella 4.1/4.2、不开 G2 runtime（AD-10）。

## Decisions

### D1：industry_mapper 失败显式化 + fallback——解 5533→18 根因

**决策**：`build_industry_map()` 不再静默返空 dict。改为返带 status 的结构（或抛具体异常让下游显式处理）：

- 东财主选失败时，加 fallback：**`ak.stock_individual_info_em` 逐只查行业**（单只接口，非全市场表，反爬风险低），或 `ak.stock_info_a_code_name` + 板块归属。`industry_mapper.py:99-102` 注释已明示同花顺 `cons_ths` 不可用——**不用同花顺**。
- fallback 也失败时，返结构带 `status=source_failed` + `attempted_sources=["eastmoney","individual_info"]`，**不再返空 dict `{}`**。
- 下游 `generate_g1_4_sample._fetch_industry_map` 不再吞异常返 `{}`，把 `source_failed` 透传给样本 Gate（G1-4 validation_gate 判不通过或换源）。

**为什么逐只 `stock_individual_info_em` 作 fallback**：它是单只查询接口（非全市场表），东财对单只接口的反爬限流远宽松于全市场板块成分接口；且 `basic.py` 的 `_fallback_em_individual` 已用它补 name/industry（`basic.py:86-101`），模式成熟可复用。

**备选方案**：(a) 同花顺 `cons_ths`——否决，`industry_mapper.py:99-102` 已证 akshare 无此接口。(b) 静默返空 dict 让下游自己判断——否决，正是当前 5533→18 根因，下游 `generate_g1_4_sample` 把空 dict 当「无行业」塌进未分类。(c) 抛异常中断——否决，单只 industry 失败不该中断全市场采集；用 status 结构透传最优。

### D2：risk.pledge_ratio 加 fallback + expose pledge_status 三态

**决策**：

- `RiskFetcher`（`risk.py`）加 fallback provider：主选 `stock_gpzy_pledge_ratio_em`（全市场表，intra-batch 复用），fallback 用单只接口（如 `ak.stock_individual_info_em` 的质押字段，或东财个股页面）。
- `_fetch_pledge_ratio`（`risk.py:30-42`）返结构区分三态：
  - 表空/`__error__` → `pledge_status="source_failed"`（provider 全失败）
  - `rows.empty`（查无该 ticker）→ `pledge_status="record_not_found"`（known-zero）
  - 值解析失败 → `pledge_status="invalid_value"`
- `fetch()` 返回值加 `pledge_status` 字段（`risk.py:88-96`），下游按三态处理：`record_not_found`→safety 满分（known-zero 最安全）、`source_failed`→safety=0 + manual_action_required（`ranking_blocked=false`）。
- `risk.py:38` 注释「视为 0」与代码返 None 不符——统一返 None + `pledge_status`，不假装「视为 0」。

**备选方案**：(a) 不加 fallback，只 expose status——否决，单源东财失败即整维 `__error__`，可用率必跌破 95% Gate。(b) 用同花顺质押接口——需先验证 akshare 可用性，design 标「fallback provider 具体源由 implementer 验证 akshare 接口可用性后定」。

### D3：valuation fallback 不塞全市场均值，标 present_but_degraded

**决策**：`_fallback_cninfo`（`valuation.py:82-102`）不再把全表均值赋给 `pe_ttm` 当真值。改为：

- fallback 路径返 `pe_ttm=None`（或保留均值但加 `pe_ttm_status="present_but_degraded"` + `provenance={"source":"fallback_cninfo_full_market_mean"}`），下游 factor PE 行业折价/PE×PB 子项**退出排名只保留诊断**（不参与 ranking 打分）。
- 矩阵 `availability_status=present_but_degraded`，不计 `usable_rate`（canonical spec 已冻结）。
- 不删 fallback 能力（provider 保留原则，canonical spec「provider 保留与兼容」requirement），只改它不当真值。

**备选方案**：(a) 删 fallback——否决，违反 provider 保留原则，且 fallback 有诊断价值。(b) 保留均值当真值——否决，正是违约点，下游基于假 PE 打分。标 `present_but_degraded` + 退出 ranking 最优。

### D4：H2 缺失 not_evaluable（禁误杀）

**决策**：`hard_gates.check_hard_gates`（`hard_gates.py:46-48`）H2 改：

- `financials` 维度缺失或 `years` 空 list → H2 输出 `not_evaluable`（不 FAIL），不再 `len([])<3` 判 FAIL 排除。
- `years` 有值但 `len<3`（真·上市不足 3 年）→ H2 FAIL（保留原语义，区分「数据缺失」与「确实不足 3 年」）。
- 返回结构加 `not_evaluable_gates` 列表（如 `{"pass":..., "failed_gates":[...], "not_evaluable_gates":["H2"]}`），与 canonical 优先级表「H2 unknown 不误杀，漏斗计数由 repair child 定」对齐——本 child 落 `not_evaluable_gates` 字段，`after_hard_gates` 如何计数 `not_evaluable` ticker 在 tasks 验证时定（不破坏 L1 stats 结构契约）。

**备选方案**：(a) 缺失也 FAIL——否决，正是误杀违约点。(b) 缺失放行不计 not_evaluable——否决，无法与「确实不足 3 年 FAIL」区分，审计断裂。返 `not_evaluable_gates` 最优。

### D5：heat_filter 缺失 not_evaluable（禁静默放行）

**决策**：`check_heat_filter`（`heat_filter.py:29-30,36-37`）改：

- `kline` 维度缺失（`not kline`）→ 返 `{"pass": False, "not_evaluable": True, "failed_filters": [], "reason": "kline_missing"}`（不放行，标 not_evaluable）。
- `close`/`turnover_rate` 不足 60 日 → 同 `not_evaluable`（不放行）。
- `not_evaluable` 的 ticker 不计入 `after_heat_filter` 放行（与 canonical 优先级表「heat unknown 阻断放行但不自动 L2 error，kline 不在 L2 critical_fields」对齐）。
- 返回结构加 `not_evaluable` bool 字段。

**备选方案**：(a) 保留 `return {"pass": True}`——否决，正是静默放行违约点。(b) 缺失返 `pass=False`——否决，`pass=False` 与 not_evaluable 语义混（pass=False 是「确有热度」，not_evaluable 是「无法判断」）。加 `not_evaluable` 字段最优。

### D6：F-Score 缺失 not_evaluable（禁转 0）

**决策**：

- `stock_features._f`（`stock_features.py:16`）的 `default=0.0` 用于 F-Score 9 项内部比率计算——保留（F-Score 内部 None→0 是比率分母处理，不是 ranking 拉低），但 `compute_f_score` 整体在 `financials` 维度缺失时返 `None`（非 0），标 `not_evaluable`。
- `factor_scores.compute_factor_scores`（`factor_scores.py:297`）`f_score = compute_f_score(financials) if financials else 0` → 改 `f_score = compute_f_score(financials) if financials else None`，F-Score 子项 `not_evaluable`（不参与 quality 子项，权重不重分配）。
- `factor_scores.py:127-128,193` 的 `if not scores: return 0.0` → 改返 `None` + 标 degraded（quality/value 子项 not_evaluable，不拉低 composite）。
- `factor_scores.py:41-42` `_score_linear_decay` 的 `if value is None: return 0.0` → 改返 `None`（子项 not_evaluable），composite 聚合时跳过 None 子项（权重不重分配，标 degraded）。

**备选方案**：(a) 保留 None→0——否决，正是拉低 quality 违约点。(b) 权重重分配——否决，canonical spec「禁止默认值静默改写」明示「不参与该子项，权重不重分配」。返 None + 跳过 + 标 degraded 最优。

### D7：TDD 验证策略——每项修复独立可测

**决策**：六项修复逐项 TDD，每项独立 commit：

1. 写测试验证当前违约行为（红测 baseline，证明 bug 存在）。
2. 最小修复使测试通过（绿测）。
3. 跑 G1-1/G1-2/G1-3 既有测试确认不回归（`test_screener.py`/`test_screener_stats.py`/`test_scout_*.py` 等）。
4. commit 单项修复。
5. 六项全完后跑全量 `pytest` + `openspec validate --strict`。

**关键回归风险**：F-Score/H2/heat 行为改变可能影响既有 L1 stats 测试（如 `test_screener_stats` 的漏斗计数断言）——tasks 落实时逐项验证，若既有测试因语义改变而需更新，在 commit 里说明「测试更新因契约行为变更」，不顺手改阈值。

**备选方案**：(a) 六项一锅炖一个大 commit——否决，无法定位单项回归。(b) 不写红测直接修——否决，违反 TDD，无法证明 bug 被修。逐项 TDD 最优。

## Risks / Trade-offs

- **[industry fallback 接口可用率]** `stock_individual_info_em` 逐只查行业可能也受限流 → **缓解**：implementer 先验证 akshare 接口可用率，若单只接口也失败，industry 标 `source_failed` 透传给 G1-4 validation_gate（样本 Gate 判不通过或换源），不用 fallback 掩盖。
- **[pledge fallback 源未定]** risk fallback 具体源（同花顺/东财个股页/其他）需验证 akshare 可用性 → **缓解**：D2 标「源由 implementer 验证后定」，先 expose `pledge_status`（契约层），fallback 源是实现细节。
- **[F-Score 行为变更影响既有测试]** `factor_scores` None→0 改 None 可能破坏 `test_screener_stats` 的 composite 断言 → **缓解**：D7 逐项 TDD，既有测试若因契约行为变更需更新，commit 里说明，不顺手改阈值。
- **[not_evaluable 返回结构扩展]** H2/heat 加 `not_evaluable_gates`/`not_evaluable` 字段，下游消费者（`main.py` L1 编排）需适配 → **缓解**：不破坏既有 `pass`/`failed_gates` 字段（向后兼容），新字段可选；`after_hard_gates` 计数方式在 tasks 验证时定，不改 L1 stats 结构契约。
- **[Trade-off] 修复不立即重跑 G1-4]** 本 child 只修 runtime，不验证 G1-4 真实 Gate → 接受，G1-4 重跑属 G1-4 child 自身（AD-10），本 child 通过后回 G1-4 重跑。
- **[Trade-off] pledge_status 字段名未冻结]** canonical spec 标「具体字段名由 repair child 定」→ 本 child 定 `pledge_status`（字符串枚举），下游（safety_margin/anti_trap/hard_gates）按此消费；若 review 认为需 spec 级冻结，另开 change。

## Migration Plan

1. 基线确认：`main@227478d` 干净，canonical `data-minimum-contract` spec strict ✓。
2. 六项修复逐项 TDD（D7），每项独立 commit：
   - D1 industry_mapper（解 5533→18 根因，优先级最高）
   - D2 risk pledge_status
   - D3 valuation fallback
   - D4 H2 not_evaluable
   - D5 heat not_evaluable
   - D6 F-Score not_evaluable
3. 全量 `pytest` + `openspec validate g1-4-data-source-resilience --strict`。
4. 停下交用户 review；通过后回 G1-4 重跑真实样本 Gate（G1-4 child 推进）。

**回滚**：每项独立 commit，`git revert <commit>` 单项回滚；整体 `git checkout main` 即回滚到 `227478d`。

## Open Questions

- **industry fallback 源**：`stock_individual_info_em` 逐只查行业是否反爬宽松到可作全市场 fallback？implementer 验证 akshare 接口可用率后定（D1）。
- **risk pledge fallback 源**：同花顺/东财个股页/其他？implementer 验证后定（D2）。
- **`not_evaluable` 漏斗计数**：H2/heat `not_evaluable` 的 ticker 是否计入 `after_hard_gates`/`after_heat_filter`？canonical spec 留给 repair child 定——本 child 倾向「不计入放行计数，单独计 `not_evaluable_count`」，tasks 落实时验证既有 `test_screener_stats` 断言是否需更新，review 确认。
