# LongPort A 股数据字段匹配记录

> 状态：SDK 静态核对完成；A 股 runtime probe 尚未完成
> 首次核对日期：2026-07-30
> 最近核对日期：2026-07-31
> 适用范围：`trade-agent` 当前 G1/G2/G3 数据消费与 Capability Gate
> 目标：只依据 LongPort 官方 SDK 仓库，记录可证明的 SDK surface、Python/Rust 暴露差异，以及它们与项目字段契约的匹配关系。

## 0. 证据范围与版本

### 0.1 唯一外部事实来源

本文唯一外部事实来源是 LongPort 官方 SDK 仓库：

- 仓库：`longportapp/openapi`
- commit：`fa0ec53f80573f448054e9e8e4abf269031a1b39`
- commit 日期：2026-07-30
- release commit message：`chore: release 4.3.5`

只采用该 commit 内的以下证据：

- 根 README 与各语言 SDK README；
- Python binding 源码及 `.pyi` 类型定义；
- Rust core 源码及类型定义；
- 仓库内 examples。

证据引用格式为：

```text
longportapp/openapi@fa0ec53:<repository path>
```

本文不使用开发者网站、独立 MCP 仓库或其他平台资料作为能力证据。因此：

- SDK 仓库没有暴露的 MCP、Skill、CLI 或平台能力，不记为已证明能力；
- Rust 源码中的 HTTP path 只用于解释 Rust method 的内部实现，不把 path 名称写成 Python SDK 方法名；
- README、类型定义或 method 存在，只能证明 SDK surface，不能证明 A 股实际返回、权限、完整性、单位或稳定性；
- 任何进入 G1/G2/G3 的字段，最终都必须通过 A 股 runtime probe 和项目 Gate。

### 0.2 核心证据索引

| 证据主题 | 仓库内证据 |
|---|---|
| Python 安装、Context 基本用法 | `longportapp/openapi@fa0ec53:python/README.md` |
| Python 完整公开类型签名 | `longportapp/openapi@fa0ec53:python/pysrc/longport/openapi.pyi` |
| Python Quote binding | `longportapp/openapi@fa0ec53:python/src/quote/context.rs`、`python/src/quote/types.rs` |
| Python Fundamental binding | `longportapp/openapi@fa0ec53:python/src/fundamental/context.rs`、`python/src/fundamental/types.rs` |
| Python Screener binding | `longportapp/openapi@fa0ec53:python/src/screener/context.rs`、`python/src/screener/types.rs` |
| Rust Quote core | `longportapp/openapi@fa0ec53:rust/src/quote/context.rs`、`rust/src/quote/types.rs` |
| Rust Fundamental core | `longportapp/openapi@fa0ec53:rust/src/fundamental/context.rs`、`rust/src/fundamental/types.rs` |
| Rust Screener core | `longportapp/openapi@fa0ec53:rust/src/screener/context.rs`、`rust/src/screener/types.rs` |
| Python 历史 K 线示例 | `longportapp/openapi@fa0ec53:examples/python/history_candlesticks.py`、`examples/python/history_candlesticks_async.py` |
| A 股 symbol/counter-id 转换 | `longportapp/openapi@fa0ec53:rust/src/utils/counter.rs` |
| Screener market 可传 `CN` 的 Python 类型说明 | `longportapp/openapi@fa0ec53:python/pysrc/longport/openapi.pyi` |

## 1. 结论摘要

仅根据官方 SDK 仓库，当前可以确认：

1. Python SDK 暴露行情、静态信息、计算指标、两种历史 K 线、财务报告、估值、行业估值、机构评级/共识、公司概况、股东、经营数据、估值对比和 Screener 等方法。
2. Rust core 还额外暴露 `business_segments`、`business_segments_history`、`industry_rank`、`industry_peers`、`financial_report_snapshot` 等方法；这些方法当前未出现在 Python `FundamentalContext` binding 和 `.pyi` 中。
3. Python 估值方法名是 `valuation()`，不是 `valuations()`；行业估值方法是 `industry_valuation()` / `industry_valuation_dist()`；历史 K 线方法是 `history_candlesticks_by_offset()` / `history_candlesticks_by_date()`。
4. SDK 类型证明 `calc_indexes` 可返回当前 PE/PB/市值/换手率等可选字段，Candlestick 可返回 OHLC、成交量和成交额，但不含历史换手率字段。
5. SDK 接受 `.SH` / `.SZ` symbol，并在 Screener 的 Python 类型说明中列出 `CN` market code；这仍不足以证明任一基本面字段对 A 股可用。
6. SDK 仓库不能证明 MCP、Skill、正式数据 CLI、平台级研究工具或账户区域限制；这些内容不进入本文件的已证明能力。

