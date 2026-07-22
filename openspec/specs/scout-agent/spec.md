# scout-agent Specification

## Purpose
定义 L2 Scout 的快筛能力边界：并发 LLM 初筛（Semaphore 20 + 60s 超时 + 重试）、verdict 覆盖逻辑（缓冲带）、24h 缓存（含输入快照）、top-20 cap（shortlist 由 full_results 派生）、L2 数据降级模式（critical 齐但 financials 不齐时优雅降级）、L2 全量结果契约（scout_batch 返回 full_results/usage_summary/failure_summary，每只输入归属 deep_dive/watch/skip/error，failure 可定位）。约束 AD-03 成本闸门（200→20）。
## Requirements
### Requirement: Scout System Prompt
Scout SHALL use a fixed system prompt that instructs the LLM to act as an A-share value investing junior analyst. The prompt SHALL require the LLM to answer 5 structured questions (business type, valuation, business quality, red flags, conclusion) and output a JSON object with verdict/confidence/one_liner/red_flags/green_flags/anti_trap_flags fields.

#### Scenario: System prompt format
- **WHEN** Scout is invoked with a stock ticker
- **THEN** the system message sent to the LLM SHALL contain the exact prompt template from design.md §2 (5 questions + JSON schema)

#### Scenario: JSON output enforcement
- **WHEN** Scout calls the LLM
- **THEN** the API request SHALL include `"response_format": {"type": "json_object"}` to enforce JSON output

---

### Requirement: Feature Snapshot Input
Scout SHALL receive a ~200-token text snapshot of stock features as the user message. The snapshot SHALL include: stock name, ticker, industry, market cap, PE(TTM) from valuation dimension, PE 5-year percentile, PB, ROE 3-year trend, net margin, debt ratio, operating cash flow, net profit, revenue growth, goodwill ratio, pledge ratio, audit opinion, 60-day price change, turnover percentile, and F-Score. Derived metrics (ROE, net margin, debt ratio, goodwill ratio) SHALL be computed using `data/lib/fin_models.py` to maintain consistency with L1.

#### Scenario: Snapshot assembly
- **WHEN** `input_assembly.assemble(ticker)` is called
- **THEN** it SHALL fetch all dimensions from `CacheManager.get(ticker, dim)` and format them into the §2 User Message template

#### Scenario: Field source specification
- **WHEN** assembling snapshot fields
- **THEN** `pe_ttm` SHALL be fetched from `valuation` dimension (key: `pe_ttm`), not from `basic` dimension (key: `pe`)

#### Scenario: Missing data handling
- **WHEN** a required feature field is missing from L0 cache
- **THEN** the snapshot SHALL use `None` placeholder and annotate "数据缺失" in the prompt

#### Scenario: Insufficient data guard
- **WHEN** critical fields (name, industry, market_cap) are missing OR more than 50% of required fields are missing
- **THEN** Scout SHALL skip LLM call and return `{"verdict": "error", "reason": "insufficient_data"}` to avoid wasting cost on garbage input

---

### Requirement: Verdict Coverage Logic
Scout SHALL apply buffer zone logic to override LLM verdict based on confidence. When confidence ≥ 60, the LLM verdict is trusted. When 40 ≤ confidence < 60, verdict is forced to "watch". When confidence < 40, verdict is forced to "watch" and marked as low-confidence anomaly.

#### Scenario: High confidence (≥60)
- **WHEN** LLM returns `{"verdict": "deep_dive", "confidence": 75}`
- **THEN** the final verdict SHALL be "deep_dive"

#### Scenario: Buffer zone (40-60)
- **WHEN** LLM returns `{"verdict": "deep_dive", "confidence": 55}`
- **THEN** the final verdict SHALL be "watch" (override applied)

#### Scenario: Low confidence (<40)
- **WHEN** LLM returns `{"verdict": "skip", "confidence": 30}`
- **THEN** the final verdict SHALL be "watch" and flagged as low-confidence anomaly

---

### Requirement: Top-20 Cap

