## Context

`g1-fast-personal-value-screening` 是 G1 umbrella；本 child 只推进 M2 的
staged screening runtime，不改变 G1 的 ranking 规则，也不承担 300+ 样本、
全市场性能/成本或 Top 20 Gate。当前 `screener.main.screen_a_shares()` 在
第一步对全部输入 ticker 调用一次 `BatchFetcher.fetch_all()`，虽然已经传入
G1 五维白名单，但仍然没有真实的阶段级 ticker 缩小。

现有 L1 函数的真实依赖如下：

- Stage A 的 `basic` 提供当前价、当前 PE/PB、市值、名称和行业；这些字段
  支持基于 basic/current valuation 的初步硬门槛。
- Stage B 的 `financials`、`risk` 提供上市年限、财务质量、质押率、审计意见、
  商誉和现金流等 hard gates/factor/anti-trap 依赖。
- Stage C 的 `valuation` 提供历史 PE/PB 序列与分位数，`kline` 提供 60 日
  换手率/收盘价，支持 factor value score 与 heat filter。

`valuation` provider 当前一次返回 current 与 historical 字段，不能在不改
provider 合同的情况下拆成两个底层 API。runtime 将其定义为逻辑上的
`valuation_history` 阶段维度：provider call 只在 Stage C、只针对 Stage B
通过的 ticker 发生；其返回中附带的 current 字段不会被 Stage C 之前消费。

## Goals / Non-Goals

**Goals:**

- 提供独立、可注入 `BatchFetcher` 的 Stage A/B/C runtime。
- 让每一阶段的输入 ticker 集合严格来自上一阶段输出，且证明
  `|A.input| >= |B.input| >= |C.input| >= |C.output|`。
- 每阶段只调用自身白名单维度：A=`basic`，B=`financials,risk`，
  C=`valuation,kline`；任何阶段都不包含 G2 dossier dimensions。
- 复用现有筛选函数，保持 hard gate、factor score、anti-trap、heat filter
  和 L1 排序语义不变。
- 对每个 stage 输出 run-scoped、可 JSON 序列化的执行证据，记录 ticker sets、
  dimensions、provider/cache 计数和失败状态。
- 失败只隔离到 ticker/stage；不使用默认值填充，不把非 available 状态转成
  available。
- 保留 canonical snapshot consumer 提供的 field-level `value/status/reason/
  provenance/as_of/freshness`，runtime 只消费已通过 consumer 的字段视图，
  不修改 snapshot 或触发 provider/LLM。

**Non-Goals:**

- 不修改已归档 `g1-canonical-snapshot-consumer`。
- 不改变 `BatchFetcher` 的 provider fallback、cache 写入或并发策略。
- 不请求 `main_business`、`peers`、`research`，不修改 G2 dossier、Council、
  watchlist、monitor 或 L2 ranking。
- 不写 production canonical snapshot、cache、watchlist、debate 或 live
  provider artifacts；测试使用 injected fake fetcher/reference data。
- 不宣称 M2、G1 或 G2 Capability passed。

## Decisions

### 1. 独立 runtime 编排器

新增 `screener/staged_runtime.py`，而不是把阶段状态继续塞进
`screen_a_shares()` 的兼容输出。编排器必须由 caller 显式注入 `BatchFetcher`
和可选 canonical field view，返回每阶段结果与最终 L1 candidates；CLI 通过
显式 `screen --staged` 入口接入，旧入口保持可用，避免无授权隐式 live fetch
或兼容迁移掩盖阶段证据。

备选方案是仅修改 `screen_a_shares()` 内部统计字段；该方案不能改变真实
provider boundary，违反本 child 的核心目标，因此不采用。

### 2. 阶段依赖与执行顺序

执行固定为：

```text
input tickers
  -> A: basic
  -> B: financials + risk
  -> C: valuation + kline
  -> final factor/anti-trap/heat result
```

