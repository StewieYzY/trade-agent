## ADDED Requirements

### Requirement: G1 最小字段集与真实消费者映射

G1 快筛闭环所需字段 SHALL 以真实代码消费者为依据确定，MUST NOT 把现有采集字段数量（21 字段底座或 5 维度）直接当作 G1 required 字段数量。字段仅在直接影响以下决策时才标为 G1 required：L1 hard gate、L1 factor ranking、anti-trap、heat filter、L2 是否进入或成本闸门、G1 evidence/gate 统计所必需的可审计元数据。只用于解释、未来 L3、调试或诊断的字段（如 `risk.goodwill` 已生产但 L1/L2 不消费、`valuation.pe_history`/`pb_history`/`pb_percentile_5y` 不被 L1 消费）SHALL 标 `criticality=optional`、`decision_scope=diagnostic`，MUST NOT 因「已采集」升级为 required。完整逐字段矩阵（含 producer/consumers(file:line)/六维属性/freshness/future_owner）见 `design/data-minimum-field-matrix.md`。

#### Scenario: 已采集但不被消费的字段不升级为 required

- **WHEN** `risk.goodwill` 被 `RiskFetcher` 生产但 L1（hard_gates/factor_scores/anti_trap/heat_filter）与 L2（assemble_snapshot 21 key）均不消费它（L1/L2 从 `financials.balance_sheet.GOODWILL` 读取）
- **THEN** 该字段 SHALL 标 `criticality=optional`、`decision_scope=diagnostic`，MUST NOT 标为 required，缺失时 MUST NOT 影响 G1 ranking 或 Gate 判定

#### Scenario: L1 量化维度以真实消费者为准

- **WHEN** 确定字段集合是否属于 G1 required
- **THEN** L1 消费的 5 维（`basic`/`financials`/`kline`/`valuation`/`risk`，由 `G1_QUANT_DIMENSIONS` 冻结）下的字段 SHALL 按真实 `.get()` 调用方逐一核对；dossier 三维（`main_business`/`peers`/`research`）SHALL 标 `future_owner=G2`、`criticality=optional`（对 G1），MUST NOT 进入 G1 required 字段集

### Requirement: 字段六维属性（拆「是否参与 G1」与「缺失后状态」）

每个进入 G1 决策路径的量化字段 SHALL 用六个正交维度标注，MUST NOT 把「是否参与 G1」与「缺失后状态」混在单一 `G1_status` 列：`decision_scope`（`l1_ranking`/`hard_gate`/`heat_gate`/`l2_gate`/`validation_gate`/`diagnostic`）、`criticality`（`required`/`optional`）、`missing_policy`（`block`/`degrade`/`manual`/`ignore`）、`rule_effect`（受影响规则 + `unknown`/`not_evaluable`/`skip`/`pass`）、`result_effect`（`error`/`skip`/`watch`/`continue`）、`availability_status`（`usable`/`present_but_degraded`/`missing`）。`criticality=required` 只回答「是否参与 G1」，缺失后行为由 `missing_policy`+`rule_effect`+`result_effect` 决定。

#### Scenario: required 字段的缺失行为由 missing_policy 决定

- **WHEN** `risk.pledge_ratio`（`criticality=required`）的 provider 全失败（`source_failed`）
- **THEN** 其 `missing_policy` SHALL 为 `manual`（不阻断，`ranking_blocked=false`），`rule_effect` 为 safety=0 惩罚 + H6/A5 skip，`result_effect` 为 continue（带标记），MUST NOT 因 `criticality=required` 就强制 `result_effect=error`

#### Scenario: present_but_degraded 不计 usable

- **WHEN** `valuation.pe_ttm` 经 CNINFO fallback 返回非空值（全市场均值，非该公司自身 PE）
- **THEN** 其 `availability_status` SHALL 为 `present_but_degraded`（非 `usable`），MUST NOT 计入 `usable_rate`

### Requirement: 缺失状态机四态语义

系统 SHALL 用四个缺失状态表达字段缺失：`required_missing`（关键字段缺失且不能判断，阻断依赖该字段的决策，输出 error/skip 并记录字段与原因）、`degraded`（非核心字段缺失或因子失效，允许继续，结果 MUST 携带 `degraded_fields` 与影响范围）、`manual_action_required`（自动 provider 全失败但人工补充可能恢复，明确是否阻断 ranking，MUST NOT 自动填默认值或把缺失当安全值）、`diagnostic_only`（缺失不影响 G1 决策，可报告缺失但 MUST NOT 悄悄进入排名或 Gate）。

