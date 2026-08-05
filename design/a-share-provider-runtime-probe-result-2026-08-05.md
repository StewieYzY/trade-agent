# A-share Provider Runtime Probe Result — 2026-08-05

## Run

- Provider adapter: `baseline / akshare-existing-fetcher-chain`
- Probe plan: `a-share-provider-qualification-v1`
- Tickers: `600519.SH`, `600009.SH`, `000858.SZ`, `300750.SZ`, `601318.SH`
- Code version: `b6385687c1bc796050802dac7a9ae6e9e99a71bc`
- Run ID: `baseline-20260805-a`
- Evidence root: `/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805/baseline-20260805-a`

## Result

本次是一次真实只读 runtime probe，结果为 bounded failure，不构成 provider qualification 或 G1 capability pass。

- `source_failed`: 50
- `not_evaluated`: 115
- `available`: 0
- `partial`: 0
- `record_not_found`: 0

主要原因：

1. `static_info`、`quote`、`calc_indexes` 通过现有 `BasicFetcher` 链路运行，但得到 `KeyError: stock_zh_a_spot_em empty`，5 只 ticker 均失败。
2. `historical_kline`、财务报表、历史估值依赖的 `akshare` 未安装，均为 `ModuleNotFoundError: No module named 'akshare'`，保持 `not_evaluated`。
3. `industry_valuation`、`consensus` 在当前 baseline contract 中没有 ticker-aligned implementation，保持 `not_evaluated`。

本次没有 LongPort/Longbridge runtime call：当前环境没有显式 SDK/凭据配置；两者继续保持 candidate/blocked，不进入 canonical snapshot。

## Boundary

- 未写入 legacy cache、ranking、canonical snapshot、watchlist 或 debate。
- 未把 `source_failed`/`not_evaluated` 转成可用值。
- `raw.json`、`evidence.json`、`comparison.json`、`method-results.json` 和 `manifest.json` 均按 run-scoped 目录保留。
- 后续若要重跑，需先由用户明确授权在隔离环境安装或启用项目已有 `requirements.txt` 依赖，并重新验证网络 source；不得以本次结果放行 provider。

## Corrected runtime run — 2026-08-05

上面的 `baseline-20260805-a` 使用了系统 Python `/opt/homebrew/bin/python3`，不是仓库运行环境，因此其中的 `akshare missing` 只能作为环境误用记录，不能作为项目 provider 结论。

使用仓库已有 venv `/Users/admin/Documents/trade-agent/value-screener/.venv` 重跑：

- Provider: `baseline / akshare-existing-fetcher-chain`
- Run ID: `baseline-20260805-b`
- Code version: `23c791d977c7455a6adb1c09dac885fc45e5ed7f`
- Evidence root: `/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805/baseline-20260805-b`
- `available`: 75
- `record_not_found`: 50
- `invalid_value`: 10
- `not_evaluated`: 30

字段级结果：

- 可用：static info 的 code/name/market；quote 的 last_price；calc_indexes 的 pe_ttm/pb；historical kline 的 dates/close；income statement 的 report_period/revenue/net_profit；balance sheet/cash flow 的 report_period；historical valuation 的 pe_ttm/pb。
- `record_not_found`：previous_close、volume、turnover_rate、dividend_yield、部分资产负债表/现金流字段、historical valuation 的 as_of。
- `invalid_value`：historical kline 的 volume/turnover_rate，原因是 numeric field not finite。
- `not_evaluated`：industry valuation、consensus；当前 baseline contract 没有 ticker-aligned implementation。

该 corrected run 证明现有 baseline chain 在部分字段上有真实 A 股返回，但仍是 partial/field-incomplete evidence，不能替代 provider qualification、canonical consumer Gate 或 G1 capability pass。LongPort/Longbridge 仍未调用，因为没有显式 SDK/凭据配置。
