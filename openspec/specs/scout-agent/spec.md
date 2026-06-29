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

