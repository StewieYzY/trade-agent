## ADDED Requirements

### Requirement: L1 主入口的采集维度边界

`screen_a_shares()` 调用 `BatchFetcher.fetch_all()` 时 SHALL 显式传入 G1 量化维度白名单 `("basic", "financials", "kline", "valuation", "risk")`，MUST NOT 依赖 `dimensions=None` 的全采兜底，从而避免全市场路径默认采集属于 G2/L3 的 dossier 维度（`main_business`/`peers`/`research`）。

#### Scenario: screen_a_shares 显式传入量化维度白名单

- **WHEN** `screen_a_shares(tickers)` 被调用
- **THEN** 传给 `BatchFetcher.fetch_all` 的 `dimensions` 参数 SHALL 恰为 `("basic", "financials", "kline", "valuation", "risk")`，MUST NOT 包含 `"main_business"`、`"peers"`、`"research"`

#### Scenario: L1 维度白名单为模块级常量

- **WHEN** `screen_a_shares` 构造对 `fetch_all` 的调用
- **THEN** 维度白名单 SHALL 来自 `screener/main.py` 模块级常量 `G1_QUANT_DIMENSIONS`，而非内联字面量，便于测试与未来调用方引用