Stage A 只依据 basic/current valuation 产生 preliminary failures；Stage B
合并 A 数据后执行依赖 financials/risk 的剩余 hard gates，并淘汰失败 ticker；
Stage C 才计算完整 factor score、anti-trap 和 heat filter。这样每一阶段的
后续输入都是真实缩小后的集合，且不会因缺少尚未请求的字段而伪造通过。

### 3. 失败与 canonical 状态

runtime 为每个 ticker/dimension 保留原始 payload；`__error__` 归一为
`source_failed`，空记录或字段缺失归一为 `record_not_found` 或
`not_evaluated`，显式 stale/degraded/invalid 状态原样保留。只有 required
stage dimensions 都没有失败且该 stage 的筛选函数通过时，ticker 才进入下一
stage。失败 ticker 不进入下一阶段，但继续处理同批其他 ticker。

若 caller 传入 `CanonicalSnapshotConsumer` 或 field mapping，runtime 只接受其
`ConsumedField` 的 value/status/reason/provenance/as_of/freshness；阶段所使用且
已被 snapshot 表示的 unavailable/rejected/stale/degraded 字段必须 fail closed，
不得继续进入候选。runtime 不调用 consumer 之外的 provider/LLM，也不写任何
cache 或生产输出。

### 4. 审计 evidence

每个 stage evidence 至少包含：

- `stage`, `run_id`, `input_tickers`, `output_tickers`
- canonical input/output ticker identities
- `requested_dimensions`
- `requests`, `provider_calls`, `cache_hits`
- `failures`（ticker、dimension、status、reason）
- stage-scoped `dimension_results`
- `passed_count`, `failed_count`

`BatchFetcher` 通过一个窄的可选 telemetry sink 暴露实际 `_fetch_one` 结果；
不改变 fetch 返回值和 cache 语义。runtime 只汇总本次调用的 telemetry，
不把 cache hit 或失败误报成 provider call。evidence object 提供
`to_dict()`/JSON serialization，failure records 按
ticker/dimension/status/reason 去重。

### 5. 测试策略

先写 RED 行为测试，使用 injected fake fetcher/telemetry，不调用 akshare、
LLM 或真实 cache。测试覆盖阶段 ticker 集合传递、维度白名单、G2 排除、
失败隔离、状态保留、审计计数、单调缩小、canonical field 元数据保留和无
生产副作用；再运行 focused、相关筛选/BatchFetcher/canonical tests 与全量
pytest。

## Risks / Trade-offs

- [Risk] `valuation` 底层接口仍返回 current 字段 → 以逻辑阶段维度控制调用
  ticker 集合，明确不宣称 provider 字段级最小响应；若未来 provider 支持字段
 选择，再单独改合同。
- [Risk] Stage A/B 的初步/剩余 hard gates 拆分可能改变旧入口统计 → 新 runtime
  不替换旧入口，最终 C 阶段复用同一 hard-gate 语义并增加契约测试。
- [Risk] 旧 CacheManager 只能按 dimension 统计 hit → telemetry 在 fetcher
  边界记录 hit/miss，无法观测 provider 内部缓存时保持 unknown，不猜测。
- [Risk] canonical snapshot 尚未覆盖全部 legacy dimension payload → 缺失字段
  进入 `not_evaluated`，不填默认值，不放行 ticker。

## Migration Plan

1. 先加入 runtime contract 与 RED tests。
2. 最小实现 telemetry、阶段编排和 evidence 序列化。
3. 接入新入口的 focused tests；旧 `screen_a_shares()` 与既有 ranking tests
   保持通过。
4. 完成相关/全量测试、strict OpenSpec、compileall 和 diff 检查。
5. independent review 前不 archive、不 push、不宣称 Capability passed。

## Open Questions

无。当前 provider 的 valuation 响应不可字段拆分，已明确采用“逻辑阶段维度
只控制调用时机与 ticker 集合”的合同。
