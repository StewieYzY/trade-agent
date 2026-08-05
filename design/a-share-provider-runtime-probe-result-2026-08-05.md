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
