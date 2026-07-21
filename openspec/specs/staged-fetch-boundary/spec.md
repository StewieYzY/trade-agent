# staged-fetch-boundary Specification

## Purpose

定义 G1 快速筛选与 G2/L3 深研之间的采集边界：L1 全市场路径只采集量化筛选所需维度，避免默认采集 dossier 数据，并用漏斗计数与失败隔离证据证明候选 ticker 集合可控缩小。

## Requirements
### Requirement: L1 全市场路径的采集维度白名单

L1 主入口 `screen_a_shares()` 调用 `BatchFetcher.fetch_all()` 时 SHALL 显式传入 G1 量化维度白名单 `("basic", "financials", "kline", "valuation", "risk")`，MUST NOT 依赖 `dimensions=None` 的全采兜底。

#### Scenario: L1 不采集 dossier 三维

- **WHEN** `screen_a_shares(tickers)` 被调用
- **THEN** 传给 `BatchFetcher.fetch_all` 的 `dimensions` 参数 SHALL 恰为 `("basic", "financials", "kline", "valuation", "risk")`，MUST NOT 包含 `"main_business"`、`"peers"` 或 `"research"`

#### Scenario: L1 维度白名单由模块级常量定义

- **WHEN** 测试或其他调用方需要引用 G1 量化维度集合
- **THEN** `screener/main.py` SHALL 暴露一个模块级常量（如 `G1_QUANT_DIMENSIONS`），其值为 G1 量化五维的有序集合，`screen_a_shares` 调用 `fetch_all` 时 SHALL 引用该常量

### Requirement: ticker 集合随漏斗逐层缩小

L1 漏斗各阶段输出的 ticker 计数 SHALL 满足反向单调性 `total ≥ after_hard_gates ≥ after_factors ≥ after_heat_filter`，证明 ticker 集合随漏斗逐层缩小。

#### Scenario: 漏斗计数反向单调

- **WHEN** `screen_a_shares(tickers)` 被调用且样本含能过/不能过各 gate 的混合 ticker
- **THEN** 返回 `stats` 中的计数 SHALL 满足 `stats["total"] >= stats["after_hard_gates"] >= stats["after_factors"] >= stats["after_heat_filter"]`

#### Scenario: 下游 fetch 消费缩小的 ticker 集合

- **WHEN** L1 输出（`candidates`，数量 = `after_heat_filter`）被 L2 `scout_batch` 消费，L2 输出（`shortlist`，≤20）被 L3 `build_research_dossier` 消费
- **THEN** 下游 fetch/LLM 调用的 ticker 集合 SHALL 分别不超过上一漏斗阶段的输出集合大小，即 L2 处理集合 ≤ `after_heat_filter`，L3 dossier fetch 集合 ≤ L2 shortlist 大小

### Requirement: 单股失败隔离不回归

L1 维度白名单化后，单只股票在某量化维度采集失败 SHALL 不影响其他 ticker 与其他维度，与既有 `BatchFetcher` resume/失败隔离行为一致。

#### Scenario: 单股单维度失败不阻断整批

- **WHEN** `screen_a_shares` 采集中某 ticker 的某一量化维度失败（`fetch_with_fallback` 返回 `__error__`）
- **THEN** 该 ticker 其他维度与其他 ticker SHALL 继续采集，MUST NOT 因单点失败中断整个 `screen_a_shares`
