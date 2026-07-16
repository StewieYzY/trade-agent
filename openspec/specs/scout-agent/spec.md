# scout-agent Specification

## Purpose
TBD - created by archiving change l2-llm-scout-agent. Update Purpose after archive.
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
Scout SHALL limit the deep_dive shortlist to at most 20 candidates, sorted by confidence descending, to maintain AD-03 cost constraint (200→20 for L3).

#### Scenario: Deep dive cap
- **WHEN** more than 20 candidates have `verdict == "deep_dive"`
- **THEN** Scout SHALL return only the top 20 by confidence descending

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
Scout SHALL cache results to `data/cache/{ticker}/{date}/l2_scout.json` with TTL=24h. The cache entry SHALL include both the LLM output (verdict/confidence/flags) and the input feature snapshot (PE/PB/ROE/market_cap/etc.). The `{date}` subdirectory isolates results by trading day, enabling cross-day diagnostic comparison.

#### Scenario: Cache hit
- **WHEN** `scout_batch` is called for a ticker that has a valid cache entry (<24h old)
- **THEN** it SHALL reuse the cached result without calling the LLM

#### Scenario: Cache structure
- **WHEN** Scout writes a cache entry
- **THEN** the JSON SHALL contain `verdict`, `confidence`, `one_liner`, `red_flags`, `green_flags`, `anti_trap_flags`, `input_snapshot` (dict of feature values), and `timestamp` (ISO format)

#### Scenario: Cache expiration
- **WHEN** a cache entry is older than 24 hours
- **THEN** it SHALL be treated as expired and the LLM shall be called again

#### Scenario: Cross-day isolation
- **WHEN** Scout runs on 2026-06-30 for a ticker that has cache from 2026-06-29
- **THEN** it SHALL create new cache entry in `data/cache/{ticker}/2026-06-30/` without overwriting the 2026-06-29 entry

---

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
The CLI SHALL provide a `scout` subcommand that reads L1 output (S5 schema), assembles feature snapshots for each candidate, calls the LLM in batch, and outputs the filtered shortlist (verdict="deep_dive", top-20 cap).

#### Scenario: Scout command invocation
- **WHEN** user runs `python cli.py scout --input l1_output.json --output l2_shortlist.json`
- **THEN** the system SHALL read L1 candidates, call Scout batch, and write the top-20 deep_dive candidates to the output file

#### Scenario: Missing input file
- **WHEN** user runs `scout` without `--input` and no L1 output is available
- **THEN** the CLI SHALL raise an error with a clear message

---

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
- **THEN** Scout SHALL return only top 20, ensuring L3 cost stays within AD-03 budget (¥400-1200)

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