#### Scenario: required_missing 阻断依赖该字段的决策

- **WHEN** `basic.market_cap` 缺失（L2 `critical_fields` 之一，`missing_policy=block`）
- **THEN** L2 SHALL fail-fast 返回 `{"verdict":"error","reason":"insufficient_data"}`，该 ticker 不进入 L2 LLM 调用；L1 H3（市值<50 亿）SHALL 输出 `not_evaluable` 而非放行

#### Scenario: degraded 允许继续但携带可见标记

- **WHEN** `basic.industry` 缺失（单 ticker L1 路径，`missing_policy=degrade`）但其余字段齐全
- **THEN** H4/H5 SHALL 跳过、factor PE 行业折价子项 SHALL 跳过、L2 snapshot SHALL 渲染「数据缺失」，结果 SHALL 携带 `degraded_fields=["industry"]` 与影响范围，MUST NOT 表现为无标记的干净结果

#### Scenario: manual_action_required 不阻断时不强盖 degraded

- **WHEN** `risk.pledge_ratio` 的自动 provider 全失败（`source_failed`），`ranking_blocked=false`
- **THEN** 该字段 SHALL 标 `manual_action_required`，safety_margin SHALL 返回 0（沿用 `quantitative-screener` spec 冻结的惩罚性降级），H6/A5 SHALL 跳过，结果 SHALL 携带 `manual_action_required_fields=["pledge_ratio"]` 标记，MUST NOT 自动填 0 当安全值，且 MUST NOT 强制 `degraded:true`（因不阻断、不改 verdict，仅带 provenance 标记）

#### Scenario: diagnostic_only 不进入排名

- **WHEN** `risk.goodwill` 或 `valuation.pe_history` 缺失
- **THEN** 该字段缺失 SHALL 仅作诊断报告，MUST NOT 影响任何 ranking/anti-trap/heat filter/Gate 判定

### Requirement: 字段/维度/结果三层状态关系

缺失状态 SHALL 挂在字段/维度/结果三个层级并保持一致：字段层有 `status`+`missing_reason`+`provenance`；维度整体失败时该维度下所有 required 字段状态聚合为维度层 status 并记 `attempted_sources`；ticker 最终结果（L1 candidate / L2 verdict）MUST 聚合其字段层 status——只要存在**阻断或改变打分**的字段缺失（`required_missing` 或 `manual_action_required` 且 `ranking_blocked=true` 或 `result_effect` 改 verdict），结果层 SHALL 携带可见标记（`degraded:true` + `degraded_fields` + `missing_reasons`）。**不阻断的 `manual_action_required`（`ranking_blocked=false`）带 `manual_action_required_fields` 标记，但不强盖 `degraded:true`。** L2 degraded 模式（`scout-agent` spec 已冻结的 verdict="watch" + confidence≤50 + `degraded:true`）SHALL 作结果层标记载体。

#### Scenario: 阻断/改分字段缺失聚合到结果层可见标记

- **WHEN** 某 ticker 存在 `required_missing`（block）或 `manual_action_required`（ranking_blocked=true）或导致 verdict 改变的 `degraded` 字段
- **THEN** 其 L1 candidate / L2 verdict 结果 SHALL 携带 `degraded:true` + `degraded_fields` + `missing_reasons`，MUST NOT 表现为无标记的干净 verdict

#### Scenario: 非阻断 manual_action 不强盖 degraded

- **WHEN** 某 ticker 仅存在不阻断的 `manual_action_required` 字段（如 pledge `source_failed`，`ranking_blocked=false`）
- **THEN** 结果 SHALL 携带 `manual_action_required_fields` 标记，MUST NOT 强制 `degraded:true`，verdict 按正常 ranking 流转（不因该非阻断缺失被压成 watch）

#### Scenario: 维度层失败聚合字段层状态

- **WHEN** `kline` 维度整体采集失败（`__error__`）
- **THEN** 维度层 SHALL 记 `attempted_sources` 与失败原因，字段层 `kline.close`/`kline.turnover_rate` SHALL 均标 `required_missing`（`missing_policy=block`），heat_filter SHALL 输出 `not_evaluable`（禁止静默 `pass`）

### Requirement: 结果优先级表（目标契约语义，runtime 机制留 repair child）