因此，LongPort 当前只能定位为：

```text
LongPort Python SDK
    → candidate provider
    → raw response + provenance/status
    → canonical snapshot
    → trade-agent G1/G2/G3
```

Rust-only method 若确有必要，应另行评估 Rust 接入或等待 Python binding 暴露；不能把 Rust core method 直接写成 Python 已可调用能力。

## 2. 判定原则

### 2.1 四层证据必须分开

| 层级 | 本文含义 |
|---|---|
| SDK method 存在 | 对应语言的 Context 公开该方法 |
| 类型字段存在 | SDK 类型定义中有该字段 |
| A 股 symbol/market 可表达 | SDK 能表达 `.SH`、`.SZ` 或 `CN` |
| A 股字段可消费 | runtime 返回、口径、单位、时点、完整性和失败语义均满足项目契约 |

前三层都不能自动推出第四层。

### 2.2 状态定义

| 状态 | 含义 |
|---|---|
| `candidate` | Python SDK method 和对应类型均存在，可进入 A 股 probe |
| `rust_only` | Rust core 存在，但当前 Python binding 未暴露 |
| `adaptable` | 可由已暴露字段派生或映射，但必须确认口径、单位、报告期或缺失语义 |
| `unconfirmed` | SDK surface 存在，但 A 股实际返回或项目所需字段不能由仓库静态证据证明 |
| `missing` | 本次 SDK 仓库核对未发现满足项目契约的 method/字段 |
| `not_considered` | 当前不属于相应 Gate 的 required 字段 |

`candidate` 和 `adaptable` 都不等于已通过 Gate。

### 2.3 市场表达边界

SDK 仓库可证明：

- symbol/counter-id 转换代码处理 `000001.SZ` 等带前导零的 A 股代码；
- Python Screener 类型说明列出 market code `"CN"`；
- Quote/Fundamental 的多数 method 接受自由字符串 symbol。

证据：

- `longportapp/openapi@fa0ec53:rust/src/utils/counter.rs`
- `longportapp/openapi@fa0ec53:python/pysrc/longport/openapi.pyi`

SDK 仓库不能静态证明：

- 某个 Fundamental method 对 `.SH` / `.SZ` 一定返回非空；
- A 股字段与美股、港股具有相同 schema 完整度；
- 账户权限、区域或数据套餐限制；
- 全 A 股覆盖率、分页上限、限流和历史长度。

## 3. 当前项目字段契约

### 3.1 G1 量化维度

```python
G1_QUANT_DIMENSIONS = (
    "basic",
    "financials",
    "kline",
    "valuation",
    "risk",
)
```

主要服务于：

- hard gates：上市年限、市值、PE×PB、质押率、审计意见；
- factor ranking：F-Score、ROE、估值分位、行业 PE 折价、质押率；
- anti-trap：ROE 趋势、商誉比、质押率、审计意见；
- heat filter：近 60 个交易日收盘价和换手率；
- L2 成本闸门：结构化 Scout 输入。

### 3.2 G1/L2 关键字段

```text
name
industry
market_cap
pe_ttm
pb
pe_percentile_5y
roe_3y
net_margin
debt_ratio
goodwill_ratio
operating_cashflow
net_profit
revenue_growth
pledge_ratio
audit_opinion
price_change_60d
turnover_avg_percentile_60d
f_score
```

派生字段仍必须追溯到 provider 原始字段、报告期和单位。

### 3.3 G2/L3 dossier 字段

```text
main_business
peers
research
capex_proxy
pledge
```

G2 数据不得污染 G1 全市场批量路径；字段不足时必须保留 `degraded` / `insufficient_data`，不得让 L3 用空数据生成完整 thesis。

### 3.4 G3 边界