Scout SHALL limit the deep_dive shortlist to at most 20 candidates, sorted by confidence descending, to maintain AD-03 cost constraint (200→20 for L3). `scout_batch` SHALL return `full_results`（每只输入一条，含全部 verdict 分类），NOT return the shortlist as its sole output; the shortlist SHALL be a derived view the consumer computes from `full_results` as `[r for r in full_results if verdict=="deep_dive"]` sorted by `confidence` descending, capped at 20.

> g1-l2-full-result-contract 修改：原 requirement 要求 Scout「return only the top 20」，与新「L2 全量结果契约」矛盾（scout_batch 现返回 full_results，shortlist 由消费方派生）。cap 语义不变（≤20、按 confidence 降序），仅改承载位置——从「scout_batch 直接返回」改为「消费方从 full_results 派生」。

#### Scenario: Deep dive cap

- **WHEN** more than 20 candidates have `verdict == "deep_dive"` in `full_results`
- **THEN** the shortlist derived from `full_results` SHALL contain only the top 20 by confidence descending

#### Scenario: scout_batch returns full_results not shortlist

- **WHEN** `scout_batch(candidates)` returns
- **THEN** the first return item SHALL be `full_results`（length == N, 含 deep_dive/watch/skip/error）, NOT the top-20 shortlist; shortlist is a consumer-derived view

---

### Requirement: Concurrent LLM Calls
Scout SHALL invoke LLM calls concurrently with a semaphore limit of 20. Each call SHALL have a 60-second timeout and retry once with 2-second backoff on HTTP errors.

#### Scenario: Batch processing
- **WHEN** `scout_batch(candidates)` is called with 200 candidates
- **THEN** it SHALL process them in batches of 20 concurrent calls

#### Scenario: Timeout handling
- **WHEN** a single LLM call exceeds 60 seconds
- **THEN** that call SHALL timeout and be skipped (not blocking the batch)

#### Scenario: Retry on failure
- **WHEN** an LLM call fails with HTTP error
- **THEN** it SHALL retry once after 2 seconds

---

### Requirement: 24h Cache with Input Snapshot
Scout SHALL cache results to `data/cache/{canonical.code}/{date}/l2_scout.json` with TTL=24h, where `{canonical.code}` is the pure 6-digit form derived from the canonical ticker (per `run-identity` SoT), NOT the raw ticker string. The cache entry SHALL include both the LLM output (verdict/confidence/flags) and the input feature snapshot (PE/PB/ROE/market_cap/etc.), AND SHALL bind run identity (`run_id`/`profile_version`/`input_ticker_set_hash` inherited from L1). The `{date}` subdirectory isolates results by trading day, enabling cross-day diagnostic comparison.

Cache hit 判定 SHALL 基于 TTL（24h）+ `profile_version` 兼容性，**MUST NOT 基于 `run_id`**。`run_id` 是 execution identity（定位某次 run + 产物隔离 + 审计溯源），降级为 cache entry 的 provenance 元数据（只写、只读、不参与 hit 判定）。不同 run_id 但相同 `profile_version`（规则未变）+ 相同 canonical ticker + 同日 → SHALL cache hit（复用 24h 内的 verdict，不重调 LLM）。`profile_version` 不同（规则 bump）→ SHALL cache miss。缺 `profile_version` 的 legacy cache entry → SHALL cache miss（无法证明规则版本兼容，避免新规则 run 静默复用规则版本不明的旧 verdict）。

> g1-canonical-run-identity-repair 修改：G1-3 实现的 `ScoutCache.get()` 把 `run_id` 误用作 cache hit 判定（不同 run_id → miss），破坏了 24h L2 cache 复用——每次新 L1 run 都重调 L2 LLM，违背 AD-03 成本闸门与原 `#### Scenario: Cache hit` 契约。本修改澄清 execution run_id（产物隔离/审计）与 cache 复用判定的边界：cache hit 只校验 TTL + profile_version，run_id 仅为 provenance。cache hit 时保留 cache 文件中的 source run_id 不改写；当前 run 产物（full_results/CLI payload）仍用当前 execution run_id。不引入 `CacheIdentity` 类，cache 目录与 entry 结构零改。

