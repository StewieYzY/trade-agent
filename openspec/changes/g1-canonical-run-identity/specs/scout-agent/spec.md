## MODIFIED Requirements

### Requirement: 24h Cache with Input Snapshot
Scout SHALL cache results to `data/cache/{canonical.code}/{date}/l2_scout.json` with TTL=24h, where `{canonical.code}` is the pure 6-digit form derived from the canonical ticker (per `run-identity` SoT), NOT the raw ticker string. The cache entry SHALL include both the LLM output (verdict/confidence/flags) and the input feature snapshot (PE/PB/ROE/market_cap/etc.), AND SHALL bind run identity (`run_id`/`profile_version`/`input_ticker_set_hash` inherited from L1). The `{date}` subdirectory isolates results by trading day, enabling cross-day diagnostic comparison.

> g1-canonical-run-identity 修改：原 requirement 路径为 `data/cache/{ticker}/{date}/l2_scout.json`，`ScoutCache._path` 直接用原始 ticker 拼路径不归一，导致 `600519` 与 `600519.SH` 双目录并存（实地证据：同票两份 cache 目录）。本修改将路径改为用 `canonical.code`（纯数字），与 L0 `CacheManager._normalize_ticker`（f1-deviation-fix D3）对齐，消除分裂。同时 cache entry 补 `run_id`/`profile_version`/`input_ticker_set_hash` 绑定（继承自 L1，纯 L2 单跑用 fallback run_id），使「数据变 vs 规则变」可区分。既有 `input_snapshot` 21 字段特征值保留作诊断用途不动。既有分裂的 L2 cache 目录按 D3 同策略安全迁移（空壳删/孤儿保/不丢真实数据）。

#### Scenario: Cache hit
- **WHEN** `scout_batch` is called for a ticker that has a valid cache entry (<24h old)
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