外部 provider 只提供行情、财报、分红、公司行动等候选事实。以下能力仍属于项目自身契约：

- `HoldingContract`
- thesis-break 判断
- 关键变量
- 反证和待验证事项
- 人的最终持仓和交易决策

## 4. Python SDK 与 Rust core 暴露差异

### 4.1 两端均暴露的主要能力

| 能力 | Python method | Rust core method | 证据 |
|---|---|---|---|
| 静态信息 | `QuoteContext.static_info()` | `QuoteContext::static_info()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 实时报价 | `QuoteContext.quote()` | `QuoteContext::quote()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 当前计算指标 | `QuoteContext.calc_indexes()` | `QuoteContext::calc_indexes()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 最近 K 线 | `QuoteContext.candlesticks()` | `QuoteContext::candlesticks()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 按 offset 历史 K 线 | `QuoteContext.history_candlesticks_by_offset()` | `QuoteContext::history_candlesticks_by_offset()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 按日期历史 K 线 | `QuoteContext.history_candlesticks_by_date()` | `QuoteContext::history_candlesticks_by_date()` | `python/src/quote/context.rs`；`rust/src/quote/context.rs` |
| 财务报告 | `FundamentalContext.financial_report()` | `FundamentalContext::financial_report()` | `python/src/fundamental/context.rs`；`rust/src/fundamental/context.rs` |
| 估值 | `FundamentalContext.valuation()` | `FundamentalContext::valuation()` | 同上 |
| 估值历史 | `FundamentalContext.valuation_history()` | `FundamentalContext::valuation_history()` | 同上 |
| 行业估值列表 | `FundamentalContext.industry_valuation()` | `FundamentalContext::industry_valuation()` | 同上 |
| 行业估值分布 | `FundamentalContext.industry_valuation_dist()` | `FundamentalContext::industry_valuation_dist()` | 同上 |
| 经营数据 | `FundamentalContext.operating()` | `FundamentalContext::operating()` | 同上 |
| 估值对比 | `FundamentalContext.valuation_comparison()` | `FundamentalContext::valuation_comparison()` | 同上 |
| Screener 搜索 | `ScreenerContext.screener_search()` | `ScreenerContext::screener_search()` | `python/src/screener/context.rs`；`rust/src/screener/context.rs` |
| Screener 指标 | `ScreenerContext.screener_indicators()` | `ScreenerContext::screener_indicators()` | 同上 |

以上全部固定到 `longportapp/openapi@fa0ec53`。

### 4.2 Rust core 已有、当前 Python binding 未暴露

| Rust core method | Rust 类型 | Python 状态 | 证据 |
|---|---|---|---|
| `business_segments()` | `BusinessSegments` | `rust_only` | `rust/src/fundamental/context.rs`；`rust/src/fundamental/types.rs`；Python `context.rs`/`.pyi` 无对应 method |
| `business_segments_history()` | `BusinessSegmentsHistory` | `rust_only` | 同上 |
| `industry_rank()` | `IndustryRankResponse` | `rust_only` | 同上 |
| `industry_peers()` | `IndustryPeersResponse` | `rust_only` | 同上 |
| `financial_report_snapshot()` | `FinancialReportSnapshot` | `rust_only` | 同上 |
| `institution_rating_views()` | `InstitutionRatingViews` | `rust_only` | 同上 |

结论：当前 Python provider 设计不能直接依赖这些 method。Rust 内部使用的 HTTP path 也不是 Python method 名称或独立能力合同。

## 5. SDK 能力清单与命名校正

| 能力 | 正确 SDK surface | 类型可证明的主要内容 | A 股判定 | 证据 |
|---|---|---|---|---|
| 实时报价 | `quote()` | 最新价、开高低、时间、成交量、成交额、交易状态 | `unconfirmed` | `python/src/quote/context.rs`；`rust/src/quote/types.rs::RealtimeQuote` |
| 静态信息 | `static_info()` | 名称、交易所、币种、手数、总/流通股本、EPS、TTM EPS、BPS、每股分红、板块 | `candidate` | `python/src/quote/context.rs`；`rust/src/quote/types.rs::SecurityStaticInfo` |
| 当前计算指标 | `calc_indexes()` | 当前价、涨跌、成交量/额、换手率、市值、PE TTM、PB、股息率等可选字段 | `candidate` | `python/src/quote/context.rs`；`rust/src/quote/types.rs::SecurityCalcIndex` |
| 最近 K 线 | `candlesticks()` | OHLC、成交量、成交额、时间、交易时段 | `candidate` | `python/src/quote/context.rs`；`rust/src/quote/types.rs::Candlestick` |
| 历史 K 线 | `history_candlesticks_by_offset()` / `history_candlesticks_by_date()` | 返回同一 `Candlestick` 类型 | `candidate` | `python/src/quote/context.rs`；`examples/python/history_candlesticks.py` |
| 财务报告 | `financial_report()` | IS/BS/CF/ALL、报告周期及动态报告结构 | `unconfirmed` | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| 估值 | `valuation()` | PE/PB/PS/股息率的统计值和历史点 | `unconfirmed` | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::ValuationData` |
| 估值历史 | `valuation_history()` | PE/PB/PS 的 high/low/median/list | `unconfirmed` | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::ValuationHistoryResponse` |
| 行业估值 | `industry_valuation()` | 同行 symbol/name/currency/assets/BPS/EPS/DPS/PE 及历史 PE/PB/PS | `unconfirmed` | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::IndustryValuationList` |
| 行业估值分布 | `industry_valuation_dist()` | PE/PB/PS 的 low/high/median/value/ranking 等 | `unconfirmed` | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::IndustryValuationDist` |
| 机构评级/共识 | `institution_rating()`、`institution_rating_detail()`、`ratings()`、`forecast_eps()`、`consensus()` | 对应 Python 类型定义中的评级、预测和共识结构 | `unconfirmed` | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| 公司与治理 | `company()`、`executive()`、`shareholder()`、`shareholder_top()`、`shareholder_detail()`、`fund_holder()` | 公司概况、高管、股东和基金持仓结构 | `unconfirmed` | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| 经营数据 | `operating()` | 报告项、财务摘要、经营指标等结构 | `unconfirmed` | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::OperatingList` |
| 公司行动/分红 | `corp_action()`、`dividend()`、`dividend_detail()` | 公司行动和分红类型 | `unconfirmed` | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| Screener | `screener_search()`、`screener_indicators()` | market 字符串、条件、show、分页；响应主要保留 raw JSON | `unconfirmed` | `python/src/screener/context.rs`；`rust/src/screener/types.rs`；`python/pysrc/longport/openapi.pyi` |
| 业务分部 | Rust `business_segments()` / `business_segments_history()` | 最新分部含名称/占比；历史结构另含地区、金额 | `rust_only` | `rust/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::BusinessSegments*` |
| 行业排行/层级 | Rust `industry_rank()` / `industry_peers()` | Rust 类型保留排行或行业链结构 | `rust_only` | `rust/src/fundamental/context.rs`；`rust/src/fundamental/types.rs` |

