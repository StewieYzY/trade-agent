# G1 最小字段矩阵（data-minimum-contract supporting artifact）

> 本文件是 `openspec/changes/g1-data-minimum-contract/` 的 supporting design artifact，属于该 change 的一部分（非游离文档），由 `design.md` 引用。
> 数据来源：代码实证扫描（2026-07-28），引用 `value-screener/` 真实消费者与 file:line。
> 维度拆分原则：**字段是否参与 G1** 与 **缺失后状态** 是两个独立维度，拆成正交六维，不混在单一 `G1_status` 列。

## 1. 六维字段属性定义

每个字段用以下六个正交维度标注：

| 维度 | 取值 | 含义 |
|---|---|---|
| `decision_scope` | `l1_ranking` / `hard_gate` / `heat_gate` / `l2_gate` / `validation_gate` / `diagnostic` | 该字段参与哪类 G1 决策。`validation_gate` = G1-4 样本 Gate（≥300/≥8 行业/每行业≥10）等校验时检查，作用于**样本集**而非单只 ticker |
| `criticality` | `required` / `optional` | 是否参与 G1 决策路径。`required` = 直接影响 hard gate/ranking/anti-trap/heat filter/L2 闸门/evidence 元数据；`optional` = 已采集但不参与 |
| `missing_policy` | `block` / `degrade` / `manual` / `ignore` | 缺失时的策略。`block`=阻断依赖该字段的决策；`degrade`=允许继续带标记；`manual`=人工补充可恢复；`ignore`=不影响决策 |
| `rule_effect` | 规则编号列表 + `unknown`/`not_evaluable`/`skip`/`pass` | 缺失时哪些规则、变成什么状态 |
| `result_effect` | `error` / `skip` / `watch` / `continue` | 缺失映射到结果层 verdict 的去向（与优先级表对齐） |
| `availability_status` | `usable` / `present_but_degraded` / `missing` | 可用率统计口径。**`present_but_degraded` = 非空但是 fallback 派生值（如 CNINFO 全市场均值），不计 `usable_rate`** |

> 关键区分：`criticality=required` 只回答「是否参与 G1」，不回答「缺失后怎么办」——后者由 `missing_policy`+`rule_effect`+`result_effect` 决定。`pledge_ratio` 是 `required`，但 `missing_policy` 视 `record_not_found` vs `source_failed` 而不同（见 §3）。

## 2. G1 required 字段矩阵（逐字段，无通配）

> producer/consumers 列的 file:line 为代码实证位置。`freshness` 为数据日期/TTL（来自 `data/cache/manager.py:_DIM_TTL` 档位与 fetcher 注释）。

### 2.1 basic 维度

| field | producer | consumers (rule + file:line) | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `basic.name` | BasicFetcher `basic.py:58` | H1 `hard_gates.py:40-43`; L2 critical_fields `input_assembly.py:350` | hard_gate, l2_gate | required | block | H1→not_evaluable; L2→fail-fast insufficient_data | L2 error | usable/missing | DAILY | G1 |
| `basic.market_cap` | BasicFetcher `basic.py:62` | H3 `hard_gates.py:51-54`; L2 critical_fields `input_assembly.py:350` | hard_gate, l2_gate | required | block | H3→not_evaluable; L2→fail-fast | L2 error | usable/missing | DAILY | G1 |
| `basic.industry` | BasicFetcher `basic.py:53,63`（从 industry_mapper 补） | H4/H5 `hard_gates.py:57-65`; factor PE 行业折价 `factor_scores.py:155-170`; L2 snapshot `input_assembly.py:281`; **G1-4 样本 Gate `generate_g1_4_sample.py:182`** | hard_gate, l1_ranking, l2_gate, **validation_gate** | required | degrade（单 ticker L1）/ **block（validation_gate 样本 Gate）** | H4/H5 skip; PE 行业折价 skip; L2 渲染「数据缺失」; **样本 Gate 判不通过或换源** | continue（L1）/ **样本 Gate 失败** | usable/missing | DAILY（行业映射 STATIC 7d `industry_mapper.py:39`） | G1 |
| `basic.pe` | BasicFetcher `basic.py:60` | H8 `hard_gates.py:80-83`; factor PE fallback `factor_scores.py:155,186` | hard_gate, l1_ranking | required | degrade | H8→not_evaluable; factor 退到 valuation.pe_ttm | continue | usable/missing | DAILY | G1 |
| `basic.pb` | BasicFetcher `basic.py:61` | factor PB fallback `factor_scores.py:180,186` | l1_ranking | required | degrade | factor PB 子项 skip | continue | usable/missing | DAILY | G1 |
| `basic.price` | BasicFetcher `basic.py:59` | DCF 诊断 `factor_scores.py:235-278`（DCF 已移出排序） | diagnostic | optional | ignore | DCF 诊断 not_evaluable（不影响排序） | continue | usable/missing | DAILY | G1 |
| `basic.code` | BasicFetcher `basic.py:56` | canonical identity（cache key） | l2_gate (identity) | required | block | canonical 失败→identity 不可审计 | error | usable | — | G1·G2·G3 |