字段缺失到结果的映射 SHALL 遵循以下优先级表。本 requirement 只冻结目标契约语义（字段情况→规则结果→L1 去向→L2 verdict）；runtime 机制（`not_evaluable` 的返回形状、`after_hard_gates` 如何计数 `not_evaluable` ticker、L2 verdict 映射的代码实现）由 `g1-4-data-source-resilience` repair child 实现，本 capability 不钉死。

| 字段情况 | 规则结果 | L1 去向 | L2 verdict |
|---|---|---|---|
| 关键字段缺失且不能判断（required_missing block，如 market_cap/name/kline） | not_evaluable | 排除/不计入该 gate 放行 | error |
| 非关键字段缺失（degraded，如 industry 单 ticker/pe_ttm 子项） | not_evaluable 该规则，其余继续 | 继续 | watch + degraded:true（仅当改分） |
| 人工补充可恢复且不阻断（manual_action_required ranking_blocked=false，如 pledge source_failed） | safety=0 惩罚但继续 | 继续，带 manual_action_required_fields 标记 | continue（不强盖 degraded:true） |
| 人工补充可恢复但阻断（manual_action_required ranking_blocked=true，如 market_cap 缺失） | not_evaluable | 排除 | error |
| 已确认查无记录（record_not_found，如 pledge known-zero） | 满分/正常 | 继续 | 不改变 verdict |
| 诊断字段缺失（diagnostic_only，如 risk.goodwill） | 不影响 | 继续 | 不改变 verdict |

#### Scenario: not_evaluable 不等于 pass

- **WHEN** 某规则因字段缺失输出 `not_evaluable`
- **THEN** 该结果 SHALL NOT 等同于 `pass=True`，MUST NOT 因 `not_evaluable` 静默放行该 ticker 进入下游；依赖该字段的 gate SHALL 不计入 `after_hard_gates` 放行计数（runtime 计数方式由 repair child 定）

#### Scenario: L2 error 与 degraded→watch 按表区分

- **WHEN** `basic.market_cap` 缺失（L2 critical_fields，阻断）
- **THEN** L2 verdict SHALL 为 `error`（非 `degraded→watch`），因 `result_effect=error`；MUST NOT 与 `degraded→watch` 路径混淆

#### Scenario: 非阻断 manual 不压成 watch

- **WHEN** `risk.pledge_ratio` `source_failed`（`ranking_blocked=false`）但其余字段齐全，LLM 原本返回 `deep_dive`
- **THEN** L2 verdict SHALL 按正常 ranking 流转（可为 `deep_dive`），MUST NOT 因该非阻断缺失被压成 `watch`；结果携带 `manual_action_required_fields=["pledge_ratio"]` provenance 标记

### Requirement: L1 单 ticker 排名 vs G1-4 样本 Gate 双消费者区分

系统 SHALL 区分字段缺失对两类消费者的影响：**单 ticker L1 排名**与 **G1-4 样本 Gate**（`decision_scope=validation_gate`，作用于样本集而非单只 ticker）。`basic.industry` 缺失对单 ticker L1 路径是 `missing_policy=degrade`（允许继续带标记），但对 G1-4 样本 Gate 是 `missing_policy=block`——样本 Gate MUST 判不通过或换源，MUST NOT 用「单票 degraded」掩盖「样本集行业覆盖崩塌」。该区分防止「单票 degraded，但样本 Gate 被误认为通过」。

#### Scenario: industry 缺失对单 ticker L1 可降级

- **WHEN** 某 ticker 的 `basic.industry` 缺失（`industry_mapper` 未覆盖该 ticker），其余字段齐全
- **THEN** 单 ticker L1 路径 SHALL `degrade`：H4/H5 skip、PE 行业折价 skip、L2 渲染「数据缺失」，结果携带 `degraded_fields=["industry"]`，MUST NOT 因 industry 缺失排除该 ticker

#### Scenario: industry 大面积缺失致样本 Gate 不通过

- **WHEN** `industry_mapper.build_industry_map()` 静默返回空 dict，全市场样本被归入单一「未分类」组（如 5533→18 的崩塌）
- **THEN** G1-4 样本 Gate（`validation_gate`）SHALL 判不通过或要求换源，MUST NOT 用「每只票 degraded」掩盖「样本集行业覆盖 <8 行业」的崩塌；样本 Gate 失败 MUST 记为 provider 能力不足，MUST NOT 宣称样本通过

