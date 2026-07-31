# Longbridge A 股数据字段映射与 Gate 边界

> 状态：官方文档级基线；未进行运行时 A 股 probe
> 最近核对：2026-07-31
> 外部事实来源：仅 [Longbridge Developers 中文文档](https://open.longbridge.com/zh-CN/docs)
> 适用范围：`trade-agent` 当前 G1/G2/G3 的数据消费与准入判断

## 1. 结论摘要

Longbridge 不能据当前官方文档被视为现有 A 股数据层的整体替代。

- **已明确到 A 股市场的能力**：A 股代码格式与实时基础行情；`CN` 市场的选股筛选、行业排行，以及由行业排行结果展开的行业层级。见[行情概览](https://open.longbridge.com/zh-CN/docs/quote/overview)、[选股](https://open.longbridge.com/zh-CN/docs/cli/research/screener)、[行业排行](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/industry-rank)和[行业层级](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/industry-peers)。
- **字段结构有官方页面、但未明确 CN/A 股覆盖的能力**：关键指标、历史 K 线、财务报表、估值、业务分部、行业估值、机构评级和一致性预测。它们只能作为待 probe 候选，不能据页面中的美股或港股示例进入 G1/G2/G3 Gate。
- **已明确不适用于 A 股的能力**：经营回顾页面明确“仅支持港股”，不得作为 A 股 `main_business` 或经营数据来源。见[经营回顾](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/operating)。
- **当前没有官方文档证据的项目关键字段**：质押率及其状态、审计意见、A 股完整 F-Score 科目映射、A 股主营按产品/地区/行业的稳定拆分、A 股逐股同行 PE 列表、A 股研报/共识覆盖与公告事件覆盖。

因此，Longbridge 在本项目中的当前定位只能是：

```text
经运行时 A 股 probe 验证的 Longbridge 数据
    → canonical snapshot + provenance/status
    → 既有 G1 / G2 / G3 消费与 Gate
```

非空返回、页面存在或单个样本成功，都不构成 G1/G2/G3 放行。

## 2. 判定口径

本文始终分开记录三件事：

| 层次 | 含义 | 可用于 Gate 的条件 |
|---|---|---|
| 接口存在 | 官方平台有对应能力页或明确功能说明 | 不可单独用于 Gate |
| CN/A 股明确支持 | 页面明确出现 `CN`、A 股，或给出 `SH`/`SZ` A 股代码说明 | 仍需字段与运行时验证 |
| 字段可消费 | 目标字段的返回语义、单位、报告期、缺失行为和市场覆盖均已验证 | 才能按项目 data contract 计入可用率 |

字段状态定义：

| 状态 | 含义 |
|---|---|
| `documented_cn_candidate` | 接口存在且官方明确 `CN` 或 A 股；字段合同仍未经 A 股 probe 验证 |
| `documented_market_unconfirmed` | 接口和字段结构存在，但页面未明确 CN/A 股覆盖 |
| `not_supported_for_cn` | 官方页面明确非 A 股能力 |
| `missing_in_docs` | 本次官方文档核对未找到足够的对应能力或字段证据 |
| `derived_after_validation` | 项目可在原始字段验证后自行派生，不能反推原始字段已经可用 |

`documented_cn_candidate` 不等于 `usable`；在运行时证据产生前，Gate 一律按未证明可消费处理。

## 3. 已明确的市场边界

Longbridge 行情概览明确：标的代码为 `ticker.region` 形式；A 股上交所使用 `SH`、深交所使用 `SZ`，示例包括 `600519.SH` 和 `399001.SZ`；基础行情包含“美/A 股实时报价”。见[行情概览](https://open.longbridge.com/zh-CN/docs/quote/overview)。

选股页面把 `CN` 列为筛选市场；行业排行页面把 `CN` 列为市场选项，并给出以营收增速对 `CN` 行业排序的示例；行业层级页说明可从 `CN` 行业排行结果继续展开。见[选股](https://open.longbridge.com/zh-CN/docs/cli/research/screener)、[行业排行](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/industry-rank)和[行业层级](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/industry-peers)。

除此之外，不能把页面中的 `.US`、`.HK` 示例泛化为 A 股支持。

## 4. 官方能力与项目消费的映射

| 官方能力 | 文档明确内容 | CN/A 股证据 | 可消费结论 | 项目边界 |
|---|---|---|---|---|
| 实时基础行情 | A 股代码规则；基础行情包含美/A 股实时报价 | 明确 | `documented_cn_candidate`：仅可确认行情能力与代码规则；具体响应字段仍应 probe | 候选补充 `code`、当前价格和时间戳，不替代全市场快照 |
| 关键指标 | 最新价、成交量/额、换手率、总市值、PE(TTM)、PB、股息率和短周期涨跌幅等字段；单次最多 500 个标的 | 指标字段有文档；该页未单独声明 CN 返回 | `documented_market_unconfirmed` | 不能直接标为 A 股 `market_cap`、`pe_ttm`、`pb`、`turnover_rate` 已覆盖 |
| 历史 K 线 | 开高低收、成交量、成交额；支持日期范围与前复权；账户有月度标的数配额 | 页面未明确 CN 返回 | `documented_market_unconfirmed` | 不得据此声明 A 股 60 日价格、成交量或历史换手率可用 |
| 选股 | 可用 `CN` 市场筛选和自定义条件 | 明确 | `documented_cn_candidate`：CN 候选发现可进入 probe | 不能由页面推断全部筛选指标、分页总量或返回字段契约 |
| 行业排行 | `CN` 可按市值、营收、营收增速、净利润、净利润增速、人气等排行 | 明确 | `documented_cn_candidate` | 仅为行业发现/排行候选；不等于单股行业分类或同行估值表 |
| 行业层级 | 可由行业排行返回的行业标识展开子板块树；显示股票数量、日内及年初至今涨跌 | 明确可从 `CN` 行业排行结果使用 | `documented_cn_candidate` | 不能替代逐股同行列表、同行 PE 均值或行业 PE 排名 |
| 财务摘要 | 利润表、资产负债表、现金流量表的摘要指标 | 页面能力和字段示例存在；示例为美股 | `documented_market_unconfirmed` | 不得宣称 A 股 ROE、营收、净利润、利润率已可直接消费 |
| 逐行财务报表 | 利润表、资产负债表、现金流量表的逐行项目 | 页面能力存在；示例为美股 | `documented_market_unconfirmed` | 不得将任一 A 股 F-Score 科目、单位或报告期映射写为已验证 |
| 估值 | PE/PB/PS/股息率、历史区间、历史时间序列和行业同类比较 | 页面能力存在；示例仅为美股、港股 | `documented_market_unconfirmed` | 不得宣称 A 股 5 年估值序列、历史分位、同业中位数或排名可用 |
| 行业估值/估值排名 | 同行业 PE/PB/EPS/股息率比较与行业内估值排名 | 页面能力存在；示例仅为美股、港股 | `documented_market_unconfirmed` | 不得替代 `peer_pe_list`、`peer_avg_pe` 或 `industry_pe_rank` |
| 业务分部 | 分部营收金额、占比及历史趋势 | 页面能力存在；示例为美股 | `documented_market_unconfirmed` | 不得作为 A 股 `main_business`、产品/地区分部或分部毛利率证据 |
| 经营回顾 | 按报告期给出财务指标与管理层评述 | 明确仅支持港股 | `not_supported_for_cn` | 不得用于任何 A 股 G2 字段 |
| 机构评级/一致性预测 | 分析师评级分布、目标价区间；营收、EBIT、EPS 预测 | 页面以“华尔街分析师”和美股示例说明 | `documented_market_unconfirmed` | 不得作为 A 股 `research` 或市场预期的已覆盖来源 |
| 公司行动 | 拆股、分红、配股等公司行动 | 页面示例为港股、美股 | `documented_market_unconfirmed` | 不得作为 A 股 G3 事件源 |

关键指标字段、500 标的上限和百分比字段的表示方式见[关键指标](https://open.longbridge.com/zh-CN/docs/quote/pull/calc-index)；历史 K 线字段与账户配额见[历史 K 线](https://open.longbridge.com/zh-CN/docs/cli/market-data/kline)；财务、估值、业务分部、评级和事件能力分别见[财务摘要](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/financial-report)、[逐行财务报表](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/financial-statement)、[估值](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/valuation)、[行业估值](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/industry-valuation)、[估值排名](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/valuation-rank)、[业务分部](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/business-segments)、[机构评级](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/institution-rating)、[一致性预测](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/consensus)和[公司行动](https://open.longbridge.com/zh-CN/docs/cli/fundamentals/corp-action)。

## 5. G1/L1 字段矩阵

### 5.1 `basic` 与 `kline`

| 项目字段 | 官方候选能力 | 当前状态 | 准入限制 |
|---|---|---|---|
| `code` / canonical ticker | A 股 `SH`/`SZ` 代码规则 | `documented_cn_candidate` | 统一为 `600519.SH`、`000858.SZ`；仅代码规则已确认 |
| `price` | 实时基础行情；关键指标中的最新价 | `documented_cn_candidate` / `documented_market_unconfirmed` | 可先 probe；保存 `as_of`、交易状态和缺失原因 |
| `market_cap` | 关键指标中的总市值 | `documented_market_unconfirmed` | 未证明 A 股返回；需确认单位，禁止直接纳入 H3 |
| `pe_ttm` / `pb` | 关键指标和估值页 | `documented_market_unconfirmed` | 未证明 A 股口径、负值/空值行为或历史一致性 |
| `turnover_rate` | 关键指标中的当前换手率 | `documented_market_unconfirmed` | 即使当前值可取，也不能代替 60 日换手率序列 |
| `industry` | CN 行业排行/行业层级 | `documented_cn_candidate` | 仅证明行业维度；需验证单股归属、taxonomy 与可追溯性 |
| `dates`、`close`、`volume`、`turnover` | 历史 K 线 | `documented_market_unconfirmed` | 需验证 A 股返回、复权口径、时区、长度与配额 |
| 历史 `turnover_rate` | 无明确 K 线字段证据 | `missing_in_docs` | heat filter 必须为 `not_evaluable`，不得用当前换手率回填 |
| `listing_date`、`name`、股本、EPS/BPS | 本次核对未获得字段级 CN 证据 | `missing_in_docs` | 不得从导航目录或旧映射推断已覆盖 |

### 5.2 `financials`

| 项目字段或派生 | 官方候选能力 | 当前状态 | 准入限制 |
|---|---|---|---|
| `income.revenue`、`income.net_profit`、`income.operating_cost` | 财务摘要/逐行财务报表 | `documented_market_unconfirmed` | 仅有美股示例；A 股科目、归母口径、单位、年报筛选均须验证 |
| `operating_cashflow` / `NETCASH_OPERATE` | 现金流量表 | `documented_market_unconfirmed` | 需验证 A 股字段、单位与报告期 |
| `TOTAL_ASSETS`、流动资产/负债、非流动负债、`SHARE_CAPITAL`、`GOODWILL` | 资产负债表 | `documented_market_unconfirmed` | 不得把“有逐行报表页面”视为 A 股字段映射完成 |
| `CONSTRUCT_LONG_ASSET` | 现金流量表科目 | `documented_market_unconfirmed` | 需逐项确认对应项目，才能作为 `capex_proxy` |
| `years`、财务单位、币种、报告期 | 财务页展示报告期与币种 | `documented_market_unconfirmed` | 需确认年报/中报/季报编码、排序与单位；不足年数为 `not_evaluable` |
| F-Score、ROE 三年序列、资产周转率、商誉比、负债率、营收增速 | 项目派生 | `derived_after_validation` | 只有原始字段完成 A 股映射和单位测试后才能计算 |

### 5.3 `valuation`

| 项目字段 | 官方候选能力 | 当前状态 | 准入限制 |
|---|---|---|---|
| `pe_ttm`、`pb` | 关键指标、估值 | `documented_market_unconfirmed` | 不得将页面所述估值能力直接认定为 A 股字段可消费 |
| `pe_history`、`pb_history`、`ps_history`、`dividend_yield` | 估值页的历史序列能力 | `documented_market_unconfirmed` | A 股返回、长度、频率、无效值和口径未证明 |
| `pe_percentile_5y`、`pb_percentile_5y` | 项目由历史序列计算 | `derived_after_validation` | 不能把官方“历史区间/排名”表述误写成项目的五年分位字段 |
| `peer_pe_list`、`peer_avg_pe`、`industry_pe_rank` | 行业估值、估值排名 | `documented_market_unconfirmed` | 官方示例并非 A 股；不得进入 G1 factor 或 G2 peers |
| `graham_number` | 项目派生 | `derived_after_validation` | 仅在价格、PE、PB 的 A 股口径通过验证后再计算 |

### 5.4 `risk`

| 项目字段 | 当前状态 | 限制 |
|---|---|---|
| `pledge_ratio`、`pledge_status` | `missing_in_docs` | 不得用股东、基金持仓、公司行动或其他字段替代 |
| `audit_opinion` 及其 provenance/status | `missing_in_docs` | 不得从财务摘要、公告标题或非空返回推断“标准无保留” |
| `goodwill` | `documented_market_unconfirmed` | 仅在 A 股资产负债表实际返回并完成科目映射后使用 |
| `goodwill_ratio` | `derived_after_validation` | 依赖 `goodwill` 和分母均有效；缺失应保持显式状态 |

## 6. G2/G3 边界

### G2 dossier

| dossier 字段 | 当前结论 |
|---|---|
| `main_business`（行业/产品/地区、收入占比、毛利率） | 业务分部能力存在，但官方页面未明确 A 股覆盖；当前为 `documented_market_unconfirmed`，不能替代现有来源。经营回顾明确仅港股，不可用。 |
| `peers`（同行数量、逐股 PE、均值、排名） | CN 行业排行/层级可用于候选行业发现；逐股估值契约仍为 `documented_market_unconfirmed`。 |
| `research`（覆盖数、评级、共识 EPS、目标价） | 评级与一致性预测页面存在，但“华尔街分析师”定位和美股示例不能证明 A 股覆盖；不得作为公司事实。 |
| `capex_proxy` | 只能在 A 股现金流逐行科目完成验证后由项目派生。 |

所有进入 G2 的字段必须附带：

```text
source
canonical_ticker
market
as_of
report_period
unit_or_currency
raw_field
field_status
mapping_note
```

数据不足应保留 `degraded` 或 `insufficient_data`，不得由空字段生成完整 thesis。

### G3

公司行动页面只证明其功能存在，且示例为港股/美股；不能作为 A 股事件监控事实源。无论候选数据来源如何，Longbridge 都不能替代项目的 `HoldingContract`、thesis-break 判断、关键变量、反证与待验证事项。

## 7. 运行时 A 股 probe 清单

在实现任何接入前，至少对下列标的作只读验证：

```text
600519.SH
600009.SH
000858.SZ
300750.SZ
601318.SH
```

| Probe | 必须确认 |
|---|---|
| 实时行情与关键指标 | 最新价、市值、PE(TTM)、PB、换手率的 A 股返回、单位、百分比表示、空值和权限失败 |
| CN 选股 | 可用筛选指标、分页总量、返回字段和条件口径 |
| CN 行业 | 单股归属是否可追溯到行业排行/层级；行业代码与 taxonomy 映射 |
| 历史 K 线 | A 股可用性、复权、日期/时区、最大长度、配额、成交量/成交额与异常值 |
| 财务报表 | IS/BS/CF 的 A 股原始科目、归母口径、报告期、币种/单位和近三年完整性 |
| 估值 | A 股历史 PE/PB 序列、频率、长度、负值与行业比较的市场适用性 |
| G2 候选字段 | A 股业务分部、同行估值、评级/共识的实际市场支持；无证据即维持不可消费 |
| 风险字段 | 明确验证质押率、审计意见不存在文档证据，不能以旁路字段填补 |

每次 probe 至少记录：

```text
run_id
canonical_ticker
endpoint_or_capability
request_params
as_of
account_region_or_permission
raw_response_hash
raw_response_path
field_status
error_code
mapping_note
```

缺失结果至少区分：

```text
record_not_found
source_failed
region_restricted
not_supported_for_market
invalid_value
not_evaluated
```

## 8. G1/G2/G3 Gate

Longbridge 数据只有同时满足以下条件，才可进入正式消费路径：

1. 至少 5 只不同类型 A 股完成字段级 probe；
2. 每个 G1 必需财务字段有固定映射、报告期规则和单位测试；
3. `pledge_ratio`、审计意见、历史换手率等缺口不被静默默认值掩盖；
4. G1 至少完成 300 只、跨行业样本的真实运行，并统计 `usable/degraded/blocking_error/manual_action`；
5. 验证全市场分页、权限/配额、限流、耗时和失败隔离；
6. G2 维持 staged-fetch boundary，未验证字段不得污染全市场 G1 批量路径；
7. 每个进入 G3 的外部事实均可追溯到原始字段、市场、报告期和状态；
8. 与现有数据源完成字段级差异报告，而非仅比较最终候选数。

在此之前：

- 不替换现有 A 股数据源；
- 不把文档页面、非空返回或单样本成功计入 `usable_rate`；
- 不把美股/港股示例当作 A 股覆盖；
- 不把 CN 选股或行业排行直接当作项目 L1 最终排序；
- 不把未验证字段用于 ranking、hard gate 或成本模型。

## 9. 变更记录

### 2026-07-31

- 以 Longbridge Developers 中文文档重新核对并重写字段映射；
- 删除旧式接口/字段名及无官方页面证据的映射；
- 将“关键指标、K 线、财务、估值、业务分部、同行估值、评级/共识、公司行动”统一降为“接口存在但 CN/A 股字段未明示”的候选能力；
- 明确估值页只证明其页面所述的估值、历史区间/序列和行业比较能力，**不证明** A 股五年历史分位、同行估值或排名可进入项目契约；
- 将经营回顾降为 `not_supported_for_cn`，因为官方页面明确其仅支持港股；
- 保留并收紧 G1/G2/G3 的消费与 Gate 边界；本次未进行运行时 probe，也未修改任何代码或 provider。
