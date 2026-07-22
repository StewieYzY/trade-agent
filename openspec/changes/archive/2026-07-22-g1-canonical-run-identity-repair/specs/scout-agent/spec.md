## MODIFIED Requirements

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