#### Scenario: Cache hit
- **WHEN** `scout_batch` is called for a ticker that has a valid cache entry (<24h old) with matching `profile_version`
- **THEN** it SHALL reuse the cached result without calling the LLM

#### Scenario: Cache structure
- **WHEN** Scout writes a cache entry
- **THEN** the JSON SHALL contain `verdict`, `confidence`, `one_liner`, `red_flags`, `green_flags`, `anti_trap_flags`, `input_snapshot` (dict of feature values), `timestamp` (ISO format), AND run identity fields `run_id`, `profile_version`, `input_ticker_set_hash`

#### Scenario: Cache path uses canonical code not raw ticker
- **WHEN** `ScoutCache` writes a cache entry for canonical ticker `600519.SH` or `600519` or `600519.sh`
- **THEN** the cache directory SHALL be `data/cache/600519/{date}/l2_scout.json` (pure 6-digit `canonical.code`), MUST NOT create `data/cache/600519.SH/` or split into two directories

#### Scenario: Cache expiration
- **WHEN** a cache entry is older than 24 hours
- **THEN** it SHALL be treated as expired and the LLM shall be called again

#### Scenario: Cross-day isolation
- **WHEN** Scout runs on 2026-06-30 for a ticker that has cache from 2026-06-29
- **THEN** it SHALL create new cache entry in `data/cache/{canonical.code}/2026-06-30/` without overwriting the 2026-06-29 entry

#### Scenario: Run identity inherited from L1
- **WHEN** `scout_batch` processes candidates carrying `run_id` from L1 output
- **THEN** each ScoutCache entry SHALL inherit the L1 `run_id`/`profile_version`/`input_ticker_set_hash`, MUST NOT generate a new run_id; pure L2 single-run (no L1 run_id) SHALL use a fallback run_id annotated `run_id_source: "scout_fallback"`

#### Scenario: Existing split cache directories safely migrated
- **WHEN** `data/cache/` already contains split L2 directories (e.g. `600519.SH/` alongside `600519/`)
- **THEN** migration SHALL follow the same safe strategy as f1-deviation-fix D3: empty-shell split dirs (no real `l2_scout.json`) deleted; orphan split dirs with real data (no pure-digit counterpart) moved to pure-digit dir then deleted; real data MUST NOT be lost; after migration no new split dirs SHALL be created

