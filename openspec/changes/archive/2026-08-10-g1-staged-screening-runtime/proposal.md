## Why

`g1-fast-personal-value-screening` 已有 L1 漏斗与 G1 量化维度白名单，但
`screen_a_shares()` 仍在第一步对全部 ticker 一次性采集所有 G1 dimensions。
这无法证明后续采集集合随漏斗缩小，也无法审计每个阶段的 provider calls、
cache hits 与失败语义。当前 Track A 需要把 G1 变成真实的 Stage A/B/C
runtime，作为 M2 的工程证据基础。

## What Changes

- 新增独立的 `g1-staged-screening-runtime` 编排入口，按 Stage A/B/C 顺序执行
  G1 筛选。
- Stage A 只请求 `basic`；Stage B 只请求 `financials`、`risk`；Stage C
  只请求 `valuation`、`kline`。
- 复用现有 hard gates、factor scores、anti-trap、heat filter 与
  `BatchFetcher`，保持 L1 排名规则不变。
- 为每个 stage 记录输入/输出 ticker 集合、requested dimensions、provider
  calls、cache hits、失败状态及 run identity。
- 显式保留 `complete`、`degraded`、`record_not_found`、`source_failed`、
  `invalid_value`、`not_evaluated`、`stale` 等状态；不以默认值替代缺失值。
- 单只 ticker 的 stage 失败不阻断其他 ticker，并产生可验证的单调缩小证据。
- G2 dossier dimensions（`main_business`、`peers`、`research`）不进入任何
  G1 stage。

## Capabilities

### New Capabilities

- `g1-staged-screening-runtime`: G1 Stage A/B/C 的真实采集边界、漏斗编排、
  失败可见性与执行证据。

### Modified Capabilities

本 child 不修改 umbrella requirement；`g1-fast-personal-value-screening` 作为
能力 charter 与范围边界被引用。

## Impact

- 影响 `value-screener/screener/` 与 `value-screener/data/lib/batch_fetcher.py`，
  新增 runtime 编排与可审计 fetch 结果。
- 复用既有 canonical snapshot consumer 的 value/status/provenance/as_of/
  freshness 语义；不修改已归档 canonical snapshot consumer change。
- 不新增依赖，不调用未经授权的 live provider 或 LLM，不写入 cache、
  watchlist、debate 或 production canonical output。