注意：

- 不使用 `valuations` 作为 SDK method 名；
- 不使用泛化的 `history_candlesticks` 作为 Python method 名；
- 不把 `industry_valuation` 与 Rust-only 的 `industry_rank` / `industry_peers` 混为一谈；
- 不从 Rust method 内部 HTTP path 推导 Python、MCP、Skill 或平台能力。

## 6. G1 字段匹配矩阵

### 6.1 `basic`

| 当前字段 | LongPort 候选 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `code` | method 的 symbol 参数/响应 symbol | `adaptable` | canonical ticker 保持 `.SH` / `.SZ` | `rust/src/utils/counter.rs`；`rust/src/quote/types.rs` |
| `name` | `static_info().name_cn/name_en/name_hk` | `candidate` | 需定义语言优先级和空值状态 | `rust/src/quote/types.rs::SecurityStaticInfo` |
| `price` | `quote().last_done` 或 `calc_indexes().last_done` | `candidate` | 保留 `as_of`、交易状态和来源 method | `rust/src/quote/types.rs::RealtimeQuote/SecurityCalcIndex` |
| `pe_ttm` | `calc_indexes().pe_ttm_ratio` | `candidate` | `Option` 字段；负值、空值不得改写为 0 | `rust/src/quote/types.rs::SecurityCalcIndex` |
| `pb` | `calc_indexes().pb_ratio` | `candidate` | 确认数值口径 | 同上 |
| `market_cap` | `calc_indexes().total_market_value` | `candidate` | 实测单位后再映射 | 同上 |
| `turnover_rate` | `calc_indexes().turnover_rate` | `candidate` | 仅证明当前指标，不证明历史序列 | 同上 |
| `industry` | Screener raw JSON 或 Fundamental 行业类能力 | `unconfirmed` | 类型未给出稳定的 Python 单股行业字段合同 | `rust/src/screener/types.rs`；`python/src/fundamental/context.rs` |
| `listing_date` | 未在 `SecurityStaticInfo` 中发现 | `missing` | 不得把其他日期字段替代上市日期 | `rust/src/quote/types.rs::SecurityStaticInfo` |
| `total_shares` | `static_info().total_shares` | `candidate` | 实测单位和更新时点 | 同上 |
| `circulating_shares` | `static_info().circulating_shares` | `candidate` | 非当前 G1 required | 同上 |