#### Scenario: validation_gate 阻断 Gate 不阻断 ticker

- **WHEN** G1-4 样本 Gate 因行业覆盖不足判不通过
- **THEN** `validation_gate` 的 `missing_policy=block` SHALL 阻断样本 Gate（不通过），MUST NOT 阻断单只 ticker 的 L1 ranking 流程（单 ticker 仍按 degrade 继续）

### Requirement: 禁止默认值静默改写排名语义

系统 MUST NOT 用默认值静默改写排名语义。具体禁止（实证代码位置见 `design/data-minimum-field-matrix.md` §4）：财务维度缺失时把 F-Score 当 0 参与排名（应 `not_evaluable`，权重不重分配）；`risk.pledge_ratio` 缺失时 safety_margin=0 与 anti_trap/hard_gates 不惩罚的三漏斗冲突（按 `pledge_status` 三态区分，仅 `source_failed` 才 safety=0 + 标 manual）；`valuation` fallback 把 `pe_ttm` 静默改写为全市场均值当真值参与排名（应标 `present_but_degraded` + provenance `source=fallback_cninfo_full_market_mean`）；`hard_gates` H2 用 `len(years)<3` 使 financials 缺失即误杀（应 `not_evaluable`）；heat_filter kline 缺失即放行（应 `not_evaluable`，禁止静默 `pass`）。

#### Scenario: 财务维度缺失不当 0 分参与排名

- **WHEN** `financials` 维度缺失或财务年度不足（ROE 5 年需 5 年、ROE 3 年趋势需 3 年、现金流连续需 len≥3、revenue_growth 需近 2 年）
- **THEN** 对应因子 SHALL 标 `not_evaluable`（不参与该子项，权重不重分配），结果 SHALL 标 `degraded` + 失效因子列表，MUST NOT 把空值转成正常 0 分拉低 quality/value 子项

#### Scenario: valuation fallback 不静默塞全市场均值当真值

- **WHEN** `ValuationFetcher` 走 `_fallback_cninfo` 路径，`pe_ttm` 被赋值为返回表全部 PE 值的均值（全市场均值，非按 ticker 行业匹配）
- **THEN** 该 `pe_ttm` SHALL 标 `present_but_degraded` + provenance `source=fallback_cninfo_full_market_mean`，下游 factor PE 行业折价/PE×PB 子项 SHALL 退出排名只保留诊断，MUST NOT 用全市场均值当该公司自己的 PE 参与排名打分

#### Scenario: H2 缺失不误杀

- **WHEN** `financials` 维度缺失或 `years` 为空 list
- **THEN** H2（上市<3 年）SHALL 输出 `not_evaluable`，MUST NOT 因 `len([])<3` 判定 H2 FAIL 而排除该股票（与「宁可漏过不误杀」一致）

#### Scenario: heat_filter 缺失不静默放行

- **WHEN** `kline` 维度缺失或 `close`/`turnover_rate` 数据不足 60 日
- **THEN** heat_filter SHALL 输出 `not_evaluable`，MUST NOT `return {"pass": True}` 静默放行该 ticker 进入下游

### Requirement: risk.pledge_ratio 缺失三态区分

`risk.pledge_ratio` 的缺失 SHALL 区分三种成因，MUST NOT 把「已确认查无记录」与「provider 失败」混为一谈：`record_not_found`（provider 成功但表查无该 ticker 记录，即 known-zero，是正面安全信号）、`source_failed`（provider 全失败，表空或 `__error__`）、`invalid_value`（值解析失败）。系统 SHALL expose `pledge_status` 字段区分三态（具体字段名由 repair child 定）。

#### Scenario: record_not_found 按已知零质押满分

- **WHEN** `risk.pledge_ratio` 返回 `None` 且 `pledge_status=record_not_found`（provider 成功，查无该 ticker 质押记录）
- **THEN** safety_margin SHALL 按已知零质押（0% 质押）给满分（最安全），H6/A5 SHALL pass/不扣分，`availability_status=usable`（非 missing），MUST NOT 当 `source_failed` 标 manual_action_required，MUST NOT 用「视为 0」掩盖（注释与代码不符，契约统一返 None + status）

#### Scenario: source_failed 才标 manual_action_required

- **WHEN** `risk.pledge_ratio` 的 provider 全失败（表空 raise 或 `__error__`），`pledge_status=source_failed`
- **THEN** safety_margin SHALL 返回 0（惩罚性降级），H6/A5 SHALL 跳过（缺失≠质押高），该字段 SHALL 标 `manual_action_required`（`ranking_blocked=false`），MUST NOT 自动填 0 当安全值