#### Scenario: Cross-run cache hit when profile_version unchanged
- **WHEN** run A writes a cache entry for `600519` on date D with `profile_version=V` and `run_id=rid_a`, and run B (different `run_id=rid_b`, same `profile_version=V`) checks the cache for `600519` on date D within 24h
- **THEN** run B SHALL cache hit (reuse run A's verdict), MUST NOT miss solely because `run_id` differs; `run_id` is provenance metadata not a hit criterion

#### Scenario: Cache miss when profile_version changed
- **WHEN** a cache entry was written with `profile_version=V1` and the current run uses `profile_version=V2` (rule bump)
- **THEN** it SHALL cache miss and call the LLM again; old rule's verdict MUST NOT be reused under a new rule version

#### Scenario: Legacy cache without profile_version misses
- **WHEN** a cache entry predates run-identity (no `profile_version` field) and the current run carries `profile_version`
- **THEN** it SHALL cache miss (cannot prove rule-version compatibility); the LLM SHALL be called again to refresh the entry under the current rule version

#### Scenario: Cache hit preserves source run_id
- **WHEN** a cache hit returns a cached entry written by run A (`run_id=rid_a`) to the current run B (`run_id=rid_b`)
- **THEN** the cache file SHALL NOT be rewritten (source `run_id=rid_a` preserved as provenance); the current run B's products (`full_results`/CLI payload) SHALL carry `run_id=rid_b` (current execution identity), not the cached `rid_a`

### Requirement: OpenAI-Compatible HTTP Client
Scout SHALL use `httpx` (already present in L0 dependencies) to call OpenAI-compatible chat completion API. The API key and base URL SHALL be read from environment variables `LLM_API_KEY` and `LLM_API_BASE` (defined in total-design §9.1). The model name SHALL be read from `LLM_MODEL` (required, no default, fail-fast if missing).

#### Scenario: API call format
- **WHEN** Scout calls the LLM
- **THEN** it SHALL POST to `{LLM_API_BASE}/v1/chat/completions` with `Authorization: Bearer {LLM_API_KEY}` and `temperature: 0.0`

#### Scenario: Environment variables
- **WHEN** Scout is initialized
- **THEN** it SHALL read `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL` from environment variables, raising `ValueError` if any is missing

---

### Requirement: CLI Integration

The CLI SHALL provide a `scout` subcommand that reads L1 output (S5 schema), assembles feature snapshots for each candidate, calls the LLM in batch, and outputs the full results bundle: `full_results`（每只输入一条 verdict 分类）, `shortlist`（deep_dive 按 confidence 降序 top-20 派生视图，供 L3 消费）, `usage_summary`, and `failure_summary`. The payload SHALL inherit run identity (`run_id`/`profile_version`/`input_ticker_set_hash`) from the L1 input file. The shortlist is a derived view, not the sole persisted output. The output file SHALL be run-scoped (named or indexed by `run_id`) so that same-day multiple runs do not overwrite each other.

> g1-canonical-run-identity 修改：在 g1-l2-full-result-contract 四字段 payload 基础上，本修改要求 payload 继承 L1 的 `run_id`/`profile_version`/`input_ticker_set_hash`（run-identity 契约），并要求输出文件 run-scoped 命名（运行隔离契约），解决原 CLI `--output` 直接 `write_text` 覆盖、同日多次运行互相覆盖的问题。四字段 payload 结构与 shortlist 派生语义不变（G1-2 闭合不重开）。

#### Scenario: Scout command invocation

- **WHEN** user runs `python cli.py scout --input l1_output.json --output l2_shortlist.json`
- **THEN** the system SHALL read L1 candidates (including `run_id`/`profile_version`/`input_ticker_set_hash` from the L1 file), call Scout batch, and write a payload of `full_results`/`shortlist`/`usage_summary`/`failure_summary` to the output file, with the payload carrying the inherited `run_id`/`profile_version`/`input_ticker_set_hash`

#### Scenario: Missing input file

- **WHEN** user runs `scout` without `--input` and no L1 output is available
- **THEN** the CLI SHALL raise an error with a clear message

#### Scenario: Run identity inherited from L1 file

- **WHEN** the L1 input file contains `run_id`/`profile_version`/`input_ticker_set_hash`
- **THEN** the scout output payload SHALL carry these fields verbatim, MUST NOT regenerate run_id

#### Scenario: Same-day multiple runs do not overwrite

- **WHEN** `scout` is run twice on the same day with the same `--output` path or default path
- **THEN** each run's output SHALL be run-scoped (named or indexed by `run_id`), prior run's output SHALL remain readable, MUST NOT be overwritten

### Requirement: Cost Constraint
Scout SHALL maintain a per-call cost of approximately ¥0.01 per stock (200 stocks → ~¥2 per run). The system SHALL use lightweight inference models (AD-04), cache results for 24 hours, and enforce top-20 cap to minimize redundant calls and maintain AD-03 cost gate.

#### Scenario: Cost per run
- **WHEN** Scout processes 200 candidates with 80% cache hit rate
- **THEN** the total LLM cost SHALL be approximately ¥0.4 (40 calls × ¥0.01)

#### Scenario: Cache-driven cost reduction
- **WHEN** Scout is run multiple times in the same trading day
- **THEN** cached results SHALL be reused, reducing LLM calls by ~80%

#### Scenario: Top-20 cap enforcement
- **WHEN** 40 candidates pass buffer zone with deep_dive verdict
- **THEN** the shortlist derived from `full_results` SHALL be capped at top 20, ensuring L3 cost stays within AD-03 budget (¥400-1200)

---

### Requirement: 全市场候选集区分度验证
Scout SHALL 在真实全市场候选集（非手工挑的 20 只样本）上验证区分度，实证 AD-03 成本闸门假设（200→20，¥0.01/只）。

> 背景：deviation-analysis §1.5 实证发现，L2 从未在真实候选集上跑过——`data/cache/` 26 个目录全是手工挑的白马（茅台/平安/五粮液等），`review-notes.md` 门 2 跑的 `batch data/tickers.txt` 只有 20 只手工清单，`stats.input_scale == "subset"` 退化标记一直在说"这不是真·全市场"。AD-03 假设零佐证。

#### Scenario: 全市场 L1→L2 链路验证
- **WHEN** L1 对全 A 股 ~5000 只跑完 `screen`，产出 candidates 列表
- **THEN** SHALL 将 L1 candidates 全量喂给 `scout_batch`，记录 deep_dive 数量 / watch 数量 / skip 数量的分布，验证漏斗比例（设计目标 200→20）

#### Scenario: L2 区分度实证
- **WHEN** Scout 对真实全市场 candidates 跑完 batch
- **THEN** SHALL 记录 confidence 分布（直方图）、deep_dive 比例、与手工 20 只样本的对比，验证 L2 不是"对所有白马都输出 deep_dive"的同质化筛选

#### Scenario: 成本实测
- **WHEN** 全市场 L2 batch 执行
- **THEN** SHALL 记录 LLM 调用次数、token 消耗（prompt_tokens + completion_tokens）、总费用，验证 AD-03 成本假设（≈¥0.01/只，200→20 总成本 ≈¥2）
- **AND** token 采集 SHALL 通过 `call_llm` 返回值携带 usage 信息实现（当前 `council/llm.py::call_llm` 只返回 JSON 字符串、丢弃 API 响应中的 usage 字段，需扩展签名返回 usage），L2 scout 与 L3 council 共享该采集能力

#### Scenario: input_scale 退化标记在全市场的表现
- **WHEN** L1 对全 A 股 ~5000 只跑 `screen`
- **THEN** `stats.input_scale` SHALL 为 "full"（≥300 只），`industry_pe_degraded` 在全市场样本下的触发面 SHALL 被记录（验证退化标记不是只在 subset 下才触发）

---

### Requirement: L2 数据降级模式（优雅降级）
`scout-agent` SHALL 在 features 不充分但非完全缺失时，从 fail-fast 改为优雅降级模式继续运行，不中断整批：

- 当 `critical_fields`（name/industry/market_cap）齐全但 `financials_floor`（pe_ttm/roe_3y/net_margin）任一缺失时，触发降级（区别于完全 insufficient 的 fail-fast）
- 降级行为：`confidence` 上限 50（`confidence_cap=50`）、`verdict` 强制 `"watch"`、标注 `degraded: true` + `degraded_reason: "incomplete_financials"`
- 降级模式 SHALL 继续调用 LLM（用不完整 features），不跳过整只，避免 200 只批处理因个别数据不全而中断

> 背景：Kimi 校准要点 4（优雅降级，数据不可得时切简化模型继续运行）。区别于 L3 的 fail-fast——L2 是 200 只批处理，单只 fail 中断整批不可接受；L3 是单只深研，数据不足硬出结论是 600900 复读茅台悲剧（[[design]] D5）。

#### Scenario: financials 不齐但 basic 齐触发降级
- **WHEN** `assemble_snapshot` 返回 name/industry/market_cap 齐全，但 pe_ttm/roe_3y/net_margin 任一为 None
- **THEN** scout SHALL 进入降级模式：confidence 上限 50、verdict 强制 "watch"、标注 `degraded: true`

#### Scenario: 降级模式继续调用 LLM
- **WHEN** 某只票触发降级模式
- **THEN** scout SHALL 仍调用 LLM（用不完整 features），不跳过该只，结果含 `degraded: true` 标记

#### Scenario: critical_fields 完全缺失仍 fail-fast
- **WHEN** `assemble_snapshot` 返回 name 或 market_cap 缺失
- **THEN** scout SHALL 保持现有 fail-fast（返回 `{"verdict": "error", "reason": "insufficient_data"}`），不进入降级模式

#### Scenario: 降级结果不进 deep_dive 短名单
- **WHEN** 降级模式的票 LLM 原本返回 `{"verdict": "deep_dive", "confidence": 70}`
- **THEN** 经降级处理后 `confidence` 上限为 50、`verdict` 强制 "watch"，不进入 deep_dive 短名单（避免数据不全的票占 L3 深研资源）

---

### Requirement: L2 快管线隔离约束（f3a 防污染）
f3a SHALL NOT 修改 `scout/input_assembly.py::assemble_snapshot`，L2 快管线不受 f3a 影响：

- `assemble_snapshot`（L2 扁平 21 字段，`input_assembly.py:242-246`）SHALL 保持不变
- capex_proxy（资本开支代理）SHALL 由 `research_dossier.py` 读已采的 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`，SHALL NOT 在 `input_assembly.py` 加读取
- pledge（芒格代理治理）SHALL 由 dossier 读已采的 `data/cache/{ticker}/risk.json` 的 `pledge_ratio`，SHALL NOT 在 `input_assembly.py` 加读取
- 新建 3 fetcher（main_business/peers/research）SHALL 注册为新 dim（`data/cache/{ticker}/{dim}.json`），SHALL NOT 改现有 basic/valuation/financials/kline/risk 五个 dim 的采集或结构

> 背景：[[design]] D4。`assemble_snapshot` 是 L1→L2 交接点（`council/features.py:7` 和 `debate.py:22` 都 import），改它污染 L2 快管线（AD-03 成本闸门，200 只 batch）。f3a 的定性维度全部走 dossier 新层，L2 零影响。探索稿 §4.2 已明确此决策。

#### Scenario: assemble_snapshot 保持不变
- **WHEN** f3a 实现 dossier 层
- **THEN** `scout/input_assembly.py::assemble_snapshot` SHALL 保持现有签名和返回的 21 字段结构不变，L2 scout 管线零影响

#### Scenario: capex 由 dossier 读不进 input_assembly
- **WHEN** dossier 组装 capex_proxy
- **THEN** SHALL 从 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]` 读取，SHALL NOT 在 `input_assembly.py` 加 capex 读取逻辑

#### Scenario: pledge 由 dossier 读不进 input_assembly
- **WHEN** dossier 组装芒格的 pledge 代理
- **THEN** SHALL 从 `data/cache/{ticker}/risk.json` 的 `pledge_ratio` 读取，SHALL NOT 在 `input_assembly.py` 加 pledge 读取逻辑

#### Scenario: 新 dim 不污染现有五个 dim
- **WHEN** 新建 fetch_main_business / fetch_peers / fetch_research
- **THEN** SHALL 注册为新 dim（main_business/peers/research），SHALL NOT 改 basic/valuation/financials/kline/risk 五个现有 dim 的采集逻辑或返回结构

### Requirement: L2 全量结果契约

`scout_batch` SHALL 返回三元组 `(full_results, usage_summary, failure_summary)`，为每只输入候选生成最终分类与可审计信息，shortlist SHALL 由 `full_results` 派生而非作为唯一返回。

- `full_results`：长度 SHALL 等于输入候选数 N（含 cache hit、degraded、缺 ticker / 非 dict 坏输入的 error result，**不丢任何输入**），每条含 `ticker`、`verdict`（`deep_dive`/`watch`/`skip`/`error`）及统一契约字段 `one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`；degraded 票额外含 `degraded`/`degraded_reason`；error 票额外含 `error`/`missing_fields`/`stage`/`input_index`（缺 ticker 时 `ticker` 为 `None`，不伪造，以 `input_index` 定位原始输入）。
- `usage_summary`：契约不变（`call_count`/`cache_hits`/`prompt_tokens`/`completion_tokens`/`total_tokens`），累加**所有** LLM 调用（含 watch/skip/error 路径，非仅 deep_dive），cache hit 不计 `call_count` 单独计 `cache_hits`。
- `failure_summary`：SHALL 把 `error`/`skip`/`watch`/`degraded` 分开计数，且 SHALL 可定位每个 `error` 的 ticker、原因与失败阶段：`{"errors":[{ticker,input_index,reason,stage}], "skips":n, "watches":n, "degraded":n, "unhandled_exceptions":0}`。
- `shortlist`：SHALL 由消费方从 `full_results` 派生为 `[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20（受既有 Top-20 Cap requirement 约束），MUST NOT 是 `scout_batch` 的唯一返回项。
- 整批运行 SHALL 无未处理异常：`failure_summary["unhandled_exceptions"] == 0`。单只采集/特征计算/LLM 调用失败、缺 ticker、非 dict 坏输入 SHALL 计入 `errors` 而非中断整批——输入校验 SHALL 在异常捕获范围内，坏输入 MUST NOT 逃逸 `asyncio.gather`。

> 背景：G1 umbrella `personal-value-screening` 的「完整漏斗与失败结果」requirement（D5）要求每只输入归属四类并保留阶段/理由/降级/失败信息，shortlist MUST 由全量结果派生。当前 `scout_batch` 返回点只留 `deep_dive`，watch/skip/error 被丢弃、无 failure_summary，shortlist 是唯一返回而非派生——本 requirement 闭合该缺口。AD-03：failure_summary 把 availability/error/degraded 分开计数，避免用 shortlist 掩盖失败分布。

#### Scenario: 全量结果含所有分类

- **WHEN** `scout_batch` 处理 3 只候选，LLM 分别返回 `deep_dive`/`watch`/`skip`
- **THEN** `full_results` SHALL 长度为 3，三条均含 `verdict` 字段（`deep_dive`/`watch`/`skip`），MUST NOT 只保留 deep_dive

#### Scenario: shortlist 由全量结果派生

- **WHEN** `full_results` 含 2 条 `verdict=="deep_dive"` 与若干 watch/skip
- **THEN** `shortlist` SHALL 等于 `[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20，MUST NOT 是 `scout_batch` 的独立返回项

#### Scenario: failure_summary 可定位失败 ticker 与原因

- **WHEN** 候选 `600002` 的 LLM 调用抛 `httpx.HTTPStatusError`
- **THEN** `failure_summary["errors"]` SHALL 含 `{"ticker":"600002","reason":<错误描述>,"stage":<失败阶段>}`，其他成功候选不受影响仍出现在 `full_results`

#### Scenario: error/skip/watch/degraded 分开计数

- **WHEN** 一批候选处理后含 1 只 error、2 只 skip、1 只 degraded（→watch）、1 只 deep_dive
- **THEN** `failure_summary` SHALL `{"errors":1, "skips":2, "watches":1, "degraded":1, "unhandled_exceptions":0}`（degraded 不计入 errors，单独计 degraded；watches 含 degraded 票的 watch 分类）

#### Scenario: 整批无未处理异常

- **WHEN** 处理过程中某只票触发非预期异常（脏数据/类型错位）
- **THEN** 该只 SHALL 计入 `failure_summary["errors"]`，`unhandled_exceptions` SHALL 为 0，整批 SHALL 继续不中断

#### Scenario: usage_summary 累加所有调用

- **WHEN** 一批候选含 deep_dive/watch/skip 三种 verdict 各调用 1 次 LLM
- **THEN** `usage_summary["call_count"]` SHALL 为 3（非仅 deep_dive 的 1），`cache_hits` SHALL 单独计 cache 命中数

#### Scenario: 缺 ticker 的输入不丢失

- **WHEN** `scout_batch` 收到含缺 ticker 候选（如 `{}`）的输入
- **THEN** 该候选 SHALL 在 `full_results` 中（长度 == 输入 N），`verdict` 为 `error`，`ticker` 为 `None`（不伪造），含 `input_index` 定位原始输入，并计入 `failure_summary["errors"]`

#### Scenario: 非 dict 坏输入不逃逸整批

- **WHEN** `scout_batch` 收到非 dict 输入（如 `None`）
- **THEN** 该输入 SHALL 不抛异常逃逸 `asyncio.gather`，返回 `verdict=error` 的 result（`stage=unexpected_exception`），整批继续，`unhandled_exceptions` SHALL 为 0

#### Scenario: error result 满足 full-result 字段契约

- **WHEN** 候选走 insufficient_data 或 LLM 调用失败路径生成 `verdict=error` 的 result
- **THEN** 该 error result SHALL 含与正常 result 相同的契约字段 `one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`（空数组/默认值），MUST NOT 只有 `ticker`/`verdict`/`error`