### 6.2 `financials`

Python `financial_report(symbol, kind, period)` 已暴露，但返回为动态财务报告结构。静态仓库证据不能证明 A 股具体科目名称和完整性。

证据：

- `longportapp/openapi@fa0ec53:python/src/fundamental/context.rs`
- `longportapp/openapi@fa0ec53:python/src/fundamental/types.rs`
- `longportapp/openapi@fa0ec53:rust/src/fundamental/types.rs`

| 当前字段组 | 状态 | 必须验证 |
|---|---|---|
| `years` / 报告期 | `adaptable` | 年报筛选、排序、财年结束日 |
| revenue / net profit / operating cost | `unconfirmed` | A 股实际 field/name、归母口径、单位 |
| operating cash flow | `unconfirmed` | CF 科目与期间口径 |
| total/current assets and liabilities | `unconfirmed` | A 股 BS 科目和单位 |
| share capital / goodwill | `unconfirmed` | 具体科目是否返回 |
| `CONSTRUCT_LONG_ASSET` | `unconfirmed` | 购建长期资产现金支出科目是否返回 |
| currency / unit | `adaptable` | 币种、缩放单位、跨期一致性 |
| financials floor | `adaptable` | 不足三年时必须 `not_evaluable` |

Rust-only 的 `financial_report_snapshot()` 含收入、净利润、现金流、资产负债、ROE、利润率等汇总字段，但当前 Python binding 未暴露，不能作为 Python provider 的现成替代。

证据：`longportapp/openapi@fa0ec53:rust/src/fundamental/context.rs`、`rust/src/fundamental/types.rs::FinancialReportSnapshot`。

### 6.3 `kline`

| 当前字段 | LongPort 候选 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `dates` | `Candlestick.timestamp` | `candidate` | 统一交易日和时区 | `rust/src/quote/types.rs::Candlestick` |
| `close` | `Candlestick.close` | `candidate` | 固定 `AdjustType` | 同上；`examples/python/history_candlesticks.py` |
| `volume` | `Candlestick.volume` | `candidate` | 实测单位 | 同上 |
| `turnover` | `Candlestick.turnover` | `candidate` | 是成交额，不是换手率 | 同上 |
| 历史 `turnover_rate` | Candlestick 无此字段 | `missing` | 不得用当前 `calc_indexes.turnover_rate` 伪造历史序列 | `rust/src/quote/types.rs::Candlestick/SecurityCalcIndex` |
| `price_change_60d` | 由复权 close 派生 | `adaptable` | 需要至少 60 个有效交易日 | 同上 |

Python 正确方法名：

```python
ctx.candlesticks(...)
ctx.history_candlesticks_by_offset(...)
ctx.history_candlesticks_by_date(...)
```

### 6.4 `valuation`