### Requirement: 人工补充契约

字段级 `manual_action_required` SHALL 携带最小结构：canonical ticker、字段名、status、失败原因、已尝试来源（`attempted_sources`）、数据日期（`as_of_date`）、人工动作描述（`requested_action`）、阻断的规则/因子列表（`blocks`）、是否阻断 ranking（`ranking_blocked`）、补充后是否需重跑（`requires_rerun`）、是否需 provenance（`provenance_required` + `manual_value_source` + `manual_value_note`）。人工补充 SHALL NOT 绕过 G1 Gate；关键字段大量进入人工补充时 SHALL 记录为 provider 能力不足（`manual_action_rate`），MUST NOT 宣称样本通过。本 requirement 只定义契约结构，不实现录入 UI。

#### Scenario: pledge_ratio 单源失败的人工补充契约

- **WHEN** `risk.pledge_ratio` 东财单一源失败（`source_failed`），自动 provider 全部失败
- **THEN** SHALL 产出人工补充契约：`field="pledge_ratio"`、`status="manual_action_required"`、`reason="all_automated_providers_failed"`、`attempted_sources=["eastmoney"]`、`blocks=["safety_margin_ranking","H6","A5"]`、`ranking_blocked=false`、`requires_rerun=true`、`provenance_required=true`

#### Scenario: 阻断 ranking 的关键字段人工补充

- **WHEN** `basic.market_cap` 缺失（L2 critical_fields）
- **THEN** 人工补充契约 SHALL 标 `ranking_blocked=true`（L2 fail-fast），MUST NOT 自动填默认市值当真值

#### Scenario: 人工补充率过高记为 provider 能力不足

- **WHEN** 关键字段大量进入 `manual_action_required`（`manual_action_rate` 超阈值）
- **THEN** SHALL 记录为 provider 能力不足，MUST NOT 宣称样本通过 G1 Gate

### Requirement: 字段可用率五拆统计

系统 SHALL 把字段可用率拆成五个互斥指标分开统计，MUST NOT 用单一「非空率」或单一「error」桶掩盖：`usable_rate`（`availability_status=usable` 的 required 字段占比）、`degraded_rate`（`present_but_degraded` + `missing_policy=degrade` 触发的字段占比）、`blocking_error_rate`（`missing_policy=block` 且缺失的字段占比）、`manual_action_rate`（`missing_policy=manual`/`source_failed` 字段占比）、`non_blocking_missing_rate`（`manual` 不阻断 `ranking_blocked=false` 字段占比）。**fallback 派生的非空值（如 CNINFO 全市场均值 pe_ttm）SHALL 计 `present_but_degraded`，MUST NOT 计 `usable_rate`。** 可用率 < 95% 时 MUST NOT 用 shortlist 数量掩盖，SHALL 标 provider 能力不足。

#### Scenario: fallback 非空值不计 usable

- **WHEN** 统计 `valuation.pe_ttm` 可用率，该字段经 CNINFO fallback 返回非空全市场均值
- **THEN** 该字段 SHALL 计 `present_but_degraded`（入 `degraded_rate`），MUST NOT 计入 `usable_rate`，避免用「非空率」把无效 fallback 误算成可用

#### Scenario: 五率分开可审计

- **WHEN** 查看样本级运行的字段可用率
- **THEN** SHALL 分开记录 `usable_rate`/`degraded_rate`/`blocking_error_rate`/`manual_action_rate`/`non_blocking_missing_rate`，MUST NOT 用聚合可用率掩盖降级、阻断或人工补充分布

### Requirement: G1/G2/G3 coverage map 与边界

系统 SHALL 建立 G1/G2/G3 coverage map（完整表见 `design/g1-g2-g3-data-coverage-map.md`），列 field / owner / source / downstream consumer / prerequisite Gate / blocking dependency / planned child，只登记字段由哪个 Goal 负责、依赖什么、前置 Gate 是什么，不要求现在实现 G2/G3 字段。G1 基础元数据（canonical ticker / run_id / profile_version / input_ticker_set_hash / as_of / provenance / 缺失状态）SHALL 可被 G2/G3 复用。G2（`main_business`/`peers`/`research`/`capex_proxy`/evidence/counter-evidence/`key_variables`/`what_would_change_my_mind`/`InvestmentThesis`）与 G3（成本价/持仓/仓位/回撤/`HoldingContract`/`MonitorSignal`/thesis-break 监控）业务字段 SHALL 只登记责任与依赖，MUST NOT 在本 child 实现，MUST NOT 反向污染 G1 全市场批量路径。G1 未通过前，MUST NOT 以 G2/G3 开发掩盖 G1 数据问题（AD-10）。