### 2.2 financials 维度

> `years` 与各报表项是独立字段。年份不足导致特定因子失效（不转 0），标 degraded。

| field | producer | consumers (rule + file:line) | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `financials.years` | FinancialsFetcher | H2 `hard_gates.py:46-48` | hard_gate | required | degrade（非 block，禁止误杀） | **H2→not_evaluable（禁 `len([])<3` 误杀）** | continue | usable/missing | QUARTERLY | G1 |
| `financials.income.net_profit` | FinancialsFetcher | F-Score `factor_scores.py:76`; ROE 5y `factor_scores.py:85-113`; anti A1/A2 `anti_trap.py:103-116`; L2 roe_3y/net_margin `input_assembly.py:23-93` | l1_ranking, l2_gate | required | degrade | 因子 not_evaluable（权重不重分配，禁 0） | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.income.revenue` | FinancialsFetcher | F-Score `factor_scores.py:76`; L2 revenue_growth `input_assembly.py:224-239` | l1_ranking, l2_gate | required | degrade | F-Score/revenue_growth not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.income.operating_cost` | FinancialsFetcher | F-Score `stock_features.py:53-117` | l1_ranking | required | degrade | F-Score 子项 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.TOTAL_ASSETS` | FinancialsFetcher | F-Score `stock_features.py`; ROE `factor_scores.py:85-113`; anti A1/A4 `anti_trap.py`; L2 debt_ratio/goodwill_ratio `input_assembly.py:96-146` | l1_ranking, l2_gate | required | degrade | 因子 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.TOTAL_CURRENT_ASSETS` | FinancialsFetcher | F-Score `stock_features.py` | l1_ranking | required | degrade | F-Score 子项 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.TOTAL_CURRENT_LIAB` | FinancialsFetcher | F-Score; ROE; anti A1; L2 debt_ratio `input_assembly.py:96-115` | l1_ranking, l2_gate | required | degrade | 因子 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.TOTAL_NONCURRENT_LIAB` | FinancialsFetcher | F-Score; ROE; anti A1; L2 debt_ratio | l1_ranking, l2_gate | required | degrade | 因子 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.SHARE_CAPITAL` | FinancialsFetcher | F-Score `stock_features.py` | l1_ranking | required | degrade | F-Score 子项 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.balance_sheet.GOODWILL` | FinancialsFetcher | anti A4 `anti_trap.py:122-153`; L2 goodwill_ratio `input_assembly.py:118-146` | l1_ranking, l2_gate | required | degrade | A4/L2 goodwill_ratio not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.cash_flow.NETCASH_OPERATE` | FinancialsFetcher | F-Score `factor_scores.py:76`; 现金流连续 3y `factor_scores.py:117-125`; anti A2 `anti_trap.py:103-116`; L2 operating_cashflow `input_assembly.py:297-303` | l1_ranking, l2_gate | required | degrade | 因子 not_evaluable | continue/degraded | usable/missing | QUARTERLY | G1 |
| `financials.cash_flow.CONSTRUCT_LONG_ASSET` | FinancialsFetcher | DCF 诊断 `factor_scores.py:235-278`; **G2 dossier capex_proxy `research-dossier` spec** | diagnostic (G1) / G2 dossier | required (G2) / optional (G1 排序) | ignore (G1) | G1 DCF 诊断 not_evaluable；G2 capex_proxy 另议 | continue | usable/missing | QUARTERLY | G1·G2 |

### 2.3 kline 维度

| field | producer | consumers (rule + file:line) | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `kline.close` | KlineFetcher `kline.py:63` | HF2 `heat_filter.py:54-61`; L2 price_change_60d `input_assembly.py:174-187` | heat_gate, l2_gate | required | block（heat_filter 放行） | **HF2→not_evaluable（禁静默 pass）** | continue（但 heat 不放行） | usable/missing | DAILY | G1 |
| `kline.turnover_rate` | KlineFetcher `kline.py:65`（baostock 兜底全 None `kline.py:117`） | HF1 `heat_filter.py:32-48`; L2 turnover_avg_percentile_60d `input_assembly.py:190-221` | heat_gate, l2_gate | required | block（heat_filter 放行） | **HF1→not_evaluable（禁静默 pass）** | continue（但 heat 不放行） | usable/missing | DAILY | G1 |
| `kline.dates` | KlineFetcher | 时间轴（派生用） | diagnostic | optional | ignore | — | continue | usable | DAILY | G1 |
| `kline.volume` | KlineFetcher | 无 G1 消费者 | diagnostic | optional | ignore | — | continue | usable | DAILY | G1 |

### 2.4 valuation 维度

| field | producer | consumers (rule + file:line) | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `valuation.pe_ttm` | ValuationFetcher `valuation.py:73`（主选 baidu）/ fallback CNINFO `valuation.py:82-102` | factor PE 行业折价/PE×PB `factor_scores.py:155-190`; L2 snapshot `input_assembly.py:286` | l1_ranking, l2_gate | required | degrade（退出部分 ranking 保诊断） | PE 子项 not_evaluable；**fallback 全市场均值不得当真值参与 ranking** | continue/degraded | usable / **present_but_degraded（CNINFO fallback）/ missing** | DAILY | G1 |
| `valuation.pb` | ValuationFetcher `valuation.py:73` | factor PB/PE×PB `factor_scores.py:180-190`; L2 snapshot `input_assembly.py:287` | l1_ranking, l2_gate | required | degrade | PB 子项 skip | continue/degraded | usable/missing | DAILY | G1 |
| `valuation.pe_percentile_5y` | ValuationFetcher `valuation.py:75` | factor PE 历史分位 `factor_scores.py:173-177`; L2 `input_assembly.py:288` | l1_ranking, l2_gate | required | degrade | PE 分位子项 skip | continue/degraded | usable/missing | DAILY | G1 |
| `valuation.graham_number` | ValuationFetcher `valuation.py:79` | L1 candidate 输出 `main.py:145` | evidence | required | degrade | 诊断缺失 | continue | usable/missing | DAILY | G1 |
| `valuation.pe_history` | ValuationFetcher | 仅 `_percentile` 派生用，不被 L1/L2 直接消费 | diagnostic | optional | ignore | — | continue | usable | DAILY | G1 |
| `valuation.pb_history` | ValuationFetcher | 仅 `_percentile` 派生用 | diagnostic | optional | ignore | — | continue | usable | DAILY | G1 |
| `valuation.pb_percentile_5y` | ValuationFetcher `valuation.py:76` | 无 L1/L2 消费者（L2 只消费 pe_percentile_5y） | diagnostic | optional | ignore | — | continue | usable | DAILY | G1 |

### 2.5 risk 维度

| field | producer | consumers (rule + file:line) | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `risk.pledge_ratio` | RiskFetcher 单源 `risk.py:30-42`（`fallback_providers=[]` `risk.py:99`） | H6 `hard_gates.py:68-71`; safety_margin 100% `factor_scores.py:220-232`; anti A5 `anti_trap.py:156-159`; L2 `input_assembly.py:310`; **G2 munger pledge 代理 `research-dossier` spec** | hard_gate, l1_ranking, l2_gate, **G2 dossier** | required | 见 §3（区分 `record_not_found`/`source_failed`） | safety=0（仅 `source_failed`）/ 满分（`record_not_found`）; H6/A5 skip | continue（带标记，非阻断） | usable / missing | QUARTERLY（质押表） | G1·G2 |
| `risk.audit_opinion` | RiskFetcher `risk.py:45-57` | H7 `hard_gates.py:74-77`; anti A6 `anti_trap.py:162-165`; L2 `input_assembly.py:311` | hard_gate, l1_ranking, l2_gate | required | degrade | H7/A6 skip | continue/degraded | usable/missing | QUARTERLY | G1 |
| `risk.goodwill` | RiskFetcher `risk.py:63-86` | **无 G1/L2 消费者**（L1/L2 从 financials.balance_sheet.GOODWILL 读 `anti_trap.py:123`） | diagnostic | optional | ignore | 不影响决策 | continue | usable/missing | QUARTERLY | G1 |

### 2.6 identity / meta（横切，G1 evidence 元数据）

| field | producer | consumers | decision_scope | criticality | missing_policy | rule_effect | result_effect | availability_status | freshness | future_owner |
|---|---|---|---|---|---|---|---|---|---|---|
| `canonical_ticker()` | run-identity SoT `data/lib/identity.py` | 全输出/聚合/cache key 分离 | l2_gate (identity) | required | block | identity 不可审计 | error | usable | — | G1·G2·G3 |
| `run_id` | run-identity（UUID4 execution） | 产物隔离/审计 provenance | evidence | required | degrade | provenance 缺失 | continue（标记） | usable | per-run | G1·G2·G3 |
| `profile_version` | `screener/PROFILE_VERSION` | 规则版本审计/cache hit 判定 | evidence | required | block | 无法证规则版本→cache miss | continue | usable | per-rule-bump | G1·G2·G3 |
| `input_ticker_set_hash` | run-identity | 输入可区分 | evidence | required | degrade | 输入变化不可区分 | continue（标记） | usable | per-run | G1·G2·G3 |
| `as_of` / 采集日 | fetcher/CacheManager | freshness 判定 | evidence | required | degrade | 新鲜度不可判 | continue（标记） | usable | DAILY/QUARTERLY | G1·G2·G3 |
| provider status (`__error__`) | BaseFetcher `fetch_with_fallback` | 失败可见 | evidence | required | degrade（标 manual） | provenance 记失败源 | continue（标 manual_action_required） | missing | — | G1·G2·G3 |

## 3. `risk.pledge_ratio` 缺失语义（决策 A：选 iii）

`pledge_ratio` 的 `None` 有两种成因，必须区分（`risk.py:30-42`）：

| 成因 | 判定 | safety_margin | H6/A5 | missing_policy | result_effect | availability_status |
|---|---|---|---|---|---|---|
| `record_not_found`（表查无该 ticker 记录，`risk.py:37-38` `rows.empty`→`return None`） | provider 成功 + 查无记录 = **known-zero** | **满分**（按 0% 质押，最安全） | pass / 不扣分 | ignore | continue（带 provenance 标记，不盖 degraded） | usable |
| `source_failed`（表空 `risk.py:33-34` raise，或 `__error__`） | provider 全失败 | 0（沿用 `quantitative-screener` spec 惩罚性降级） | skip（缺失≠质押高） | manual（不阻断，`ranking_blocked=false`） | continue（带 `manual_action_required_fields`，不强盖 degraded:true） | missing |
| `invalid_value`（值非法） | 解析失败 | 0 | skip | manual | continue（标 manual） | missing |

> 决策 A（iii）：`record_not_found` = known-zero，genuinely safe，**应拿满分**，但前提是 provenance 证明 provider 成功且查无记录（不是 `source_failed`）。只有 `source_failed` 才标 `manual_action_required`。
> `risk.py:38` 注释「无质押记录视为 0」与代码（返 None）不符——契约统一为：返 None + 状态字段 `pledge_status=record_not_found`，下游按 known-zero 满分处理，不「视为 0 当安全值」掩盖。

## 4. 「缺失即 0」禁止清单（实证代码位置）

以下为当前 runtime「默认值静默改写排名语义」点，本契约只冻结目标语义，修复归 `g1-4-data-source-resilience` child：

| 禁止行为 | 当前代码位置 | 目标语义 |
|---|---|---|
| financials 维度缺失→F-Score=0 | `stock_features.py:16` `_f(default=0.0)` + `factor_scores.py:297` `f_score=0 if not financials` | F-Score 子项 not_evaluable（不参与该子项，权重不重分配），结果标 degraded |
| pledge_ratio None→safety=0 与 anti/hard_gates 不惩罚冲突 | `factor_scores.py:231-232` vs `anti_trap.py:156-157` / `hard_gates.py:68-71` | 按 §3 区分 `record_not_found`/`source_failed`；`source_failed` 才 safety=0 + 标 manual |
| CNINFO fallback 把 pe_ttm 静默改写为全市场均值 | `valuation.py:89-95` | 标 present_but_degraded + provenance `source=fallback_cninfo_full_market_mean`，禁止当真值参与 ranking |
| H2 `len(years)<3` 缺失误杀 | `hard_gates.py:46-48` | financials 缺失→H2 not_evaluable（不 FAIL） |
| heat_filter kline 缺失即放行 | `heat_filter.py:29-37` | kline 缺失/不足 60 日→HF not_evaluable（禁静默 pass） |
| L1 输出 None→"" 改写（实际仅 key 缺失时触发） | `main.py:139-140` | 仅 key 缺失用空串；显式 None 由字段状态/provenance 区分，不掩盖 |
| `risk.py:38` 注释「视为 0」但返 None | `risk.py:38` | 返 None + `pledge_status` 状态，按 §3 处理 |

## 5. 字段可用率统计口径（拆五率）

| 指标 | 口径 | 来源 |
|---|---|---|
| `usable_rate` | `availability_status=usable` 的 required 字段占比 | 矩阵 §2 |
| `degraded_rate` | `present_but_degraded`（fallback 派生值非真值）+ `missing_policy=degrade` 触发的字段占比 | 矩阵 §2 + §3 |
| `blocking_error_rate` | `missing_policy=block` 且缺失的字段占比（L2 fail-fast、heat 阻断放行） | 矩阵 §2 |
| `manual_action_rate` | `missing_policy=manual`（`source_failed`）的字段占比 | §3 |
| `non_blocking_missing_rate` | `manual` 不阻断（`ranking_blocked=false`）的字段占比 | §3 |

> **关键**：CNINFO fallback 补出的非空 `pe_ttm` 计 `present_but_degraded`，**不计 `usable_rate`**——避免用「非空率」把无效 fallback 误算成可用。可用率 < 95% 时不用 shortlist 数量掩盖（与 G1-4 design D6 一致）。