| 当前字段 | LongPort 候选 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `pe_ttm` | `calc_indexes().pe_ttm_ratio` | `candidate` | 当前值优先来自明确标注 TTM 的字段 | `rust/src/quote/types.rs::SecurityCalcIndex` |
| `pb` | `calc_indexes().pb_ratio` | `candidate` | 与历史 PB 口径需实测 | 同上 |
| `pe_history` | `valuation_history().history.metrics.pe.list` | `unconfirmed` | A 股返回长度和频率待 probe | `rust/src/fundamental/types.rs::ValuationHistory*` |
| `pb_history` | `valuation_history().history.metrics.pb.list` | `unconfirmed` | 同上 | 同上 |
| `pe_percentile_5y` | `valuation()` 的描述/统计或由历史序列自算 | `adaptable` | 不依赖自然语言 `desc` 作为 ranking 真值 | `rust/src/fundamental/types.rs::ValuationData` |
| `pb_percentile_5y` | 同上 | `adaptable` | 固定窗口和异常值规则 | 同上 |
| `graham_number` | SDK 无直接字段 | `missing` | 保持项目派生口径 | 本次 SDK surface/type 扫描 |

### 6.5 `risk`

| 当前字段 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|
| `pledge_ratio` | `missing` | 股东或基金持仓不能替代质押率 | 本次 Python/Rust Fundamental method/type 扫描 |
| `pledge_status` | `missing` | 保留项目 `record_not_found/source_failed/invalid_value` 等状态 | 同上 |
| `audit_opinion` | `missing` | 不得从公告、财报非空或标题推断 | 同上 |
| `goodwill` | `unconfirmed` | 只能在 A 股财报实际科目映射后使用 | `financial_report()` 动态结构 |
| `goodwill_ratio` | `adaptable` | 商誉和净资产两端均需有效 | 项目派生字段 |

`risk` 仍是 LongPort 候选 provider 对 G1 的主要缺口。

## 7. G2/L3 dossier 匹配矩阵

### 7.1 `main_business`

| 当前字段 | 候选能力 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `by_industry` / `by_product` | Rust `business_segments()` | `rust_only` | 类型只有统一 `business` 列表，不能静态证明分类语义 | `rust/src/fundamental/types.rs::BusinessSegments` |
| `by_region` | Rust `business_segments_history()` | `rust_only` | 历史类型有 `regionals`，A 股返回待 probe | `rust/src/fundamental/types.rs::BusinessSegmentsHistory` |
| `revenue_ratio` | segment `percent` | `rust_only` | 字符串比例需校验 | 同上 |
| `revenue` | history item `value` / total | `rust_only` | 币种和单位需校验 | 同上 |
| `gross_margin` | 未发现 segment 毛利率字段 | `missing` | 不得由收入占比推断 | 同上 |
| `main_business_text` | `company()` / `operating()` 候选文本或结构 | `unconfirmed` | 不能替代结构化主营构成 | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |

在 Python provider 下，`main_business` 不能依赖 Rust-only surface；未完成接入与 probe 前应 fail closed。

### 7.2 `peers`

| 当前字段 | 候选能力 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `peer_pe_list` | Python `industry_valuation()` | `unconfirmed` | 类型有同行 PE，但 A 股返回待 probe | `python/src/fundamental/context.rs`；`rust/src/fundamental/types.rs::IndustryValuationList` |
| `peer_avg_pe` | 由有效同行 PE 派生 | `adaptable` | 明确排除规则并同时保留中位数 | 同上 |
| `industry_pe_rank` | `industry_valuation_dist().ranking` 候选 | `unconfirmed` | 先确认 ranking 含义和方向 | `rust/src/fundamental/types.rs::IndustryValuationDist` |
| `industry` / hierarchy | Rust `industry_peers()` | `rust_only` | Python 未暴露 | `rust/src/fundamental/context.rs`；`rust/src/fundamental/types.rs` |
| 行业排行 | Rust `industry_rank()` | `rust_only` | Python 未暴露；不等同于单股同行估值 | 同上 |

### 7.3 `research`

| 当前字段 | Python 候选 method | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `consensus_eps` | `forecast_eps()` / `consensus()` | `unconfirmed` | A 股覆盖、预测期和口径待 probe | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| `target_price` | `institution_rating*()` / `ratings()` 类型中的候选字段 | `unconfirmed` | 不与项目派生目标价混用 | 同上 |
| `buy_rating_pct` | 评级结构派生 | `adaptable` | 评级枚举映射后再计算 | 同上 |
| `coverage_count` | 分析师数或评级明细数候选 | `unconfirmed` | 不直接等同研报篇数 | 同上 |
| `rating_distribution` | `institution_rating()` / `ratings()` | `unconfirmed` | 保留原始枚举和来源 | 同上 |