#### Scenario: G2/G3 字段不污染 G1 批量路径

- **WHEN** G1 全市场 L1 路径 `screen_a_shares` 运行
- **THEN** 传给 `BatchFetcher.fetch_all` 的 dimensions SHALL 恰为 `G1_QUANT_DIMENSIONS`（basic/financials/kline/valuation/risk），MUST NOT 包含 `main_business`/`peers`/`research`（由 `staged-fetch-boundary` 冻结，本 capability 复用作边界依据）

#### Scenario: G2/G3 字段只登记不实现

- **WHEN** 定义 coverage map
- **THEN** G2 的 `main_business`/`peers`/`research`/`capex_proxy`/`key_variables`/`what_would_change_my_mind` SHALL 标 `future_owner=G2` 且对 G1 `criticality=optional`，G3 的 `HoldingContract`/`MonitorSignal`/成本价/持仓 SHALL 标 `future_owner=G3`，本 child MUST NOT 实现其运行时代码或采集

#### Scenario: G1 基础元数据可被 G2/G3 复用

- **WHEN** G2/G3 实现其业务字段
- **THEN** SHALL 可复用 G1 的 canonical ticker / run_id / profile_version / as_of / provenance / 缺失状态作其 provenance 载体，MUST NOT 重新发明身份与 provenance 体系

#### Scenario: G2 dossier 复用 G1 已采字段

- **WHEN** G2 dossier 组装 capex_proxy 或 munger pledge 代理
- **THEN** SHALL 复用 G1 已采的 `financials.cash_flow.CONSTRUCT_LONG_ASSET` / `risk.pledge_ratio`，MUST NOT 新建 fetcher，MUST NOT 改 `scout/input_assembly.py`（`scout-agent` f3a 防污染 requirement）

### Requirement: provider 保留与兼容

本 capability SHALL NOT 删除、替换或绕过现有 fetcher（`BasicFetcher`/`FinancialsFetcher`/`KlineFetcher`/`ValuationFetcher`/`RiskFetcher`）、provider fallback chain、cache/resume、`BatchFetcher` 的 `_DIM_FETCHERS` 注册与 `dimensions=None` 兜底逻辑、已有输出字段（含 `risk.goodwill` 等 diagnostic_only 字段）。新契约 SHALL 通过 status/provenance 标注现有能力而非隐藏失败——`__error__` 标记、`attempted_sources`、`missing_reason` 全部保留可见。后续 provider 新增或修复（如 `risk.py` 加 fallback provider、`industry_mapper` 加同花顺兜底）SHALL 开独立 implementation/repair child，MUST NOT 在本 capability 实现。本 capability MUST NOT 修改 G1-1/G1-2/G1-3 已冻结的 runtime contract（L1 stats 结构、L2 三元组、canonical identity）。

#### Scenario: 现有 fetcher 与 fallback chain 保留

- **WHEN** 本 capability 落地
- **THEN** `BatchFetcher._DIM_FETCHERS` 注册表、`fetch_with_fallback` 失败返回 `__error__` 的语义、cache/resume 行为 SHALL 保持不变，MUST NOT 删除或静默替换为未经验证的新源

#### Scenario: 失败可见不被隐藏

- **WHEN** 某 fetcher 失败
- **THEN** `__error__` 标记、`attempted_sources`、`missing_reason` SHALL 全部保留可见并进入字段层/维度层 provenance，MUST NOT 被新契约隐藏成「成功」

#### Scenario: 不修改已冻结 runtime contract

- **WHEN** 本 capability 落地
- **THEN** L1 stats 结构（`total/after_hard_gates/after_factors/after_heat_filter/input_scale/industry_pe_degraded`）、L2 三元组（`full_results/usage_summary/failure_summary`）、canonical identity（`run_id`/`profile_version`/`input_ticker_set_hash`/`canonical_ticker()`）SHALL 保持不变，MUST NOT 修改 G1-1/G1-2/G1-3 已冻结的 requirement