即使 probe 成功，这些字段也只能进入“市场预期”，不能写入“公司事实”。

### 7.4 `capex_proxy`

| 当前字段 | 候选能力 | 状态 | 处理与限制 | 证据 |
|---|---|---|---|---|
| `CONSTRUCT_LONG_ASSET` | `financial_report(kind=CashFlow)` 动态科目 | `unconfirmed` | 需确认 A 股字段名、单位和报告期 | `python/src/fundamental/context.rs`；`python/src/fundamental/types.rs` |
| `series` | 多报告期 values | `adaptable` | 至少两期或三期，并固定排序 | 同上 |
| `latest` | 最新有效报告期 | `adaptable` | 保存 `as_of` 和 `report_period` | 同上 |

## 8. 当前可进入 probe、Rust-only 与缺失清单

### 8.1 Python SDK 可进入 A 股 probe

- `quote`
- `static_info`
- `calc_indexes`
- `candlesticks`
- `history_candlesticks_by_offset`
- `history_candlesticks_by_date`
- `financial_report`
- `valuation`
- `valuation_history`
- `industry_valuation`
- `industry_valuation_dist`
- `valuation_comparison`
- `institution_rating`
- `institution_rating_detail`
- `ratings`
- `forecast_eps`
- `consensus`
- `company`
- `operating`
- `shareholder` / `shareholder_top` / `shareholder_detail`
- `fund_holder`
- `corp_action`
- `dividend` / `dividend_detail`
- `screener_search`
- `screener_indicators`

统一证据：`longportapp/openapi@fa0ec53:python/src/**/context.rs` 与 `python/pysrc/longport/openapi.pyi`。

### 8.2 当前仅 Rust core 暴露

- `business_segments`
- `business_segments_history`
- `industry_rank`
- `industry_peers`
- `financial_report_snapshot`
- `institution_rating_views`

统一证据：`longportapp/openapi@fa0ec53:rust/src/fundamental/context.rs`；Python `FundamentalContext` 与 `.pyi` 无对应 method。

### 8.3 当前 SDK 仓库不能证明满足项目契约

- A 股全市场基础快照覆盖率；
- `listing_date`；
- 历史换手率序列；
- 质押率及 `pledge_status`；
- 审计意见；
- 所有 F-Score 原始科目的 A 股稳定映射；
- Python 可直接调用的业务分部和行业层级；
- 分部毛利率；
- A 股研报篇数、评级覆盖和共识完整性；
- A 股公司行动是否足以作为 G3 事件源；
- MCP、Skill、正式数据 CLI 或平台研究能力；
- 账户区域、数据中心、套餐和权限限制。

## 9. 对 G1/G2/G3 的影响

### G1

可优先验证：

```text
screener_search(market="CN")
    → 候选发现
calc_indexes + static_info + history_candlesticks_* + financial_report
    → 结构化补数
trade-agent L1
    → 自己计算 F-Score、估值分位、反陷阱和热度
```

但以下任一 required 字段缺失时，不能宣称完整替代现有链路：

- 上市年限来源；
- 质押率；
- 审计意见；
- 历史换手率；
- F-Score 关键财务科目。

### G2

Python 已有行业估值、评级、共识、公司概况和经营数据候选 method；业务分部和行业层级仍是 Rust-only。dossier 必须保留：

```text
source
sdk_language
sdk_method
sdk_commit
market
report_period
as_of
field_status
raw_field
mapping_note
```

数据不足时必须 `degraded` 或 `insufficient_data`。

### G3

`quote`、`corp_action`、`dividend` 和财务相关 method 可作为事件候选，但只有 runtime probe 能证明 A 股覆盖。provider 数据不能替代项目自己的持有纪律和 thesis-break 判断。

## 10. 必做的 A 股 probe

建议样本：

```text
600519.SH
600009.SH
000858.SZ
300750.SZ
601318.SH
```

| Probe | 必须确认 |
|---|---|
| Screener | `market="CN"` 实际可用性、指标 raw schema、分页总数、show 字段 |
| `calc_indexes` | PE/PB/市值/换手率单位、空值和亏损股行为 |
| `static_info` | 名称、股本、EPS/BPS、board；确认确实没有上市日期 |
| `history_candlesticks_by_*` | 复权、长度、成交量/额、日期边界；确认不含换手率 |
| `financial_report` | IS/BS/CF 科目、报告期、币种、单位、三年完整性 |
| `valuation` / `valuation_history` | PE/PB 历史长度、异常值、统计窗口 |
| `industry_valuation*` | A 股同行列表、PE/PB/PS、ranking 语义 |
| `company` / `operating` | A 股文本和经营指标实际结构 |
| ratings / consensus | 覆盖数量、枚举、预测期、分析师数 |
| governance | 质押率、审计意见、商誉是否只能从其他来源补齐 |

若后续选择 Rust 接入，再单独 probe：

- `business_segments*`
- `industry_rank`
- `industry_peers`
- `financial_report_snapshot`

Probe 输出至少记录：

```text
run_id
canonical_ticker
sdk_language
sdk_method
sdk_commit
request_params
as_of
raw_response_hash
raw_response_path
field_status
error_code
mapping_note
```

缺失状态必须区分：

```text
record_not_found
source_failed
permission_denied
not_supported_for_market
invalid_value
not_evaluated
```

## 11. 采用 LongPort 前的 Gate

LongPort provider 只有满足以下条件，才能进入正式 G1/G2 数据路径：

1. 通过至少 5 只不同类型 A 股的字段 probe；
2. 财报关键字段完成固定映射和单位测试；
3. 关键字段可用率按 `usable/degraded/blocking_error/manual_action` 分开统计；
4. 不把 SDK method 存在当作 A 股字段可用；
5. 不把 Rust-only method 当作 Python 已暴露；
6. 缺失不静默填默认值；
7. G1 至少完成 300 只多行业样本；
8. 全市场规模下验证分页、限流、耗时和失败隔离；
9. G2 与 G1 保持 staged-fetch boundary；
10. 每个进入 L3 的事实都能追溯到 SDK method、commit、原始字段和报告期；
11. 与当前 provider 做字段级差异报告，而不是只比较最终候选数量。

在这些 Gate 通过前：

- 不替换现有 provider；
- 不把非空返回直接计入 `usable_rate`；
- 不用 mock、示例运行成功或 method 可调用证明 A 股 capability；
- 不把其他市场的 example 当作 A 股覆盖；
- 不把 Screener 结果直接当作 trade-agent 的 L1 最终排序；
- 不让 G2/G3 agent 自由拉取未冻结的临时数据。

## 12. 维护规则

每次 SDK 仓库发生变化时：

1. 固定新的 commit；
2. 逐语言检查 Context 和 `.pyi`，不能只看 Rust core；
3. 检查 method 名和返回类型，不沿用 HTTP、MCP 或其他平台命名；
4. 重新检查 `.SH` / `.SZ` / `CN` 的表达能力；
5. 重新执行 A 股 probe；
6. 同步更新 provider mapping、字段状态和下游 Gate；
7. 字段口径变化时更新项目 data contract 和测试；
8. 不以 method、example 或 raw endpoint 存在替代 runtime 证据。

## 13. 变更记录

### 2026-07-30

- 初次建立 A 股字段匹配记录；
- 建立 G1/G2/G3 字段与 Gate 的对应关系。

### 2026-07-31

- 将唯一外部事实来源收敛为 `longportapp/openapi@fa0ec53f80573f448054e9e8e4abf269031a1b39`；
- 删除不能由该 SDK 仓库证明的 MCP、Skill、CLI、平台能力和账户数据中心限制；
- 将 SDK method 存在与 A 股 runtime 可用性分开，未实测能力统一降级；
- 修正方法名：`valuation()`、`industry_valuation()`、`industry_valuation_dist()`、`history_candlesticks_by_offset()`、`history_candlesticks_by_date()`；
- 明确 `business_segments*`、`industry_rank`、`industry_peers`、`financial_report_snapshot` 等为 Rust-only，当前 Python binding 未暴露；
- 修正 `SecurityStaticInfo` 不含 `listing_date`，Candlestick 不含历史 `turnover_rate`；
- 为每类外部能力补充官方 SDK 仓库路径和固定 commit 证据；
- 保留项目 G1/G2/G3 字段契约、fail-closed 原则和 Capability Gate。
